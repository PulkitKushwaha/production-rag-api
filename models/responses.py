"""
Response schemas: Pydantic models for API responses.
 
Design decision: structured responses with metadata.
Every response includes latency, token usage, and guardrail info, essential for monitoring and debugging production systems.
"""
 
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
 
 
class SourceDocument(BaseModel):
    """A single source document cited in the answer."""
    filename: str
    chunk_id: str
    relevance_score: float = Field(ge=0.0, le=1.0)
    content_preview: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
 
 
class QueryMetadata(BaseModel):
    """Metadata about how the query was processed."""
    model: str
    latency_ms: float
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    chunks_retrieved: int = 0
    guardrails_applied: List[str] = Field(default_factory=list)
    request_id: Optional[str] = None
    timestamp: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat()
    )
 
 
class QueryResponse(BaseModel):
    """
    Standard response for POST /query.
 
    Contains the answer, optional sources, and full metadata
    for observability and debugging.
    """
 
    answer: str = Field(..., description="The generated answer")
    sources: Optional[List[SourceDocument]] = Field(
        default=None,
        description="Source documents used to generate the answer"
    )
    metadata: QueryMetadata = Field(
        ...,
        description="Processing metadata for observability"
    )
    reasoning: Optional[str] = Field(
        default=None,
        description="Retrieval reasoning (only if include_reasoning=True)"
    )
 
    class Config:
        json_schema_extra = {
            "example": {
                "answer": "Our return policy allows returns within 30 days of purchase.",
                "sources": [
                    {
                        "filename": "return_policy.pdf",
                        "chunk_id": "doc_return_policy_chunk_3",
                        "relevance_score": 0.92,
                        "content_preview": "Our return policy allows..."
                    }
                ],
                "metadata": {
                    "model": "gpt-4",
                    "latency_ms": 1243,
                    "total_tokens": 847,
                    "chunks_retrieved": 5,
                    "guardrails_applied": []
                }
            }
        }
 
 
class ErrorResponse(BaseModel):
    """Standard error response schema."""
    error: str
    message: str
    request_id: Optional[str] = None