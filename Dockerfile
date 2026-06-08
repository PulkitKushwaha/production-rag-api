# ── Stage 1: Builder ─────────────────────────────────────────
FROM python:3.11-slim AS builder
 
WORKDIR /build
 
# Install build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*
 
# Copy and install Python dependencies
# Copy requirements first for better layer caching —
# dependencies only reinstall when requirements.txt changes
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir --user -r requirements.txt
 
 
# ── Stage 2: Production image ─────────────────────────────────
FROM python:3.11-slim AS production
 
# Security: run as non-root user
RUN addgroup --system appgroup && \
    adduser --system --ingroup appgroup appuser
 
WORKDIR /app
 
# Copy installed packages from builder stage
COPY --from=builder /root/.local /home/appuser/.local
 
# Copy application code
COPY app/ ./app/
COPY .env.example ./.env.example
 
# Create data directory for vector store
RUN mkdir -p /app/data && chown appuser:appgroup /app/data
 
# Switch to non-root user
USER appuser
 
# Make sure local bin is in PATH
ENV PATH=/home/appuser/.local/bin:$PATH
 
# Environment defaults (override at runtime)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LOG_LEVEL=INFO \
    ENABLE_METRICS=true
 
# Expose application port
EXPOSE 8000
 
# Health check — Docker uses this to determine container health
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1
 
# Start the application
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--log-level", "info"]