import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set
from uuid import UUID

from geoalchemy2.elements import WKTElement
from geoalchemy2.functions import ST_AsGeoJSON, ST_X, ST_Y
from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.exceptions import (
    ArchivedIncidentModificationError,
    DatabaseConflictError,
    IncidentNotFoundError,
    InternalServiceError,
    InvalidStatusTransitionError,
)
from app.models.detection_result import DetectionResult  # noqa: F401
from app.models.environmental_observation import EnvironmentalObservation
from app.models.hazard_prediction import HazardPrediction
from app.models.incident import Incident
from app.models.uploaded_media import UploadedMedia
from app.schemas.incident import (
    CoordinatePoint,
    DisasterType,
    IncidentCreate,
    IncidentDetailResponse,
    IncidentListResponse,
    IncidentResponse,
    IncidentStatus,
    IncidentSummaryCounts,
    IncidentUpdate,
    Severity,
)

logger = logging.getLogger(__name__)

# Canonical Scalar Projection for List and Write Operations (Excludes raw geometry and observed_perimeter)
INCIDENT_SCALAR_PROJECTION = [
    Incident.id,
    Incident.disaster_type,
    Incident.title,
    Incident.status,
    Incident.severity,
    ST_X(Incident.location).label("longitude"),
    ST_Y(Incident.location).label("latitude"),
    Incident.reported_at,
    Incident.updated_at,
    Incident.contained_at,
    Incident.is_archived,
    Incident.archived_at,
    Incident.incident_metadata.label("metadata"),
]

# Canonical Detail Projection (Includes perimeter metadata and PostGIS GeoJSON representation)
INCIDENT_DETAIL_PROJECTION = [
    *INCIDENT_SCALAR_PROJECTION,
    Incident.perimeter_updated_at,
    ST_AsGeoJSON(Incident.observed_perimeter).label("perimeter_geojson"),
]

# Approved operational lifecycle transitions
ALLOWED_TRANSITIONS: Dict[str, Set[str]] = {
    "reported": {"investigating", "active", "false_alarm"},
    "investigating": {"active", "contained", "resolved", "false_alarm"},
    "active": {"contained", "resolved"},
    "contained": {"active", "resolved"},
    "resolved": {"active"},
    "false_alarm": set(),
}

# Operational Severity Ranking: Critical (1) > High (2) > Moderate (3) > Low (4)
SEVERITY_ORDER = case(
    {
        "critical": 1,
        "high": 2,
        "moderate": 3,
        "low": 4,
    },
    value=Incident.severity,
    else_=5,
)


def _row_to_incident_response(row: Any) -> IncidentResponse:
    """Converts a projected scalar row to an IncidentResponse schema using row._mapping."""
    m = row._mapping
    return IncidentResponse(
        id=m["id"],
        disaster_type=m["disaster_type"],
        title=m["title"],
        status=m["status"],
        severity=m["severity"],
        location=CoordinatePoint(latitude=m["latitude"], longitude=m["longitude"]),
        observed_perimeter=None,
        perimeter_updated_at=None,
        reported_at=m["reported_at"],
        updated_at=m["updated_at"],
        contained_at=m["contained_at"],
        is_archived=m["is_archived"],
        archived_at=m["archived_at"],
        metadata=m["metadata"],
    )


def _row_to_detail_response(row: Any, counts: IncidentSummaryCounts) -> IncidentDetailResponse:
    """Converts a projected detail row to an IncidentDetailResponse schema with parsed GeoJSON."""
    m = row._mapping
    perimeter_dict = json.loads(m["perimeter_geojson"]) if m["perimeter_geojson"] else None
    return IncidentDetailResponse(
        id=m["id"],
        disaster_type=m["disaster_type"],
        title=m["title"],
        status=m["status"],
        severity=m["severity"],
        location=CoordinatePoint(latitude=m["latitude"], longitude=m["longitude"]),
        observed_perimeter=perimeter_dict,
        perimeter_updated_at=m["perimeter_updated_at"],
        reported_at=m["reported_at"],
        updated_at=m["updated_at"],
        contained_at=m["contained_at"],
        is_archived=m["is_archived"],
        archived_at=m["archived_at"],
        metadata=m["metadata"],
        summary_counts=counts,
    )


def create_incident(db: Session, schema: IncidentCreate) -> IncidentResponse:
    """
    Registers a new disaster incident with PostGIS POINT SRID 4326.
    Enforces initial status='reported', is_archived=False, and assigns UTC timestamps.
    """
    now = datetime.now(timezone.utc)
    point_wkt = WKTElement(f"POINT({schema.location.longitude} {schema.location.latitude})", srid=4326)

    incident = Incident(
        disaster_type=schema.disaster_type.value,
        title=schema.title,
        status=IncidentStatus.REPORTED.value,
        severity=schema.severity.value,
        location=point_wkt,
        reported_at=now,
        updated_at=now,
        is_archived=False,
        incident_metadata=schema.metadata,
    )

    try:
        db.add(incident)
        db.flush()

        stmt = select(*INCIDENT_SCALAR_PROJECTION).where(Incident.id == incident.id)
        row = db.execute(stmt).one()
        db.commit()
        return _row_to_incident_response(row)
    except IntegrityError as exc:
        db.rollback()
        logger.warning("Database integrity violation on incident create: %s", exc)
        raise DatabaseConflictError("Incident creation violated database integrity constraints.") from exc
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Unexpected database error on incident create: %s", exc)
        raise InternalServiceError("An unexpected database error occurred while creating the incident.") from exc


def list_incidents(
    db: Session,
    limit: int = 20,
    offset: int = 0,
    disaster_type: Optional[DisasterType] = None,
    status: Optional[IncidentStatus] = None,
    severity: Optional[Severity] = None,
    is_archived: bool = False,
    order_by: str = "reported_at",
    order_direction: str = "desc",
) -> IncidentListResponse:
    """
    Retrieves a paginated collection of incidents matching the specified filters.
    Selects only scalar columns and coordinate projections.
    Perimeter polygons are never loaded in list queries.
    """
    filters = [Incident.is_archived == is_archived]

    if disaster_type is not None:
        filters.append(Incident.disaster_type == disaster_type.value)
    if status is not None:
        filters.append(Incident.status == status.value)
    if severity is not None:
        filters.append(Incident.severity == severity.value)

    # 1. Total matching count query
    count_stmt = select(func.count(Incident.id)).where(*filters)
    total = db.scalar(count_stmt) or 0

    # 2. Ordering definition
    direction = order_direction.lower()
    if order_by == "severity":
        # desc: critical (1) -> low (4); asc: low (4) -> critical (1)
        sort_col = SEVERITY_ORDER.asc() if direction == "desc" else SEVERITY_ORDER.desc()
    elif order_by == "updated_at":
        sort_col = Incident.updated_at.desc() if direction == "desc" else Incident.updated_at.asc()
    else:  # default: reported_at
        sort_col = Incident.reported_at.desc() if direction == "desc" else Incident.reported_at.asc()

    # 3. Data query with deterministic secondary sort on Incident.id.asc()
    data_stmt = (
        select(*INCIDENT_SCALAR_PROJECTION)
        .where(*filters)
        .order_by(sort_col, Incident.id.asc())
        .limit(limit)
        .offset(offset)
    )
    rows = db.execute(data_stmt).all()

    items = [_row_to_incident_response(r) for r in rows]
    has_next = (offset + limit) < total
    has_prev = offset > 0

    return IncidentListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        has_next=has_next,
        has_prev=has_prev,
    )


def get_incident_detail(db: Session, incident_id: UUID) -> IncidentDetailResponse:
    """
    Retrieves full details of an incident including related record counts and perimeter GeoJSON.
    Uses aggregate subqueries rather than hydrating child collections.
    """
    stmt = select(*INCIDENT_DETAIL_PROJECTION).where(Incident.id == incident_id)
    row = db.execute(stmt).first()
    if row is None:
        raise IncidentNotFoundError(incident_id)

    # Efficient scalar count queries for associated multimodal records
    media_count = (
        db.scalar(select(func.count(UploadedMedia.id)).where(UploadedMedia.incident_id == incident_id)) or 0
    )
    obs_count = (
        db.scalar(
            select(func.count(EnvironmentalObservation.id)).where(
                EnvironmentalObservation.incident_id == incident_id
            )
        )
        or 0
    )
    pred_count = (
        db.scalar(
            select(func.count(HazardPrediction.id)).where(HazardPrediction.incident_id == incident_id)
        )
        or 0
    )

    counts = IncidentSummaryCounts(
        media_count=media_count,
        observations_count=obs_count,
        predictions_count=pred_count,
    )

    return _row_to_detail_response(row, counts)


def update_incident(db: Session, incident_id: UUID, schema: IncidentUpdate) -> IncidentResponse:
    """
    Partially updates mutable attributes of an incident.
    Enforces status transition rules, contained_at lifecycle, and archived incident immutability.
    """
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise IncidentNotFoundError(incident_id)

    if incident.is_archived:
        raise ArchivedIncidentModificationError(incident_id)

    fields_to_update = schema.model_fields_set

    # 1. Handle Status Transition and Contained Timestamp Lifecycle
    if "status" in fields_to_update and schema.status is not None:
        current_status = incident.status
        new_status = schema.status.value

        if new_status != current_status:
            allowed = ALLOWED_TRANSITIONS.get(current_status, set())
            if new_status not in allowed:
                raise InvalidStatusTransitionError(current_status, new_status)

            # Contained timestamp lifecycle rules
            if new_status == "contained":
                if incident.contained_at is None:
                    incident.contained_at = datetime.now(timezone.utc)
            elif current_status == "contained" and new_status == "active":
                # Containment lost / flare-up
                incident.contained_at = None
            elif current_status == "resolved" and new_status == "active":
                # Resolved incident rekindled into active
                incident.contained_at = None
            elif current_status == "contained" and new_status == "resolved":
                # Containment achieved prior to resolution: preserve timestamp
                pass

            incident.status = new_status

    # 2. Handle Title Update
    if "title" in fields_to_update and schema.title is not None:
        incident.title = schema.title

    # 3. Handle Severity Update
    if "severity" in fields_to_update and schema.severity is not None:
        incident.severity = schema.severity.value

    # 4. Handle Location Update
    if "location" in fields_to_update and schema.location is not None:
        point_wkt = WKTElement(
            f"POINT({schema.location.longitude} {schema.location.latitude})",
            srid=4326,
        )
        incident.location = point_wkt

    # 5. Handle Metadata Update (Full JSONB replacement semantics)
    if "metadata" in fields_to_update and schema.metadata is not None:
        incident.incident_metadata = schema.metadata

    incident.updated_at = datetime.now(timezone.utc)

    try:
        db.flush()
        stmt = select(*INCIDENT_SCALAR_PROJECTION).where(Incident.id == incident.id)
        row = db.execute(stmt).one()
        db.commit()
        return _row_to_incident_response(row)
    except IntegrityError as exc:
        db.rollback()
        logger.warning("Database integrity violation on incident update: %s", exc)
        raise DatabaseConflictError("Incident update violated database integrity constraints.") from exc
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Unexpected database error on incident update: %s", exc)
        raise InternalServiceError("An unexpected database error occurred while updating the incident.") from exc


def archive_incident(db: Session, incident_id: UUID) -> IncidentResponse:
    """
    Soft-deletes an incident by marking it archived.
    Idempotent: repeating an archive request on an already-archived incident succeeds with 200.
    """
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise IncidentNotFoundError(incident_id)

    # Idempotent response if already archived
    if incident.is_archived:
        stmt = select(*INCIDENT_SCALAR_PROJECTION).where(Incident.id == incident.id)
        row = db.execute(stmt).one()
        return _row_to_incident_response(row)

    now = datetime.now(timezone.utc)
    incident.is_archived = True
    incident.archived_at = now
    incident.updated_at = now

    try:
        db.flush()
        stmt = select(*INCIDENT_SCALAR_PROJECTION).where(Incident.id == incident.id)
        row = db.execute(stmt).one()
        db.commit()
        return _row_to_incident_response(row)
    except IntegrityError as exc:
        db.rollback()
        logger.warning("Database integrity violation on incident archive: %s", exc)
        raise DatabaseConflictError("Incident archival violated database integrity constraints.") from exc
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Unexpected database error on incident archive: %s", exc)
        raise InternalServiceError("An unexpected database error occurred while archiving the incident.") from exc
