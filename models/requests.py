"""
Request schemas — Pydantic models for incoming API requests.
 
Design decision: strict validation at the API boundary.
Invalid requests are rejected before they reach the pipeline.
Clear error messages make debugging easy for API consumers.
"""
 
from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any
 
 
class QueryRequest(BaseModel):
    """
    Schema for POST /query and POST /query/stream requests.
 
    All fields except question are optional with sensible defaults.
    """
 
    question: str = Field(
        ...,
        min_length=3,
        max_length=2000,
        description="The question to ask the RAG pipeline",
        example="What is the return policy for online orders?"
    )
 
    k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Number of chunks to retrieve (1-20)",
        example=5
    )
 
    metadata_filter: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional metadata filter for retrieval",
        example={"department": "customer_support", "access_level": "internal"}
    )
 
    include_sources: bool = Field(
        default=True,
        description="Whether to include source citations in response"
    )
 
    include_reasoning: bool = Field(
        default=False,
        description="Whether to include retrieval reasoning in response"
    )
 
    @validator("question")
    def question_must_not_be_blank(cls, v):
        if not v.strip():
            raise ValueError("question must not be blank or whitespace only")
        return v.strip()
 
    class Config:
        json_schema_extra = {
            "example": {
                "question": "What is the return policy for online orders?",
                "k": 5,
                "metadata_filter": None,
                "include_sources": True,
                "include_reasoning": False
            }
        }