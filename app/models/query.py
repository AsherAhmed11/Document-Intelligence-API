"""
Pydantic models for Q&A query requests and cited answer responses.
"""
from pydantic import BaseModel, Field
from typing import Optional


# ── Request Models ─────────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    """
    Body of a POST /documents/{document_id}/query request.

    NOTE: top_k controls how many chunks are retrieved from the vector store
    before being passed to the LLM. This is YOUR architecture decision —
    the default here is a placeholder.
    """
    question: str = Field(
        ...,
        min_length=5,
        max_length=1000,
        description="The natural-language question to answer from the document",
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Number of chunks to retrieve from vector store (tune this yourself)",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "question": "What was the total revenue in Q3 2024?",
                "top_k": 5,
            }
        }
    }


# ── Response Models ────────────────────────────────────────────────────────────

class Citation(BaseModel):
    """
    A single source chunk that contributed to the answer.

    The fields here depend on what metadata YOU store alongside each
    vector in ChromaDB — adjust to match your schema.
    """
    chunk_index: int = Field(..., description="Index of the source chunk (0-based)")
    page_number: Optional[int] = Field(
        None, description="Page number in the original document, if available"
    )
    excerpt: str = Field(..., description="Raw text excerpt from the source chunk")
    relevance_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Similarity score from vector retrieval (higher = more relevant)",
    )


class QueryResponse(BaseModel):
    """
    Returned by POST /documents/{document_id}/query.

    Contains the LLM-generated answer plus the source citations
    that grounded it.
    """
    document_id: str
    question: str
    answer: str = Field(..., description="LLM-generated answer grounded in the document")
    citations: list[Citation] = Field(
        default_factory=list,
        description="Source chunks that informed the answer",
    )
    answer_found: bool = Field(
        ...,
        description="False if the document did not contain enough context to answer",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "document_id": "doc_a1b2c3d4",
                "question": "What was the total revenue in Q3 2024?",
                "answer": "Total revenue in Q3 2024 was $4.2 billion, representing a 12% YoY increase.",
                "citations": [
                    {
                        "chunk_index": 17,
                        "page_number": 8,
                        "excerpt": "Q3 2024 revenue reached $4.2 billion, up 12% year-over-year...",
                        "relevance_score": 0.94,
                    }
                ],
                "answer_found": True,
            }
        }
    }
