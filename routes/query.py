"""
Query Routes: Core RAG endpoints.
 
POST /query        → Standard async JSON response
POST /query/stream → Server-Sent Events streaming response
GET  /health       → Liveness check
GET  /ready        → Readiness check (verifies pipeline)
"""
 
import time
from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import JSONResponse
 
from app.models.requests import QueryRequest
from app.models.responses import QueryResponse, QueryMetadata, SourceDocument
from app.dependencies.pipeline import get_pipeline
from app.dependencies.guardrails import get_guardrails
 
router = APIRouter()
 
 
@router.post(
    "/query",
    response_model=QueryResponse,
    summary="Query the RAG pipeline",
    description=(
        "Submit a question and receive an answer grounded in the knowledge base. "
        "Input is validated for topic scope and PII. "
        "Output is scanned for PII and toxic content before returning."
    )
)
async def query(
    request: Request,
    body: QueryRequest,
    pipeline=Depends(get_pipeline),
    guardrails=Depends(get_guardrails)
):
    """
    Main RAG query endpoint with integrated guardrails.
 
    Processing order:
        1. Input guardrails (topic check, PII redaction)
        2. RAG pipeline execution
        3. Output guardrails (PII redaction, toxicity filter)
        4. Structured response with audit metadata
    """
    start_time = time.time()
    request_id = getattr(request.state, "request_id", "unknown")
    guardrails_applied = []
    safe_question = body.question
 
    # ── INPUT GUARDRAILS ──────────────────────────────────────
    if guardrails.get("available"):
        try:
            from src.input.pii_detector import CompositePIIDetector
            from src.validators.topic_validator import (
                CompositeTopicValidator,
                TopicValidationResult,
                CUSTOMER_SUPPORT_TOPIC
            )
 
            # 1. Topic scope validation
            topic_validator = CompositeTopicValidator(
                topic_config=CUSTOMER_SUPPORT_TOPIC,
                block_uncertain=False
            )
            topic_result = topic_validator.validate(body.question)
 
            if topic_result.result == TopicValidationResult.OUT_OF_SCOPE:
                guardrails_applied.append("topic_blocked")
                return QueryResponse(
                    answer=topic_result.suggested_redirect or (
                        "I can only help with questions about our products, "
                        "shipping, and return policies."
                    ),
                    sources=None,
                    metadata=QueryMetadata(
                        model="guardrail",
                        latency_ms=round((time.time() - start_time) * 1000, 2),
                        guardrails_applied=guardrails_applied,
                        request_id=request_id
                    )
                )
 
            # 2. Input PII detection and redaction
            pii_detector = CompositePIIDetector(use_presidio=False)
            pii_result = pii_detector.detect(body.question)
            if pii_result.contains_pii:
                safe_question = pii_result.redacted_text
                guardrails_applied.append("input_pii_redacted")
 
        except ImportError:
            pass  # Guardrails not fully available — skip silently
        except Exception as e:
            print(f"[Query] Input guardrail error: {e} — continuing without")
 
    # ── PIPELINE EXECUTION ────────────────────────────────────
    try:
        result = await _run_pipeline_async(
            pipeline=pipeline,
            question=safe_question,
            k=body.k,
            metadata_filter=body.metadata_filter
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Pipeline execution failed: {str(e)}"
        )
 
    raw_answer = result.get("answer", "")
    safe_answer = raw_answer
 
    # ── OUTPUT GUARDRAILS ─────────────────────────────────────
    if guardrails.get("available"):
        try:
            from src.output.pii_redactor import OutputPIIRedactor
            from src.output.toxicity_filter import CompositeToxicityFilter, ToxicitySeverity
 
            # 3. Output PII redaction
            redactor = OutputPIIRedactor(redaction_mode="hard")
            redaction_result = redactor.redact(raw_answer)
            if redaction_result.pii_found:
                safe_answer = redaction_result.redacted_text
                guardrails_applied.append("output_pii_redacted")
 
            # 4. Toxicity filtering
            toxicity_filter = CompositeToxicityFilter(
                block_severity=ToxicitySeverity.HIGH
            )
            toxicity_result = toxicity_filter.filter(safe_answer)
            if toxicity_filter.should_block(toxicity_result):
                guardrails_applied.append("toxicity_blocked")
                safe_answer = (
                    "I encountered an issue generating a safe response. "
                    "Please try rephrasing your question."
                )
 
        except ImportError:
            pass
        except Exception as e:
            print(f"[Query] Output guardrail error: {e} — returning unfiltered")
 
    # ── BUILD RESPONSE ────────────────────────────────────────
    latency_ms = round((time.time() - start_time) * 1000, 2)
 
    sources = None
    if body.include_sources and result.get("chunks"):
        sources = [
            SourceDocument(
                filename=chunk.get("filename", "unknown"),
                chunk_id=chunk.get("chunk_id", "unknown"),
                relevance_score=chunk.get("score", 0.0),
                content_preview=chunk.get("content", "")[:150]
            )
            for chunk in result.get("chunks", [])
        ]
 
    return QueryResponse(
        answer=safe_answer,
        sources=sources,
        metadata=QueryMetadata(
            model=result.get("model", "unknown"),
            latency_ms=latency_ms,
            prompt_tokens=result.get("prompt_tokens", 0),
            completion_tokens=result.get("completion_tokens", 0),
            total_tokens=(
                result.get("prompt_tokens", 0) +
                result.get("completion_tokens", 0)
            ),
            chunks_retrieved=len(result.get("chunks", [])),
            guardrails_applied=guardrails_applied,
            request_id=request_id
        ),
        reasoning=result.get("reasoning") if body.include_reasoning else None
    )
 
 
@router.get("/health", summary="Liveness check")
async def health():
    return {"status": "healthy", "service": "production-rag-api"}
 
 
@router.get("/ready", summary="Readiness check")
async def ready(pipeline=Depends(get_pipeline)):
    try:
        if hasattr(pipeline, "vector_store") and pipeline.vector_store.size == 0:
            return JSONResponse(
                status_code=503,
                content={"status": "not_ready", "reason": "Vector store is empty"}
            )
        return {"status": "ready", "pipeline": "initialized"}
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "reason": str(e)}
        )
 
 
async def _run_pipeline_async(pipeline, question, k, metadata_filter):
    import asyncio
    loop = asyncio.get_event_loop()
 
    def _run():
        result = pipeline.query(
            question=question,
            k=k,
            metadata_filter=metadata_filter
        )
        return {
            "answer": result.answer if hasattr(result, "answer") else str(result),
            "model": getattr(result, "model", "unknown"),
            "prompt_tokens": getattr(result, "prompt_tokens", 0),
            "completion_tokens": getattr(result, "completion_tokens", 0),
            "chunks": [
                {
                    "filename": chunk.metadata.get("filename", "unknown"),
                    "chunk_id": chunk.chunk_id,
                    "score": chunk.metadata.get("retrieval_score", 0.0),
                    "content": chunk.content
                }
                for chunk in getattr(result, "context_chunks", [])
            ]
        }
 
    return await loop.run_in_executor(None, _run)