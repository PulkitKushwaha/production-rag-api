"""
FastAPI Application Entry Point
 
Assembles the full application:
    - Route registration
    - Middleware stack
    - Startup/shutdown lifecycle
    - Exception handlers
    - CORS configuration
"""
 
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import time
import uuid
 
from app.routes.query import router as query_router
from app.routes.health import router as health_router
from app.core.logging import setup_logging, get_logger
 
 
def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
 
    # Setup logging first
    setup_logging()
    logger = get_logger(__name__)
 
    app = FastAPI(
        title="Production RAG API",
        description=(
            "A production-grade REST API wrapping a RAG pipeline. "
            "Async endpoints, JWT/API key auth, rate limiting, "
            "streaming responses, and integrated LLM guardrails."
        ),
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )
 
    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
 
    # Request ID + timing + structured logging middleware
    @app.middleware("http")
    async def request_context_middleware(request: Request, call_next):
        request_id = str(uuid.uuid4())[:8]
        request.state.request_id = request_id
        request.state.start_time = time.time()
 
        response = await call_next(request)
 
        latency_ms = round((time.time() - request.state.start_time) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time"] = f"{latency_ms}ms"
 
        # Structured log every request
        logger.info(
            "request_completed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            latency_ms=latency_ms,
            request_id=request_id
        )
 
        return response
 
    # Exception handlers
    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        return JSONResponse(
            status_code=400,
            content={
                "error": "Bad Request",
                "message": str(exc),
                "request_id": getattr(request.state, "request_id", "unknown")
            }
        )
 
    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        logger.error("unhandled_exception", error=str(exc))
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal Server Error",
                "message": "An unexpected error occurred",
                "request_id": getattr(request.state, "request_id", "unknown")
            }
        )
 
    # Lifecycle
    @app.on_event("startup")
    async def startup_event():
        logger.info("api_startup", version="0.1.0")
 
    @app.on_event("shutdown")
    async def shutdown_event():
        logger.info("api_shutdown")
 
    # Routes
    app.include_router(query_router, prefix="/api/v1", tags=["Query"])
    app.include_router(health_router, prefix="/api/v1", tags=["Observability"])
 
    @app.get("/", tags=["Root"])
    async def root():
        return {
            "service": "production-rag-api",
            "version": "0.1.0",
            "docs": "/docs",
            "health": "/api/v1/health",
            "metrics": "/api/v1/metrics"
        }
 
    return app
 
 
app = create_app()