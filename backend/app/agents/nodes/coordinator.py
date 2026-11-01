"""
backend/app/agents/nodes/coordinator.py
Coordinator Agent node for SCOUT LangGraph Disaster Response Workflow (Milestone 12.5).
Orchestrates agent execution synthesis, constructs executive coordinator report,
aggregates cross-agent uncertainties, and preserves audit trail and evidence provenance.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
from uuid import uuid4

from app.agents.schemas import (
    AgentExecutionRecord,
    CoordinatorReportOutput,
    HumanApprovalStatus,
    WorkflowError,
    WorkflowStage,
    WorkflowStatus,
)
from app.agents.state import DisasterWorkflowState

logger = logging.getLogger(__name__)


def coordinator_agent_node(state: DisasterWorkflowState) -> Dict[str, Any]:
    """
    Coordinator Agent Node (Agent 6 / Synthesis Layer)
    Responsibilities:
    - Ingests upstream agent outputs: intelligence, weather, geospatial, risk, plan, and approval gate.
    - Synthesizes an executive coordinator report (CoordinatorReportOutput).
    - Summarizes cross-agent findings: hazard context, weather, exposure, and recommended actions.
    - Aggregates unresolved uncertainties and highlights required human decisions.
    - Preserves execution history, errors, warnings, and evidence provenance.
    - Determines final lifecycle status (e.g. SUSPENDED_FOR_APPROVAL if pending human review,
      or FAILED if unrecoverable upstream failures exist, or COMPLETED).
    - Strictly advisory: does not autonomously dispatch resources or activate physical systems.
    """
    start_time = datetime.now(timezone.utc)
    workflow_id = state.get("workflow_id", "unassigned")
    request_id = state.get("request_id", "unassigned")
    disaster_type = state.get("disaster_type", "wildfire")
    lat = state.get("latitude", 0.0)
    lon = state.get("longitude", 0.0)

    current_status = state.get("status", WorkflowStatus.INITIALIZED.value)
    errors: List[Dict[str, Any]] = list(state.get("errors", []))
    warnings: List[str] = list(state.get("warnings", []))
    execution_records = list(state.get("execution_records", []))

    intel_out = state.get("intelligence_output")
    weather_out = state.get("weather_output")
    geo_out = state.get("geospatial_output")
    risk_out = state.get("risk_assessment_output")
    plan_out = state.get("response_plan_output")
    approval_state = state.get("human_approval")

    has_errors = bool(current_status == WorkflowStatus.FAILED.value or errors)

    # 1. Synthesize Incident Status and Severity
    incident_status = "UNKNOWN"
    if risk_out and risk_out.get("incident_status"):
        incident_status = risk_out["incident_status"]
    elif intel_out and intel_out.get("incident_status"):
        incident_status = intel_out["incident_status"]

    incident_severity = None
    if risk_out and risk_out.get("incident_severity"):
        incident_severity = risk_out["incident_severity"]
    elif intel_out and intel_out.get("severity"):
        incident_severity = intel_out["severity"]

    # 2. Composite Threat Level
    composite_threat_level = "UNKNOWN"
    if risk_out and risk_out.get("composite_threat_level"):
        composite_threat_level = risk_out["composite_threat_level"]
    elif intel_out and intel_out.get("threat_level"):
        composite_threat_level = intel_out["threat_level"]

    # 3. Weather Summary
    weather_summary = "Weather observations unavailable."
    if weather_out:
        fwi_val = weather_out.get("fwi_value")
        fwi_cat = weather_out.get("fwi_category", "UNKNOWN")
        temp = weather_out.get("temperature_c")
        rh = weather_out.get("relative_humidity_pct")
        wind = weather_out.get("wind_speed_kmh")
        wind_dir = weather_out.get("wind_direction_deg")
        weather_summary = (
            f"Conditions: Temp={temp}°C, RH={rh}%, Wind={wind} km/h (dir {wind_dir}°). "
            f"Fire Weather Index (FWI)={fwi_val} [{fwi_cat}]."
        )

    # 4. Exposure Summary
    exposure_summary = "Geospatial exposure data unavailable."
    if geo_out:
        crit_count = geo_out.get("critical_infrastructure_count", 0)
        res_count = geo_out.get("residential_settlement_count", 0)
        tot_features = geo_out.get("total_features_found", 0)
        exposure_cat = geo_out.get("exposure_category", "UNKNOWN")
        exposure_summary = (
            f"Exposure Category: {exposure_cat}. Total features within radius: {tot_features} "
            f"(Critical Infrastructure: {crit_count}, Residential: {res_count})."
        )

    # 5. Recommendations Summary
    recommendations_summary: List[str] = []
    if plan_out and plan_out.get("recommendations"):
        for rec in plan_out["recommendations"]:
            title = rec.get("title", "Advisory Action")
            prio = rec.get("priority", "ROUTINE")
            action_type = rec.get("action_type", "advisory")
            recommendations_summary.append(f"[{prio}] {title} (Type: {action_type})")
    elif plan_out:
        overall = plan_out.get("overall_plan_status", "unknown")
        recommendations_summary.append(f"No specific action recommendations generated. Plan status: {overall}.")
    else:
        recommendations_summary.append("Response plan not generated or unavailable.")

    # 6. Human Decisions Required
    human_decisions_required: List[str] = []
    if approval_state:
        appr_status = approval_state.get("approval_status", "pending")
        requires_appr = approval_state.get("requires_approval", True)
        if requires_appr and appr_status == HumanApprovalStatus.PENDING.value:
            human_decisions_required.append(
                "Human incident commander review and authorization of the advisory response plan is required (Status: PENDING)."
            )
        elif appr_status == HumanApprovalStatus.NEEDS_REVISION.value:
            human_decisions_required.append(
                "Response plan requires revision based on incident commander operational feedback."
            )
        elif appr_status == HumanApprovalStatus.REJECTED.value:
            human_decisions_required.append(
                "Response plan was rejected by incident commander; alternative response strategy required."
            )
    else:
        human_decisions_required.append("Human approval gate not reached or uninitialized.")

    if plan_out and plan_out.get("operational_limitations"):
        for lim in plan_out["operational_limitations"]:
            human_decisions_required.append(f"Operational constraint to resolve: {lim}")

    # 7. Unresolved Uncertainties
    unresolved_uncertainties: List[str] = []
    if risk_out:
        for item in risk_out.get("conflicting_evidence", []):
            unresolved_uncertainties.append(f"Conflicting Evidence: {item}")
        for item in risk_out.get("missing_evidence", []):
            unresolved_uncertainties.append(f"Missing Evidence: {item}")

    if plan_out:
        for item in plan_out.get("responder_information_gaps", []):
            unresolved_uncertainties.append(f"Information Gap: {item}")
        for item in plan_out.get("missing_information", []):
            unresolved_uncertainties.append(f"Missing Information: {item}")

    # 8. Executive Summary
    executive_summary = (
        f"SCOUT Coordinator Report for {disaster_type.upper()} incident at ({lat:.4f}, {lon:.4f}). "
        f"Incident Status: {incident_status} (Severity: {incident_severity or 'N/A'}). "
        f"Composite Threat: {composite_threat_level}. {weather_summary} {exposure_summary} "
        f"Total Recommended Actions: {len(recommendations_summary)}. "
        f"Human Review: {'PENDING' if approval_state and approval_state.get('approval_status') == 'pending' else 'RESOLVED'}."
    )

    # 9. Audit Trail
    agent_names_executed = [rec.get("agent_name") for rec in execution_records if isinstance(rec, dict)]
    audit_trail: Dict[str, Any] = {
        "workflow_id": workflow_id,
        "request_id": request_id,
        "disaster_type": disaster_type,
        "coordinates": {"latitude": lat, "longitude": lon},
        "agents_executed": agent_names_executed,
        "total_execution_records": len(execution_records),
        "total_errors": len(errors),
        "total_warnings": len(warnings),
        "provenance_origin": state.get("provenance", {}).get("origin", "disaster_workflow_request"),
        "has_human_review_gate": approval_state is not None,
    }

    report = CoordinatorReportOutput(
        report_id=f"rep-{uuid4().hex[:12]}",
        executive_summary=executive_summary,
        incident_status=incident_status,
        incident_severity=incident_severity,
        composite_threat_level=composite_threat_level,
        weather_summary=weather_summary,
        exposure_summary=exposure_summary,
        recommendations_summary=recommendations_summary,
        human_decisions_required=human_decisions_required,
        unresolved_uncertainties=unresolved_uncertainties,
        audit_trail=audit_trail,
        generated_at=datetime.now(timezone.utc),
    )

    end_time = datetime.now(timezone.utc)
    duration = (end_time - start_time).total_seconds()
    now_iso = end_time.isoformat()

    # Determine final lifecycle status and stage
    if has_errors:
        final_status = WorkflowStatus.FAILED.value
        final_stage = WorkflowStage.TERMINATED_WITH_ERROR.value
    elif approval_state and approval_state.get("approval_status") == HumanApprovalStatus.PENDING.value:
        final_status = WorkflowStatus.SUSPENDED_FOR_APPROVAL.value
        final_stage = WorkflowStage.COORDINATOR_REPORT.value
    else:
        final_status = WorkflowStatus.COMPLETED.value
        final_stage = WorkflowStage.COMPLETED.value

    rec = AgentExecutionRecord(
        agent_name="coordinator_agent",
        stage=WorkflowStage.COORDINATOR_REPORT.value,
        status="failed" if has_errors else "success",
        start_time=start_time,
        end_time=end_time,
        duration_seconds=round(duration, 4),
        details=(
            f"Coordinator synthesis completed: ReportID='{report.report_id}', "
            f"IncidentStatus='{incident_status}', Threat='{composite_threat_level}', "
            f"FinalStatus='{final_status}'."
        ),
    ).model_dump(mode="json")

    return {
        "status": final_status,
        "stage": final_stage,
        "coordinator_report": report.model_dump(mode="json"),
        "execution_records": [rec],
        "errors": [],
        "warnings": [],
        "updated_at": now_iso,
        "completed_at": now_iso if final_status == WorkflowStatus.COMPLETED.value else None,
    }
