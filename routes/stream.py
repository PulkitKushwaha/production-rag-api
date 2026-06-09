"""
Streaming Response Endpoint — Server-Sent Events (SSE)
 
Why streaming matters for RAG APIs:
 
Standard JSON response:
    User sends request → waits 3-8 seconds → receives full answer
    Bad UX for long answers. Feels like the app is frozen.
 
Streaming SSE response:
    User sends request → tokens appear word-by-word → feels instant
    Same total time, but perceived latency is dramatically lower.
    This is how ChatGPT, Claude, and all modern LLM interfaces work.
 
How SSE works:
    Server-Sent Events is a simple HTTP protocol where the server
    pushes a stream of text/event-stream data to the client.
    Each chunk is prefixed with "data: " and ends with "\n\n".
    The client reads chunks as they arrive and renders them.
 
    data: {"token": "Our", "done": false}\n\n
    data: {"token": " return", "done": false}\n\n
    data: {"token": " policy", "done": false}\n\n
    data: {"token": ".", "done": true, "sources": [...]}\n\n
 
Why SSE over WebSockets:
    SSE is simpler — it's a one-way stream over plain HTTP.
    No handshake, no connection management, no special client.
    Works through firewalls, proxies, and CDNs that block WebSockets.
    For RAG responses (server → client only), SSE is the right choice.
 
Client usage:
    Python:
        import httpx
        with httpx.stream("POST", "/api/v1/query/stream",
                          json={"question": "..."}) as r:
            for chunk in r.iter_text():
                process(chunk)
 
    JavaScript:
        const response = await fetch("/api/v1/query/stream", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({question: "..."})
        });
        const reader = response.body.getReader();
        // Read stream chunks...
"""
 
import json
import asyncio
from typing import AsyncGenerator, Optional, Dict, Any
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
 
from app.models.requests import QueryRequest
from app.dependencies.pipeline import get_pipeline
 
router = APIRouter()
 
 
async def generate_rag_stream(
    question: str,
    pipeline,
    k: int = 5,
    metadata_filter: Optional[Dict[str, Any]] = None
) -> AsyncGenerator[str, None]:
    """
    Async generator that yields SSE-formatted chunks.
 
    Simulates token-by-token streaming from the RAG pipeline.
    In production with OpenAI streaming: replace the simulation
    with actual streaming calls using stream=True parameter.
 
    Each yielded string is a complete SSE event:
        data: <json>\n\n
 
    Final event includes sources and signals completion with done=True.
    """
    try:
        # Signal stream start
        yield _sse_event({
            "type": "start",
            "message": "Retrieving relevant context...",
            "done": False
        })
 
        await asyncio.sleep(0.1)  # Simulated retrieval latency
 
        # In production: run retrieval async and yield a status event
        yield _sse_event({
            "type": "status",
            "message": "Generating answer...",
            "done": False
        })
 
        # Run pipeline (blocking — wrap in executor for real async)
        loop = asyncio.get_event_loop()
 
        def _run_pipeline():
            return pipeline.query(
                question=question,
                k=k,
                metadata_filter=metadata_filter
            )
 
        result = await loop.run_in_executor(None, _run_pipeline)
        answer = result.answer if hasattr(result, "answer") else str(result)
 
        # Stream the answer word by word
        # In production with OpenAI streaming: replace with actual token stream
        words = answer.split()
        for i, word in enumerate(words):
            chunk = word + (" " if i < len(words) - 1 else "")
            yield _sse_event({
                "type": "token",
                "token": chunk,
                "done": False
            })
            # Small delay between tokens for realistic streaming feel
            await asyncio.sleep(0.02)
 
        # Final event with sources and completion signal
        sources = []
        if hasattr(result, "context_chunks"):
            sources = [
                {
                    "filename": chunk.metadata.get("filename", "unknown"),
                    "chunk_id": chunk.chunk_id,
                    "score": chunk.metadata.get("retrieval_score", 0.0)
                }
                for chunk in (result.context_chunks or [])
            ]
 
        yield _sse_event({
            "type": "done",
            "token": "",
            "sources": sources,
            "metadata": {
                "model": getattr(result, "model", "unknown"),
                "total_tokens": (
                    getattr(result, "prompt_tokens", 0) +
                    getattr(result, "completion_tokens", 0)
                )
            },
            "done": True
        })
 
    except Exception as e:
        # Always yield an error event so the client knows what happened
        yield _sse_event({
            "type": "error",
            "error": str(e),
            "done": True
        })
 
 
def _sse_event(data: dict) -> str:
    """
    Format a dict as an SSE event string.
 
    SSE format: "data: <json>\n\n"
    The double newline signals end of event to the client.
    """
    return f"data: {json.dumps(data)}\n\n"
 
 
@router.post(
    "/query/stream",
    summary="Query with streaming response",
    description=(
        "Submit a question and receive the answer as a Server-Sent Events stream. "
        "Tokens are yielded as they are generated — improving perceived latency "
        "for long answers. Final event includes source citations."
    ),
    response_class=StreamingResponse
)
async def query_stream(
    request: Request,
    body: QueryRequest,
    pipeline=Depends(get_pipeline)
):
    """
    Streaming RAG query endpoint.
 
    Returns a Server-Sent Events stream where each event is a JSON object:
 
    Stream events:
        {"type": "start", "message": "...", "done": false}
        {"type": "status", "message": "...", "done": false}
        {"type": "token", "token": "word ", "done": false}  (repeated)
        {"type": "done", "sources": [...], "metadata": {...}, "done": true}
        {"type": "error", "error": "...", "done": true}  (on failure)
 
    The client should accumulate "token" events and display them
    progressively, then use the "done" event to show sources.
    """
    return StreamingResponse(
        generate_rag_stream(
            question=body.question,
            pipeline=pipeline,
            k=body.k,
            metadata_filter=body.metadata_filter
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering for SSE
            "X-Request-ID": getattr(request.state, "request_id", "unknown")
        }
    )
 
 
@router.get(
    "/query/stream/test",
    summary="Test streaming endpoint",
    description="Simple test that streams 5 events — useful for verifying SSE works.",
    response_class=StreamingResponse
)
async def stream_test():
    """
    Test endpoint for verifying SSE connectivity.
 
    Streams 5 simple events with 0.5s delay between each.
    Use this to verify your SSE client is working correctly
    before testing with real RAG queries.
    """
    async def test_stream():
        for i in range(1, 6):
            yield _sse_event({
                "event": i,
                "message": f"Test event {i} of 5",
                "done": i == 5
            })
            await asyncio.sleep(0.5)
 
    return StreamingResponse(
        test_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )