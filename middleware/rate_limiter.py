"""
Rate Limiting Middleware
 
Enforces per-user request limits to prevent abuse and
control costs in production LLM API deployments.
 
Why rate limiting matters for LLM APIs:
    Each request to a RAG pipeline costs money for embedding calls,
    LLM completion calls, and compute. Without rate limiting:
    - A single user can exhaust your OpenAI budget
    - Abusive queries can degrade performance for all users
    - No protection against credential theft and automated abuse
 
Implementation: in-memory sliding window
    Tracks request timestamps per user in a dict.
    Sliding window (not fixed window) prevents burst attacks
    at window boundaries.
 
    In production: replace with Redis for multi-instance deployments.
    The interface is identical, just swap the storage backend.
 
Limits:
    - Per minute: prevents burst attacks
    - Per hour: prevents sustained high-volume abuse
"""
 
from fastapi import HTTPException, Request
from typing import Dict, List
from collections import defaultdict
import time
 
from app.core.config import settings
 
 
class InMemoryRateLimiter:
    """
    Sliding window rate limiter backed by in-memory storage.
 
    Thread-safe for single-process deployments.
    For multi-process/multi-instance: use Redis backend.
    """
 
    def __init__(self):
        # user_id → list of request timestamps
        self._requests: Dict[str, List[float]] = defaultdict(list)
 
    def check_rate_limit(self, user_id: str) -> None:
        """
        Check if user has exceeded rate limits.
 
        Raises 429 Too Many Requests if limit exceeded.
        Updates request history if within limits.
 
        Args:
            user_id: Identifier for the requesting user/API key
        """
        now = time.time()
 
        # Clean old entries (older than 1 hour)
        self._requests[user_id] = [
            ts for ts in self._requests[user_id]
            if now - ts < 3600
        ]
 
        requests = self._requests[user_id]
 
        # Check per-minute limit
        requests_last_minute = sum(1 for ts in requests if now - ts < 60)
        if requests_last_minute >= settings.rate_limit_per_minute:
            retry_after = int(60 - (now - min(
                ts for ts in requests if now - ts < 60
            )))
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "Rate limit exceeded",
                    "limit": f"{settings.rate_limit_per_minute} requests per minute",
                    "retry_after_seconds": max(retry_after, 1)
                },
                headers={"Retry-After": str(max(retry_after, 1))}
            )
 
        # Check per-hour limit
        requests_last_hour = len(requests)
        if requests_last_hour >= settings.rate_limit_per_hour:
            retry_after = int(3600 - (now - min(requests)))
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "Hourly rate limit exceeded",
                    "limit": f"{settings.rate_limit_per_hour} requests per hour",
                    "retry_after_seconds": max(retry_after, 1)
                },
                headers={"Retry-After": str(max(retry_after, 1))}
            )
 
        # Within limits — record this request
        self._requests[user_id].append(now)
 
    def get_usage(self, user_id: str) -> Dict[str, int]:
        """Return current usage stats for a user."""
        now = time.time()
        requests = self._requests.get(user_id, [])
        return {
            "requests_last_minute": sum(1 for ts in requests if now - ts < 60),
            "requests_last_hour": sum(1 for ts in requests if now - ts < 3600),
            "limit_per_minute": settings.rate_limit_per_minute,
            "limit_per_hour": settings.rate_limit_per_hour
        }
 
    def reset(self, user_id: str) -> None:
        """Reset rate limit for a user (admin use)."""
        if user_id in self._requests:
            del self._requests[user_id]
 
 
# Singleton limiter instance
rate_limiter = InMemoryRateLimiter()
 
 
def check_rate_limit(caller_id: str) -> None:
    """
    FastAPI dependency for rate limit checking.
 
    Usage in routes:
        @router.post("/query")
        async def query(
            body: QueryRequest,
            caller: str = Depends(verify_any_auth),
            _: None = Depends(lambda: check_rate_limit(caller))
        ):
    """
    rate_limiter.check_rate_limit(caller_id)