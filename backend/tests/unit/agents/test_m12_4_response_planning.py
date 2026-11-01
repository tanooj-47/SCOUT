"""
backend/tests/unit/agents/test_m12_4_response_planning.py
Comprehensive unit and integration test suite for Milestone 12.4:
Response Planning Agent & Human Approval Gate.
Verifies all 7 deterministic planning cases (A-G), strict decision-support advisory rules,
human approval lifecycle transitions, and end-to-end LangGraph execution.
"""

from datetime import datetime, timezone
import json
from typing import Any, Dict, List, Optional
from unittest.mock import patch
import pytest

from app.agents.graph import (
    compile_workflow_graph,
    create_disaster_workflow_graph,
)
from app.agents.nodes.human_approval import (
    apply_human_approval_decision,
    human_review_gate_node,
)
from app.agents.nodes.response_planning import response_planning_agent_node
from app.agents.schemas import (
    ActionRecommendation,
    DisasterResponseWorkflowRequest,
    GeospatialAgentOutput,
    HumanApprovalState,
    HumanApprovalStatus,
    IntelligenceAgentOutput,
    RecommendationPriority,
    ResponsePlanningAgentOutput,
    RiskAssessmentAgentOutput,
    RiskAssessmentStatus,
    WeatherAgentOutput,
    WorkflowError,
    WorkflowExecutionResult,
    WorkflowStage,
    WorkflowStatus,
)
from app.agents.services.workflow_service import DisasterWorkflowService
from app.agents.state import (
    DisasterWorkflowState,
    deserialize_workflow_state,
    initialize_workflow_state,
    serialize_workflow_state,
)
from app.intelligence.schemas import (
    ContextSummary,
    CoordinateLocation,
    DisasterAssessmentLevel,
    EvidenceCategory,
    EvidenceItem,
    EvidenceQuality,
    EvidenceStatus,
    ExposureAssessment,
    HazardAssessment,
    IncidentEvidenceState,
    IncidentStatus,
    MultimodalIntelligenceAssessment,
)
from app.schemas.incident import DisasterType


# ---------------------------------------------------------------------------
# Test Fixtures & Builders
# ---------------------------------------------------------------------------

def _build_test_state(
    risk_output: Optional[Dict[str, Any]] = None,
    intel_output: Optional[Dict[str, Any]] = None,
    weather_output: Optional[Dict[str, Any]] = None,
    geospatial_output: Optional[Dict[str, Any]] = None,
    status: str = WorkflowStatus.RUNNING.value,
    stage: str = WorkflowStage.RISK_ASSESSMENT.value,
    errors: Optional[List[Dict[str, Any]]] = None,
    warnings: Optional[List[str]] = None,
) -> DisasterWorkflowState:
    """Builds a DisasterWorkflowState ready for Response Planning Agent execution."""
    req = DisasterResponseWorkflowRequest(
        latitude=30.3256,
        longitude=78.0422,
        disaster_type=DisasterType.WILDFIRE,
        search_radius_meters=5000.0,
    )
    state = initialize_workflow_state(req, workflow_id="wf-test-planning-m12-4")
    state["status"] = status
    state["stage"] = stage
    state["risk_assessment_output"] = risk_output
    state["intelligence_output"] = intel_output
    state["weather_output"] = weather_output
    state["geospatial_output"] = geospatial_output
    if errors:
        state["errors"] = errors
    if warnings:
        state["warnings"] = warnings
    return state


def _build_risk_output(
    incident_status: str = "CONFIRMED",
    overall_threat_level: str = "CRITICAL_EMERGENCY",
    assessment_status: str = "complete",
    evidence_conflict: bool = False,
    key_risk_drivers: Optional[List[str]] = None,
    mitigating_factors: Optional[List[str]] = None,
    geographic_exposure_status: str = "VERIFIED_HIGH",
    potential_consequences_status: str = "POTENTIAL_IMPACT",
) -> Dict[str, Any]:
    return RiskAssessmentAgentOutput(
        assessment_status=assessment_status,
        incident_status=incident_status,
        incident_severity="HIGH" if incident_status == "CONFIRMED" else None,
        fire_weather_danger="HIGH",
        geographic_exposure_status=geographic_exposure_status,
        potential_consequences_status=potential_consequences_status,
        overall_threat_level=overall_threat_level,
        heuristic_risk_index=85.0 if incident_status == "CONFIRMED" else 45.0,
        hazard_summary="Active fire signatures detected.",
        exposure_summary="Populated settlements present in radius.",
        consequence_summary="Potential structure and life safety exposure.",
        fire_weather_summary="Elevated fire weather indices.",
        supporting_evidence=["Thermal anomaly", "Visual flame signature"],
        missing_evidence=[],
        conflicting_evidence=["Sensor discordance between visual and weather"] if evidence_conflict else [],
        uncertainty_qualification="Assessment grounded in multi-sensor fusion.",
        assessment_rationale="High threat due to active fire near residential structures.",
        key_risk_drivers=key_risk_drivers or ["Proximity to settlements", "Active flame front"],
        mitigating_factors=mitigating_factors or ["Low wind velocity"],
        source_agent_provenance={"intel": "complete", "weather": "complete", "geo": "complete"},
        generated_at=datetime.now(timezone.utc).isoformat(),
    ).model_dump(mode="json")


def _build_intel_output(
    incident_status: str = "CONFIRMED",
    visual_state: str = "DETECTION_CONFIRMED",
    conflicting_streams: Optional[List[str]] = None,
) -> Dict[str, Any]:
    return IntelligenceAgentOutput(
        incident_status=incident_status,
        incident_severity="HIGH" if incident_status == "CONFIRMED" else None,
        active_evidence_state=visual_state,
        visual_evidence_summary="Verified flame signature in optical spectrum",
        conflicting_streams=conflicting_streams or [],
        assessment_id="assess-101",
        provenance={"source": "m11_assessment"},
    ).model_dump(mode="json")


def _build_weather_output(
    fwi: Optional[float] = 32.5,
    danger_rating: str = "VERY_HIGH",
    wind_kmh: float = 24.0,
    missing_parameters: Optional[List[str]] = None,
) -> Dict[str, Any]:
    return WeatherAgentOutput(
        temperature_c=34.0,
        relative_humidity_pct=20.0,
        wind_speed_kmh=wind_kmh,
        precipitation_mm=0.0,
        fwi=fwi,
        danger_rating=danger_rating,
        fire_weather_explanation="High atmospheric fire-weather danger",
        is_experimental=True,
        stale_observations=[],
        missing_parameters=missing_parameters or [],
        observation_timestamp=datetime.now(timezone.utc).isoformat(),
        source="open-meteo",
        provenance={"provider": "open-meteo"},
    ).model_dump(mode="json")


def _build_geo_output(
    settlements: int = 3,
    closest_name: str = "Dehradun Outskirts Sector 5",
    closest_dist: float = 1450.0,
    hospitals: int = 1,
    water_bodies: int = 2,
    is_verified: bool = True,
) -> Dict[str, Any]:
    return GeospatialAgentOutput(
        exposure_level="HIGH" if settlements > 0 else "LOW",
        exposure_score=80.0,
        settlements_within_radius=settlements,
        closest_settlement_distance_meters=closest_dist,
        closest_settlement_name=closest_name,
        hospitals_within_radius=hospitals,
        fire_stations_within_radius=1,
        transport_corridors_count=2,
        water_bodies_count=water_bodies,
        catalog_completeness_notes=["Catalog verified against vector features"],
        is_verified=is_verified,
        data_provider="postgis_vector_catalog",
        provenance={"catalog_version": "v1.4"},
    ).model_dump(mode="json")


def _build_mock_m11_assessment(
    incident_status: IncidentStatus = IncidentStatus.CONFIRMED,
    incident_severity: Optional[DisasterAssessmentLevel] = DisasterAssessmentLevel.HIGH,
    active_evidence: IncidentEvidenceState = IncidentEvidenceState.SUPPORTING_FIRE,
    fire_weather_level: str = "HIGH",
    fire_weather_score: float = 65.0,
    fwi_value: Optional[float] = 22.4,
    exposure_level: str = "MODERATE",
    exposure_score: Optional[float] = 52.0,
    total_geo_features: int = 8,
) -> MultimodalIntelligenceAssessment:
    """Builds a real typed MultimodalIntelligenceAssessment for full workflow testing."""
    loc = CoordinateLocation(latitude=30.3256, longitude=78.0422)

    weather_payload = {
        "temperature_c": 28.5,
        "relative_humidity_pct": 35.0,
        "wind_speed_kmh": 18.0,
        "precipitation_mm": 0.0,
        "fwi_indices": {
            "fire_weather_index_fwi": fwi_value,
            "danger_rating": fire_weather_level,
        },
        "missing_meteorological_variables": [],
        "fwi_methodology": "instantaneous_weather_indicator (experimental_uninitialized_fwi)",
    }

    env_evidence = EvidenceItem(
        category=EvidenceCategory.ENVIRONMENTAL,
        source_name="open-meteo",
        status=EvidenceStatus.VALID,
        raw_value=weather_payload,
        quality=EvidenceQuality(
            is_stale=False,
            age_seconds=300.0,
            has_confidence_measure=False,
            provider_type="reanalysis_model",
        ),
        location=loc,
        observation_timestamp=datetime(2026, 11, 1, 6, 0, tzinfo=timezone.utc),
        provenance={"provider": "open-meteo", "grid_cell": "30.32_78.04"},
    )

    geo_payload = {
        "settlements_found": 3 if total_geo_features > 0 else 0,
        "closest_settlement_distance_meters": 1250.0 if total_geo_features > 0 else None,
        "closest_settlement_name": "Dehradun Outskirts" if total_geo_features > 0 else None,
        "hospitals_found": 1 if total_geo_features > 0 else 0,
        "fire_stations_found": 1 if total_geo_features > 0 else 0,
        "road_corridors_found": 2 if total_geo_features > 0 else 0,
        "water_bodies_found": 1 if total_geo_features > 0 else 0,
        "total_features_evaluated": total_geo_features,
    }

    geo_evidence = EvidenceItem(
        category=EvidenceCategory.GEOSPATIAL_CONTEXT,
        source_name="local_vector_catalog",
        status=EvidenceStatus.VALID,
        raw_value=geo_payload,
        quality=EvidenceQuality(
            is_stale=False,
            has_confidence_measure=False,
            provider_type="vector_catalog",
        ),
        location=loc,
        provenance={"catalog_version": "dehradun_calibration_v1"},
    )

    context_summary = ContextSummary(
        settlements_found=geo_payload["settlements_found"],
        closest_settlement_distance_meters=geo_payload["closest_settlement_distance_meters"],
        closest_settlement_name=geo_payload["closest_settlement_name"],
        hospitals_found=geo_payload["hospitals_found"],
        fire_stations_found=geo_payload["fire_stations_found"],
        road_corridors_found=geo_payload["road_corridors_found"],
        water_bodies_found=geo_payload["water_bodies_found"],
        total_features_evaluated=total_geo_features,
        spatial_coverage_notes=["Calibrated local vector catalog (13 baseline features)"],
    )

    hazard_eval = HazardAssessment(
        hazard_score=72.0,
        hazard_level=DisasterAssessmentLevel.HIGH,
        visual_score=78.0,
        environmental_score=fire_weather_score,
        visual_evidence_state=active_evidence,
        visual_explanation="Visual classification identified active flame features (p_fire=0.78).",
        active_incident_score=78.0,
        active_incident_level=DisasterAssessmentLevel.HIGH,
        active_incident_evidence=active_evidence,
        active_incident_explanation="Visual evidence consistent with wildfire flame front.",
        incident_status=incident_status,
        incident_severity=incident_severity,
        fire_weather_score=fire_weather_score,
        fire_weather_level=fire_weather_level,
        fire_weather_explanation=f"Atmospheric fire-weather danger rated as {fire_weather_level}.",
        factors=["High flame probability", f"Fire weather danger: {fire_weather_level}"],
    )

    exposure_eval = ExposureAssessment(
        exposure_score=exposure_score,
        exposure_level=exposure_level,
        settlement_distance_meters=geo_payload["closest_settlement_distance_meters"],
        factors=["Residential settlement within 2km"],
    )

    return MultimodalIntelligenceAssessment(
        disaster_type="wildfire",
        coordinates=loc,
        assessment_level=DisasterAssessmentLevel.HIGH,
        heuristic_risk_index=68.5,
        assessment_rationale="High threat due to flame features and elevated fire weather.",
        hazard_assessment=hazard_eval,
        exposure_assessment=exposure_eval,
        active_incident_evidence=active_evidence,
        incident_status=incident_status,
        incident_severity=incident_severity,
        fire_weather_danger=fire_weather_level,
        fire_weather_score=fire_weather_score,
        geographic_exposure=exposure_level,
        evidence_summary="Physical: CONFIRMED; Fire Weather: HIGH (FWI=22.4); Exposure: MODERATE",
        evidence_items=[env_evidence, geo_evidence],
        context_summary=context_summary,
        caveats_and_limitations=["Uncalibrated deep learning model; single observation FWI."],
    )


# ===========================================================================
# 1. Confirmed Wildfire Generates Evidence-Grounded Recommendations (Case A)
# ===========================================================================

def test_confirmed_wildfire_generates_evidence_grounded_recommendations():
    """Case A: Confirmed wildfire generates life-safety, containment, structure defense, and water recommendations."""
    risk = _build_risk_output(incident_status="CONFIRMED", overall_threat_level="CRITICAL_EMERGENCY")
    geo = _build_geo_output(settlements=3, closest_name="Sector 5", hospitals=1, water_bodies=2, is_verified=True)
    weather = _build_weather_output(fwi=32.0, wind_kmh=25.0)
    intel = _build_intel_output(incident_status="CONFIRMED")
    state = _build_test_state(risk_output=risk, geospatial_output=geo, weather_output=weather, intel_output=intel)

    result = response_planning_agent_node(state)
    plan = result["response_plan_output"]

    assert plan is not None
    assert plan["overall_plan_status"] == "complete"
    assert plan["incident_status"] == "CONFIRMED"
    assert plan["human_approval_status"] == HumanApprovalStatus.PENDING.value
    assert plan["priority_level"] == "CRITICAL"

    # Verify categories
    categories = [r["category"] for r in plan["recommendations"]]
    assert "LIFE_SAFETY" in categories
    assert "CONTAINMENT" in categories
    assert "STRUCTURE_PROTECTION" in categories
    assert "MONITORING" in categories

    # Verify human authorization is mandated on every action
    for rec in plan["recommendations"]:
        assert rec["requires_human_authorization"] is True
        assert len(rec["suggested_resource_categories"]) > 0
        assert len(rec["preconditions"]) > 0
        assert len(rec["safety_constraints"]) > 0


# ===========================================================================
# 2. Suspected Wildfire Preserves Suspected Status (Case B)
# ===========================================================================

def test_suspected_wildfire_preserves_suspected_status():
    """Case B: Suspected wildfire recommends verification and standby; strictly NO unverified evacuation orders."""
    risk = _build_risk_output(
        incident_status="SUSPECTED",
        overall_threat_level="ELEVATED_WATCH",
        key_risk_drivers=["Suspected smoke plume"],
    )
    intel = _build_intel_output(incident_status="SUSPECTED", visual_state="SUSPECTED_SMOKE")
    geo = _build_geo_output(settlements=2, is_verified=True)
    state = _build_test_state(risk_output=risk, intel_output=intel, geospatial_output=geo)

    result = response_planning_agent_node(state)
    plan = result["response_plan_output"]

    assert plan is not None
    assert plan["incident_status"] == "SUSPECTED"
    assert plan["overall_plan_status"] == "partial"

    # Must contain VERIFICATION and PREPAREDNESS standby
    categories = [r["category"] for r in plan["recommendations"]]
    assert "VERIFICATION" in categories
    assert "PREPAREDNESS" in categories
    assert "LIFE_SAFETY" not in categories  # No premature unverified evacuation orders!

    # Life safety notes emphasize verification before evacuation
    assert any("not issue unverified mandatory evacuation" in n.lower() for n in plan["life_safety_notes"])


# ===========================================================================
# 3. Extreme FWI Without Active Fire Generates Preparedness Recommendations (Case C)
# ===========================================================================

def test_extreme_fwi_without_active_fire_generates_preparedness_recommendations():
    """Case C: Extreme FWI without active fire produces preventative preparedness plan, NOT suppression."""
    risk = _build_risk_output(
        incident_status="NONE",
        overall_threat_level="HIGH_ALERT",
        key_risk_drivers=["Severe atmospheric dryness", "Extreme fire weather FWI"],
    )
    weather = _build_weather_output(fwi=38.0, danger_rating="EXTREME")
    intel = _build_intel_output(incident_status="NONE", visual_state="NOT_DETECTED")
    state = _build_test_state(risk_output=risk, weather_output=weather, intel_output=intel)

    result = response_planning_agent_node(state)
    plan = result["response_plan_output"]

    assert plan is not None
    assert plan["overall_plan_status"] == "preparedness_only"

    # Recommendations must focus on ignition bans, pre-positioning, and lookout surveillance
    titles = [r["title"] for r in plan["recommendations"]]
    assert any("Red Flag" in t or "Ignition Bans" in t for t in titles)
    assert any("Pre-position" in t for t in titles)
    assert any("Lookout" in t or "Patrol" in t for t in titles)

    # Life safety notes explicitly clarify absence of active wildfire
    assert any("no active wildfire confirmed" in n.lower() for n in plan["life_safety_notes"])


# ===========================================================================
# 4. Unverified Geographic Context Does Not Invent Assets (Case D)
# ===========================================================================

def test_unverified_geographic_context_does_not_invent_assets():
    """Case D: Confirmed incident with unverified geospatial layer generates GIS ground-truthing and zero invented assets."""
    risk = _build_risk_output(incident_status="CONFIRMED", overall_threat_level="CRITICAL_EMERGENCY")
    geo = _build_geo_output(settlements=0, is_verified=False)
    geo["exposure_level"] = "UNVERIFIED"
    state = _build_test_state(risk_output=risk, geospatial_output=geo)

    result = response_planning_agent_node(state)
    plan = result["response_plan_output"]

    assert plan is not None
    assert plan["overall_plan_status"] == "partial"

    # Must include rapid GIS ground-truthing recommendation
    categories = [r["category"] for r in plan["recommendations"]]
    assert "VERIFICATION" in categories
    titles = [r["title"] for r in plan["recommendations"]]
    assert any("Rapid Exposure Survey and GIS Ground-Truthing" in t for t in titles)

    # Operational limitations and missing information flag unverified exposure
    assert any("GEOSPATIAL EXPOSURE UNVERIFIED" in lim for lim in plan["operational_limitations"])
    assert any("Verified spatial footprint" in m for m in plan["missing_information"])


# ===========================================================================
# 5. Insufficient Intelligence Produces Limited Recommendations (Case E)
# ===========================================================================

def test_insufficient_intelligence_produces_limited_recommendations():
    """Case E: Insufficient intelligence restricts plan strictly to reconnaissance and enumerates gaps."""
    risk = _build_risk_output(
        incident_status="INSUFFICIENT_EVIDENCE",
        overall_threat_level="ADVISORY_MONITORING",
        assessment_status="insufficient_evidence",
    )
    state = _build_test_state(risk_output=risk, intel_output=None)

    result = response_planning_agent_node(state)
    plan = result["response_plan_output"]

    assert plan is not None
    assert plan["overall_plan_status"] == "insufficient_evidence"
    assert len(plan["recommendations"]) == 1
    assert plan["recommendations"][0]["category"] == "VERIFICATION"

    # Intelligence gaps enumerated
    assert len(plan["missing_information"]) >= 2
    assert len(plan["responder_information_gaps"]) >= 2
    assert any("strictly restricted to reconnaissance" in lim for lim in plan["operational_limitations"])


# ===========================================================================
# 6. Missing Weather Handled Explicitly (Case F)
# ===========================================================================

def test_missing_weather_handled_explicitly():
    """Case F: Missing weather intelligence omits wind/spread-dependent tactics and recommends IMET spot forecast."""
    risk = _build_risk_output(incident_status="CONFIRMED")
    geo = _build_geo_output(settlements=2, is_verified=True)
    state = _build_test_state(risk_output=risk, geospatial_output=geo, weather_output=None)

    result = response_planning_agent_node(state)
    plan = result["response_plan_output"]

    assert plan is not None
    assert any("WEATHER DATA DEFICIT" in lim for lim in plan["operational_limitations"])
    assert any("Real-time on-site wind speed" in m for m in plan["missing_information"])

    # Must recommend IMET spot forecast / portable weather station
    titles = [r["title"] for r in plan["recommendations"]]
    assert any("Spot Forecast" in t or "Portable Weather Station" in t for t in titles)


# ===========================================================================
# 7. Conflicting Evidence Reduces Certainty and Triggers Verification (Case G)
# ===========================================================================

def test_conflicting_evidence_reduces_certainty_and_triggers_verification():
    """Case G: Contradictory evidence triggers CRITICAL conflict resolution verification and reduces confidence."""
    risk = _build_risk_output(
        incident_status="SUSPECTED",
        evidence_conflict=True,
    )
    state = _build_test_state(risk_output=risk)

    result = response_planning_agent_node(state)
    plan = result["response_plan_output"]

    assert plan is not None
    assert plan["priority_level"] == "CRITICAL"
    assert plan["overall_plan_status"] == "partial"

    # Must contain conflict verification recommendation
    conflict_recs = [r for r in plan["recommendations"] if "Resolve Intelligence Conflict" in r["title"]]
    assert len(conflict_recs) == 1
    assert conflict_recs[0]["priority"] == "critical"
    assert "LOW" in conflict_recs[0]["confidence_description"]

    # Prominently noted in operational limitations and life safety
    assert any("CRITICAL EVIDENCE CONFLICT DETECTED" in lim for lim in plan["operational_limitations"])
    assert any("ALERT: Conflicting intelligence evidence" in note for note in plan["life_safety_notes"])


# ===========================================================================
# 8. Recommendations Include Evidence References
# ===========================================================================

def test_recommendations_include_evidence_references():
    """All action recommendations contain auditable references back to upstream agents."""
    risk = _build_risk_output(incident_status="CONFIRMED")
    geo = _build_geo_output(settlements=2, is_verified=True)
    weather = _build_weather_output(fwi=28.0)
    state = _build_test_state(risk_output=risk, geospatial_output=geo, weather_output=weather)

    result = response_planning_agent_node(state)
    plan = result["response_plan_output"]

    assert len(plan["recommendations"]) >= 3
    for rec in plan["recommendations"]:
        assert len(rec["evidence_references"]) >= 1
        assert any(
            ref.startswith("risk_assessment_agent:")
            or ref.startswith("weather_agent:")
            or ref.startswith("geospatial_agent:")
            or ref.startswith("intelligence_agent:")
            for ref in rec["evidence_references"]
        )


# ===========================================================================
# 9. Resource Categories Do Not Imply Actual Inventory
# ===========================================================================

def test_resource_categories_do_not_imply_actual_inventory():
    """Suggested resource categories describe generic equipment types, not real-time inventory."""
    risk = _build_risk_output(incident_status="CONFIRMED")
    geo = _build_geo_output(settlements=2, hospitals=1, is_verified=True)
    state = _build_test_state(risk_output=risk, geospatial_output=geo)

    result = response_planning_agent_node(state)
    plan = result["response_plan_output"]

    categories = plan["suggested_resource_categories"]
    assert len(categories) > 0

    # Ensure no fabricated station names or personnel rosters
    for cat in categories:
        assert isinstance(cat, str)
        assert "Station " not in cat
        assert "Unit #" not in cat
        assert "Crew #" not in cat


# ===========================================================================
# 10. Safety Constraints Are Preserved
# ===========================================================================

def test_safety_constraints_are_preserved():
    """Safety precautions and recommendation constraints enforce LCES, escape routes, and defensible space rules."""
    risk = _build_risk_output(incident_status="CONFIRMED")
    state = _build_test_state(risk_output=risk)

    result = response_planning_agent_node(state)
    plan = result["response_plan_output"]

    # Global safety precautions
    assert any("LCES" in p for p in plan["safety_precautions"])
    assert any("Standard Firefighting Orders" in p for p in plan["safety_precautions"])

    # Specific tactical recommendation constraints
    for rec in plan["recommendations"]:
        assert len(rec["safety_constraints"]) >= 1


# ===========================================================================
# 11. Unsupported Recommendations Are Not Generated
# ===========================================================================

def test_unsupported_recommendations_are_not_generated():
    """No autonomous 911 calls, physical system commands, or unreviewed actions are generated."""
    risk = _build_risk_output(incident_status="CONFIRMED")
    state = _build_test_state(risk_output=risk)

    result = response_planning_agent_node(state)
    plan = result["response_plan_output"]

    for rec in plan["recommendations"]:
        assert rec["requires_human_authorization"] is True
        assert "dispatch_emergency_vehicle" not in rec["title"].lower()
        assert "activate_sprinklers" not in rec["title"].lower()
        assert "call_911" not in rec["title"].lower()


# ===========================================================================
# 12. Response Plan Is Initially PENDING
# ===========================================================================

def test_response_plan_is_initially_pending():
    """Response planning agent output is strictly initialized with human_approval_status='pending'."""
    risk = _build_risk_output(incident_status="CONFIRMED")
    state = _build_test_state(risk_output=risk)

    result = response_planning_agent_node(state)
    plan = result["response_plan_output"]

    assert plan["human_approval_status"] == HumanApprovalStatus.PENDING.value


# ===========================================================================
# 13. Approval Cannot Be Assumed
# ===========================================================================

def test_approval_cannot_be_assumed():
    """The workflow stops at human_review_gate with status SUSPENDED_FOR_APPROVAL and approval PENDING."""
    risk = _build_risk_output(incident_status="CONFIRMED")
    state = _build_test_state(risk_output=risk)

    plan_state = response_planning_agent_node(state)
    state.update(plan_state)

    gate_result = human_review_gate_node(state)

    assert gate_result["status"] == WorkflowStatus.SUSPENDED_FOR_APPROVAL.value
    assert gate_result["stage"] == WorkflowStage.HUMAN_REVIEW_GATE.value
    assert gate_result["human_approval"]["approval_status"] == HumanApprovalStatus.PENDING.value
    assert gate_result["human_approval"]["requires_approval"] is True


# ===========================================================================
# 14. Rejection Remains Explicit
# ===========================================================================

def test_rejection_remains_explicit():
    """Human reviewer explicitly rejects a pending response plan with required justification."""
    approval = HumanApprovalState(plan_id="plan-test-1", approval_status=HumanApprovalStatus.PENDING).model_dump(mode="json")

    # Missing reason raises ValueError
    with pytest.raises(ValueError, match="reason is required"):
        apply_human_approval_decision(
            approval_state=approval,
            decision_status=HumanApprovalStatus.REJECTED,
            reviewer_id="chief-01",
            rejection_or_revision_reason="",
        )

    # Valid rejection
    updated = apply_human_approval_decision(
        approval_state=approval,
        decision_status=HumanApprovalStatus.REJECTED,
        reviewer_id="chief-01",
        rejection_or_revision_reason="Weather shift makes flank containment untenable.",
    )
    assert updated["approval_status"] == HumanApprovalStatus.REJECTED.value
    assert updated["reviewer_id"] == "chief-01"
    assert updated["rejection_or_revision_reason"] == "Weather shift makes flank containment untenable."


# ===========================================================================
# 15. Revision Requests Remain Explicit
# ===========================================================================

def test_revision_requests_remain_explicit():
    """Human reviewer requests revision with required operational notes."""
    approval = HumanApprovalState(plan_id="plan-test-2", approval_status=HumanApprovalStatus.PENDING).model_dump(mode="json")

    with pytest.raises(ValueError, match="reason is required"):
        apply_human_approval_decision(
            approval_state=approval,
            decision_status=HumanApprovalStatus.NEEDS_REVISION,
            reviewer_id="chief-02",
            rejection_or_revision_reason=None,
        )

    updated = apply_human_approval_decision(
        approval_state=approval,
        decision_status=HumanApprovalStatus.NEEDS_REVISION,
        reviewer_id="chief-02",
        reviewer_comments="Please request spot weather forecast before setting staging area.",
        rejection_or_revision_reason="Need real-time spot weather verification.",
    )
    assert updated["approval_status"] == HumanApprovalStatus.NEEDS_REVISION.value
    assert updated["reviewer_comments"] == "Please request spot weather forecast before setting staging area."


# ===========================================================================
# 16. Missing Risk Assessment Prevents Fabricated Planning
# ===========================================================================

def test_missing_risk_assessment_prevents_fabricated_planning():
    """When risk_assessment_output is absent, planning agent halts safely without fabricating plan."""
    state = _build_test_state(risk_output=None)

    result = response_planning_agent_node(state)

    assert result["status"] == WorkflowStatus.FAILED.value
    assert result["stage"] == WorkflowStage.TERMINATED_WITH_ERROR.value
    assert result["response_plan_output"] is None
    assert len(result["errors"]) == 1
    assert result["errors"][0]["code"] == "MISSING_RISK_ASSESSMENT"


# ===========================================================================
# 17. Workflow Reaches the Human Review Boundary
# ===========================================================================

def test_workflow_reaches_the_human_review_boundary():
    """Full workflow execution runs 7 nodes: validator -> intel -> weather -> geo -> risk -> plan -> gate."""
    mock_assessment = _build_mock_m11_assessment()

    with patch("app.agents.nodes.intelligence.MultimodalIntelligenceService") as mock_svc_cls:
        instance = mock_svc_cls.return_value
        instance.analyze_observation.return_value = mock_assessment

        service = DisasterWorkflowService(include_planning_agent=True, include_coordinator=False)
        req = DisasterResponseWorkflowRequest(
            latitude=30.3256,
            longitude=78.0422,
            disaster_type=DisasterType.WILDFIRE,
            search_radius_meters=5000.0,
        )

        result: WorkflowExecutionResult = service.run_workflow(req, workflow_id="wf-test-7-nodes")

        # Must halt at human review gate in suspended status
        assert result.status == WorkflowStatus.SUSPENDED_FOR_APPROVAL
        assert result.stage == WorkflowStage.HUMAN_REVIEW_GATE
        assert len(result.errors) == 0

        # Exactly 7 execution records in sequence
        assert len(result.execution_records) == 7
        agent_names = [r.agent_name for r in result.execution_records]
        assert agent_names == [
            "request_validator",
            "intelligence_agent",
            "weather_agent",
            "geospatial_agent",
            "risk_assessment_agent",
            "response_planning_agent",
            "human_review_gate",
        ]

        # Plan and approval both present and pending
        assert result.response_plan_output is not None
        assert result.human_approval is not None
        assert result.human_approval.approval_status == HumanApprovalStatus.PENDING

        # Test applying approval via workflow service
        approved_result = service.apply_human_approval(
            workflow_result=result,
            decision_status=HumanApprovalStatus.APPROVED,
            reviewer_id="commander-101",
            reviewer_comments="Plan approved for execution.",
        )
        assert approved_result.status == WorkflowStatus.COMPLETED
        assert approved_result.human_approval.approval_status == HumanApprovalStatus.APPROVED
        assert approved_result.response_plan_output.human_approval_status == "approved"


# ===========================================================================
# 18. Pending Approval Is Serialized Correctly
# ===========================================================================

def test_pending_approval_is_serialized_correctly():
    """Final workflow state with response plan and approval gate is 100% JSON serializable and deserializable."""
    mock_assessment = _build_mock_m11_assessment()

    with patch("app.agents.nodes.intelligence.MultimodalIntelligenceService") as mock_svc_cls:
        instance = mock_svc_cls.return_value
        instance.analyze_observation.return_value = mock_assessment

        service = DisasterWorkflowService(include_planning_agent=True, include_coordinator=False)
        req = DisasterResponseWorkflowRequest(
            latitude=30.3256,
            longitude=78.0422,
            disaster_type=DisasterType.WILDFIRE,
        )

        initial_state = initialize_workflow_state(req)
        final_state = service.graph.invoke(initial_state)

        # Full round-trip serialization
        serialized_json = serialize_workflow_state(final_state)
        assert isinstance(serialized_json, str)
        parsed = json.loads(serialized_json)

        assert "response_plan_output" in parsed
        assert "human_approval" in parsed
        assert parsed["human_approval"]["approval_status"] == "pending"

        deserialized = deserialize_workflow_state(serialized_json)
        assert deserialized["workflow_id"] == final_state["workflow_id"]
        assert deserialized["human_approval"]["plan_id"] == final_state["human_approval"]["plan_id"]


# ===========================================================================
# 19. Existing M12.1, M12.2 and M12.3 Tests Remain Valid
# ===========================================================================

def test_existing_m12_1_m12_2_and_m12_3_boundaries_remain_valid():
    """Verify that graph compiles and functions across all milestone sub-graph boundaries."""
    # M12.1 validation-only graph
    g1 = compile_workflow_graph(include_agents=False)
    assert g1 is not None

    # M12.2 perception-only graph
    g2 = compile_workflow_graph(include_agents=True, include_risk_agent=False)
    assert g2 is not None

    # M12.3 risk-only graph
    g3 = compile_workflow_graph(include_agents=True, include_risk_agent=True, include_planning_agent=False)
    assert g3 is not None

    # M12.4 full planning & approval graph
    g4 = compile_workflow_graph(include_agents=True, include_risk_agent=True, include_planning_agent=True, include_coordinator=False)
    assert g4 is not None

    # M12.5 full coordinator graph
    g5 = compile_workflow_graph(include_agents=True, include_risk_agent=True, include_planning_agent=True, include_coordinator=True)
    assert g5 is not None


# ===========================================================================
# 20. Execution Records, Errors, and Warnings Remain Correct
# ===========================================================================

def test_execution_records_errors_and_warnings_remain_correct():
    """Auditable execution records, errors, and warnings accumulate correctly through Agent 5 and Gate."""
    mock_assessment = _build_mock_m11_assessment()

    with patch("app.agents.nodes.intelligence.MultimodalIntelligenceService") as mock_svc_cls:
        instance = mock_svc_cls.return_value
        instance.analyze_observation.return_value = mock_assessment

        service = DisasterWorkflowService(include_planning_agent=True, include_coordinator=False)
        req = DisasterResponseWorkflowRequest(
            latitude=30.3256,
            longitude=78.0422,
            disaster_type=DisasterType.WILDFIRE,
        )

        result: WorkflowExecutionResult = service.run_workflow(req)

        planning_rec = next(r for r in result.execution_records if r.agent_name == "response_planning_agent")
        gate_rec = next(r for r in result.execution_records if r.agent_name == "human_review_gate")

        assert planning_rec.status == "success"
        assert planning_rec.duration_seconds >= 0.0
        assert "ApprovalStatus=PENDING" in planning_rec.details

        assert gate_rec.status == "success"
        assert gate_rec.duration_seconds >= 0.0
        assert "SuspendedForApproval=True" in gate_rec.details
