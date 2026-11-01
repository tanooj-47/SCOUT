from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
from uuid import UUID
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)
from app.schemas.common import PaginatedResponse


class DisasterType(str, Enum):
    """Approved disaster classification categories."""
    WILDFIRE = "wildfire"
    FLOOD = "flood"
    EARTHQUAKE = "earthquake"


class IncidentStatus(str, Enum):
    """Approved operational lifecycle statuses."""
    REPORTED = "reported"
    INVESTIGATING = "investigating"
    ACTIVE = "active"
    CONTAINED = "contained"
    RESOLVED = "resolved"
    FALSE_ALARM = "false_alarm"


class Severity(str, Enum):
    """Approved impact severity tiers."""
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class CoordinateInput(BaseModel):
    """
    Client coordinate input schema.
    Strictly accepts decimal latitude and longitude within physical bounds.
    Rejects NaN, +inf, -inf, and extra fields.
    SRID is server-controlled (EPSG:4326) and excluded from client requests.
    """
    model_config = ConfigDict(extra="forbid")

    latitude: float = Field(
        ...,
        ge=-90.0,
        le=90.0,
        allow_inf_nan=False,
        description="WGS 84 Latitude in decimal degrees [-90.0, 90.0]"
    )
    longitude: float = Field(
        ...,
        ge=-180.0,
        le=180.0,
        allow_inf_nan=False,
        description="WGS 84 Longitude in decimal degrees [-180.0, 180.0]"
    )


class CoordinatePoint(BaseModel):
    """
    Server coordinate response schema.
    Returns latitude, longitude, and constant server-controlled SRID 4326.
    """
    latitude: float = Field(..., description="WGS 84 Latitude in decimal degrees")
    longitude: float = Field(..., description="WGS 84 Longitude in decimal degrees")
    srid: int = Field(default=4326, description="Spatial reference system identifier (WGS 84)")


class IncidentCreate(BaseModel):
    """
    Schema for creating a new disaster incident.
    Omitted protected fields (status, timestamps, archive flags) are assigned by the service.
    """
    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., min_length=3, max_length=255, description="Operational callsign or incident title")
    disaster_type: DisasterType = Field(..., description="Hazard category")
    severity: Severity = Field(default=Severity.LOW, description="Initial severity assessment")
    location: CoordinateInput = Field(..., description="Point of origin geographic coordinates")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Operational metadata dictionary")

    @field_validator("title")
    @classmethod
    def validate_title_trimmed(cls, v: str) -> str:
        trimmed = v.strip()
        if len(trimmed) < 3:
            raise ValueError("Title must contain at least 3 non-whitespace characters")
        return trimmed


class IncidentUpdate(BaseModel):
    """
    Partial update schema for incidents.
    
    Rules:
    - Omitted fields: Preserved as-is in database.
    - Explicit null: Rejected for every non-nullable mutable field.
    - Empty payload ({}): Explicitly rejected.
    - Extra fields: Rejected.
    """
    model_config = ConfigDict(extra="forbid")

    title: Optional[str] = None
    status: Optional[IncidentStatus] = None
    severity: Optional[Severity] = None
    location: Optional[CoordinateInput] = None
    metadata: Optional[Dict[str, Any]] = None

    @field_validator("title")
    @classmethod
    def validate_title_trimmed(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            trimmed = v.strip()
            if len(trimmed) < 3:
                raise ValueError("Title must contain at least 3 non-whitespace characters")
            return trimmed
        return v

    @model_validator(mode="after")
    def validate_patch_semantics(self) -> "IncidentUpdate":
        # 1. Reject empty PATCH payload
        if not self.model_fields_set:
            raise ValueError("At least one mutable field must be provided in the update payload")

        # 2. Reject explicit null for non-nullable fields
        non_nullable_fields = ("title", "status", "severity", "location", "metadata")
        for field_name in non_nullable_fields:
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"Field '{field_name}' is non-nullable and cannot be set to null")

        return self


class IncidentResponse(BaseModel):
    """Standard incident output schema."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    disaster_type: DisasterType
    title: str
    status: IncidentStatus
    severity: Severity
    location: CoordinatePoint
    observed_perimeter: Optional[Dict[str, Any]] = None
    perimeter_updated_at: Optional[datetime] = None
    reported_at: datetime
    updated_at: datetime
    contained_at: Optional[datetime] = None
    is_archived: bool
    archived_at: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        validation_alias="incident_metadata",
        serialization_alias="metadata",
    )


class IncidentSummaryCounts(BaseModel):
    """Summary record counts for related multimodal entities."""
    media_count: int = Field(default=0, ge=0, description="Count of associated media records")
    observations_count: int = Field(default=0, ge=0, description="Count of environmental observations")
    predictions_count: int = Field(default=0, ge=0, description="Count of hazard predictions")


class IncidentDetailResponse(IncidentResponse):
    """Detailed incident response with summary counts of related multimodal data."""
    summary_counts: IncidentSummaryCounts = Field(default_factory=IncidentSummaryCounts)


class IncidentListResponse(PaginatedResponse[IncidentResponse]):
    """Paginated collection of incident summaries."""
    pass
