"""
backend/app/geospatial/schemas.py
Pydantic schemas for geospatial validation, spatial queries, exposure analysis, and risk assessments.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator


class FeatureCategory(str, Enum):
    """Categorization of geographic features surrounding an incident."""
    SETTLEMENT = "settlement"
    ROAD = "road"
    VEGETATION = "vegetation"
    WATER_BODY = "water_body"
    INFRASTRUCTURE = "infrastructure"
    ADMINISTRATIVE = "administrative"
    OTHER = "other"


class SpatialRelationship(str, Enum):
    """Topological relationship between incident and a geographic feature."""
    INTERSECTS = "intersects"
    WITHIN_RADIUS = "within_radius"
    ADJACENT = "adjacent"
    DISJOINT = "disjoint"


class DistanceUnit(str, Enum):
    METERS = "meters"
    KILOMETERS = "kilometers"


# ==============================================================================
# Coordinate Schemas
# ==============================================================================

class CoordinateValidationRequest(BaseModel):
    """Client request to validate raw geographic coordinates."""
    model_config = ConfigDict(extra="forbid")

    latitude: float = Field(..., description="Latitude in decimal degrees [-90.0, 90.0]")
    longitude: float = Field(..., description="Longitude in decimal degrees [-180.0, 180.0]")


class CoordinateValidationResponse(BaseModel):
    """Response returned by the coordinate validation service."""
    is_valid: bool
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    srid: int = 4326
    utm_epsg: Optional[int] = None
    error_message: Optional[str] = None


# ==============================================================================
# Geographic Feature & Geometry Schemas
# ==============================================================================

class GeoJSONGeometry(BaseModel):
    """GeoJSON representation of geometry."""
    type: str
    coordinates: Any


class GeographicFeatureItem(BaseModel):
    """Structured representation of a spatial entity in the landscape."""
    id: str = Field(..., description="Unique feature identifier")
    name: str = Field(..., description="Human-readable name or label")
    category: FeatureCategory = Field(..., description="Feature category")
    distance_meters: float = Field(..., ge=0.0, description="Shortest geodesic distance in meters")
    relationship: SpatialRelationship = Field(..., description="Topological relationship")
    source_dataset: str = Field(..., description="Provenance / source registry name")
    geometry: Optional[GeoJSONGeometry] = Field(None, description="GeoJSON geometry (if requested)")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Source-specific attributes")

    @property
    def latitude(self) -> Optional[float]:
        """Convenience property resolving feature centroid latitude."""
        if "latitude" in self.metadata:
            return float(self.metadata["latitude"])
        if "centroid_lat" in self.metadata:
            return float(self.metadata["centroid_lat"])
        if self.geometry and self.geometry.type == "Point":
            coords = self.geometry.coordinates
            if isinstance(coords, (list, tuple)) and len(coords) >= 2:
                return float(coords[1])
        return None

    @property
    def longitude(self) -> Optional[float]:
        """Convenience property resolving feature centroid longitude."""
        if "longitude" in self.metadata:
            return float(self.metadata["longitude"])
        if "centroid_lon" in self.metadata:
            return float(self.metadata["centroid_lon"])
        if self.geometry and self.geometry.type == "Point":
            coords = self.geometry.coordinates
            if isinstance(coords, (list, tuple)) and len(coords) >= 2:
                return float(coords[0])
        return None


# ==============================================================================
# Spatial Query & Exposure Schemas
# ==============================================================================

class NearbyFeaturesQuery(BaseModel):
    """Query parameters for finding nearby geographic entities."""
    model_config = ConfigDict(extra="forbid")

    latitude: float = Field(..., ge=-90.0, le=90.0, description="Origin latitude")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Origin longitude")
    radius_meters: float = Field(default=5000.0, ge=100.0, le=100000.0, description="Search radius in meters [100m, 100km]")
    categories: Optional[List[FeatureCategory]] = Field(default=None, description="Optional category filters")
    limit: int = Field(default=50, ge=1, le=200, description="Max features to return")
    include_geometry: bool = Field(default=False, description="Whether to include full GeoJSON geometries")


class ExposureAnalysisRequest(BaseModel):
    """Request payload to perform exposure analysis on an incident or point."""
    model_config = ConfigDict(extra="forbid")

    incident_id: Optional[UUID] = Field(None, description="Existing incident UUID (if assessing registered incident)")
    latitude: Optional[float] = Field(None, ge=-90.0, le=90.0, description="Custom latitude (if not using incident_id)")
    longitude: Optional[float] = Field(None, ge=-180.0, le=180.0, description="Custom longitude (if not using incident_id)")
    search_radius_meters: float = Field(default=5000.0, ge=100.0, le=100000.0, description="Search radius in meters")
    disaster_type: str = Field(default="wildfire", description="Disaster context ('wildfire', 'flood', 'earthquake')")
    include_geometry: bool = Field(default=False, description="Whether to include full geometry objects")


class ExposureSummary(BaseModel):
    """Aggregated exposure metrics for an analysis area."""
    total_features_found: int = Field(..., ge=0)
    category_counts: Dict[str, int] = Field(default_factory=dict)
    closest_feature_distance_meters: Optional[float] = None
    closest_feature_name: Optional[str] = None
    highlighted_exposed_features: List[GeographicFeatureItem] = Field(default_factory=list)


# ==============================================================================
# Geospatial Assessment & Risk Schemas
# ==============================================================================

class IncidentSpatialContext(BaseModel):
    """Contextual metadata regarding the assessed incident location."""
    incident_id: Optional[UUID] = None
    disaster_type: str
    latitude: float
    longitude: float
    srid: int = 4326
    utm_epsg: int
    search_radius_meters: float


class GeospatialAssessmentResponse(BaseModel):
    """
    Standard explainable geospatial assessment response.
    Explicitly separates evidence-based geographic exposure from speculative hazard models.
    """
    assessment_id: str = Field(..., description="Unique assessment execution identifier")
    generated_at_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    incident_context: IncidentSpatialContext
    exposure_summary: ExposureSummary
    features: List[GeographicFeatureItem] = Field(default_factory=list)
    contributing_factors: List[str] = Field(
        default_factory=list,
        description="Explainable, transparent contributing factors derived from verified spatial facts",
    )
    missing_data_indicators: List[str] = Field(
        default_factory=list,
        description="Explicit enumeration of missing or unavailable geographic layers",
    )
    assessment_limitations: List[str] = Field(
        default_factory=list,
        description="Scientific limitations, boundary assumptions, and usage cautions",
    )
    data_provider: str = Field(
        ...,
        description="Origin of geographic features ('postgis_spatial_db', 'local_vector_catalog', 'none')",
    )


# ==============================================================================
# Health Check Schema
# ==============================================================================

class GeospatialHealthResponse(BaseModel):
    """Health and subsystem availability report for the geospatial engine."""
    status: str
    postgis_connected: bool
    shapely_available: bool
    pyproj_available: bool
    supported_crs: List[str]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ==============================================================================
# Persistent Geospatial Layer & Catalog Schemas (Milestone 10)
# ==============================================================================

class LayerSummaryResponse(BaseModel):
    """Summary of a persistent geographic layer."""
    layer_name: str
    feature_count: int
    categories: List[str] = Field(default_factory=list)


class DataSourceItemResponse(BaseModel):
    """External geographic data source provenance."""
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


class IngestionRunItemResponse(BaseModel):
    """Ingestion audit run record."""
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
    status: str
    error_summary: Optional[str] = None


class FeatureListResponse(BaseModel):
    """Paginated list of persistent geographic features."""
    total: int
    limit: int
    offset: int
    features: List[GeographicFeatureItem] = Field(default_factory=list)
