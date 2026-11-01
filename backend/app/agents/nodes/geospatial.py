"""
backend/app/agents/nodes/geospatial.py
Geospatial Agent node for SCOUT LangGraph Multi-Agent Disaster Response Workflow (Milestone 12.2).
Interprets geographic exposure, infrastructure proximity, and catalog completeness boundaries.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional

from app.agents.schemas import (
    AgentExecutionRecord,
    GeospatialAgentOutput,
    WorkflowStage,
    WorkflowStatus,
)
from app.agents.state import DisasterWorkflowState

logger = logging.getLogger(__name__)


def geospatial_agent_node(state: DisasterWorkflowState) -> Dict[str, Any]:
    """
    Agent 3: Geospatial Agent Node
    Responsibilities:
    - Consumes geographic exposure information from the M11 intelligence assessment.
    - Interprets settlements, healthcare facilities, fire stations, roads, and water bodies.
    - Preserves feature counts, distances, data provider source, and catalog completeness limitations.
    - Distinguishes verified zero exposure from unverified or unavailable geographic context.
    - Concludes M12.2 milestone workflow execution, transitioning to COMPLETED (or TERMINATED_WITH_ERROR).
    - Returns a validated GeospatialAgentOutput schema.
    """
    start_time = datetime.now(timezone.utc)
    warnings: List[str] = []

    m11_assessment = state.get("m11_assessment")

    # If M11 assessment is not available, emit explicit unavailable output
    if not m11_assessment:
        logger.warning(
            "Geospatial agent executed without valid M11 assessment in workflow %s",
            state.get("workflow_id"),
        )
        unavailable_output = GeospatialAgentOutput(
            exposure_level="UNAVAILABLE",
            exposure_score=None,
            settlements_within_radius=0,
            closest_settlement_distance_meters=None,
            closest_settlement_name=None,
            hospitals_within_radius=0,
            fire_stations_within_radius=0,
            transport_corridors_count=0,
            water_bodies_count=0,
            catalog_completeness_notes=["Geospatial context unavailable: M11 assessment was not provided."],
            is_verified=False,
            data_provider=None,
            provenance={"agent": "geospatial_agent", "status": "unavailable"},
        ).model_dump(mode="json")

        end_time = datetime.now(timezone.utc)
        duration = (end_time - start_time).total_seconds()
        now_iso = end_time.isoformat()

        rec = AgentExecutionRecord(
            agent_name="geospatial_agent",
            stage=WorkflowStage.CONTEXT_INTERPRETATION.value,
            status="skipped" if state.get("status") == WorkflowStatus.FAILED.value else "success",
            start_time=start_time,
            end_time=end_time,
            duration_seconds=round(duration, 4),
            details="Geospatial context unavailable: upstream M11 assessment missing.",
        ).model_dump(mode="json")

        has_errors = bool(state.get("status") == WorkflowStatus.FAILED.value or state.get("errors"))
        final_status = (
            WorkflowStatus.FAILED.value
            if has_errors
            else state.get("status", WorkflowStatus.RUNNING.value)
        )
        final_stage = (
            WorkflowStage.TERMINATED_WITH_ERROR.value
            if has_errors
            else WorkflowStage.CONTEXT_INTERPRETATION.value
        )

        return {
            "status": final_status,
            "stage": final_stage,
            "geospatial_output": unavailable_output,
            "execution_records": [rec],
            "updated_at": now_iso,
        }

    # Extract geospatial context summary and exposure assessment
    context_summary = m11_assessment.get("context_summary") or {}
    exposure_assessment = m11_assessment.get("exposure_assessment") or {}

    # Locate geospatial evidence item for detailed provenance
    evidence_items = m11_assessment.get("evidence_items", [])
    geo_item = next(
        (item for item in evidence_items if item.get("category") == "geospatial_context"),
        None,
    )

    data_provider: Optional[str] = None
    provenance_details: Dict[str, Any] = {}
    if geo_item:
        data_provider = geo_item.get("source_name", "local_vector_catalog")
        provenance_details = {
            "source_name": data_provider,
            "evidence_id": geo_item.get("id"),
            "features_evaluated": context_summary.get("total_features_evaluated", 0),
            "retrieval_timestamp": geo_item.get("retrieval_timestamp"),
        }
    else:
        data_provider = "geospatial_context"
        provenance_details = {"source": "M11 context_summary"}

    # Extract spatial feature counts & distances
    settlements_count = context_summary.get("settlements_found", 0)
    closest_settlement_dist = context_summary.get("closest_settlement_distance_meters")
    closest_settlement_name = context_summary.get("closest_settlement_name")
    hospitals_count = context_summary.get("hospitals_found", 0)
    fire_stations_count = context_summary.get("fire_stations_found", 0)
    corridors_count = context_summary.get("road_corridors_found", 0)
    water_bodies_count = context_summary.get("water_bodies_found", 0)
    total_features = context_summary.get("total_features_evaluated", 0)

    spatial_notes = list(context_summary.get("spatial_coverage_notes", []))

    # Resolve exposure level & score
    exposure_level = (
        exposure_assessment.get("exposure_level")
        or m11_assessment.get("geographic_exposure")
        or "UNKNOWN"
    )
    exposure_score = exposure_assessment.get("exposure_score")

    # Strict distinction between verified exposure and unverified catalog gap
    is_verified = True
    if (
        "UNVERIFIED" in exposure_level
        or total_features == 0
        or exposure_score is None
    ):
        is_verified = False
        unverified_msg = (
            "Exposure is UNVERIFIED (0 local features in catalog). "
            "Absence of catalog features is NOT evidence of zero exposure."
        )
        if not any("0 local features" in n for n in spatial_notes):
            spatial_notes.append(unverified_msg)
        warnings.append(unverified_msg)

    # Validate output schema
    geospatial_out = GeospatialAgentOutput(
        exposure_level=exposure_level,
        exposure_score=exposure_score,
        settlements_within_radius=settlements_count,
        closest_settlement_distance_meters=closest_settlement_dist,
        closest_settlement_name=closest_settlement_name,
        hospitals_within_radius=hospitals_count,
        fire_stations_within_radius=fire_stations_count,
        transport_corridors_count=corridors_count,
        water_bodies_count=water_bodies_count,
        catalog_completeness_notes=spatial_notes,
        is_verified=is_verified,
        data_provider=data_provider,
        provenance=provenance_details,
    ).model_dump(mode="json")

    end_time = datetime.now(timezone.utc)
    duration = (end_time - start_time).total_seconds()
    now_iso = end_time.isoformat()

    rec = AgentExecutionRecord(
        agent_name="geospatial_agent",
        stage=WorkflowStage.CONTEXT_INTERPRETATION.value,
        status="success",
        start_time=start_time,
        end_time=end_time,
        duration_seconds=round(duration, 4),
        details=(
            f"Geospatial context evaluated: Exposure={exposure_level}, "
            f"Settlements={settlements_count}, Hospitals={hospitals_count}, "
            f"FireStations={fire_stations_count}, Verified={is_verified}."
        ),
    ).model_dump(mode="json")

    has_errors = bool(state.get("status") == WorkflowStatus.FAILED.value or state.get("errors"))
    final_status = (
        WorkflowStatus.FAILED.value
        if has_errors
        else WorkflowStatus.COMPLETED.value
    )
    final_stage = (
        WorkflowStage.TERMINATED_WITH_ERROR.value
        if has_errors
        else WorkflowStage.COMPLETED.value
    )

    return {
        "status": final_status,
        "stage": final_stage,
        "geospatial_output": geospatial_out,
        "warnings": warnings,
        "execution_records": [rec],
        "updated_at": now_iso,
    }
