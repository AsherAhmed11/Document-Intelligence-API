"""
Health check router — used by Railway and load balancers to verify the service is alive.
"""
from fastapi import APIRouter
from pydantic import BaseModel
from datetime import datetime

router = APIRouter(prefix="/health", tags=["Health"])


class HealthResponse(BaseModel):
    status: str
    timestamp: datetime
    version: str


@router.api_route(
    "",
    methods=["GET", "HEAD"],
    response_model=HealthResponse,
    summary="Health Check",
    description="Returns 200 OK if the API is running. Used by Railway for deployment health checks.",
)
async def health_check() -> HealthResponse:
    from app.config import get_settings
    settings = get_settings()
    return HealthResponse(
        status="ok",
        timestamp=datetime.utcnow(),
        version=settings.app_version,
    )
