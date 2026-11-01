"""
backend/app/agents/nodes/intelligence.py
Intelligence Agent node for SCOUT LangGraph Multi-Agent Disaster Response Workflow (Milestone 12.2).
Coordinates multimodal incident assessment by reusing the Milestone 11 intelligence service.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from app.agents.schemas import (
    AgentExecutionRecord,
    IntelligenceAgentOutput,
    WorkflowError,
    WorkflowStage,
    WorkflowStatus,
)
from app.agents.state import DisasterWorkflowState
from app.intelligence.schemas import IncidentObservationInput
from app.intelligence.service import MultimodalIntelligenceService
from app.schemas.incident import DisasterType

logger = logging.getLogger(__name__)


def intelligence_agent_node(
    state: DisasterWorkflowState,
    service: Optional[MultimodalIntelligenceService] = None,
) -> Dict[str, Any]:
    """
    Agent 1: Intelligence Agent Node
    Responsibilities:
    - Obtains existing M11 multimodal intelligence assessment via MultimodalIntelligenceService.
    - Preserves incident status, severity, fire-weather danger, exposure, potential consequences,
      uncertainty, evidence summary, and evidence provenance.
    - Represents unavailable assessments explicitly if inputs are missing or service fails.
    - Reuses existing M07/M09/M08/M11 capabilities without duplicate model evaluation or fabrication.
    """
    start_time = datetime.now(timezone.utc)
    errors: List[Dict[str, Any]] = []
    warnings: List[str] = []

    # If workflow has already failed in upstream nodes, record skipped execution and return
    if state.get("status") == WorkflowStatus.FAILED.value:
        rec = AgentExecutionRecord(
            agent_name="intelligence_agent",
            stage=WorkflowStage.INTELLIGENCE_ASSESSMENT.value,
            status="skipped",
            start_time=start_time,
            end_time=datetime.now(timezone.utc),
            duration_seconds=0.0,
            details="Intelligence assessment skipped due to prior workflow failure.",
        ).model_dump(mode="json")
        return {
            "execution_records": [rec],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    lat = state.get("latitude")
    lon = state.get("longitude")
    disaster_type_raw = state.get("disaster_type", "wildfire")
    radius = state.get("search_radius_meters", 5000.0)
    image_path = state.get("image_path")
    source_desc = state.get("source_description", "workflow_request")
    incident_id_raw = state.get("incident_id")

    # Validate presence of coordinates
    if lat is None or lon is None:
        err = WorkflowError(
            code="MISSING_COORDINATES",
            message="Coordinates (latitude and longitude) are required to execute intelligence analysis.",
            stage=WorkflowStage.INTELLIGENCE_ASSESSMENT.value,
            agent="intelligence_agent",
            recoverable=False,
        ).model_dump(mode="json")
        errors.append(err)

        unavailable_output = IntelligenceAgentOutput(
            incident_status="UNAVAILABLE",
            incident_severity=None,
            active_evidence_state="unavailable",
            visual_evidence_summary=None,
            satellite_evidence_summary=None,
            environmental_evidence_summary=None,
            missing_streams=["coordinates", "all_modalities"],
            conflicting_streams=[],
            uncertainty_qualification="Assessment unavailable: required coordinates missing.",
            fire_weather_danger="UNAVAILABLE",
            exposure_level="UNAVAILABLE",
            potential_consequences=None,
            evidence_summary="Assessment unavailable due to missing coordinates.",
            assessment_level="INSUFFICIENT_DATA",
            assessment_id=None,
            provenance={"agent": "intelligence_agent", "error": "MISSING_COORDINATES"},
        ).model_dump(mode="json")

        end_time = datetime.now(timezone.utc)
        duration = (end_time - start_time).total_seconds()
        rec = AgentExecutionRecord(
            agent_name="intelligence_agent",
            stage=WorkflowStage.INTELLIGENCE_ASSESSMENT.value,
            status="failed",
            start_time=start_time,
            end_time=end_time,
            duration_seconds=round(duration, 4),
            details="Intelligence assessment failed: missing required coordinates.",
        ).model_dump(mode="json")

        return {
            "status": WorkflowStatus.FAILED.value,
            "stage": WorkflowStage.TERMINATED_WITH_ERROR.value,
            "intelligence_output": unavailable_output,
            "errors": errors,
            "warnings": warnings,
            "execution_records": [rec],
            "updated_at": end_time.isoformat(),
        }

    # Resolve disaster category enum
    try:
        disaster_type_enum = DisasterType(disaster_type_raw)
    except (ValueError, KeyError):
        disaster_type_enum = DisasterType.WILDFIRE

    # Resolve incident UUID if present
    incident_uuid: Optional[UUID] = None
    if incident_id_raw:
        try:
            incident_uuid = UUID(str(incident_id_raw))
        except (ValueError, AttributeError):
            incident_uuid = None

    obs_input = IncidentObservationInput(
        disaster_type=disaster_type_enum,
        latitude=float(lat),
        longitude=float(lon),
        search_radius_meters=float(radius),
        observation_timestamp=datetime.now(timezone.utc),
        source_description=source_desc,
        image_path=image_path,
        incident_id=incident_uuid,
    )

    intelligence_svc = service or MultimodalIntelligenceService()

    try:
        assessment = intelligence_svc.analyze_observation(
            observation=obs_input,
            image_bytes=None,
            db=None,
        )
    except Exception as exc:
        logger.error("MultimodalIntelligenceService invocation failed: %s", exc)
        err = WorkflowError(
            code="INTELLIGENCE_SERVICE_ERROR",
            message=f"Failed to obtain M11 multimodal intelligence assessment: {str(exc)}",
            stage=WorkflowStage.INTELLIGENCE_ASSESSMENT.value,
            agent="intelligence_agent",
            recoverable=False,
        ).model_dump(mode="json")
        errors.append(err)

        unavailable_output = IntelligenceAgentOutput(
            incident_status="UNAVAILABLE",
            incident_severity=None,
            active_evidence_state="unavailable",
            visual_evidence_summary=None,
            satellite_evidence_summary=None,
            environmental_evidence_summary=None,
            missing_streams=["m11_assessment"],
            conflicting_streams=[],
            uncertainty_qualification=f"M11 assessment failed: {str(exc)}",
            fire_weather_danger="UNAVAILABLE",
            exposure_level="UNAVAILABLE",
            potential_consequences=None,
            evidence_summary=f"Assessment unavailable due to service error: {str(exc)}",
            assessment_level="INSUFFICIENT_DATA",
            assessment_id=None,
            provenance={"agent": "intelligence_agent", "error": str(exc)},
        ).model_dump(mode="json")

        end_time = datetime.now(timezone.utc)
        duration = (end_time - start_time).total_seconds()
        rec = AgentExecutionRecord(
            agent_name="intelligence_agent",
            stage=WorkflowStage.INTELLIGENCE_ASSESSMENT.value,
            status="failed",
            start_time=start_time,
            end_time=end_time,
            duration_seconds=round(duration, 4),
            details=f"Intelligence assessment failed with error: {str(exc)}",
        ).model_dump(mode="json")

        return {
            "status": WorkflowStatus.FAILED.value,
            "stage": WorkflowStage.TERMINATED_WITH_ERROR.value,
            "intelligence_output": unavailable_output,
            "errors": errors,
            "warnings": warnings,
            "execution_records": [rec],
            "updated_at": end_time.isoformat(),
        }

    # Extract summaries from M11 assessment
    visual_summary: Optional[str] = None
    env_summary: Optional[str] = None
    if assessment.hazard_assessment:
        visual_summary = assessment.hazard_assessment.visual_explanation
        env_summary = assessment.hazard_assessment.fire_weather_explanation

    # Build provenance dictionary preserving full trace
    provenance_data: Dict[str, Any] = {
        "assessment_id": assessment.assessment_id,
        "generated_at": assessment.generated_at.isoformat(),
        "disaster_type": assessment.disaster_type,
        "coordinates": assessment.coordinates.model_dump(),
        "heuristic_risk_index": assessment.heuristic_risk_index,
        "evidence_items_count": len(assessment.evidence_items),
        "source": "MultimodalIntelligenceService (M11)",
    }

    intelligence_out = IntelligenceAgentOutput(
        incident_status=assessment.incident_status.value,
        incident_severity=(
            assessment.incident_severity.value if assessment.incident_severity else None
        ),
        active_evidence_state=assessment.active_incident_evidence.value,
        visual_evidence_summary=visual_summary,
        satellite_evidence_summary=None,
        environmental_evidence_summary=env_summary,
        missing_streams=list(assessment.missing_evidence),
        conflicting_streams=list(assessment.conflicting_evidence),
        uncertainty_qualification=assessment.uncertainty or assessment.uncertainty_qualification,
        fire_weather_danger=assessment.fire_weather_danger,
        exposure_level=assessment.geographic_exposure,
        potential_consequences=(
            assessment.potential_consequences.value if assessment.potential_consequences else None
        ),
        evidence_summary=assessment.evidence_summary,
        assessment_level=assessment.assessment_level.value,
        assessment_id=assessment.assessment_id,
        provenance=provenance_data,
    ).model_dump(mode="json")

    end_time = datetime.now(timezone.utc)
    duration = (end_time - start_time).total_seconds()
    now_iso = end_time.isoformat()

    rec = AgentExecutionRecord(
        agent_name="intelligence_agent",
        stage=WorkflowStage.INTELLIGENCE_ASSESSMENT.value,
        status="success",
        start_time=start_time,
        end_time=end_time,
        duration_seconds=round(duration, 4),
        details=(
            f"M11 assessment {assessment.assessment_id} ingested. "
            f"Status={assessment.incident_status.value}, "
            f"Level={assessment.assessment_level.value}."
        ),
    ).model_dump(mode="json")

    return {
        "stage": WorkflowStage.INTELLIGENCE_ASSESSMENT.value,
        "m11_assessment": assessment.model_dump(mode="json"),
        "intelligence_output": intelligence_out,
        "warnings": warnings,
        "execution_records": [rec],
        "updated_at": now_iso,
    }
