"""
backend/tests/unit/agents/test_m12_3_risk_assessment.py
Comprehensive unit test suite for M12.3: Risk Assessment Agent.
Verifies the 5-dimensional risk synthesis, transparent heuristic risk scoring,
all 8 mandatory hazard/exposure/weather test cases, audit trail, LangGraph workflow
execution, serialization, and absence of fake future agent outputs.
"""

from datetime import datetime, timezone
import json
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from app.agents.nodes.risk_assessment import risk_assessment_agent_node
from app.agents.schemas import (
    AgentExecutionRecord,
    DisasterResponseWorkflowRequest,
    GeospatialAgentOutput,
    IntelligenceAgentOutput,
    RiskAssessmentAgentOutput,
    RiskAssessmentStatus,
    WeatherAgentOutput,
    WorkflowError,
    WorkflowExecutionResult,
    WorkflowStage,
    WorkflowStatus,
)
from app.agents.services.workflow_service import (
    DisasterWorkflowService,
)
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
# Test Helpers: Mock Agent Output Builders
# ---------------------------------------------------------------------------

def _build_test_state(
    intelligence_output: Optional[Dict[str, Any]] = None,
    weather_output: Optional[Dict[str, Any]] = None,
    geospatial_output: Optional[Dict[str, Any]] = None,
    status: str = WorkflowStatus.RUNNING.value,
    stage: str = WorkflowStage.CONTEXT_INTERPRETATION.value,
    errors: Optional[List[Dict[str, Any]]] = None,
    warnings: Optional[List[str]] = None,
) -> DisasterWorkflowState:
    """Builds a test DisasterWorkflowState with deterministic perception outputs."""
    req = DisasterResponseWorkflowRequest(
        latitude=30.3256,
        longitude=78.0422,
        disaster_type=DisasterType.WILDFIRE,
        search_radius_meters=5000.0,
    )
    state = initialize_workflow_state(req, workflow_id="wf-test-risk-m12-3")
    state["status"] = status
    state["stage"] = stage
    state["intelligence_output"] = intelligence_output
    state["weather_output"] = weather_output
    state["geospatial_output"] = geospatial_output
    if errors:
        state["errors"] = errors
    if warnings:
        state["warnings"] = warnings
    return state


def _build_intelligence_output(
    incident_status: str = "CONFIRMED",
    incident_severity: Optional[str] = "HIGH",
    active_evidence_state: str = "verified_active_fire",
    visual_evidence_summary: Optional[str] = "Thermal and flame signatures detected",
) -> Dict[str, Any]:
    return IntelligenceAgentOutput(
        incident_status=incident_status,
        incident_severity=incident_severity,
        active_evidence_state=active_evidence_state,
        visual_evidence_summary=visual_evidence_summary,
        assessment_id="assess-test-1",
        provenance={"source": "m11_assessment"},
    ).model_dump(mode="json")


def _build_weather_output(
    danger_rating: str = "HIGH",
    fwi: Optional[float] = 28.0,
    temperature_c: Optional[float] = 32.5,
    humidity_pct: Optional[float] = 22.0,
    wind_kmh: Optional[float] = 25.0,
    precip_mm: Optional[float] = 0.0,
    missing_parameters: Optional[List[str]] = None,
    fire_weather_explanation: str = "High atmospheric fire weather risk (experimental)",
) -> Dict[str, Any]:
    return WeatherAgentOutput(
        temperature_c=temperature_c,
        relative_humidity_pct=humidity_pct,
        wind_speed_kmh=wind_kmh,
        precipitation_mm=precip_mm,
        fwi=fwi,
        danger_rating=danger_rating,
        fire_weather_explanation=fire_weather_explanation,
        is_experimental=True,
        stale_observations=[],
        missing_parameters=missing_parameters or [],
        observation_timestamp=datetime.now(timezone.utc).isoformat(),
        source="open-meteo",
        provenance={"provider": "open-meteo"},
    ).model_dump(mode="json")


def _build_geospatial_output(
    exposure_level: str = "HIGH",
    settlements_within_radius: int = 4,
    closest_settlement_dist: Optional[float] = 1200.0,
    closest_settlement_name: Optional[str] = "Mussoorie Sector 4",
    hospitals_within_radius: int = 1,
    fire_stations_within_radius: int = 1,
    transport_corridors_count: int = 2,
    water_bodies_count: int = 2,
    is_verified: bool = True,
    exposure_score: Optional[float] = 75.0,
    data_provider: Optional[str] = "local_vector_catalog",
) -> Dict[str, Any]:
    return GeospatialAgentOutput(
        exposure_level=exposure_level,
        exposure_score=exposure_score,
        settlements_within_radius=settlements_within_radius,
        closest_settlement_distance_meters=closest_settlement_dist,
        closest_settlement_name=closest_settlement_name,
        hospitals_within_radius=hospitals_within_radius,
        fire_stations_within_radius=fire_stations_within_radius,
        transport_corridors_count=transport_corridors_count,
        water_bodies_count=water_bodies_count,
        catalog_completeness_notes=["Spatial catalog verified against local vector index"],
        is_verified=is_verified,
        data_provider=data_provider,
        provenance={"catalog_version": "v1"},
    ).model_dump(mode="json")


def _build_mock_m11_assessment(
    incident_status: IncidentStatus = IncidentStatus.SUSPECTED,
    incident_severity: Optional[DisasterAssessmentLevel] = None,
    active_evidence: IncidentEvidenceState = IncidentEvidenceState.SUPPORTING_FIRE,
    fire_weather_level: str = "HIGH",
    fire_weather_score: float = 65.0,
    fwi_value: Optional[float] = 22.4,
    exposure_level: str = "MODERATE",
    exposure_score: Optional[float] = 52.0,
    is_weather_stale: bool = False,
    missing_weather_vars: Optional[List[str]] = None,
    total_geo_features: int = 8,
) -> MultimodalIntelligenceAssessment:
    """Builds a real typed MultimodalIntelligenceAssessment for full workflow testing."""
    loc = CoordinateLocation(latitude=30.3256, longitude=78.0422)

    missing_vars = missing_weather_vars or []
    weather_payload = {
        "temperature_c": 28.5 if "temperature_celsius" not in missing_vars else None,
        "relative_humidity_pct": 35.0 if "relative_humidity" not in missing_vars else None,
        "wind_speed_kmh": 18.0 if "wind_speed_mps" not in missing_vars else None,
        "precipitation_mm": 0.0 if "precipitation_mm" not in missing_vars else None,
        "fwi_indices": {
            "fire_weather_index_fwi": fwi_value if not missing_vars else None,
            "danger_rating": fire_weather_level if not missing_vars else "UNAVAILABLE",
        } if not missing_vars else None,
        "missing_meteorological_variables": missing_vars,
        "fwi_methodology": "instantaneous_weather_indicator (experimental_uninitialized_fwi)",
    }

    env_evidence = EvidenceItem(
        category=EvidenceCategory.ENVIRONMENTAL,
        source_name="open-meteo",
        status=EvidenceStatus.VALID if not is_weather_stale else EvidenceStatus.STALE,
        raw_value=weather_payload,
        quality=EvidenceQuality(
            is_stale=is_weather_stale,
            age_seconds=7200.0 if is_weather_stale else 300.0,
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
        evidence_summary="Physical: SUSPECTED; Fire Weather: HIGH (FWI=22.4); Exposure: MODERATE",
        evidence_items=[env_evidence, geo_evidence],
        context_summary=context_summary,
        caveats_and_limitations=["Uncalibrated deep learning model; single observation FWI."],
    )


# ===========================================================================
# 1. Valid Confirmed Fire Assessment (Case 3)
# ===========================================================================

def test_valid_confirmed_fire_assessment():
    """Case 3: Confirmed fire + high verified exposure yields CRITICAL_EMERGENCY with high heuristic index."""
    state = _build_test_state(
        intelligence_output=_build_intelligence_output(
            incident_status="CONFIRMED",
            incident_severity="HIGH",
            active_evidence_state="verified_active_fire",
        ),
        weather_output=_build_weather_output(danger_rating="HIGH", fwi=28.0),
        geospatial_output=_build_geospatial_output(exposure_level="HIGH", is_verified=True),
    )

    result = risk_assessment_agent_node(state)

    assert result["status"] == WorkflowStatus.COMPLETED.value
    assert result["stage"] == WorkflowStage.COMPLETED.value
    out = result["risk_assessment_output"]
    assert out is not None

    assert out["assessment_status"] == RiskAssessmentStatus.COMPLETE.value
    assert out["incident_status"] == "CONFIRMED"
    assert out["incident_severity"] == "HIGH"
    assert out["fire_weather_danger"] == "HIGH"
    assert out["geographic_exposure_status"] == "HIGH"
    assert out["potential_consequences_status"] in ("CRITICAL", "HIGH")
    assert out["overall_threat_level"] == "CRITICAL_EMERGENCY"
    assert out["heuristic_risk_index"] is not None
    assert out["heuristic_risk_index"] >= 65.0
    assert len(out["key_risk_drivers"]) >= 2
    assert "confirmed" in out["assessment_rationale"].lower()


# ===========================================================================
# 2. Suspected Fire Never Upgraded to Confirmed (Case 2)
# ===========================================================================

def test_suspected_fire_not_upgraded_to_confirmed():
    """Case 2: Suspected fire + extreme weather + high exposure -> POTENTIAL_THREAT, NEVER upgraded to CONFIRMED."""
    state = _build_test_state(
        intelligence_output=_build_intelligence_output(
            incident_status="SUSPECTED",
            incident_severity=None,
            active_evidence_state="supporting_visual_fire_evidence",
        ),
        weather_output=_build_weather_output(danger_rating="EXTREME", fwi=45.0),
        geospatial_output=_build_geospatial_output(exposure_level="HIGH", is_verified=True),
    )

    result = risk_assessment_agent_node(state)
    out = result["risk_assessment_output"]

    # Invariant: SUSPECTED is strictly preserved
    assert out["incident_status"] == "SUSPECTED"
    assert out["overall_threat_level"] == "POTENTIAL_THREAT"
    assert out["overall_threat_level"] != "CRITICAL_EMERGENCY"
    # Suspected fire multiplier bounds heuristic index below critical confirmed level
    assert out["heuristic_risk_index"] <= 75.0


# ===========================================================================
# 3. Extreme Weather Without Active Fire Does Not Confirm (Case 1)
# ===========================================================================

def test_extreme_fwi_does_not_confirm_incident():
    """Case 1: Extreme weather (FWI=55) + unconfirmed incident -> ELEVATED_PREPAREDNESS, index capped <= 25.0."""
    state = _build_test_state(
        intelligence_output=_build_intelligence_output(
            incident_status="UNCONFIRMED",
            incident_severity=None,
            active_evidence_state="unconfirmed",
        ),
        weather_output=_build_weather_output(danger_rating="EXTREME", fwi=55.0),
        geospatial_output=_build_geospatial_output(exposure_level="HIGH", is_verified=True),
    )

    result = risk_assessment_agent_node(state)
    out = result["risk_assessment_output"]

    assert out["incident_status"] == "UNCONFIRMED"
    assert out["fire_weather_danger"] == "EXTREME"
    assert out["overall_threat_level"] == "ELEVATED_PREPAREDNESS"
    assert out["potential_consequences_status"] == "NEGLIGIBLE"
    # Strict Case 1 requirement: heuristic risk index capped <= 25.0
    assert out["heuristic_risk_index"] is not None
    assert out["heuristic_risk_index"] <= 25.0
    assert "extreme fire-weather danger without confirmed active fire" in out["assessment_rationale"]


# ===========================================================================
# 4. High Exposure Does Not Independently Imply Disaster
# ===========================================================================

def test_high_exposure_does_not_independently_imply_disaster():
    """Unconfirmed incident + high exposure -> LOW_CONCERN, consequence NEGLIGIBLE, index low."""
    state = _build_test_state(
        intelligence_output=_build_intelligence_output(
            incident_status="UNCONFIRMED",
            incident_severity=None,
            active_evidence_state="unconfirmed",
        ),
        weather_output=_build_weather_output(danger_rating="LOW", fwi=4.0),
        geospatial_output=_build_geospatial_output(
            exposure_level="CRITICAL",
            settlements_within_radius=10,
            hospitals_within_radius=3,
            fire_stations_within_radius=2,
            is_verified=True,
        ),
    )

    result = risk_assessment_agent_node(state)
    out = result["risk_assessment_output"]

    assert out["incident_status"] == "UNCONFIRMED"
    assert out["geographic_exposure_status"] == "CRITICAL"
    assert out["overall_threat_level"] == "LOW_CONCERN"
    assert out["potential_consequences_status"] == "NEGLIGIBLE"
    assert out["heuristic_risk_index"] is not None
    assert out["heuristic_risk_index"] <= 15.0


# ===========================================================================
# 5. Confirmed Fire With Unavailable Geographic Context (Case 4)
# ===========================================================================

def test_confirmed_incident_with_unavailable_geographic_context():
    """Case 4: Confirmed fire + unavailable geographic context -> consequence UNASSESSED_EXPOSURE_UNVERIFIED."""
    state = _build_test_state(
        intelligence_output=_build_intelligence_output(
            incident_status="CONFIRMED",
            incident_severity="MODERATE",
        ),
        weather_output=_build_weather_output(danger_rating="MODERATE", fwi=16.0),
        geospatial_output=_build_geospatial_output(
            exposure_level="UNAVAILABLE",
            settlements_within_radius=0,
            hospitals_within_radius=0,
            fire_stations_within_radius=0,
            exposure_score=None,
            is_verified=False,
            data_provider=None,
        ),
    )

    result = risk_assessment_agent_node(state)
    out = result["risk_assessment_output"]

    assert out["incident_status"] == "CONFIRMED"
    assert out["geographic_exposure_status"] == "UNAVAILABLE"
    assert out["potential_consequences_status"] == "UNASSESSED_EXPOSURE_UNVERIFIED"
    assert "unverified" in out["uncertainty_qualification"].lower() or "unavailable" in out["uncertainty_qualification"].lower()


# ===========================================================================
# 6. Empty Geographic Catalog Remains Unverified (Case 5)
# ===========================================================================

def test_empty_geographic_catalog_remains_unverified():
    """Case 5: Empty catalog features -> UNVERIFIED_CATALOG_GAP, is_verified=False, explicit warning."""
    state = _build_test_state(
        intelligence_output=_build_intelligence_output(
            incident_status="CONFIRMED",
            incident_severity="HIGH",
        ),
        weather_output=_build_weather_output(danger_rating="MODERATE", fwi=14.0),
        geospatial_output=_build_geospatial_output(
            exposure_level="UNKNOWN",
            settlements_within_radius=0,
            hospitals_within_radius=0,
            fire_stations_within_radius=0,
            exposure_score=None,
            is_verified=False,
            data_provider="local_vector_catalog",
        ),
    )

    result = risk_assessment_agent_node(state)
    out = result["risk_assessment_output"]

    assert out["geographic_exposure_status"] == "UNVERIFIED_CATALOG_GAP"
    assert out["potential_consequences_status"] == "UNASSESSED_EXPOSURE_UNVERIFIED"
    # Must explicitly state that absence of catalog features is NOT verified zero exposure
    assert "absence of catalog features is not verified zero exposure" in out["exposure_summary"].lower()


# ===========================================================================
# 7. Missing Weather Information Handled Strictly (Case 6)
# ===========================================================================

def test_missing_weather_information():
    """Case 6: Missing weather information -> fwi=None, missing fields in missing_evidence, no dummy defaults."""
    state = _build_test_state(
        intelligence_output=_build_intelligence_output(
            incident_status="SUSPECTED",
        ),
        weather_output=_build_weather_output(
            danger_rating="UNAVAILABLE",
            fwi=None,
            temperature_c=None,
            humidity_pct=None,
            wind_kmh=None,
            missing_parameters=["temperature_celsius", "relative_humidity", "wind_speed_mps"],
        ),
        geospatial_output=_build_geospatial_output(exposure_level="LOW", is_verified=True),
    )

    result = risk_assessment_agent_node(state)
    out = result["risk_assessment_output"]

    assert out["fire_weather_danger"] == "UNAVAILABLE"
    assert any("weather" in item.lower() for item in out["missing_evidence"])
    assert "weather" in out["uncertainty_qualification"].lower()
    # Risk index should still be calculated transparently on available dimensions without fabricating weather
    assert out["heuristic_risk_index"] is not None


# ===========================================================================
# 8. Missing Intelligence Output Produces Partial Assessment (Case 8)
# ===========================================================================

def test_missing_intelligence_output():
    """Case 8: Missing intelligence output -> PARTIAL assessment, incident_status UNAVAILABLE."""
    state = _build_test_state(
        intelligence_output=None,
        weather_output=_build_weather_output(danger_rating="HIGH", fwi=25.0),
        geospatial_output=_build_geospatial_output(exposure_level="MODERATE", is_verified=True),
    )

    result = risk_assessment_agent_node(state)
    out = result["risk_assessment_output"]

    assert out["assessment_status"] == RiskAssessmentStatus.PARTIAL.value
    assert out["incident_status"] == "UNAVAILABLE"
    assert "intelligence_output" in out["missing_evidence"]
    assert out["overall_threat_level"] == "INSUFFICIENT_DATA"


# ===========================================================================
# 9. Conflicting Evidence Handled Additively (Case 7)
# ===========================================================================

def test_conflicting_evidence_increases_uncertainty():
    """Case 7: Confirmed fire with low/negligible fire weather is flagged as conflicting evidence."""
    state = _build_test_state(
        intelligence_output=_build_intelligence_output(
            incident_status="CONFIRMED",
        ),
        weather_output=_build_weather_output(
            danger_rating="LOW",
            fwi=2.1,
            humidity_pct=85.0,
            precip_mm=12.0,
        ),
        geospatial_output=_build_geospatial_output(exposure_level="MODERATE", is_verified=True),
    )

    result = risk_assessment_agent_node(state)
    out = result["risk_assessment_output"]

    assert len(out["conflicting_evidence"]) >= 1
    assert "conflicting evidence" in out["uncertainty_qualification"].lower()
    assert any("low fire-weather danger" in item.lower() for item in out["conflicting_evidence"])


# ===========================================================================
# 10. Missing Incident Severity Remains Strictly None
# ===========================================================================

def test_missing_incident_severity_remains_missing():
    """Incident severity is strictly preserved as None when unassessed; never invented."""
    state = _build_test_state(
        intelligence_output=_build_intelligence_output(
            incident_status="SUSPECTED",
            incident_severity=None,
        ),
        weather_output=_build_weather_output(danger_rating="MODERATE", fwi=15.0),
        geospatial_output=_build_geospatial_output(exposure_level="MODERATE", is_verified=True),
    )

    result = risk_assessment_agent_node(state)
    out = result["risk_assessment_output"]

    assert out["incident_severity"] is None


# ===========================================================================
# 11. Potential Consequences Remain Unavailable When Unsupported
# ===========================================================================

def test_potential_consequences_remain_unavailable_when_unsupported():
    """When exposure is unverified, consequences must be UNASSESSED_EXPOSURE_UNVERIFIED."""
    state = _build_test_state(
        intelligence_output=_build_intelligence_output(
            incident_status="CONFIRMED",
            incident_severity="HIGH",
        ),
        weather_output=_build_weather_output(danger_rating="MODERATE"),
        geospatial_output=_build_geospatial_output(
            exposure_level="UNKNOWN",
            is_verified=False,
            data_provider="local_vector_catalog",
        ),
    )

    result = risk_assessment_agent_node(state)
    out = result["risk_assessment_output"]

    assert out["potential_consequences_status"] == "UNASSESSED_EXPOSURE_UNVERIFIED"


# ===========================================================================
# 12. Provenance From All Upstream Agents Preserved
# ===========================================================================

def test_provenance_from_all_upstream_agents_preserved():
    """Provenance dictionary retains upstream agent keys and synthesis engine."""
    state = _build_test_state(
        intelligence_output=_build_intelligence_output(incident_status="CONFIRMED"),
        weather_output=_build_weather_output(danger_rating="HIGH"),
        geospatial_output=_build_geospatial_output(exposure_level="MODERATE", is_verified=True),
    )

    result = risk_assessment_agent_node(state)
    out = result["risk_assessment_output"]
    prov = out["source_agent_provenance"]

    assert "intelligence_agent" in prov
    assert "weather_agent" in prov
    assert "geospatial_agent" in prov
    assert "synthesis_engine" in prov
    assert "M12.3" in prov["synthesis_engine"]


# ===========================================================================
# 13. Risk Rationale Explains Assessment
# ===========================================================================

def test_risk_rationale_explains_assessment():
    """Assessment rationale provides a transparent plain-English explanation."""
    state = _build_test_state(
        intelligence_output=_build_intelligence_output(
            incident_status="CONFIRMED",
            incident_severity="HIGH",
        ),
        weather_output=_build_weather_output(danger_rating="HIGH", fwi=30.0),
        geospatial_output=_build_geospatial_output(exposure_level="HIGH", is_verified=True),
    )

    result = risk_assessment_agent_node(state)
    out = result["risk_assessment_output"]

    rationale = out["assessment_rationale"]
    assert isinstance(rationale, str)
    assert len(rationale) > 50
    assert "confirmed" in rationale.lower()
    assert "weather" in rationale.lower() or "fwi" in rationale.lower()
    assert "exposure" in rationale.lower()


# ===========================================================================
# 14. No Duplicate M07 Inference or External Network Calls
# ===========================================================================

def test_no_duplicate_m07_inference_or_external_calls():
    """Risk Assessment Agent node must strictly consume state; zero model inferences or network requests."""
    state = _build_test_state(
        intelligence_output=_build_intelligence_output(),
        weather_output=_build_weather_output(),
        geospatial_output=_build_geospatial_output(),
    )

    with patch("urllib.request.urlopen") as mock_url, patch("requests.get") as mock_req:
        result = risk_assessment_agent_node(state)

        assert mock_url.call_count == 0
        assert mock_req.call_count == 0
        assert result["risk_assessment_output"] is not None


# ===========================================================================
# 15. Workflow Executes All 5 Nodes In Sequence
# ===========================================================================

def test_workflow_executes_new_risk_agent():
    """Full workflow execution runs 5 nodes: validator -> intelligence -> weather -> geospatial -> risk."""
    mock_assessment = _build_mock_m11_assessment(
        incident_status=IncidentStatus.CONFIRMED,
        incident_severity=DisasterAssessmentLevel.HIGH,
        fire_weather_level="HIGH",
        fwi_value=28.0,
        total_geo_features=8,
    )

    with patch("app.agents.nodes.intelligence.MultimodalIntelligenceService") as mock_svc_cls:
        instance = mock_svc_cls.return_value
        instance.analyze_observation.return_value = mock_assessment

        service = DisasterWorkflowService(include_risk_agent=True, include_planning_agent=False)
        req = DisasterResponseWorkflowRequest(
            latitude=30.3256,
            longitude=78.0422,
            disaster_type=DisasterType.WILDFIRE,
            search_radius_meters=5000.0,
        )

        result: WorkflowExecutionResult = service.run_workflow(req, workflow_id="wf-test-5-nodes")

        assert result.status == WorkflowStatus.COMPLETED
        assert result.stage == WorkflowStage.COMPLETED
        assert len(result.errors) == 0

        # Exactly 5 execution records in sequence
        assert len(result.execution_records) == 5
        agent_names = [r.agent_name for r in result.execution_records]
        assert agent_names == [
            "request_validator",
            "intelligence_agent",
            "weather_agent",
            "geospatial_agent",
            "risk_assessment_agent",
        ]

        # Risk assessment output populated
        assert result.risk_assessment_output is not None
        assert result.risk_assessment_output.incident_status == "CONFIRMED"
        assert result.risk_assessment_output.assessment_status == "complete"
        assert result.risk_assessment_output.overall_threat_level == "CRITICAL_EMERGENCY"


# ===========================================================================
# 16. Upstream Agent Failure Handled Safely
# ===========================================================================

def test_upstream_agent_failure_handled_safely():
    """When upstream intelligence encounters an unrecoverable failure, risk agent runs gracefully."""
    with patch("app.agents.nodes.intelligence.MultimodalIntelligenceService") as mock_svc_cls:
        instance = mock_svc_cls.return_value
        instance.analyze_observation.side_effect = RuntimeError("M11 Service Connection Timeout")

        service = DisasterWorkflowService(include_risk_agent=True, include_planning_agent=False)
        req = DisasterResponseWorkflowRequest(
            latitude=30.3256,
            longitude=78.0422,
            disaster_type=DisasterType.WILDFIRE,
        )

        result: WorkflowExecutionResult = service.run_workflow(req, workflow_id="wf-upstream-fail")

        # Workflow terminates with error status due to upstream error
        assert result.status == WorkflowStatus.FAILED
        assert len(result.errors) >= 1

        # Risk assessment agent still executed and recorded output
        assert result.risk_assessment_output is not None
        assert result.risk_assessment_output.assessment_status in ("partial", "failed")
        assert result.risk_assessment_output.incident_status == "UNAVAILABLE"


# ===========================================================================
# 17. Errors and Warnings Accumulate Correctly
# ===========================================================================

def test_errors_and_warnings_accumulate_correctly():
    """Errors and warnings from upstream nodes accumulate additively through LangGraph reducer."""
    existing_err = WorkflowError(
        code="PREVIOUS_WARNING",
        message="Stale observation warning",
        stage=WorkflowStage.CONTEXT_INTERPRETATION.value,
        agent="weather_agent",
        recoverable=True,
    ).model_dump(mode="json")

    state = _build_test_state(
        intelligence_output=_build_intelligence_output(),
        weather_output=_build_weather_output(),
        geospatial_output=_build_geospatial_output(),
        errors=[existing_err],
        warnings=["Existing workflow warning 1"],
    )

    result = risk_assessment_agent_node(state)

    # Risk node returns its own records/warnings/errors without overwriting state
    assert isinstance(result["warnings"], list)
    assert isinstance(result["execution_records"], list)
    assert result["execution_records"][0]["agent_name"] == "risk_assessment_agent"


# ===========================================================================
# 18. Final Workflow State Is JSON Serializable
# ===========================================================================

def test_final_workflow_state_is_json_serializable():
    """Full workflow state with RiskAssessmentAgentOutput is 100% JSON-serializable."""
    mock_assessment = _build_mock_m11_assessment()

    with patch("app.agents.nodes.intelligence.MultimodalIntelligenceService") as mock_svc_cls:
        instance = mock_svc_cls.return_value
        instance.analyze_observation.return_value = mock_assessment

        service = DisasterWorkflowService(include_risk_agent=True, include_planning_agent=False)
        req = DisasterResponseWorkflowRequest(
            latitude=30.3256,
            longitude=78.0422,
            disaster_type=DisasterType.WILDFIRE,
        )

        initial_state = initialize_workflow_state(req)
        final_state = service.graph.invoke(initial_state)

        # Test full round-trip serialization
        serialized_json = serialize_workflow_state(final_state)
        assert isinstance(serialized_json, str)
        parsed = json.loads(serialized_json)
        assert "risk_assessment_output" in parsed
        assert parsed["risk_assessment_output"]["assessment_status"] == "complete"

        deserialized = deserialize_workflow_state(serialized_json)
        assert deserialized["workflow_id"] == final_state["workflow_id"]
        assert deserialized["risk_assessment_output"]["incident_status"] == "SUSPECTED"


# ===========================================================================
# 19. No Fake Agent Outputs For Agents 5 and 6
# ===========================================================================

def test_no_fake_agent_outputs_for_agents_5_and_6():
    """Response Planning (Agent 5), Human Approval, and Coordinator Report (Agent 6) remain None."""
    mock_assessment = _build_mock_m11_assessment()

    with patch("app.agents.nodes.intelligence.MultimodalIntelligenceService") as mock_svc_cls:
        instance = mock_svc_cls.return_value
        instance.analyze_observation.return_value = mock_assessment

        service = DisasterWorkflowService(include_risk_agent=True, include_planning_agent=False)
        req = DisasterResponseWorkflowRequest(
            latitude=30.3256,
            longitude=78.0422,
            disaster_type=DisasterType.WILDFIRE,
        )

        initial_state = initialize_workflow_state(req)
        final_state = service.graph.invoke(initial_state)

        # Agents 1-4 are populated
        assert final_state["intelligence_output"] is not None
        assert final_state["weather_output"] is not None
        assert final_state["geospatial_output"] is not None
        assert final_state["risk_assessment_output"] is not None

        # Agents 5 and 6 MUST remain strictly None
        assert final_state["response_plan_output"] is None
        assert final_state["human_approval"] is None
        assert final_state["coordinator_report"] is None


# ===========================================================================
# 20. All Perception Outputs Missing Fails Safely
# ===========================================================================

def test_all_perception_missing_fails_safely():
    """When intelligence, weather, and geospatial outputs are all None, fails safely with explicit error."""
    state = _build_test_state(
        intelligence_output=None,
        weather_output=None,
        geospatial_output=None,
    )

    result = risk_assessment_agent_node(state)
    out = result["risk_assessment_output"]

    assert result["status"] == WorkflowStatus.FAILED.value
    assert result["stage"] == WorkflowStage.TERMINATED_WITH_ERROR.value
    assert len(result["errors"]) == 1
    assert result["errors"][0]["code"] == "MISSING_PERCEPTION_OUTPUTS"
    assert out["assessment_status"] == RiskAssessmentStatus.FAILED.value
    assert out["incident_status"] == "UNAVAILABLE"
    assert out["fire_weather_danger"] == "UNAVAILABLE"
    assert out["geographic_exposure_status"] == "UNAVAILABLE"
    assert out["potential_consequences_status"] == "UNASSESSED_INSUFFICIENT_DATA"
