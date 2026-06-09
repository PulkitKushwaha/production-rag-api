"""
Structured Logging Configuration
 
Uses structlog for JSON-structured logs in production.
Human-readable logs in development.
 
Why structured logging matters:
    Plain text logs: "2024-03-15 INFO Request completed in 1243ms"
    Structured logs: {"timestamp": "2024-03-15", "level": "INFO",
                      "latency_ms": 1243, "request_id": "abc123",
                      "user": "api_key:dev-k...", "tokens": 847}
 
    Structured logs can be:
        - Queried with exact field matches (find all requests > 2000ms)
        - Aggregated (average tokens per user)
        - Alerted on (error rate > 5% in last 5 minutes)
        - Correlated by request_id across services
 
    Plain text logs cannot do any of this reliably.
"""
 
import logging
import sys
from app.core.config import settings
 
 
def setup_logging() -> None:
    """
    Configure application logging.
 
    Development: human-readable colored output
    Production: JSON structured output for log aggregation
    """
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
 
    try:
        import structlog
 
        if settings.debug:
            # Development: pretty printed, colored
            structlog.configure(
                processors=[
                    structlog.contextvars.merge_contextvars,
                    structlog.processors.add_log_level,
                    structlog.processors.TimeStamper(fmt="%H:%M:%S"),
                    structlog.dev.ConsoleRenderer(colors=True)
                ],
                wrapper_class=structlog.make_filtering_bound_logger(log_level),
                logger_factory=structlog.PrintLoggerFactory(),
            )
        else:
            # Production: JSON output
            structlog.configure(
                processors=[
                    structlog.contextvars.merge_contextvars,
                    structlog.processors.add_log_level,
                    structlog.processors.TimeStamper(fmt="iso"),
                    structlog.processors.dict_tracebacks,
                    structlog.processors.JSONRenderer()
                ],
                wrapper_class=structlog.make_filtering_bound_logger(log_level),
                logger_factory=structlog.PrintLoggerFactory(),
            )
 
        print(f"[Logging] Structured logging configured (level: {settings.log_level})")
 
    except ImportError:
        # Fallback to standard logging if structlog not available
        logging.basicConfig(
            level=log_level,
            format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            handlers=[logging.StreamHandler(sys.stdout)]
        )
        print(f"[Logging] Standard logging configured (structlog not installed)")
 
 
def get_logger(name: str):
    """
    Get a logger instance.
 
    Usage:
        from app.core.logging import get_logger
        logger = get_logger(__name__)
        logger.info("Request processed", latency_ms=243, tokens=847)
    """
    try:
        import structlog
        return structlog.get_logger(name)
    except ImportError:
        return logging.getLogger(name)