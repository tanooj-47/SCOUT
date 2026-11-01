"""
backend/app/geospatial/ingestion/schemas.py
Pydantic schemas for geospatial ingestion, validation, and metadata auditing.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

from app.geospatial.schemas import FeatureCategory


class ConflictPolicy(str, Enum):
    """Conflict resolution strategy for ingestion."""
    UPSERT = "upsert"
    SKIP_EXISTING = "skip_existing"
    FAIL_ON_CONFLICT = "fail_on_conflict"


class IngestionStatus(str, Enum):
    """Audit status of an ingestion run."""
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    DRY_RUN = "dry_run"


class SourceRegistrationCreate(BaseModel):
    """Payload to register an external geographic data source."""
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(..., min_length=2, max_length=64, description="Provider identifier, e.g. openstreetmap, ghsl")
    dataset_name: str = Field(..., min_length=2, max_length=128, description="Dataset title, e.g. osm_critical_facilities")
    dataset_version: Optional[str] = Field(None, max_length=32, description="Dataset release or crawl date")
    source_url: Optional[str] = Field(None, max_length=512, description="Upstream download URL")
    license_identifier: str = Field(..., min_length=2, max_length=64, description="License tag, e.g. ODbL-1.0, CC-BY-4.0")
    attribution_text: str = Field(..., min_length=5, max_length=512, description="Mandatory attribution string")
    source_crs: str = Field(default="EPSG:4326", max_length=32, description="Native coordinate reference system")
    metadata_payload: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary provider metadata")


class SourceRegistrationResponse(BaseModel):
    """Response model for a registered geographic data source."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    provider: str
    dataset_name: str
    dataset_version: Optional[str] = None
    source_url: Optional[str] = None
    license_identifier: str
    attribution_text: str
    source_crs: str
    metadata_payload: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime


class IngestionOptions(BaseModel):
    """Runtime options passed to the ingestion pipeline."""
    model_config = ConfigDict(extra="forbid")

    layer_name: str = Field(..., min_length=2, max_length=64, description="Target layer identifier, e.g. critical_facilities")
    area_of_interest: Optional[str] = Field(None, max_length=128, description="Canonical AOI tag, e.g. in_dehradun_basin")
    dry_run: bool = Field(default=False, description="Simulate ingestion without writing to database")
    conflict_policy: ConflictPolicy = Field(default=ConflictPolicy.UPSERT, description="Conflict resolution policy")
    batch_size: int = Field(default=250, ge=10, le=2000, description="Features per database commit batch")


class NormalizedFeature(BaseModel):
    """Cleaned, validated, and normalized geospatial feature ready for persistence."""
    source_feature_id: str
    layer_name: str
    category: FeatureCategory
    name: str
    properties: Dict[str, Any]
    geometry_wkt: str
    geometry_type: str
    source_crs: str = "EPSG:4326"
    hazard_relevance: List[str]
    bbox_min_lon: float
    bbox_min_lat: float
    bbox_max_lon: float
    bbox_max_lat: float


class IngestionRunSummary(BaseModel):
    """Auditing summary of an ingestion execution."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_id: UUID
    layer_name: str
    area_of_interest: Optional[str] = None
    source_file_name: Optional[str] = None
    source_checksum: Optional[str] = None
    started_at: datetime
    completed_at: Optional[datetime] = None
    total_features: int
    inserted_features: int
    updated_features: int
    skipped_features: int
    rejected_features: int
    status: IngestionStatus
    error_summary: Optional[str] = None
