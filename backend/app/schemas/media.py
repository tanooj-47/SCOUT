from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import PaginatedResponse
from app.schemas.incident import CoordinatePoint


class MediaFormat(str, Enum):
    """Approved raster image media formats."""
    JPEG = "jpeg"
    PNG = "png"
    WEBP = "webp"


class MediaSourceType(str, Enum):
    """Common operational disaster intelligence media source classifications."""
    DRONE = "drone"
    SATELLITE = "satellite"
    FIELD_CAMERA = "field_camera"
    GROUND_TEAM = "ground_team"
    CITIZEN_REPORT = "citizen_report"
    SENSOR = "sensor"
    OTHER = "other"


class MediaResponse(BaseModel):
    """
    Standard serialized representation of an ingested media asset.
    Never exposes absolute internal filesystem paths.
    """
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Unique media entity identifier")
    incident_id: Optional[UUID] = Field(None, description="Associated disaster incident identifier if linked")
    storage_path: str = Field(..., description="Relative storage path within the configured media root")
    media_format: str = Field(..., max_length=32, description="Validated raster image format (jpeg, png, webp)")
    source_type: str = Field(..., max_length=32, description="Platform or acquisition source category (standard: drone, satellite, field_camera, ground_team, citizen_report, sensor, other; max 32 characters)")
    file_size_bytes: int = Field(..., ge=0, description="Exact binary size in bytes")
    capture_location: Optional[CoordinatePoint] = Field(None, description="Geographic point where media was acquired")
    captured_at: Optional[datetime] = Field(None, description="Timestamp of visual media acquisition")
    created_at: datetime = Field(..., description="Server ingestion timestamp")


class MediaListResponse(PaginatedResponse[MediaResponse]):
    """Paginated collection of media asset records."""
    pass
