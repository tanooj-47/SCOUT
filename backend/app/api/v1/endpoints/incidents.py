from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.incident import (
    DisasterType,
    IncidentCreate,
    IncidentDetailResponse,
    IncidentListResponse,
    IncidentResponse,
    IncidentStatus,
    IncidentUpdate,
    Severity,
)
from app.services import incident_service

router = APIRouter()


@router.post(
    "",
    response_model=IncidentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new disaster incident",
)
def create_incident(
    payload: IncidentCreate,
    db: Session = Depends(get_db),
) -> IncidentResponse:
    """
    Registers a new disaster incident in physical space and time.
    Location coordinates are persisted as a PostGIS POINT (SRID 4326).
    """
    return incident_service.create_incident(db=db, schema=payload)


@router.get(
    "",
    response_model=IncidentListResponse,
    status_code=status.HTTP_200_OK,
    summary="List, filter, and paginate disaster incidents",
)
def list_incidents(
    limit: int = Query(default=20, ge=1, le=100, description="Items per page (max 100)"),
    offset: int = Query(default=0, ge=0, description="Number of items to skip"),
    disaster_type: Optional[DisasterType] = Query(default=None, description="Filter by disaster type"),
    incident_status: Optional[IncidentStatus] = Query(default=None, alias="status", description="Filter by operational status"),
    severity: Optional[Severity] = Query(default=None, description="Filter by impact severity"),
    is_archived: bool = Query(default=False, description="Filter by archival status (default: false)"),
    order_by: str = Query(default="reported_at", pattern="^(reported_at|updated_at|severity)$", description="Field to sort by"),
    order_direction: str = Query(default="desc", pattern="^(asc|desc)$", description="Sort direction (asc/desc)"),
    db: Session = Depends(get_db),
) -> IncidentListResponse:
    """
    Retrieves paginated incident records matching the query parameters.
    Deterministic secondary sorting on incident ID is enforced on all paths.
    """
    return incident_service.list_incidents(
        db=db,
        limit=limit,
        offset=offset,
        disaster_type=disaster_type,
        status=incident_status,
        severity=severity,
        is_archived=is_archived,
        order_by=order_by,
        order_direction=order_direction,
    )


@router.get(
    "/{incident_id}",
    response_model=IncidentDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve incident detail and associated multimodal summary counts",
)
def get_incident(
    incident_id: UUID,
    db: Session = Depends(get_db),
) -> IncidentDetailResponse:
    """
    Retrieves complete details for a single incident including projected geometry,
    observed perimeter GeoJSON (if present), and summary counts of related assets.
    """
    return incident_service.get_incident_detail(db=db, incident_id=incident_id)


@router.patch(
    "/{incident_id}",
    response_model=IncidentResponse,
    status_code=status.HTTP_200_OK,
    summary="Partially update mutable attributes of an incident",
)
def patch_incident(
    incident_id: UUID,
    payload: IncidentUpdate,
    db: Session = Depends(get_db),
) -> IncidentResponse:
    """
    Applies partial updates to mutable incident fields.
    Validates lifecycle state transitions and manages contained_at timestamp updates.
    Archived incidents cannot be modified (returns 409).
    """
    return incident_service.update_incident(db=db, incident_id=incident_id, schema=payload)


@router.post(
    "/{incident_id}/archive",
    response_model=IncidentResponse,
    status_code=status.HTTP_200_OK,
    summary="Soft-archive a disaster incident (idempotent)",
)
def archive_incident(
    incident_id: UUID,
    db: Session = Depends(get_db),
) -> IncidentResponse:
    """
    Soft-deletes an incident by marking it archived.
    Physical deletions are prohibited to preserve disaster intelligence history.
    """
    return incident_service.archive_incident(db=db, incident_id=incident_id)
