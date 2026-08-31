"""
Query router.

Handles:
  POST /documents/{document_id}/query — ask a question, get a cited answer
"""
from fastapi import APIRouter, HTTPException, Depends, status

from app.models.query import QueryRequest, QueryResponse
from app.config import get_settings, Settings
from app.services.query_service import QueryService

router = APIRouter(prefix="/documents", tags=["Query"])

_query_service_instance: QueryService | None = None

def get_query_service(settings: Settings = Depends(get_settings)) -> QueryService:
    """Singleton dependency for QueryService to avoid re-opening ChromaDB on every request."""
    global _query_service_instance
    if _query_service_instance is None:
        _query_service_instance = QueryService(settings)
    return _query_service_instance


@router.post(
    "/{document_id}/query",
    response_model=QueryResponse,
    summary="Query a document",
    description=(
        "Ask a natural-language question about a previously uploaded document. "
        "Returns an LLM-generated answer with citations pointing back to the "
        "exact source chunks that grounded it. If the information is not in the document, "
        "provides a general knowledge response with clear notice."
    ),
)
async def query_document(
    document_id: str,
    body: QueryRequest,
    service: QueryService = Depends(get_query_service),
) -> QueryResponse:
    # Verify document exists
    exists = await service.document_exists(document_id)
    if not exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found. Upload it first.",
        )

    try:
        result = await service.answer(
            document_id=document_id,
            question=body.question,
            top_k=body.top_k,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Query failed: {str(exc)}",
        )

    return result
