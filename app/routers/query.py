"""
Query router.

Handles:
  POST /documents/{document_id}/query — ask a question on a specific document (or 'general')
  POST /query — ask a general question without uploading a document
"""
import traceback
from fastapi import APIRouter, HTTPException, Depends, status

from app.models.query import QueryRequest, QueryResponse
from app.config import get_settings, Settings
from app.services.query_service import QueryService

router = APIRouter(tags=["Query"])


def get_query_service(settings: Settings = Depends(get_settings)) -> QueryService:
    """Provides a QueryService instance per request."""
    return QueryService(settings)


@router.post(
    "/documents/{document_id}/query",
    response_model=QueryResponse,
    summary="Query a document or general AI",
    description=(
        "Ask a natural-language question about a document or pass document_id='general'. "
        "Returns cited answers or general knowledge fallback with sources."
    ),
)
async def query_document(
    document_id: str,
    body: QueryRequest,
    service: QueryService = Depends(get_query_service),
) -> QueryResponse:
    if document_id not in ["general", "none", ""]:
        exists = await service.document_exists(document_id)
        if not exists:
            document_id = "general"

    try:
        return await service.answer(
            document_id=document_id,
            question=body.question,
            top_k=body.top_k,
        )
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Query failed: {str(exc)}",
        )


@router.post(
    "/query",
    response_model=QueryResponse,
    summary="Ask a general question (No document required)",
    description="Ask any question without uploading a document.",
)
async def query_general(
    body: QueryRequest,
    service: QueryService = Depends(get_query_service),
) -> QueryResponse:
    try:
        return await service.answer(
            document_id="general",
            question=body.question,
            top_k=body.top_k,
        )
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Query failed: {str(exc)}",
        )
