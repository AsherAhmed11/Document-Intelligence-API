"""
Query router.

Handles:
  POST /documents/{document_id}/query — ask a question, get a cited answer

NOTE: The retrieval logic (vector search, context formatting, LLM call,
citation extraction) lives in app/services/query_service.py.
That is YOUR architecture to design — this router only handles HTTP.
"""
from fastapi import APIRouter, HTTPException, Depends, status

from app.models.query import QueryRequest, QueryResponse
from app.config import get_settings, Settings
from app.services.query_service import QueryService

router = APIRouter(prefix="/documents", tags=["Query"])


def get_query_service(settings: Settings = Depends(get_settings)) -> QueryService:
    """Dependency that provides a QueryService instance."""
    return QueryService(settings)


@router.post(
    "/{document_id}/query",
    response_model=QueryResponse,
    summary="Query a document",
    description=(
        "Ask a natural-language question about a previously uploaded document. "
        "Returns an LLM-generated answer with citations pointing back to the "
        "exact source chunks that grounded it."
    ),
)
async def query_document(
    document_id: str,
    body: QueryRequest,
    service: QueryService = Depends(get_query_service),
) -> QueryResponse:
    # Verify the document exists before querying
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
