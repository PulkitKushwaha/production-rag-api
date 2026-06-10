# production-rag-api
 
[![CI/CD](https://github.com/pulkitkushwaha/production-rag-api/actions/workflows/ci.yml/badge.svg)](https://github.com/pulkitkushwaha/production-rag-api/actions/workflows/ci.yml)
 
A production-grade REST API wrapping a RAG pipeline built using FastAPI,
async endpoints, JWT/API key auth, rate limiting, SSE streaming,
Prometheus metrics, Docker, GitHub Actions CI/CD, and integrated
LLM guardrails.
 
> Most RAG demos are Jupyter notebooks. This repo shows what
> it actually takes to ship one: auth, rate limiting,
> observability, streaming, Docker, and a CI/CD pipeline
> that tests before it deploys.
 
---
 
## What's built
 
| Feature | Implementation | Status |
|---|---|---|
| Async RAG endpoint | FastAPI + `run_in_executor` | Completed |
| Streaming responses | Server-Sent Events (SSE) | Completed |
| API key authentication | `X-API-Key` header + `secrets.compare_digest` | Completed |
| JWT Bearer auth | `python-jose` + configurable expiry | Completed |
| Rate limiting | Sliding window — per-minute + per-hour | Completed |
| Input guardrails | Topic scope + PII detection | Completed |
| Output guardrails | PII redaction + toxicity filter | Completed |
| Liveness probe | `GET /api/v1/health` | Completed |
| Readiness probe | `GET /api/v1/ready` | Completed |
| Prometheus metrics | `GET /api/v1/metrics` | Completed |
| Structured logging | structlog: JSON in prod, colored in dev | Completed |
| Docker | Multi-stage build, non-root user, HEALTHCHECK | Completed |
| docker-compose | Production + dev profiles | Completed |
| CI/CD | GitHub Actions: test, lint, Docker build, security scan | Completed |
| Dependency injection | `lru_cache` singletons — testable, no re-init | Completed |
 
---
 
## Architecture
 
```
Client
  ↓
┌────────────────────────────────────────────┐
│            FastAPI Application             │
│                                            │
│  CORS → Request ID → Timing → Logging      │
│                    ↓                       │
│  ┌─────────┐  ┌──────────────┐             │
│  │  Auth   │  │ Rate Limiter │             │
│  │Middleware│  │  Middleware  │             │
│  └────┬────┘  └──────┬───────┘             │
│       └──────────────┘                     │
│                    ↓                       │
│  POST /query ──────────────────────────    │
│    Input Guardrails                        │
│      ├─ Topic scope validation             │
│      └─ PII detection + redaction          │
│    RAG Pipeline (async)                    │
│    Output Guardrails                       │
│      ├─ PII redaction                      │
│      └─ Toxicity filter                    │
│    QueryResponse (answer + sources + meta) │
│                                            │
│  POST /query/stream ───────────────────    │
│    Same guardrails → SSE token stream      │
│                                            │
│  GET /health · /ready · /metrics · /stats  │
└────────────────────────────────────────────┘
```
 
---
 
## Quick start
 
```bash
# 1. Clone and configure
git clone https://github.com/pulkitkushwaha/production-rag-api
cd production-rag-api
cp .env.example .env
# Edit .env — add API keys and change SECRET_KEY
 
# 2. Run with Docker (recommended)
docker-compose up
 
# 3. Or run locally
pip install -r requirements.txt
uvicorn app.main:app --reload
 
# 4. Test the API
curl -X POST http://localhost:8000/api/v1/query \
  -H "X-API-Key: dev-key-1" \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the return policy?"}'
 
# 5. View interactive docs
open http://localhost:8000/docs
```
 
---
 
## API Reference
 
### POST /api/v1/query
 
Submit a question. Returns a JSON answer with sources and metadata.
 
**Request:**
```json
{
  "question": "What is the return policy for online orders?",
  "k": 5,
  "metadata_filter": {"department": "customer_support"},
  "include_sources": true,
  "include_reasoning": false
}
```
 
**Response:**
```json
{
  "answer": "Online orders can be returned within 30 days of purchase.",
  "sources": [
    {
      "filename": "return_policy.pdf",
      "chunk_id": "doc_chunk_3",
      "relevance_score": 0.92,
      "content_preview": "Our return policy allows..."
    }
  ],
  "metadata": {
    "model": "gpt-4",
    "latency_ms": 1243,
    "total_tokens": 847,
    "chunks_retrieved": 5,
    "guardrails_applied": ["input_pii_redacted"],
    "request_id": "abc12345"
  }
}
```
 
### POST /api/v1/query/stream
 
Same as `/query` but returns a Server-Sent Events stream.
 
```python
import httpx
 
with httpx.stream(
    "POST", "http://localhost:8000/api/v1/query/stream",
    json={"question": "Summarize the return policy"},
    headers={"X-API-Key": "dev-key-1"}
) as r:
    for chunk in r.iter_text():
        if chunk.startswith("data: "):
            import json
            event = json.loads(chunk[6:])
            if event["type"] == "token":
                print(event["token"], end="", flush=True)
            elif event["type"] == "done":
                print()  # newline
                break
```
 
Stream event types:
```
{"type": "start",  "message": "Retrieving...",  "done": false}
{"type": "status", "message": "Generating...",  "done": false}
{"type": "token",  "token": "word ",            "done": false}
{"type": "done",   "sources": [...], "metadata": {...}, "done": true}
{"type": "error",  "error": "...",              "done": true}
```
 
### Authentication
 
**API Key** (server-to-server):
```
X-API-Key: your-api-key
```
 
**JWT Bearer** (user-facing):
```
Authorization: Bearer <jwt_token>
```
 
Configure keys in `.env`:
```
ALLOWED_API_KEYS=key1,key2,key3
SECRET_KEY=your-jwt-secret-min-32-chars
```
 
### Rate limits
 
| Limit | Default | Config |
|---|---|---|
| Per minute | 20 requests | `RATE_LIMIT_PER_MINUTE` |
| Per hour | 200 requests | `RATE_LIMIT_PER_HOUR` |
 
Returns `429 Too Many Requests` with `Retry-After` header when exceeded.
 
---
 
## Observability
 
```bash
# Liveness (always 200 if process running)
curl http://localhost:8000/api/v1/health
 
# Readiness (200 only if pipeline initialized)
curl http://localhost:8000/api/v1/ready
 
# Prometheus metrics
curl http://localhost:8000/api/v1/metrics
 
# Human-readable stats
curl http://localhost:8000/api/v1/stats
```
 
Metrics exposed:
- `rag_requests_total` — total request count
- `rag_requests_success_total` / `rag_requests_error_total`
- `rag_requests_blocked_auth_total` / `rag_requests_blocked_rate_total`
- `rag_latency_avg_ms` — average request latency
- `rag_tokens_total` — cumulative LLM tokens consumed
- `rag_uptime_seconds` — service uptime
---
 
## Guardrails
 
When [llm-guardrails](https://github.com/pulkitkushwaha/llm-guardrails) is
configured, every `/query` request passes through a 4-step safety pipeline:
 
```
1. Topic scope validation  → blocks off-topic queries immediately
2. Input PII redaction     → strips SSNs, emails from the question
3. RAG pipeline execution
4. Output PII redaction    → strips PII from the LLM response
5. Toxicity filtering      → blocks harmful output
```
 
Every step that fires is logged in `metadata.guardrails_applied`:
```json
"guardrails_applied": ["input_pii_redacted", "output_pii_redacted"]
```
 
Configure the guardrails path:
```
GUARDRAILS_PATH=../llm-guardrails
```
 
---
 
## Docker
 
```bash
# Production
docker-compose up
 
# Development (hot reload on port 8001)
docker-compose --profile dev up api-dev
 
# Build manually
docker build -t production-rag-api .
 
# Run manually
docker run -p 8000:8000 \
  -e SECRET_KEY=your-secret \
  -e ALLOWED_API_KEYS=key1 \
  production-rag-api
```
 
The production Docker image:
- Multi-stage build (dependencies installed in builder, not production)
- Runs as non-root user (`appuser`)
- HEALTHCHECK configured for Docker/Kubernetes
- Data directory mounted as volume (vector store not baked in)
---
 
## CI/CD
 
GitHub Actions runs 4 jobs on every push and PR:
 
| Job | What it does |
|---|---|
| `test` | Runs pytest + verifies app instantiates |
| `lint` | black, isort, flake8 |
| `docker` | Builds image + starts container + hits `/health` |
| `security` | `safety` (dependency CVEs) + `bandit` (static analysis) |
 
The `docker` job is the most valuable — it proves the container actually starts and the health endpoint responds, on every PR.
 
---
 
## Project structure
 
```
production-rag-api/
├── app/
│   ├── main.py              # Factory function, middleware, lifecycle
│   ├── routes/
│   │   ├── query.py         # POST /query (with guardrails)
│   │   ├── stream.py        # POST /query/stream (SSE)
│   │   └── health.py        # GET /health /ready /metrics /stats
│   ├── middleware/
│   │   ├── auth.py          # API key + JWT Bearer
│   │   └── rate_limiter.py  # Sliding window per-user limits
│   ├── models/
│   │   ├── requests.py      # QueryRequest (validated)
│   │   └── responses.py     # QueryResponse + metadata
│   ├── dependencies/
│   │   ├── pipeline.py      # lru_cache RAG pipeline singleton
│   │   └── guardrails.py    # lru_cache guardrails singleton
│   └── core/
│       ├── config.py        # pydantic-settings Settings
│       └── logging.py       # structlog setup
├── tests/
├── Dockerfile               # Multi-stage, non-root, HEALTHCHECK
├── docker-compose.yml       # Production + dev profiles
└── .github/workflows/
    └── ci.yml               # test + lint + docker + security
```
 
---
 
## Related repos
 
| Repo | How it relates |
|---|---|
| [rag-pipeline](https://github.com/pulkitkushwaha/rag-pipeline) | The RAG pipeline this API wraps |
| [llm-guardrails](https://github.com/pulkitkushwaha/llm-guardrails) | Safety layer integrated in `/query` |
| [llm-eval-framework](https://github.com/pulkitkushwaha/llm-eval-framework) | Evaluates the underlying pipeline |
| [llm-security-playbook](https://github.com/pulkitkushwaha/llm-security-playbook) | Security patterns applied here |
| [multi-agent-system](https://github.com/pulkitkushwaha/multi-agent-system) | Alternative orchestration layer |
 
---
 
*Built by [Pulkit Kushwaha](https://linkedin.com/in/pulkit-kushwaha-514764197)
· Part of [ai-engineering-portfolio](https://github.com/pulkitkushwaha/ai-engineering-portfolio)*
