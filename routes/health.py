"""
Health and Observability Endpoints
 
Three types of endpoints for production observability:
 
1. Liveness (/health)
   Is the process alive? Used by Kubernetes to decide if
   the container should be restarted. Should always return
   200 as long as the process is running, even if the
   pipeline isn't fully ready yet.
2. Readiness (/ready)
   Is the service ready to serve traffic? Used by Kubernetes
   load balancer to decide if traffic should be routed here.
   Checks that the RAG pipeline is initialized and the vector
   store has content. Returns 503 until ready.
3. Metrics (/metrics)
   Prometheus-format metrics for dashboards and alerting.
   Tracks request counts, latency distributions, error rates,
   and LLM-specific metrics (token usage, pipeline calls).
Why these matter in production:
   Without /health and /ready, Kubernetes can't distinguish
   between a starting container and a crashed one. Without
   /metrics, you're flying blind on performance and cost.
   These three endpoints are the minimum for a production API.
"""
 
import time
from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from typing import Dict, Any
 
from app.dependencies.pipeline import get_pipeline
 
router = APIRouter()
 
# ── In-memory metrics store ───────────────────────────────────
# In production: use prometheus_client for proper metric tracking
 
_metrics: Dict[str, Any] = {
    "requests_total": 0,
    "requests_success": 0,
    "requests_error": 0,
    "requests_blocked_auth": 0,
    "requests_blocked_rate": 0,
    "latency_sum_ms": 0.0,
    "tokens_total": 0,
    "startup_time": time.time(),
}
 
 
def record_request(success: bool, latency_ms: float, tokens: int = 0):
    """Record metrics for a single request."""
    _metrics["requests_total"] += 1
    _metrics["latency_sum_ms"] += latency_ms
    _metrics["tokens_total"] += tokens
    if success:
        _metrics["requests_success"] += 1
    else:
        _metrics["requests_error"] += 1
 
 
def record_auth_block():
    _metrics["requests_blocked_auth"] += 1
 
 
def record_rate_limit_block():
    _metrics["requests_blocked_rate"] += 1
 
 
# ── Endpoints ─────────────────────────────────────────────────
 
@router.get(
    "/health",
    summary="Liveness check",
    tags=["Observability"]
)
async def health():
    """
    Liveness probe.
 
    Returns 200 as long as the process is running.
    Does not check pipeline state — that's readiness.
    """
    uptime_seconds = round(time.time() - _metrics["startup_time"], 1)
    return {
        "status": "healthy",
        "service": "production-rag-api",
        "uptime_seconds": uptime_seconds
    }
 
 
@router.get(
    "/ready",
    summary="Readiness check",
    tags=["Observability"]
)
async def ready(pipeline=Depends(get_pipeline)):
    """
    Readiness probe.
 
    Returns 200 only when the RAG pipeline is initialized
    and the vector store has content.
    Returns 503 if not ready — Kubernetes stops routing traffic here.
    """
    checks = {}
 
    # Check 1: pipeline initialized
    checks["pipeline"] = "ok" if pipeline is not None else "not initialized"
 
    # Check 2: vector store has content
    if hasattr(pipeline, "vector_store"):
        store_size = getattr(pipeline.vector_store, "size", 0)
        checks["vector_store"] = f"ok ({store_size} chunks)" if store_size > 0 else "empty"
    else:
        checks["vector_store"] = "not applicable (mock pipeline)"
 
    # Determine overall readiness
    all_ok = all("ok" in v or "not applicable" in v for v in checks.values())
 
    if not all_ok:
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "checks": checks,
                "hint": "Ingest documents before serving traffic"
            }
        )
 
    return {
        "status": "ready",
        "checks": checks
    }
 
 
@router.get(
    "/metrics",
    summary="Prometheus metrics",
    response_class=PlainTextResponse,
    tags=["Observability"]
)
async def metrics():
    """
    Prometheus-format metrics endpoint.
 
    Exposes request counts, latency, token usage, and
    error rates for monitoring dashboards and alerting.
 
    In production: use prometheus_client library for
    proper histogram and gauge types. This implementation
    uses simple counters for portfolio demonstration.
    """
    total = max(_metrics["requests_total"], 1)
    avg_latency = _metrics["latency_sum_ms"] / total
 
    prometheus_text = f"""# HELP rag_requests_total Total number of RAG query requests
# TYPE rag_requests_total counter
rag_requests_total {_metrics["requests_total"]}
 
# HELP rag_requests_success_total Successful RAG query requests
# TYPE rag_requests_success_total counter
rag_requests_success_total {_metrics["requests_success"]}
 
# HELP rag_requests_error_total Failed RAG query requests
# TYPE rag_requests_error_total counter
rag_requests_error_total {_metrics["requests_error"]}
 
# HELP rag_requests_blocked_auth_total Requests blocked by authentication
# TYPE rag_requests_blocked_auth_total counter
rag_requests_blocked_auth_total {_metrics["requests_blocked_auth"]}
 
# HELP rag_requests_blocked_rate_total Requests blocked by rate limiter
# TYPE rag_requests_blocked_rate_total counter
rag_requests_blocked_rate_total {_metrics["requests_blocked_rate"]}
 
# HELP rag_latency_avg_ms Average request latency in milliseconds
# TYPE rag_latency_avg_ms gauge
rag_latency_avg_ms {round(avg_latency, 2)}
 
# HELP rag_tokens_total Total LLM tokens consumed
# TYPE rag_tokens_total counter
rag_tokens_total {_metrics["tokens_total"]}
 
# HELP rag_uptime_seconds Service uptime in seconds
# TYPE rag_uptime_seconds gauge
rag_uptime_seconds {round(time.time() - _metrics["startup_time"], 1)}
"""
    return PlainTextResponse(content=prometheus_text)
 
 
@router.get(
    "/stats",
    summary="Request statistics",
    tags=["Observability"]
)
async def stats():
    """
    Human-readable request statistics.
 
    Useful for quick operational checks without a
    Prometheus/Grafana setup.
    """
    total = max(_metrics["requests_total"], 1)
    success_rate = round(_metrics["requests_success"] / total * 100, 1)
    avg_latency = round(_metrics["latency_sum_ms"] / total, 1)
    uptime = round(time.time() - _metrics["startup_time"], 0)
 
    return {
        "requests": {
            "total": _metrics["requests_total"],
            "successful": _metrics["requests_success"],
            "errors": _metrics["requests_error"],
            "blocked_auth": _metrics["requests_blocked_auth"],
            "blocked_rate_limit": _metrics["requests_blocked_rate"],
            "success_rate_pct": success_rate
        },
        "performance": {
            "avg_latency_ms": avg_latency,
            "total_tokens_used": _metrics["tokens_total"]
        },
        "service": {
            "uptime_seconds": uptime,
            "uptime_human": _format_uptime(uptime)
        }
    }
 
 
def _format_uptime(seconds: float) -> str:
    """Format uptime in human-readable form."""
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    else:
        h = seconds // 3600
        m = (seconds % 3600) // 60
        return f"{h}h {m}m"