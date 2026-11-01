"""
backend/app/intelligence/schemas.py
Pydantic data schemas for SCOUT Multimodal Disaster Intelligence (Milestone 11).
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.incident import DisasterType


class EvidenceCategory(str, Enum):
    """Broad categories for multimodal disaster intelligence evidence."""

    COMPUTER_VISION = "computer_vision"
    ENVIRONMENTAL = "environmental"
    GEOSPATIAL_CONTEXT = "geospatial_context"
    SOURCE_METADATA = "source_metadata"
    SATELLITE_OBSERVATION = "satellite_observation"
    FIELD_REPORT = "field_report"


class EvidenceStatus(str, Enum):
    """Validation and operational availability status of an evidence stream."""

    VALID = "valid"
    STALE = "stale"
    UNAVAILABLE = "unavailable"
    CONFLICTING = "conflicting"
    UNSUPPORTED = "unsupported"


class DisasterAssessmentLevel(str, Enum):
    """Categorical threat tier determined by transparent heuristic assessment."""

    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class IncidentStatus(str, Enum):
    """
    Epistemic operational status of an active incident.
    Decoupled from atmospheric fire weather conditions.
    """

    CONFIRMED = "CONFIRMED"
    SUSPECTED = "SUSPECTED"
    UNCONFIRMED = "UNCONFIRMED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class CoordinateLocation(BaseModel):
    """Geographic point representation with WGS 84 spatial reference."""

    model_config = ConfigDict(extra="forbid")

    latitude: float = Field(..., ge=-90.0, le=90.0, description="Latitude [-90.0, 90.0]")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Longitude [-180.0, 180.0]")
    srid: int = Field(default=4326, description="Spatial reference identifier (WGS 84)")


class EvidenceQuality(BaseModel):
    """Metadata regarding evidence freshness, integrity, and provenance."""

    model_config = ConfigDict(extra="forbid")

    is_stale: bool = Field(default=False, description="Whether evidence exceeds freshness threshold")
    age_seconds: Optional[float] = Field(None, ge=0.0, description="Age of observation in seconds")
    has_confidence_measure: bool = Field(
        default=False, description="True only if source emits a mathematically sound confidence"
    )
    confidence_scale: Optional[str] = Field(
        None, description="Explanation of confidence metric scale (e.g. 'softmax_probability [0,1]')"
    )
    provider_type: str = Field(
        ..., description="Data provider typology (e.g., 'deep_learning_model', 'reanalysis_model', 'vector_catalog')"
    )


class EvidenceItem(BaseModel):
    """
    Standard multimodal evidence entity.
    Preserves strict provenance, units, and limitations for each contributing data source.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: f"ev-{uuid4().hex[:12]}", description="Unique evidence identifier")
    category: EvidenceCategory = Field(..., description="Evidence classification category")
    source_name: str = Field(..., description="Name of contributing model, provider, or dataset")
    status: EvidenceStatus = Field(default=EvidenceStatus.VALID, description="Evidence operational validity")
    observation_timestamp: Optional[datetime] = Field(
        None, description="Timestamp when measurement/imagery was captured"
    )
    retrieval_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="Timestamp when SCOUT ingested or processed the evidence"
    )
    location: Optional[CoordinateLocation] = Field(None, description="Geographic point associated with evidence")
    raw_value: Any = Field(..., description="Structured payload, class probability, or measurement dictionary")
    confidence: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Confidence score if source provides a calibrated metric; None otherwise"
    )
    quality: EvidenceQuality = Field(..., description="Quality and freshness metadata")
    provenance: Dict[str, Any] = Field(
        default_factory=dict, description="Detailed lineage (checkpoint path, provider model, sensor platform)"
    )
    caveats: List[str] = Field(
        default_factory=list, description="Explicit caveats and scientific constraints applicable to this item"
    )


class ContextSummary(BaseModel):
    """Structured synthesis of spatial exposure and critical infrastructure."""

    model_config = ConfigDict(extra="forbid")

    settlements_found: int = Field(default=0, ge=0, description="Number of populated places within radius")
    closest_settlement_distance_meters: Optional[float] = Field(
        None, ge=0.0, description="Distance to nearest settlement in meters"
    )
    closest_settlement_name: Optional[str] = Field(None, description="Name of closest settlement")
    hospitals_found: int = Field(default=0, ge=0, description="Number of healthcare facilities within radius")
    closest_hospital_distance_meters: Optional[float] = Field(
        None, ge=0.0, description="Distance to nearest healthcare facility in meters"
    )
    fire_stations_found: int = Field(default=0, ge=0, description="Number of fire stations within radius")
    closest_fire_station_distance_meters: Optional[float] = Field(
        None, ge=0.0, description="Distance to nearest fire station in meters"
    )
    road_corridors_found: int = Field(default=0, ge=0, description="Number of transport corridors within radius")
    water_bodies_found: int = Field(default=0, ge=0, description="Number of hydrological features within radius")
    total_features_evaluated: int = Field(default=0, ge=0, description="Total geographic entities inspected")
    spatial_coverage_notes: List[str] = Field(
        default_factory=list, description="Coverage completeness limitations (e.g., partial OSM fire stations)"
    )


class IncidentObservationInput(BaseModel):
    """API input payload for initiating a multimodal incident assessment."""

    model_config = ConfigDict(extra="forbid")

    disaster_type: DisasterType = Field(default=DisasterType.WILDFIRE, description="Disaster category")
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Latitude [-90.0, 90.0]")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Longitude [-180.0, 180.0]")
    search_radius_meters: float = Field(
        default=5000.0, ge=100.0, le=100000.0, description="Geographic exposure radius in meters"
    )
    observation_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="Timestamp of observation; defaults to UTC now"
    )
    source_description: str = Field(
        default="field_observation", max_length=255, description="Source or reporting platform"
    )
    image_path: Optional[str] = Field(
        None, description="Optional local file path or stored media reference for visual analysis"
    )
    incident_id: Optional[UUID] = Field(
        None, description="Optional foreign key to registered Incident entity in DB"
    )


class IncidentEvidenceState(str, Enum):
    """
    Explicit epistemic classification of direct physical evidence of an active incident.
    Separated from atmospheric fire weather danger.
    Prevents false negatives: absence of visual flame features in a single 2D perspective
    is NEVER equated with proof that no wildfire exists in the surrounding area.
    """

    SUPPORTING_FIRE = "supporting_visual_fire_evidence"
    SUPPORTING_SMOKE = "supporting_visual_smoke_evidence"
    SATELLITE_THERMAL_ANOMALY = "satellite_thermal_anomaly"
    FIELD_CONFIRMED = "field_confirmed_incident"
    NO_SUPPORTING_EVIDENCE = "no_supporting_visual_evidence"
    MISSING_EVIDENCE = "missing_visual_evidence"
    UNCERTAIN_OR_CONFLICTING = "uncertain_or_conflicting_visual_evidence"


# Backward compatibility alias
VisualEvidenceState = IncidentEvidenceState


class HazardAssessment(BaseModel):
    """
    Evaluation of active wildfire hazard and atmospheric combustibility.
    Derived strictly from direct physical hazard evidence, separated from atmospheric fire weather danger,
    and never inflated by static human exposure or infrastructure proximity.
    """

    model_config = ConfigDict(extra="forbid")

    hazard_score: float = Field(..., ge=0.0, le=100.0, description="Active hazard intensity score [0.0 - 100.0]")
    hazard_level: DisasterAssessmentLevel = Field(..., description="Active hazard threat tier: LOW, MODERATE, HIGH, CRITICAL")
    visual_score: Optional[float] = Field(None, ge=0.0, le=100.0, description="Visual flame/smoke intensity [0.0 - 100.0]")
    environmental_score: Optional[float] = Field(
        None, ge=0.0, le=100.0, description="Atmospheric combustibility / FWI danger score [0.0 - 100.0]"
    )
    visual_evidence_state: VisualEvidenceState = Field(
        default=VisualEvidenceState.MISSING_EVIDENCE,
        description="Explicit characterization of visual observation evidence",
    )
    visual_explanation: str = Field(
        default="No visual observation provided.",
        description="Scientific explanation of visual findings and perspective limitations",
    )
    active_incident_score: Optional[float] = Field(
        None, ge=0.0, le=100.0, description="Score derived strictly from direct physical observations of active fire"
    )
    active_incident_level: Optional[DisasterAssessmentLevel] = Field(
        None, description="Active fire presence tier: LOW, MODERATE, HIGH, CRITICAL"
    )
    active_incident_evidence: IncidentEvidenceState = Field(
        default=IncidentEvidenceState.MISSING_EVIDENCE,
        description="Epistemic status of direct physical evidence of active incident",
    )
    active_incident_explanation: str = Field(
        default="No active incident evidence evaluated.",
        description="Direct incident evidence rationale",
    )
    incident_status: IncidentStatus = Field(
        default=IncidentStatus.INSUFFICIENT_EVIDENCE,
        description="Operational incident status: CONFIRMED, SUSPECTED, UNCONFIRMED, INSUFFICIENT_EVIDENCE",
    )
    incident_severity: Optional[DisasterAssessmentLevel] = Field(
        None,
        description="Active incident severity tier: LOW, MODERATE, HIGH, CRITICAL, or None if unassessed",
    )
    fire_weather_score: Optional[float] = Field(
        None, ge=0.0, le=100.0, description="Atmospheric combustibility / FWI danger score [0.0 - 100.0]"
    )
    fire_weather_level: Optional[str] = Field(
        None, description="Atmospheric fire weather danger rating: LOW, MODERATE, HIGH, VERY_HIGH, EXTREME"
    )
    fire_weather_explanation: str = Field(
        default="No fire weather observation evaluated.",
        description="Atmospheric fire weather explanation",
    )
    factors: List[str] = Field(default_factory=list, description="Specific hazard drivers identified")


class ExposureAssessment(BaseModel):
    """
    Evaluation of human settlement, healthcare facilities, and infrastructure exposure.
    Represents vulnerability at the location, NOT active fire hazard.
    """

    model_config = ConfigDict(extra="forbid")

    exposure_score: Optional[float] = Field(
        None, ge=0.0, le=100.0, description="Spatial exposure score [0.0 - 100.0]; null if unverified"
    )
    exposure_level: str = Field(..., description="Exposure tier: LOW, MODERATE, HIGH, CRITICAL, or UNVERIFIED (NO_LOCAL_FEATURES)")
    settlement_distance_meters: Optional[float] = Field(None, ge=0.0, description="Distance to nearest settlement")
    hospital_distance_meters: Optional[float] = Field(None, ge=0.0, description="Distance to nearest healthcare facility")
    factors: List[str] = Field(default_factory=list, description="Exposure drivers identified")


class ConsequenceAssessment(BaseModel):
    """
    Evaluation of potential impact resulting from the intersection of hazard and exposure.
    If hazard is zero, potential consequence is negligible regardless of exposure.
    If hazard is positive but exposure is unverified, consequence cannot be computed (INSUFFICIENT_DATA).
    """

    model_config = ConfigDict(extra="forbid")

    consequence_score: Optional[float] = Field(
        None, ge=0.0, le=100.0, description="Estimated consequence score [0.0 - 100.0]; null if exposure is unverified"
    )
    consequence_tier: DisasterAssessmentLevel = Field(..., description="Potential consequence tier")
    rationale: str = Field(..., description="Plain-English explanation of hazard-exposure interaction")


class MultimodalIntelligenceAssessment(BaseModel):
    """
    Unified multimodal intelligence assessment response.
    Combines computer vision, environmental data, and spatial exposure into an explainable result.
    Separates active hazard from spatial exposure and consequence.
    """

    model_config = ConfigDict(extra="forbid")

    assessment_id: str = Field(
        default_factory=lambda: f"assess-{uuid4().hex[:12]}", description="Unique assessment identifier"
    )
    incident_id: Optional[UUID] = Field(None, description="Associated incident UUID if applicable")
    disaster_type: str = Field(..., description="Target hazard category")
    coordinates: CoordinateLocation = Field(..., description="Point of interest coordinates")
    assessment_level: DisasterAssessmentLevel = Field(..., description="Categorical threat tier")
    heuristic_risk_index: Optional[float] = Field(
        None, ge=0.0, le=100.0, description="Rule-based heuristic index [0.0 - 100.0]; NOT a probability"
    )
    assessment_rationale: str = Field(
        ..., description="Concise human-readable explanation of why this assessment level was determined"
    )
    hazard_assessment: Optional[HazardAssessment] = Field(
        None, description="Direct hazard intensity assessment (visual and atmospheric)"
    )
    exposure_assessment: Optional[ExposureAssessment] = Field(
        None, description="Spatial exposure assessment (settlements, hospitals, corridors)"
    )
    consequence_assessment: Optional[ConsequenceAssessment] = Field(
        None, description="Potential consequence assessment from hazard-exposure intersection"
    )
    active_incident_evidence: IncidentEvidenceState = Field(
        default=IncidentEvidenceState.MISSING_EVIDENCE,
        description="Epistemic status of direct physical evidence of active incident",
    )
    incident_status: IncidentStatus = Field(
        default=IncidentStatus.INSUFFICIENT_EVIDENCE,
        description="Operational incident status: CONFIRMED, SUSPECTED, UNCONFIRMED, INSUFFICIENT_EVIDENCE",
    )
    incident_severity: Optional[DisasterAssessmentLevel] = Field(
        None,
        description="Active incident physical severity: LOW, MODERATE, HIGH, CRITICAL, or INSUFFICIENT_DATA",
    )
    fire_weather_danger: Optional[str] = Field(
        None,
        description="Atmospheric fire weather danger rating: LOW, MODERATE, HIGH, VERY_HIGH, EXTREME, UNAVAILABLE",
    )
    fire_weather_danger_level: Optional[str] = Field(
        None, description="Atmospheric fire weather danger rating (legacy alias)"
    )
    fire_weather_score: Optional[float] = Field(
        None,
        ge=0.0,
        le=100.0,
        description="Atmospheric combustibility / FWI danger score [0.0 - 100.0]",
    )
    geographic_exposure: Optional[str] = Field(
        None,
        description="Spatial exposure tier: LOW, MODERATE, HIGH, CRITICAL, or UNVERIFIED (NO_LOCAL_FEATURES)",
    )
    potential_consequences: Optional[DisasterAssessmentLevel] = Field(
        None,
        description="Potential consequence tier: LOW, MODERATE, HIGH, CRITICAL, or INSUFFICIENT_DATA",
    )
    has_conflicting_evidence: bool = Field(
        default=False, description="True if contradictory observations were detected across modalities"
    )
    uncertainty: Optional[str] = Field(
        None,
        description="Uncertainty qualification and operational guidance",
    )
    uncertainty_qualification: Optional[str] = Field(
        None, description="Uncertainty qualification if conflicts or missing streams degrade assessment confidence (legacy alias)"
    )
    evidence_summary: Optional[str] = Field(
        None,
        description="Consolidated summary of available evidence across observation streams",
    )
    contributing_factors: List[str] = Field(
        default_factory=list, description="Factors that increased the hazard level or severity concern"
    )
    mitigating_factors: List[str] = Field(
        default_factory=list, description="Factors that reduced the hazard level or severity concern"
    )
    missing_evidence: List[str] = Field(
        default_factory=list, description="Required or desirable streams that were absent or unavailable"
    )
    conflicting_evidence: List[str] = Field(
        default_factory=list, description="Contradictory observations detected across modalities"
    )
    evidence_items: List[EvidenceItem] = Field(
        default_factory=list, description="Full trace of contributing evidence items with complete provenance"
    )
    context_summary: ContextSummary = Field(..., description="Structured synthesis of geographic context")
    caveats_and_limitations: List[str] = Field(
        default_factory=list, description="Scientific constraints, calibration limitations, and assumptions applied"
    )
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="Assessment generation timestamp"
    )


class IntelligenceHealthResponse(BaseModel):
    """Operational health probe schema for the intelligence subsystem."""

    model_config = ConfigDict(extra="forbid")

    status: str = Field(..., description="'operational', 'degraded', or 'offline'")
    cv_model_available: bool = Field(..., description="Whether M07 vision model weights are loadable")
    environmental_service_available: bool = Field(..., description="Whether environmental providers are reachable")
    geospatial_service_available: bool = Field(..., description="Whether spatial catalog or PostGIS is active")
    supported_disaster_types: List[str] = Field(..., description="Supported disaster categories")
    version: str = Field(default="1.0.0", description="Intelligence subsystem version")
