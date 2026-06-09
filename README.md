# production-rag-api
 
A production-grade REST API wrapping a RAG pipeline, built
with FastAPI, async endpoints, JWT/API key authentication,
rate limiting, Docker, GitHub Actions CI/CD, streaming
responses, and integrated LLM guardrails.
 
> Most RAG demos are Jupyter notebooks. This repo shows what
> it takes to actually ship one : auth, rate limiting,
> observability, streaming, Docker, and a CI/CD pipeline
> that tests before it deploys.
 
---
 
## What this covers
 
| Feature | Implementation |
|---|---|
| Async RAG endpoint | FastAPI + async LangChain |
| Authentication | JWT tokens + API key header |
| Rate limiting | slowapi — per-user, per-endpoint |
| Streaming responses | Server-Sent Events (SSE) |
| Input/output safety | llm-guardrails integration |
| Observability | Prometheus metrics + structured logging |
| Health checks | /health + /ready endpoints |
| Containerization | Docker + docker-compose |
| CI/CD | GitHub Actions — test, build, push |
 
---
 
## Architecture
 
```
Client Request
      ↓
┌─────────────────────────────────────┐
│         FastAPI Application         │
│                                     │
│  ┌──────────┐   ┌────────────────┐  │
│  │   Auth   │   │ Rate Limiter   │  │
│  │Middleware│   │   Middleware   │  │
│  └──────────┘   └────────────────┘  │
│         ↓               ↓           │
│  ┌──────────────────────────────┐   │
│  │      Request Logger          │   │
│  └──────────────┬───────────────┘   │
│                 ↓                   │
│  ┌──────────────────────────────┐   │
│  │    /query endpoint           │   │
│  │                              │   │
│  │  Input → Guardrails          │   │
│  │       → RAG Pipeline         │   │
│  │       → Output Guardrails    │   │
│  │       → Response             │   │
│  └──────────────────────────────┘   │
│                 ↓                   │
│  ┌──────────────────────────────┐   │
│  │  Metrics + Structured Logs   │   │
│  └──────────────────────────────┘   │
└─────────────────────────────────────┘
```
 
---
 
## API Design
 
### Endpoints
 
| Method | Path | Description | Auth |
|---|---|---|---|
| `POST` | `/query` | RAG query (returns JSON answer) | Required |
| `POST` | `/query/stream` | RAG query (returns SSE stream) | Required |
| `GET` | `/health` | Liveness check | None |
| `GET` | `/ready` | Readiness check (checks pipeline) | None |
| `GET` | `/metrics` | Prometheus metrics | Internal |
 
### Request schema
 
```json
POST /query
{
  "question": "What is the return policy?",
  "k": 5,
  "metadata_filter": {
    "department": "customer_support"
  },
  "include_sources": true
}
```
 
### Response schema
 
```json
{
  "answer": "Our return policy allows returns within 30 days...",
  "sources": [
    {
      "filename": "return_policy.pdf",
      "chunk_id": "doc_return_policy_chunk_3",
      "relevance_score": 0.92
    }
  ],
  "metadata": {
    "model": "gpt-4",
    "latency_ms": 1243,
    "tokens_used": 847,
    "guardrails_applied": ["pii_redaction"]
  }
}
```
 
---
 
## Production features
 
### Authentication
 
Two auth methods supported, use either or both:
 
**API Key** (recommended for server-to-server):
```
X-API-Key: your-api-key
```
 
**JWT Bearer Token** (for user-facing applications):
```
Authorization: Bearer <jwt_token>
```
 
### Rate limiting
 
Per-user rate limits enforced at the API level:
- 20 requests per minute
- 200 requests per hour
Configurable via environment variables.
Returns `429 Too Many Requests` with retry-after header.
 
### Streaming
 
For long-form answers, use the streaming endpoint:
 
```python
import httpx
 
with httpx.stream("POST", "http://localhost:8000/query/stream",
                  json={"question": "Summarize the return policy"},
                  headers={"X-API-Key": "your-key"}) as r:
    for chunk in r.iter_text():
        print(chunk, end="", flush=True)
```
 
### Observability
 
- **Structured logging** via structlog: JSON logs in production
- **Prometheus metrics**: request count, latency, token usage
- **Request tracing**: correlation ID on every request
- **Health endpoints**: liveness + readiness for Kubernetes
---
 
## Quick start
 
```bash
# Clone and configure
git clone https://github.com/pulkitkushwaha/production-rag-api
cp .env.example .env
# Edit .env with your API keys
 
# Run with Docker
docker-compose up
 
# Or run locally
pip install -r requirements.txt
uvicorn app.main:app --reload
 
# Test
curl -X POST http://localhost:8000/query \
  -H "X-API-Key: dev-key" \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the return policy?"}'
```
 
---
 
## Structure
 
```
production-rag-api/
├── app/
│   ├── main.py              # FastAPI app entry point
│   ├── routes/
│   │   ├── query.py         # POST /query and /query/stream
│   │   └── health.py        # GET /health and /ready
│   ├── middleware/
│   │   ├── auth.py          # JWT + API key authentication
│   │   └── rate_limiter.py  # Per-user rate limiting
│   ├── models/
│   │   ├── requests.py      # QueryRequest schema
│   │   └── responses.py     # QueryResponse schema
│   ├── dependencies/
│   │   └── pipeline.py      # RAG pipeline dependency injection
│   └── core/
│       ├── config.py        # Settings from environment
│       └── logging.py       # Structured logging setup
├── tests/
│   ├── test_query.py
│   ├── test_auth.py
│   └── test_rate_limiting.py
├── Dockerfile
├── docker-compose.yml
└── .github/workflows/
    └── ci.yml
```
 
---
 
## Status
 
| Component | Status |
|---|---|
| FastAPI project scaffold | ✅ Done |
| RAG query endpoint (async) | 🟡 In progress |
| Authentication middleware | ⬜ Coming soon |
| Rate limiting | ⬜ Coming soon |
| Docker + docker-compose | ⬜ Coming soon |
| GitHub Actions CI/CD | ⬜ Coming soon |
| Health + observability endpoints | ⬜ Coming soon |
| Streaming responses (SSE) | ⬜ Coming soon |
| llm-guardrails integration | ⬜ Coming soon |
 
---
 
*Part of the [ai-engineering-portfolio](https://github.com/pulkitkushwaha/ai-engineering-portfolio)
— built by [Pulkit Kushwaha](https://linkedin.com/in/pulkit-kushwaha-514764197)*
