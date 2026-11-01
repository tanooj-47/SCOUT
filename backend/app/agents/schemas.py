"""
backend/app/agents/schemas.py
Pydantic schemas and typed contracts for SCOUT Multi-Agent Disaster Response Workflow.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.incident import DisasterType


class WorkflowStatus(str, Enum):
    """Lifecycle status of the multi-agent workflow execution."""

    INITIALIZED = "initialized"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SUSPENDED_FOR_APPROVAL = "suspended_for_approval"


class HumanApprovalStatus(str, Enum):
    """Approval status for human review gate decisions (M12.4)."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_REVISION = "needs_revision"


class RecommendationPriority(str, Enum):
    """Priority level for recommended disaster response actions (M12.4)."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class WorkflowStage(str, Enum):
    """Fine-grained execution stages in the multi-agent disaster response pipeline."""

    INITIALIZED = "initialized"
    REQUEST_VALIDATION = "request_validation"
    REQUEST_VALIDATED = "request_validated"
    INTELLIGENCE_ASSESSMENT = "intelligence_assessment"  # Planned M12.2
    CONTEXT_INTERPRETATION = "context_interpretation"    # Planned M12.3
    RISK_ASSESSMENT = "risk_assessment"                  # Planned M12.4
    RESPONSE_PLANNING = "response_planning"              # Planned M12.4
    HUMAN_REVIEW_GATE = "human_review_gate"              # Planned M12.5
    COORDINATOR_REPORT = "coordinator_report"            # Planned M12.5
    COMPLETED = "completed"
    TERMINATED_WITH_ERROR = "terminated_with_error"


class WorkflowError(BaseModel):
    """Structured error descriptor recorded during workflow execution."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(..., description="Machine-readable error classification code")
    message: str = Field(..., description="Human-readable error diagnostic message")
    stage: str = Field(..., description="Workflow stage where error materialized")
    agent: Optional[str] = Field(None, description="Logical agent responsible for execution when error occurred")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when error occurred",
    )
    recoverable: bool = Field(
        default=False, description="True if error allows graph retry or graceful fallback"
    )


class AgentExecutionRecord(BaseModel):
    """Auditable log entry recording the execution of a specific agent or node."""

    model_config = ConfigDict(extra="forbid")

    agent_name: str = Field(..., description="Name of the executing agent or graph node")
    stage: str = Field(..., description="Workflow stage executed")
    status: str = Field(..., description="'success', 'failed', or 'skipped'")
    start_time: datetime = Field(..., description="Execution start timestamp")
    end_time: Optional[datetime] = Field(None, description="Execution completion timestamp")
    duration_seconds: Optional[float] = Field(None, ge=0.0, description="Execution duration in seconds")
    details: Optional[str] = Field(None, description="Contextual diagnostic details or execution summary")


# ---------------------------------------------------------------------------
# Request Schemas
# ---------------------------------------------------------------------------

class DisasterResponseWorkflowRequest(BaseModel):
    """
    Initial input contract submitted to trigger a multi-agent response workflow.
    Validates coordinates, search radius, and disaster category.
    """

    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(
        default_factory=lambda: f"req-{uuid4().hex[:12]}",
        description="Unique request tracking identifier",
    )
    disaster_type: DisasterType = Field(
        default=DisasterType.WILDFIRE,
        description="Target hazard category (pilot supports WILDFIRE)",
    )
    latitude: float = Field(
        ...,
        ge=-90.0,
        le=90.0,
        description="Observation latitude [-90.0, 90.0]",
    )
    longitude: float = Field(
        ...,
        ge=-180.0,
        le=180.0,
        description="Observation longitude [-180.0, 180.0]",
    )
    search_radius_meters: float = Field(
        default=5000.0,
        ge=100.0,
        le=100000.0,
        description="Geographic exposure radius in meters [100.0 - 100,000.0]",
    )
    image_path: Optional[str] = Field(
        None,
        description="Optional local filesystem path or stored media reference for visual analysis",
    )
    source_description: str = Field(
        default="workflow_request",
        max_length=255,
        description="Source or reporting platform description",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional structured metadata or tags associated with request",
    )


# ---------------------------------------------------------------------------
# Contract Schemas for Future Specialized Agents (M12.2 - M12.5)
# ---------------------------------------------------------------------------

class IntelligenceAgentOutput(BaseModel):
    """Contract specification for Agent 1 (Intelligence Agent) output."""

    model_config = ConfigDict(extra="forbid")

    incident_status: str
    incident_severity: Optional[str] = None
    active_evidence_state: str
    visual_evidence_summary: Optional[str] = None
    satellite_evidence_summary: Optional[str] = None
    environmental_evidence_summary: Optional[str] = None
    missing_streams: List[str] = Field(default_factory=list)
    conflicting_streams: List[str] = Field(default_factory=list)
    uncertainty_qualification: Optional[str] = None
    fire_weather_danger: Optional[str] = None
    exposure_level: Optional[str] = None
    potential_consequences: Optional[str] = None
    evidence_summary: Optional[str] = None
    assessment_level: Optional[str] = None
    assessment_id: Optional[str] = None
    provenance: Dict[str, Any] = Field(default_factory=dict)


class WeatherAgentOutput(BaseModel):
    """Contract specification for Agent 2 (Weather Agent) output."""

    model_config = ConfigDict(extra="forbid")

    temperature_c: Optional[float] = None
    relative_humidity_pct: Optional[float] = None
    wind_speed_kmh: Optional[float] = None
    precipitation_mm: Optional[float] = None
    fwi: Optional[float] = None
    danger_rating: Optional[str] = None
    fire_weather_explanation: str
    is_experimental: bool = True
    stale_observations: List[str] = Field(default_factory=list)
    missing_parameters: List[str] = Field(default_factory=list)
    observation_timestamp: Optional[str] = None
    source: Optional[str] = None
    provenance: Dict[str, Any] = Field(default_factory=dict)


class GeospatialAgentOutput(BaseModel):
    """Contract specification for Agent 3 (Geospatial Agent) output."""

    model_config = ConfigDict(extra="forbid")

    exposure_level: str
    exposure_score: Optional[float] = None
    settlements_within_radius: int = 0
    closest_settlement_distance_meters: Optional[float] = None
    closest_settlement_name: Optional[str] = None
    hospitals_within_radius: int = 0
    fire_stations_within_radius: int = 0
    transport_corridors_count: int = 0
    water_bodies_count: int = 0
    catalog_completeness_notes: List[str] = Field(default_factory=list)
    is_verified: bool = False
    data_provider: Optional[str] = None
    provenance: Dict[str, Any] = Field(default_factory=dict)


class RiskAssessmentStatus(str, Enum):
    """Operational completion status of risk assessment synthesis."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    FAILED = "failed"


class RiskAssessmentAgentOutput(BaseModel):
    """Contract specification for Agent 4 (Risk Assessment Agent) output."""

    model_config = ConfigDict(extra="forbid")

    assessment_status: str = Field(
        default=RiskAssessmentStatus.COMPLETE.value,
        description="Status of risk synthesis: complete, partial, insufficient_evidence, failed",
    )
    incident_status: str = Field(
        ...,
        description="Preserved operational incident status: CONFIRMED, SUSPECTED, UNCONFIRMED, INSUFFICIENT_EVIDENCE, UNAVAILABLE",
    )
    incident_severity: Optional[str] = Field(
        None,
        description="Preserved physical incident severity: LOW, MODERATE, HIGH, CRITICAL, or None if unassessed",
    )
    fire_weather_danger: Optional[str] = Field(
        None,
        description="Preserved atmospheric fire-weather danger rating: LOW, MODERATE, HIGH, VERY_HIGH, EXTREME, UNAVAILABLE",
    )
    geographic_exposure_status: str = Field(
        ...,
        description="Status of geographic exposure: VERIFIED_HIGH, VERIFIED_MODERATE, VERIFIED_LOW, UNVERIFIED_CATALOG_GAP, UNAVAILABLE",
    )
    potential_consequences_status: str = Field(
        ...,
        description="Status of potential consequences: CRITICAL, HIGH, MODERATE, LOW, NEGLIGIBLE, UNASSESSED_EXPOSURE_UNVERIFIED, UNASSESSED_INSUFFICIENT_DATA",
    )
    overall_threat_level: str = Field(
        ...,
        description="Qualitative risk classification: CRITICAL_EMERGENCY, ACTIVE_THREAT, POTENTIAL_THREAT, ELEVATED_PREPAREDNESS, LOW_CONCERN, INSUFFICIENT_DATA",
    )
    heuristic_risk_index: Optional[float] = Field(
        None,
        ge=0.0,
        le=100.0,
        description="Transparent rule-based heuristic index [0.0 - 100.0]; NOT a probability",
    )
    hazard_summary: str = Field(..., description="Summary of active physical incident evidence")
    exposure_summary: str = Field(..., description="Summary of exposed settlements and infrastructure")
    consequence_summary: str = Field(..., description="Summary of potential consequences and vulnerability")
    fire_weather_summary: str = Field(..., description="Summary of atmospheric dryness and combustibility")
    supporting_evidence: List[str] = Field(default_factory=list, description="Evidence items supporting this assessment")
    missing_evidence: List[str] = Field(default_factory=list, description="Missing observation streams or data gaps")
    conflicting_evidence: List[str] = Field(default_factory=list, description="Contradictory observations across perception streams")
    uncertainty_qualification: str = Field(..., description="Explicit description of uncertainties, limitations, and caveats")
    assessment_rationale: str = Field(..., description="Transparent plain-English justification for the overall assessment")
    key_risk_drivers: List[str] = Field(default_factory=list, description="Primary drivers escalating risk")
    mitigating_factors: List[str] = Field(default_factory=list, description="Factors reducing risk or limiting spread")
    source_agent_provenance: Dict[str, Any] = Field(default_factory=dict, description="Audit trace linking back to Agents 1, 2, and 3")
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="Assessment generation timestamp",
    )


class ActionRecommendation(BaseModel):
    """Individual evidence-grounded action recommendation (M12.4)."""

    model_config = ConfigDict(extra="forbid")

    action_id: str = Field(default_factory=lambda: f"act-{uuid4().hex[:8]}")
    category: str = Field(..., description="VERIFICATION, MONITORING, PREPAREDNESS, COORDINATION, LIFE_SAFETY, STRUCTURE_PROTECTION, CONTAINMENT")
    title: str = Field(...)
    description: str = Field(...)
    priority: str = Field(..., description="CRITICAL, HIGH, MEDIUM, LOW")
    intended_objective: str = Field(..., description="Specific operational goal of this recommendation")
    suggested_responsible_role: str = Field(..., description="Suggested ICS role for this action")
    suggested_resource_categories: List[str] = Field(default_factory=list, description="Suggested categories of equipment or personnel (not inventory)")
    preconditions: List[str] = Field(default_factory=list, description="Preconditions required before executing")
    safety_constraints: List[str] = Field(default_factory=list, description="Critical responder safety constraints")
    evidence_references: List[str] = Field(default_factory=list, description="Auditable references to upstream agent outputs")
    confidence_description: str = Field(..., description="Qualitative confidence assessment")
    target_infrastructure: Optional[str] = None
    rationale: str = Field(...)
    is_conditional: bool = Field(default=False)
    condition_description: Optional[str] = None
    requires_human_authorization: bool = Field(default=True)


class ResponsePlanningAgentOutput(BaseModel):
    """Contract specification for Agent 5 (Response Planning Agent) output (M12.4)."""

    model_config = ConfigDict(extra="forbid")

    plan_id: str = Field(default_factory=lambda: f"plan-{uuid4().hex[:8]}")
    disaster_type: str = Field(default="wildfire")
    incident_status: str = Field(..., description="Assessed incident status (CONFIRMED, SUSPECTED, etc.)")
    assessed_threat_level: str = Field(..., description="Assessed composite threat level")
    overall_plan_status: str = Field(..., description="complete, partial, preparedness_only, insufficient_evidence, failed")
    recommendations: List[ActionRecommendation] = Field(default_factory=list)
    relevant_geographic_context: Dict[str, Any] = Field(default_factory=dict)
    suggested_resource_categories: List[str] = Field(default_factory=list)
    safety_precautions: List[str] = Field(default_factory=list)
    missing_information: List[str] = Field(default_factory=list)
    operational_limitations: List[str] = Field(default_factory=list)
    human_approval_status: str = Field(default="pending")
    source_agent_provenance: Dict[str, Any] = Field(default_factory=dict)
    priority_level: str = Field(default="HIGH")
    life_safety_notes: List[str] = Field(default_factory=list)
    responder_information_gaps: List[str] = Field(default_factory=list)
    evacuation_alert_guidance: Optional[str] = None
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="Plan generation timestamp",
    )


class HumanApprovalState(BaseModel):
    """Contract specification for Human Review Gate (M12.4)."""

    model_config = ConfigDict(extra="forbid")

    approval_id: str = Field(default_factory=lambda: f"appr-{uuid4().hex[:8]}")
    plan_id: str = Field(..., description="Reference to response plan awaiting approval")
    approval_status: HumanApprovalStatus = Field(default=HumanApprovalStatus.PENDING)
    requires_approval: bool = Field(default=True)
    reviewer_id: Optional[str] = None
    review_timestamp: Optional[str] = None
    reviewer_comments: Optional[str] = None
    rejection_or_revision_reason: Optional[str] = None
    decision_type: Optional[str] = None
    decision_summary: Optional[str] = None
    authorized_by: Optional[str] = None
    authorized_at: Optional[datetime] = None
    comments: Optional[str] = None
    decision_status: str = Field(default="pending", description="pending, approved, rejected, needs_revision")


class CoordinatorReportOutput(BaseModel):
    """Contract specification for Agent 6 (Coordinator Agent) final report (Planned M12.5)."""

    model_config = ConfigDict(extra="forbid")

    report_id: str = Field(default_factory=lambda: f"rep-{uuid4().hex[:12]}")
    executive_summary: str
    incident_status: str
    incident_severity: Optional[str] = None
    composite_threat_level: str
    weather_summary: str
    exposure_summary: str
    recommendations_summary: List[str] = Field(default_factory=list)
    human_decisions_required: List[str] = Field(default_factory=list)
    unresolved_uncertainties: List[str] = Field(default_factory=list)
    audit_trail: Dict[str, Any] = Field(default_factory=dict)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Execution Result Schema
# ---------------------------------------------------------------------------

class WorkflowExecutionResult(BaseModel):
    """Summary representation of a completed or halted disaster response workflow."""

    model_config = ConfigDict(extra="forbid")

    workflow_id: str
    request_id: str
    status: WorkflowStatus
    stage: WorkflowStage
    disaster_type: str
    location: Dict[str, float]
    search_radius_meters: float
    execution_records: List[AgentExecutionRecord] = Field(default_factory=list)
    errors: List[WorkflowError] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    intelligence_output: Optional[IntelligenceAgentOutput] = None
    weather_output: Optional[WeatherAgentOutput] = None
    geospatial_output: Optional[GeospatialAgentOutput] = None
    risk_assessment_output: Optional[RiskAssessmentAgentOutput] = None
    response_plan_output: Optional[ResponsePlanningAgentOutput] = None
    human_approval: Optional[HumanApprovalState] = None
    coordinator_report: Optional[CoordinatorReportOutput] = None
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
