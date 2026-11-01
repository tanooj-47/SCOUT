from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.media import MediaListResponse, MediaResponse
from app.services import media_service

router = APIRouter()


@router.post(
    "",
    response_model=MediaResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest a new raster image media asset",
)
def upload_media(
    file: UploadFile = File(..., description="Raster image binary file (JPEG, PNG, WebP)"),
    incident_id: Optional[UUID] = Form(None, description="Optional associated incident UUID"),
    source_type: Optional[str] = Form(None, description="Acquisition platform or source category (standard: drone, satellite, field_camera, ground_team, citizen_report, sensor, other; max 32 characters; default: other)"),
    latitude: Optional[float] = Form(None, description="Capture point latitude [-90.0, 90.0]"),
    longitude: Optional[float] = Form(None, description="Capture point longitude [-180.0, 180.0]"),
    captured_at: Optional[datetime] = Form(None, description="ISO-8601 acquisition timestamp"),
    db: Session = Depends(get_db),
) -> MediaResponse:
    """
    Ingests an image via multipart/form-data.
    Verifies actual byte signature, limits size in chunks, stores to filesystem,
    and commits metadata and capture coordinates to PostgreSQL/PostGIS.
    """
    return media_service.ingest_media(
        db=db,
        upload_file=file,
        incident_id=incident_id,
        source_type=source_type,
        latitude=latitude,
        longitude=longitude,
        captured_at=captured_at,
    )


@router.get(
    "/{media_id}",
    response_model=MediaResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve media metadata by ID",
)
def get_media(
    media_id: UUID,
    db: Session = Depends(get_db),
) -> MediaResponse:
    """
    Retrieves metadata for an existing media entity.
    Never exposes internal filesystem paths or returns raw image binary.
    """
    return media_service.get_media_by_id(db=db, media_id=media_id)


@router.get(
    "",
    response_model=MediaListResponse,
    status_code=status.HTTP_200_OK,
    summary="List and filter media asset metadata",
)
def list_media(
    incident_id: Optional[UUID] = Query(None, description="Filter by associated incident UUID"),
    source_type: Optional[str] = Query(None, description="Filter by acquisition source type"),
    limit: int = Query(default=20, ge=1, le=100, description="Items per page (max 100)"),
    offset: int = Query(default=0, ge=0, description="Items to skip"),
    order_direction: str = Query(default="desc", pattern="^(asc|desc)$", description="Sort by created_at (asc/desc)"),
    db: Session = Depends(get_db),
) -> MediaListResponse:
    """
    Retrieves paginated media metadata records.
    Supports filtering by incident or source type with deterministic secondary ordering.
    """
    return media_service.list_media(
        db=db,
        incident_id=incident_id,
        source_type=source_type,
        limit=limit,
        offset=offset,
        order_direction=order_direction,
    )
