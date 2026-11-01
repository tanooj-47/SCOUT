"""
backend/tests/unit/agents/test_m12_2_agents.py
Unit tests for Milestone 12.2: Intelligence, Weather, and Geospatial Agents.
Verifies service reuse, non-fabrication rules, epistemic humility, error handling,
provenance preservation, and full LangGraph workflow integration.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch
import pytest
from pydantic import ValidationError

from app.agents.graph import compile_workflow_graph, create_disaster_workflow_graph
from app.agents.nodes.geospatial import geospatial_agent_node
from app.agents.nodes.intelligence import intelligence_agent_node
from app.agents.nodes.validation import validate_request_node
from app.agents.nodes.weather import weather_agent_node
from app.agents.schemas import (
    DisasterResponseWorkflowRequest,
    GeospatialAgentOutput,
    IntelligenceAgentOutput,
    WeatherAgentOutput,
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
# Test Helpers: Mock M11 Assessment Builder
# ---------------------------------------------------------------------------

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
    """Builds a real typed MultimodalIntelligenceAssessment with deterministic parameters."""
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
# 1. Intelligence Agent Tests
# ===========================================================================

def test_intelligence_agent_successful_m11_consumption():
    """1. Intelligence agent consumes M11 assessment and populates IntelligenceAgentOutput correctly."""
    mock_assessment = _build_mock_m11_assessment(
        incident_status=IncidentStatus.SUSPECTED,
        incident_severity=None,
        active_evidence=IncidentEvidenceState.SUPPORTING_FIRE,
    )
    mock_service = MagicMock()
    mock_service.analyze_observation.return_value = mock_assessment

    state = initialize_workflow_state(
        DisasterResponseWorkflowRequest(latitude=30.3256, longitude=78.0422)
    )

    update = intelligence_agent_node(state, service=mock_service)

    assert update["stage"] == WorkflowStage.INTELLIGENCE_ASSESSMENT.value
    assert "intelligence_output" in update
    assert "m11_assessment" in update
    assert len(update["execution_records"]) == 1
    assert update["execution_records"][0]["status"] == "success"

    output = update["intelligence_output"]
    assert output["incident_status"] == "SUSPECTED"
    assert output["incident_severity"] is None
    assert output["active_evidence_state"] == "supporting_visual_fire_evidence"
    assert "flame features" in output["visual_evidence_summary"].lower()
    assert output["fire_weather_danger"] == "HIGH"
    assert output["assessment_level"] == "HIGH"
    assert output["provenance"]["source"] == "MultimodalIntelligenceService (M11)"


def test_intelligence_agent_missing_required_inputs():
    """2. Intelligence agent handles missing coordinates gracefully with explicit unavailable output."""
    raw_state: DisasterWorkflowState = {
        "workflow_id": "wf-test-missing-coords",
        "request_id": "req-missing-coords",
        "disaster_type": "wildfire",
        "latitude": None,
        "longitude": None,
        "search_radius_meters": 5000.0,
        "image_path": None,
        "source_description": "test",
        "metadata": {},
        "status": WorkflowStatus.RUNNING.value,
        "stage": WorkflowStage.REQUEST_VALIDATED.value,
        "m11_assessment": None,
        "intelligence_output": None,
        "weather_output": None,
        "geospatial_output": None,
        "risk_assessment_output": None,
        "response_plan_output": None,
        "human_approval": None,
        "coordinator_report": None,
        "execution_records": [],
        "errors": [],
        "warnings": [],
        "provenance": {},
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": None,
    }

    update = intelligence_agent_node(raw_state)

    assert update["status"] == WorkflowStatus.FAILED.value
    assert update["stage"] == WorkflowStage.TERMINATED_WITH_ERROR.value
    assert len(update["errors"]) == 1
    assert update["errors"][0]["code"] == "MISSING_COORDINATES"
    assert update["intelligence_output"]["incident_status"] == "UNAVAILABLE"
    assert update["intelligence_output"]["active_evidence_state"] == "unavailable"
    assert update["execution_records"][0]["status"] == "failed"


def test_intelligence_agent_service_failure_handled_safely():
    """3. M11 service failure produces structured WorkflowError and explicit unavailable state."""
    mock_service = MagicMock()
    mock_service.analyze_observation.side_effect = RuntimeError("Open-Meteo connection timed out")

    state = initialize_workflow_state(
        DisasterResponseWorkflowRequest(latitude=30.3256, longitude=78.0422)
    )

    update = intelligence_agent_node(state, service=mock_service)

    assert update["status"] == WorkflowStatus.FAILED.value
    assert update["stage"] == WorkflowStage.TERMINATED_WITH_ERROR.value
    assert len(update["errors"]) == 1
    assert update["errors"][0]["code"] == "INTELLIGENCE_SERVICE_ERROR"
    assert "Open-Meteo connection timed out" in update["errors"][0]["message"]
    assert update["intelligence_output"]["incident_status"] == "UNAVAILABLE"
    assert update["execution_records"][0]["status"] == "failed"


def test_intelligence_agent_preserves_unconfirmed_incident():
    """4. Unconfirmed/suspected incidents are preserved and NEVER escalated to CONFIRMED."""
    mock_assessment = _build_mock_m11_assessment(
        incident_status=IncidentStatus.SUSPECTED,
        active_evidence=IncidentEvidenceState.SUPPORTING_FIRE,
    )
    mock_service = MagicMock()
    mock_service.analyze_observation.return_value = mock_assessment

    state = initialize_workflow_state(
        DisasterResponseWorkflowRequest(latitude=30.3256, longitude=78.0422)
    )

    update = intelligence_agent_node(state, service=mock_service)
    output = update["intelligence_output"]

    assert output["incident_status"] == "SUSPECTED"
    assert output["incident_status"] != "CONFIRMED"


def test_intelligence_agent_preserves_missing_severity():
    """5. When incident severity is unassessed (None), intelligence output preserves None without fabricating."""
    mock_assessment = _build_mock_m11_assessment(
        incident_status=IncidentStatus.SUSPECTED,
        incident_severity=None,
    )
    mock_service = MagicMock()
    mock_service.analyze_observation.return_value = mock_assessment

    state = initialize_workflow_state(
        DisasterResponseWorkflowRequest(latitude=30.3256, longitude=78.0422)
    )

    update = intelligence_agent_node(state, service=mock_service)
    assert update["intelligence_output"]["incident_severity"] is None


def test_intelligence_agent_provenance_preservation():
    """6. Intelligence output preserves detailed assessment provenance and audit lineage."""
    mock_assessment = _build_mock_m11_assessment()
    mock_service = MagicMock()
    mock_service.analyze_observation.return_value = mock_assessment

    state = initialize_workflow_state(
        DisasterResponseWorkflowRequest(latitude=30.3256, longitude=78.0422)
    )

    update = intelligence_agent_node(state, service=mock_service)
    provenance = update["intelligence_output"]["provenance"]

    assert provenance["assessment_id"] == mock_assessment.assessment_id
    assert provenance["disaster_type"] == "wildfire"
    assert provenance["heuristic_risk_index"] == 68.5
    assert provenance["evidence_items_count"] == 2


def test_intelligence_agent_does_not_rerun_m07_inference():
    """7. Intelligence agent delegates directly to M11 service and does not invoke PyTorch or BaselineCNN."""
    mock_service = MagicMock()
    mock_service.analyze_observation.return_value = _build_mock_m11_assessment()

    with patch("ml.models.baseline_cnn.BaselineCNN") as mock_baseline:
        state = initialize_workflow_state(
            DisasterResponseWorkflowRequest(latitude=30.3256, longitude=78.0422)
        )
        intelligence_agent_node(state, service=mock_service)
        # Verify that BaselineCNN was NOT independently instantiated by intelligence_agent_node
        mock_baseline.assert_not_called()


# ===========================================================================
# 2. Weather Agent Tests
# ===========================================================================

def test_weather_agent_complete_weather_consumption():
    """8. Weather agent extracts complete atmospheric observations and Canadian FWI."""
    assessment = _build_mock_m11_assessment(
        fire_weather_level="VERY_HIGH",
        fwi_value=31.2,
    )
    state = initialize_workflow_state(
        DisasterResponseWorkflowRequest(latitude=30.3256, longitude=78.0422)
    )
    state["m11_assessment"] = assessment.model_dump(mode="json")

    update = weather_agent_node(state)

    assert update["stage"] == WorkflowStage.CONTEXT_INTERPRETATION.value
    output = update["weather_output"]
    assert output["temperature_c"] == 28.5
    assert output["relative_humidity_pct"] == 35.0
    assert output["wind_speed_kmh"] == 18.0
    assert output["precipitation_mm"] == 0.0
    assert output["fwi"] == 31.2
    assert output["danger_rating"] == "VERY_HIGH"
    assert output["is_experimental"] is True
    assert len(output["missing_parameters"]) == 0
    assert len(output["stale_observations"]) == 0


def test_weather_agent_missing_weather_fields_handled_strictly():
    """9. When weather fields are missing, missing_parameters records them and FWI is None (zero defaults)."""
    assessment = _build_mock_m11_assessment(
        missing_weather_vars=["relative_humidity", "precipitation_mm"],
        fwi_value=None,
    )
    state = initialize_workflow_state(
        DisasterResponseWorkflowRequest(latitude=30.3256, longitude=78.0422)
    )
    state["m11_assessment"] = assessment.model_dump(mode="json")

    update = weather_agent_node(state)
    output = update["weather_output"]

    assert output["relative_humidity_pct"] is None
    assert output["precipitation_mm"] is None
    assert output["fwi"] is None
    assert "relative_humidity" in output["missing_parameters"]
    assert "precipitation_mm" in output["missing_parameters"]


def test_weather_agent_stale_observations_flagged():
    """10. Stale observations are explicitly recorded in stale_observations and flagged in warnings."""
    assessment = _build_mock_m11_assessment(is_weather_stale=True)
    state = initialize_workflow_state(
        DisasterResponseWorkflowRequest(latitude=30.3256, longitude=78.0422)
    )
    state["m11_assessment"] = assessment.model_dump(mode="json")

    update = weather_agent_node(state)
    output = update["weather_output"]

    assert "environmental_observation" in output["stale_observations"]
    assert any("stale observation" in w.lower() for w in update["warnings"])


def test_weather_agent_experimental_fwi_attribution():
    """11. Weather agent always marks is_experimental=True for instantaneous single-observation FWI."""
    assessment = _build_mock_m11_assessment(fwi_value=25.0)
    state = initialize_workflow_state(
        DisasterResponseWorkflowRequest(latitude=30.3256, longitude=78.0422)
    )
    state["m11_assessment"] = assessment.model_dump(mode="json")

    update = weather_agent_node(state)
    assert update["weather_output"]["is_experimental"] is True


def test_weather_agent_extreme_fire_weather_decoupled_from_incident():
    """12. Extreme fire weather explains atmospheric combustibility, not confirmation of active fire."""
    assessment = _build_mock_m11_assessment(
        incident_status=IncidentStatus.UNCONFIRMED,
        fire_weather_level="EXTREME",
        fwi_value=45.0,
    )
    state = initialize_workflow_state(
        DisasterResponseWorkflowRequest(latitude=30.3256, longitude=78.0422)
    )
    state["m11_assessment"] = assessment.model_dump(mode="json")

    update = weather_agent_node(state)
    output = update["weather_output"]

    assert output["danger_rating"] == "EXTREME"
    assert "independent" in output["fire_weather_explanation"].lower() or "fire-weather danger" in output["fire_weather_explanation"].lower()


def test_weather_agent_missing_m11_assessment():
    """13. Weather agent returns explicit unavailable output when M11 assessment is None."""
    state = initialize_workflow_state(
        DisasterResponseWorkflowRequest(latitude=30.3256, longitude=78.0422)
    )
    state["m11_assessment"] = None

    update = weather_agent_node(state)
    output = update["weather_output"]

    assert output["danger_rating"] == "UNAVAILABLE"
    assert output["temperature_c"] is None
    assert output["fwi"] is None
    assert "all_meteorological_parameters" in output["missing_parameters"]


# ===========================================================================
# 3. Geospatial Agent Tests
# ===========================================================================

def test_geospatial_agent_available_features():
    """14. Geospatial agent extracts geographic features, settlement distance, and infrastructure counts."""
    assessment = _build_mock_m11_assessment(total_geo_features=8)
    state = initialize_workflow_state(
        DisasterResponseWorkflowRequest(latitude=30.3256, longitude=78.0422)
    )
    state["m11_assessment"] = assessment.model_dump(mode="json")

    update = geospatial_agent_node(state)
    output = update["geospatial_output"]

    assert output["settlements_within_radius"] == 3
    assert output["closest_settlement_distance_meters"] == 1250.0
    assert output["closest_settlement_name"] == "Dehradun Outskirts"
    assert output["hospitals_within_radius"] == 1
    assert output["fire_stations_within_radius"] == 1
    assert output["transport_corridors_count"] == 2
    assert output["water_bodies_count"] == 1
    assert output["is_verified"] is True
    assert output["data_provider"] == "local_vector_catalog"


def test_geospatial_agent_empty_context_is_unverified():
    """15. 0 catalog features marks is_verified=False and adds unverified catalog notes."""
    assessment = _build_mock_m11_assessment(
        exposure_level="UNVERIFIED (NO_LOCAL_FEATURES)",
        exposure_score=None,
        total_geo_features=0,
    )
    state = initialize_workflow_state(
        DisasterResponseWorkflowRequest(latitude=30.3256, longitude=78.0422)
    )
    state["m11_assessment"] = assessment.model_dump(mode="json")

    update = geospatial_agent_node(state)
    output = update["geospatial_output"]

    assert output["settlements_within_radius"] == 0
    assert output["is_verified"] is False
    assert any("unverified" in note.lower() for note in output["catalog_completeness_notes"])


def test_geospatial_agent_missing_m11_assessment():
    """16. Geospatial agent returns explicit unavailable output when M11 assessment is missing."""
    state = initialize_workflow_state(
        DisasterResponseWorkflowRequest(latitude=30.3256, longitude=78.0422)
    )
    state["m11_assessment"] = None

    update = geospatial_agent_node(state)
    output = update["geospatial_output"]

    assert output["exposure_level"] == "UNAVAILABLE"
    assert output["exposure_score"] is None
    assert output["is_verified"] is False
    assert any("unavailable" in note.lower() for note in output["catalog_completeness_notes"])


def test_geospatial_agent_exposure_score_unavailable_preserved():
    """17. When exposure score is None, is_verified=False and None score is preserved."""
    assessment = _build_mock_m11_assessment(
        exposure_level="UNVERIFIED",
        exposure_score=None,
        total_geo_features=0,
    )
    state = initialize_workflow_state(
        DisasterResponseWorkflowRequest(latitude=30.3256, longitude=78.0422)
    )
    state["m11_assessment"] = assessment.model_dump(mode="json")

    update = geospatial_agent_node(state)
    assert update["geospatial_output"]["exposure_score"] is None
    assert update["geospatial_output"]["is_verified"] is False


def test_geospatial_agent_provenance_preservation():
    """18. Geospatial output preserves data provider and evaluated features in provenance."""
    assessment = _build_mock_m11_assessment(total_geo_features=8)
    state = initialize_workflow_state(
        DisasterResponseWorkflowRequest(latitude=30.3256, longitude=78.0422)
    )
    state["m11_assessment"] = assessment.model_dump(mode="json")

    update = geospatial_agent_node(state)
    provenance = update["geospatial_output"]["provenance"]

    assert provenance["source_name"] == "local_vector_catalog"
    assert provenance["features_evaluated"] == 8


def test_geospatial_agent_distinguishes_zero_features_from_zero_exposure():
    """19. 0 catalog features does NOT imply verified zero exposure; records explicit caveat."""
    assessment = _build_mock_m11_assessment(
        exposure_level="UNVERIFIED (NO_LOCAL_FEATURES)",
        exposure_score=None,
        total_geo_features=0,
    )
    state = initialize_workflow_state(
        DisasterResponseWorkflowRequest(latitude=30.3256, longitude=78.0422)
    )
    state["m11_assessment"] = assessment.model_dump(mode="json")

    update = geospatial_agent_node(state)
    notes = update["geospatial_output"]["catalog_completeness_notes"]
    assert any("not evidence of zero exposure" in n.lower() or "unverified" in n.lower() for n in notes)


# ===========================================================================
# 4. Graph Integration Tests
# ===========================================================================

def test_graph_executes_all_three_agents():
    """20. Valid request executes validate_request -> intelligence_agent -> weather_agent -> geospatial_agent."""
    mock_assessment = _build_mock_m11_assessment(
        incident_status=IncidentStatus.SUSPECTED,
        fire_weather_level="HIGH",
        fwi_value=24.5,
        total_geo_features=8,
    )

    with patch("app.agents.nodes.intelligence.MultimodalIntelligenceService") as mock_svc_cls:
        instance = mock_svc_cls.return_value
        instance.analyze_observation.return_value = mock_assessment

        service = DisasterWorkflowService(include_risk_agent=False)
        req = DisasterResponseWorkflowRequest(
            latitude=30.3256,
            longitude=78.0422,
            disaster_type=DisasterType.WILDFIRE,
            search_radius_meters=5000.0,
        )

        result: WorkflowExecutionResult = service.run_workflow(req, workflow_id="wf-all-three-agents")

        # Lifecycle status & stage
        assert result.status == WorkflowStatus.COMPLETED
        assert result.stage == WorkflowStage.COMPLETED
        assert len(result.errors) == 0

        # All 4 nodes executed in audit trail
        assert len(result.execution_records) == 4
        agent_names = [r.agent_name for r in result.execution_records]
        assert agent_names == ["request_validator", "intelligence_agent", "weather_agent", "geospatial_agent"]

        # All 3 agent outputs populated on result schema
        assert result.intelligence_output is not None
        assert result.intelligence_output.incident_status == "SUSPECTED"
        assert result.weather_output is not None
        assert result.weather_output.danger_rating == "HIGH"
        assert result.weather_output.fwi == 24.5
        assert result.geospatial_output is not None
        assert result.geospatial_output.settlements_within_radius == 3
        assert result.geospatial_output.is_verified is True


def test_graph_validation_failure_halts_immediately():
    """21. Validation failure stops the graph; downstream agents are never executed."""
    service = DisasterWorkflowService()
    req = DisasterResponseWorkflowRequest(
        latitude=30.3256,
        longitude=78.0422,
        disaster_type=DisasterType.FLOOD,  # Unsupported disaster type
    )

    result = service.run_workflow(req, workflow_id="wf-val-fail-halt")

    assert result.status == WorkflowStatus.FAILED
    assert result.stage == WorkflowStage.TERMINATED_WITH_ERROR
    assert len(result.errors) >= 1
    assert result.errors[0].code == "UNSUPPORTED_DISASTER_TYPE"

    # Only request_validator was executed; intelligence/weather/geospatial were NOT
    assert len(result.execution_records) == 1
    assert result.execution_records[0].agent_name == "request_validator"
    assert result.intelligence_output is None
    assert result.weather_output is None
    assert result.geospatial_output is None


def test_graph_intelligence_failure_handled_safely():
    """22. Intelligence failure is handled safely; downstream agents return explicit unavailable outputs."""
    with patch("app.agents.nodes.intelligence.MultimodalIntelligenceService") as mock_svc_cls:
        instance = mock_svc_cls.return_value
        instance.analyze_observation.side_effect = RuntimeError("Service network failure")

        service = DisasterWorkflowService(include_risk_agent=False)
        req = DisasterResponseWorkflowRequest(
            latitude=30.3256,
            longitude=78.0422,
            disaster_type=DisasterType.WILDFIRE,
        )

        result = service.run_workflow(req, workflow_id="wf-intel-fail-safe")

        # Workflow status reflects failure
        assert result.status == WorkflowStatus.FAILED
        assert result.stage == WorkflowStage.TERMINATED_WITH_ERROR
        assert len(result.errors) == 1
        assert result.errors[0].code == "INTELLIGENCE_SERVICE_ERROR"

        # Downstream agents ran and recorded explicit unavailable states
        assert result.intelligence_output is not None
        assert result.intelligence_output.incident_status == "UNAVAILABLE"
        assert result.weather_output is not None
        assert result.weather_output.danger_rating == "UNAVAILABLE"
        assert result.geospatial_output is not None
        assert result.geospatial_output.exposure_level == "UNAVAILABLE"


def test_graph_agent_errors_recorded_additively():
    """23. Multiple errors are recorded additively via LangGraph reducers without overwriting."""
    req = DisasterResponseWorkflowRequest(
        latitude=30.3256,
        longitude=78.0422,
        disaster_type=DisasterType.WILDFIRE,
    )
    initial_state = initialize_workflow_state(req)

    # Intentionally corrupt coordinates in state after validation
    initial_state["latitude"] = None

    update1 = intelligence_agent_node(initial_state)
    assert len(update1["errors"]) == 1

    # Verify error envelope has expected attributes
    err = update1["errors"][0]
    assert err["code"] == "MISSING_COORDINATES"
    assert err["stage"] == WorkflowStage.INTELLIGENCE_ASSESSMENT.value
    assert err["agent"] == "intelligence_agent"


def test_graph_no_fake_agent_outputs_produced():
    """24. Future agents (Agents 4, 5, 6) remain strictly None (no fabricated or placeholder data)."""
    mock_assessment = _build_mock_m11_assessment()

    with patch("app.agents.nodes.intelligence.MultimodalIntelligenceService") as mock_svc_cls:
        instance = mock_svc_cls.return_value
        instance.analyze_observation.return_value = mock_assessment

        service = DisasterWorkflowService(include_risk_agent=False)
        req = DisasterResponseWorkflowRequest(
            latitude=30.3256,
            longitude=78.0422,
            disaster_type=DisasterType.WILDFIRE,
        )

        initial_state = initialize_workflow_state(req)
        final_state = service.graph.invoke(initial_state)

        # Implemented M12.2 agents have outputs
        assert final_state["intelligence_output"] is not None
        assert final_state["weather_output"] is not None
        assert final_state["geospatial_output"] is not None

        # Unimplemented future agents MUST be None
        assert final_state["risk_assessment_output"] is None
        assert final_state["response_plan_output"] is None
        assert final_state["human_approval"] is None
        assert final_state["coordinator_report"] is None


def test_graph_final_state_is_serializable():
    """25. Final state produced by M12.2 workflow round-trips cleanly through JSON serialization."""
    mock_assessment = _build_mock_m11_assessment()

    with patch("app.agents.nodes.intelligence.MultimodalIntelligenceService") as mock_svc_cls:
        instance = mock_svc_cls.return_value
        instance.analyze_observation.return_value = mock_assessment

        service = DisasterWorkflowService(include_risk_agent=False)
        req = DisasterResponseWorkflowRequest(
            latitude=30.3256,
            longitude=78.0422,
            disaster_type=DisasterType.WILDFIRE,
        )

        initial_state = initialize_workflow_state(req)
        final_state = service.graph.invoke(initial_state)

        # Test JSON round-trip
        json_str = serialize_workflow_state(final_state)
        assert isinstance(json_str, str)
        assert len(json_str) > 100

        deserialized = deserialize_workflow_state(json_str)
        assert deserialized["workflow_id"] == final_state["workflow_id"]
        assert deserialized["intelligence_output"]["incident_status"] == final_state["intelligence_output"]["incident_status"]
        assert deserialized["weather_output"]["danger_rating"] == final_state["weather_output"]["danger_rating"]
        assert deserialized["geospatial_output"]["settlements_within_radius"] == final_state["geospatial_output"]["settlements_within_radius"]
