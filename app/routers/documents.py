"""
Document router — upload, list, get metadata, delete.

POST   /documents/upload          — upload & index a document
GET    /documents                 — list all uploaded documents
GET    /documents/{document_id}   — get document metadata
DELETE /documents/{document_id}   — delete document and its vectors
"""
import uuid
from typing import List
from fastapi import APIRouter, File, UploadFile, HTTPException, Depends, status

from app.models.document import (
    DocumentUploadResponse,
    DocumentMetadataResponse,
    DocumentDeleteResponse,
    DocumentStatus,
)
from app.config import get_settings, Settings
from app.services.document_service import DocumentService

router = APIRouter(prefix="/documents", tags=["Documents"])

_document_service_instance: DocumentService | None = None

def get_document_service(settings: Settings = Depends(get_settings)) -> DocumentService:
    """Singleton dependency for DocumentService to reuse ChromaDB connection."""
    global _document_service_instance
    if _document_service_instance is None:
        _document_service_instance = DocumentService(settings)
    return _document_service_instance


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a document",
    description=(
        "Upload a PDF, TXT, or DOCX file. The document will be parsed, chunked, "
        "embedded with Gemini gemini-embedding-001, and stored in ChromaDB. "
        "Returns a document_id to use for all subsequent queries."
    ),
)
async def upload_document(
    file: UploadFile = File(..., description="PDF, TXT, or DOCX file to index"),
    settings: Settings = Depends(get_settings),
    service: DocumentService = Depends(get_document_service),
) -> DocumentUploadResponse:
    extension = (file.filename or "").rsplit(".", 1)[-1].lower()
    if extension not in settings.allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type '.{extension}'. Allowed: {settings.allowed_extensions}",
        )

    contents = await file.read()
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if len(contents) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the {settings.max_upload_size_mb} MB limit.",
        )

    document_id = f"doc_{uuid.uuid4().hex[:8]}"
    try:
        chunk_count = await service.process_and_index(
            document_id=document_id,
            filename=file.filename or "unknown",
            contents=contents,
            extension=extension,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process document: {str(exc)}",
        )

    return DocumentUploadResponse(
        document_id=document_id,
        filename=file.filename or "unknown",
        status=DocumentStatus.READY,
        chunk_count=chunk_count,
    )


@router.get(
    "",
    response_model=List[DocumentMetadataResponse],
    summary="List all documents",
    description="Returns all uploaded documents, newest first.",
)
async def list_documents(
    service: DocumentService = Depends(get_document_service),
) -> List[DocumentMetadataResponse]:
    return await service.list_documents()


@router.get(
    "/{document_id}",
    response_model=DocumentMetadataResponse,
    summary="Get document metadata",
)
async def get_document(
    document_id: str,
    service: DocumentService = Depends(get_document_service),
) -> DocumentMetadataResponse:
    metadata = await service.get_metadata(document_id)
    if metadata is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found.",
        )
    return metadata


@router.delete(
    "/{document_id}",
    response_model=DocumentDeleteResponse,
    summary="Delete a document",
)
async def delete_document(
    document_id: str,
    service: DocumentService = Depends(get_document_service),
) -> DocumentDeleteResponse:
    deleted = await service.delete(document_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found.",
        )
    return DocumentDeleteResponse(document_id=document_id)
