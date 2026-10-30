from datetime import datetime, timezone
from fastapi import APIRouter
from pydantic import BaseModel, Field
from app.core.config import settings

router = APIRouter()


class HealthResponse(BaseModel):
    """
    Response schema for application liveness probe.
    Confirms the web process is running and responding to HTTP requests.
    """
    status: str = Field(..., description="Application liveness status indicator")
    app_name: str = Field(..., description="Configured application name")
    environment: str = Field(..., description="Active runtime environment")
    timestamp: datetime = Field(..., description="Current UTC timestamp of response")


@router.get("/health", response_model=HealthResponse, summary="Application Liveness Probe")
def get_health() -> HealthResponse:
    """
    Basic application liveness check.

    Confirms that the FastAPI application is initialized and accepting requests.
    Note: This is an application-level liveness probe only. It does not test or guarantee
    the availability of downstream infrastructure, database connections, or ML workers.
    """
    return HealthResponse(
        status="healthy",
        app_name=settings.PROJECT_NAME,
        environment=settings.APP_ENV,
        timestamp=datetime.now(timezone.utc),
    )
