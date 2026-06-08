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
 
router = APIRouter()
 
 
@router.post(
    "/query",
    response_model=QueryResponse,
    summary="Query the RAG pipeline",
    description=(
        "Submit a question and receive an answer grounded in the knowledge base. "
        "Returns JSON with answer, sources, and processing metadata."
    )
)
async def query(
    request: Request,
    body: QueryRequest,
    pipeline=Depends(get_pipeline)
):
    """
    Main RAG query endpoint.
 
    Accepts a question, runs it through the RAG pipeline,
    and returns a structured response with answer, sources,
    and full metadata for observability.
 
    The pipeline dependency is injected, making this endpoint
    fully testable without a real RAG pipeline.
    """
    start_time = time.time()
    request_id = getattr(request.state, "request_id", "unknown")
 
    try:
        # Run the RAG pipeline
        result = await _run_pipeline_async(
            pipeline=pipeline,
            question=body.question,
            k=body.k,
            metadata_filter=body.metadata_filter
        )
 
        latency_ms = round((time.time() - start_time) * 1000, 2)
 
        # Build source documents
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
            answer=result.get("answer", ""),
            sources=sources,
            metadata=QueryMetadata(
                model=result.get("model", "unknown"),
                latency_ms=latency_ms,
                prompt_tokens=result.get("prompt_tokens", 0),
                completion_tokens=result.get("completion_tokens", 0),
                total_tokens=result.get("prompt_tokens", 0) + result.get("completion_tokens", 0),
                chunks_retrieved=len(result.get("chunks", [])),
                guardrails_applied=result.get("guardrails_applied", []),
                request_id=request_id
            ),
            reasoning=result.get("reasoning") if body.include_reasoning else None
        )
 
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Pipeline execution failed: {str(e)}"
        )
 
 
@router.get(
    "/health",
    summary="Liveness check",
    description="Returns 200 if the service is running."
)
async def health():
    """
    Liveness probe: used by Kubernetes/Docker to check if
    the container is alive. Does not check pipeline readiness.
    """
    return {"status": "healthy", "service": "production-rag-api"}
 
 
@router.get(
    "/ready",
    summary="Readiness check",
    description="Returns 200 if the pipeline is ready to serve requests."
)
async def ready(pipeline=Depends(get_pipeline)):
    """
    Readiness probe: checks that the RAG pipeline is initialized
    and the vector store has content. Returns 503 if not ready.
    """
    try:
        # Check pipeline has content
        if hasattr(pipeline, "vector_store") and pipeline.vector_store.size == 0:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "not_ready",
                    "reason": "Vector store is empty — ingest documents first"
                }
            )
        return {"status": "ready", "pipeline": "initialized"}
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "reason": str(e)}
        )
 
 
async def _run_pipeline_async(
    pipeline,
    question: str,
    k: int,
    metadata_filter: dict
) -> dict:
    """
    Run the RAG pipeline asynchronously.
 
    Wraps the synchronous pipeline in an async context.
    In production with a high-traffic API, use run_in_executor
    to avoid blocking the event loop.
    """
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