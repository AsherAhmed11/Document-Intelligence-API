"""
Pydantic models for document upload and document metadata responses.
"""
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


class DocumentStatus(str, Enum):
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


# ── Response Models ────────────────────────────────────────────────────────────

class DocumentUploadResponse(BaseModel):
    """Returned immediately after a successful file upload and processing."""
    document_id: str = Field(..., description="Unique ID assigned to this document")
    filename: str = Field(..., description="Original filename as uploaded")
    status: DocumentStatus = Field(..., description="Current processing status")
    chunk_count: int = Field(..., description="Number of chunks the document was split into")
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {
        "json_schema_extra": {
            "example": {
                "document_id": "doc_a1b2c3d4",
                "filename": "annual_report_2024.pdf",
                "status": "ready",
                "chunk_count": 42,
                "uploaded_at": "2024-01-15T10:30:00Z",
            }
        }
    }


class DocumentMetadataResponse(BaseModel):
    """Returned when fetching metadata for an existing document."""
    document_id: str
    filename: str
    status: DocumentStatus
    chunk_count: int
    uploaded_at: datetime
    file_size_bytes: int = Field(..., description="Original file size in bytes")

    model_config = {
        "json_schema_extra": {
            "example": {
                "document_id": "doc_a1b2c3d4",
                "filename": "annual_report_2024.pdf",
                "status": "ready",
                "chunk_count": 42,
                "uploaded_at": "2024-01-15T10:30:00Z",
                "file_size_bytes": 204800,
            }
        }
    }


class DocumentDeleteResponse(BaseModel):
    """Returned after a successful document deletion."""
    document_id: str
    message: str = "Document deleted successfully."
