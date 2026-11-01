"""
backend/tests/unit/intelligence/test_semantic_release_scenarios.py
Comprehensive scenario-based test suite for M11 Final Semantic Release Audit.
Validates:
1. Concern A: Visual evidence classifications and neutral image epistemic status.
2. Concern B: Decoupled incident severity from fire-weather danger, life-safety contradiction preservation.
3. Concern C: Unverified vs. verified low exposure, null exposure scores, and consequence calculations.
4. Serialized API response schema validation.
"""

import json
from unittest.mock import MagicMock, patch
import pytest
from pydantic import ValidationError

from app.geospatial.exceptions import PostGISUnavailableError
from app.geospatial.schemas import FeatureCategory, GeographicFeatureItem, SpatialRelationship
from app.intelligence.evidence import EvidenceCollector
from app.intelligence.fusion import MultimodalFusionEngine
from app.intelligence.risk import HeuristicRiskAssessor
from app.intelligence.schemas import (
    ContextSummary,
    CoordinateLocation,
    DisasterAssessmentLevel,
    EvidenceStatus,
    IncidentEvidenceState,
    IncidentObservationInput,
    IncidentStatus,
    MultimodalIntelligenceAssessment,
)
from app.intelligence.service import MultimodalIntelligenceService
from app.schemas.incident import DisasterType


# ---------------------------------------------------------------------------
# Helper Fixture Factories
# ---------------------------------------------------------------------------

def _make_cv_evidence(fire: float, smoke: float, neutral: float):
    return EvidenceCollector.create_cv_evidence(
        probabilities={"fire": fire, "smoke": smoke, "neutral": neutral},
        model_name="BaselineCNN",
        checkpoint_path="baseline_cnn_best.pt",
    )


def _make_env_evidence(temp=25.0, rh=50.0, fwi=10.0, rating="Moderate", rain=0.0):
    weather = {
        "temperature_c": temp,
        "relative_humidity_pct": rh,
        "precipitation_mm": rain,
    }
    if fwi is not None:
        weather["fwi_indices"] = {
            "fire_weather_index_fwi": fwi,
            "danger_rating": rating,
        }
    return EvidenceCollector.create_environmental_evidence(
        weather_data=weather,
        provider="open-meteo",
        model_or_dataset="best_match",
        is_stale=False,
    )


def _make_context(features_count=0, settlement_dist=None, hospital_dist=None, coverage_notes=None):
    return ContextSummary(
        settlements_found=1 if settlement_dist is not None else 0,
        closest_settlement_distance_meters=settlement_dist,
        closest_settlement_name="Test Settlement" if settlement_dist is not None else None,
        hospitals_found=1 if hospital_dist is not None else 0,
        closest_hospital_distance_meters=hospital_dist,
        fire_stations_found=0,
        road_corridors_found=1 if features_count > 0 else 0,
        water_bodies_found=0,
        total_features_evaluated=features_count,
        spatial_coverage_notes=coverage_notes or [],
    )


# ---------------------------------------------------------------------------
# CONCERN A: Visual Evidence & Confirmation Semantics Scenarios
# ---------------------------------------------------------------------------

def test_visual_fire_prediction_without_corroboration_yields_suspected():
    """Requirement 1: High-confidence fire prediction alone (p >= 0.70) without corroboration produces SUSPECTED, not CONFIRMED."""
    cv = _make_cv_evidence(fire=0.85, smoke=0.10, neutral=0.05)
    env = _make_env_evidence(fwi=15.0, rating="High")
    context = _make_context(features_count=2, settlement_dist=1200.0)

    fusion = MultimodalFusionEngine.fuse([cv, env], context)
    assert fusion.active_evidence_state == IncidentEvidenceState.SUPPORTING_FIRE
    assert fusion.visual_fire_probability == 0.85
    assert fusion.is_corroborated is False

    level, score, haz, exp, con, _, _ = HeuristicRiskAssessor.evaluate_detailed(DisasterType.WILDFIRE, fusion)
    status, severity = HeuristicRiskAssessor.determine_incident_status(
        fusion.active_evidence_state, haz.hazard_level, is_corroborated=fusion.is_corroborated
    )

    assert status == IncidentStatus.SUSPECTED
    assert status != IncidentStatus.CONFIRMED
    assert severity == DisasterAssessmentLevel.HIGH
    assert severity != DisasterAssessmentLevel.CRITICAL
    assert haz.hazard_score >= 80.0
    assert haz.incident_status == IncidentStatus.SUSPECTED
    assert haz.active_incident_level == DisasterAssessmentLevel.HIGH

    # Provenance and raw scores preserved in EvidenceItem
    assert cv.raw_value["fire"] == 0.85
    assert cv.provenance["top_predicted_class"] == "fire"
    assert cv.confidence == 0.85


def test_visual_smoke_prediction_without_corroboration_yields_suspected():
    """Requirement 2: Smoke prediction alone (p >= 0.50, low fire) produces SUSPECTED incident status."""
    cv = _make_cv_evidence(fire=0.15, smoke=0.75, neutral=0.10)
    env = _make_env_evidence(fwi=12.0, rating="Moderate")
    context = _make_context(features_count=1, settlement_dist=2000.0)

    fusion = MultimodalFusionEngine.fuse([cv, env], context)
    assert fusion.active_evidence_state == IncidentEvidenceState.SUPPORTING_SMOKE
    assert fusion.is_corroborated is False

    level, score, haz, exp, con, _, _ = HeuristicRiskAssessor.evaluate_detailed(DisasterType.WILDFIRE, fusion)
    status, severity = HeuristicRiskAssessor.determine_incident_status(
        fusion.active_evidence_state, haz.hazard_level, is_corroborated=fusion.is_corroborated
    )

    assert status == IncidentStatus.SUSPECTED
    assert severity in (DisasterAssessmentLevel.MODERATE, DisasterAssessmentLevel.HIGH)
    assert haz.incident_status == IncidentStatus.SUSPECTED


def test_fire_prediction_with_independent_verified_corroboration_yields_confirmed():
    """Requirement 3: Fire prediction with independent verified corroboration (vision + satellite) produces CONFIRMED."""
    cv = _make_cv_evidence(fire=0.85, smoke=0.10, neutral=0.05)
    sat = EvidenceCollector.create_satellite_evidence(
        satellite_data={"thermal_anomaly": True, "confidence": 92.0},
        source_name="VIIRS_S-NPP",
        brightness_temp_k=365.2,
        frp_mw=45.8,
    )
    context = _make_context(features_count=2, settlement_dist=1200.0)

    fusion = MultimodalFusionEngine.fuse([cv, sat], context)
    assert fusion.is_corroborated is True
    assert "computer_vision" in fusion.corroboration_sources
    assert "satellite_observation" in fusion.corroboration_sources
    assert fusion.active_evidence_state == IncidentEvidenceState.SUPPORTING_FIRE

    level, score, haz, exp, con, _, _ = HeuristicRiskAssessor.evaluate_detailed(DisasterType.WILDFIRE, fusion)
    status, severity = HeuristicRiskAssessor.determine_incident_status(
        fusion.active_evidence_state, haz.hazard_level, is_corroborated=fusion.is_corroborated
    )

    assert status == IncidentStatus.CONFIRMED
    assert severity in (DisasterAssessmentLevel.HIGH, DisasterAssessmentLevel.CRITICAL)
    assert haz.incident_status == IncidentStatus.CONFIRMED


def test_explicit_verified_field_confirmation_yields_confirmed():
    """Requirement 4: Explicit verified field confirmation (is_confirmed=True) produces CONFIRMED."""
    field = EvidenceCollector.create_field_evidence(
        report_data={"location": "Forest Sector 4", "is_confirmed": True, "reported_by": "Ranger Team B"},
        source_name="Uttarakhand_Forest_Guard",
        is_confirmed=True,
    )
    context = _make_context(features_count=2, settlement_dist=800.0)

    fusion = MultimodalFusionEngine.fuse([field], context)
    assert fusion.is_corroborated is True
    assert fusion.active_evidence_state == IncidentEvidenceState.FIELD_CONFIRMED
    assert "field_report" in fusion.corroboration_sources

    level, score, haz, exp, con, _, _ = HeuristicRiskAssessor.evaluate_detailed(DisasterType.WILDFIRE, fusion)
    status, severity = HeuristicRiskAssessor.determine_incident_status(
        fusion.active_evidence_state, haz.hazard_level, is_corroborated=fusion.is_corroborated
    )

    assert status == IncidentStatus.CONFIRMED
    assert severity in (DisasterAssessmentLevel.HIGH, DisasterAssessmentLevel.CRITICAL)
    assert haz.incident_status == IncidentStatus.CONFIRMED


def test_visual_neutral_prediction_yields_unconfirmed():
    """Requirement 5: Neutral prediction yields UNCONFIRMED incident status and None (null) severity."""
    cv = _make_cv_evidence(fire=0.02, smoke=0.03, neutral=0.95)
    env = _make_env_evidence(fwi=5.0, rating="Low")
    context = _make_context(features_count=1, settlement_dist=1500.0)

    fusion = MultimodalFusionEngine.fuse([cv, env], context)
    assert fusion.active_evidence_state == IncidentEvidenceState.NO_SUPPORTING_EVIDENCE

    level, score, haz, exp, con, _, _ = HeuristicRiskAssessor.evaluate_detailed(DisasterType.WILDFIRE, fusion)
    status, severity = HeuristicRiskAssessor.determine_incident_status(
        fusion.active_evidence_state, haz.hazard_level, is_corroborated=fusion.is_corroborated
    )

    assert status == IncidentStatus.UNCONFIRMED
    assert severity is None  # Unassessed / unavailable, NOT LOW
    assert haz.hazard_score == 0.0
    assert haz.incident_status == IncidentStatus.UNCONFIRMED
    assert haz.active_incident_level is None

    # Preserves classifier details
    assert cv.raw_value["neutral"] == 0.95
    assert cv.provenance["top_predicted_class"] == "neutral"


def test_visual_missing_image_evidence_yields_insufficient_evidence():
    """Requirement 6: Missing imagery evidence yields INSUFFICIENT_EVIDENCE incident status and None severity."""
    cv = EvidenceCollector.create_unavailable_cv_evidence("No image file provided")
    env = _make_env_evidence(fwi=12.0, rating="Moderate")
    context = _make_context(features_count=1, settlement_dist=2000.0)

    fusion = MultimodalFusionEngine.fuse([cv, env], context)
    assert fusion.active_evidence_state == IncidentEvidenceState.MISSING_EVIDENCE

    level, score, haz, exp, con, _, _ = HeuristicRiskAssessor.evaluate_detailed(DisasterType.WILDFIRE, fusion)
    status, severity = HeuristicRiskAssessor.determine_incident_status(
        fusion.active_evidence_state, haz.hazard_level, is_corroborated=fusion.is_corroborated
    )

    assert status == IncidentStatus.INSUFFICIENT_EVIDENCE
    assert severity is None
    assert "computer_vision_imagery" in fusion.missing_streams


def test_single_image_prediction_cannot_independently_establish_critical_severity():
    """Requirement 7: Single-image prediction cannot independently establish CRITICAL severity (capped at HIGH)."""
    cv = _make_cv_evidence(fire=0.99, smoke=0.01, neutral=0.00)
    env = _make_env_evidence(fwi=12.0, rating="Moderate")
    context = _make_context(features_count=2, settlement_dist=1500.0)

    fusion = MultimodalFusionEngine.fuse([cv, env], context)
    assert fusion.is_corroborated is False

    level, score, haz, exp, con, _, _ = HeuristicRiskAssessor.evaluate_detailed(DisasterType.WILDFIRE, fusion)
    status, severity = HeuristicRiskAssessor.determine_incident_status(
        fusion.active_evidence_state, haz.hazard_level, is_corroborated=fusion.is_corroborated
    )

    assert status == IncidentStatus.SUSPECTED
    assert severity != DisasterAssessmentLevel.CRITICAL
    assert severity == DisasterAssessmentLevel.HIGH
    assert haz.active_incident_level == DisasterAssessmentLevel.HIGH


def test_visual_uncertain_or_conflicting_evidence():
    """Diffuse visual class scores yield SUSPECTED incident status with diffuse explanation."""
    cv = _make_cv_evidence(fire=0.36, smoke=0.34, neutral=0.30)
    env = _make_env_evidence(fwi=8.0, rating="Moderate")
    context = _make_context(features_count=1, settlement_dist=3000.0)

    fusion = MultimodalFusionEngine.fuse([cv, env], context)
    assert fusion.active_evidence_state == IncidentEvidenceState.UNCERTAIN_OR_CONFLICTING

    level, score, haz, exp, con, _, _ = HeuristicRiskAssessor.evaluate_detailed(DisasterType.WILDFIRE, fusion)
    status, severity = HeuristicRiskAssessor.determine_incident_status(
        fusion.active_evidence_state, haz.hazard_level, is_corroborated=fusion.is_corroborated
    )

    assert status == IncidentStatus.SUSPECTED
    assert haz.incident_status == IncidentStatus.SUSPECTED
    assert "diffuse" in haz.visual_explanation.lower()


def test_neutral_image_does_not_establish_regional_fire_absence():
    """Neutral image must NOT be interpreted as proof that the surrounding region is fire-free."""
    cv = _make_cv_evidence(fire=0.01, smoke=0.01, neutral=0.98)
    env = _make_env_evidence(fwi=4.0, rating="Low")
    context = _make_context(features_count=1, settlement_dist=2000.0)

    fusion = MultimodalFusionEngine.fuse([cv, env], context)
    _, _, haz, _, _, _, _ = HeuristicRiskAssessor.evaluate_detailed(DisasterType.WILDFIRE, fusion)

    # Explanation and factor text must explicitly mention FOV / perspective constraints
    explanation = haz.visual_explanation
    assert "does not prove that no wildfire exists in the surrounding area" in explanation.lower() or \
           "field of view" in explanation.lower()
    assert any("does not eliminate regional fire risk" in f.lower() or "field of view" in f.lower() for f in haz.factors)


# ---------------------------------------------------------------------------
# CONCERN B: Separate Incident Severity from Fire-Weather Danger
# ---------------------------------------------------------------------------

def test_extreme_fire_weather_without_incident_evidence():
    """
    Requirement 9: Extreme fire-weather danger does not confirm an incident.
    Must report elevated fire-weather danger without inventing an active incident.
    Active incident status is UNCONFIRMED, severity is None (null).
    """
    cv = _make_cv_evidence(fire=0.02, smoke=0.02, neutral=0.96)
    env = _make_env_evidence(temp=39.0, rh=12.0, fwi=45.0, rating="Extreme")
    context = _make_context(features_count=2, settlement_dist=1000.0)  # Settlement nearby

    fusion = MultimodalFusionEngine.fuse([cv, env], context)
    level, score, haz, exp, con, _, _ = HeuristicRiskAssessor.evaluate_detailed(DisasterType.WILDFIRE, fusion)
    status, severity = HeuristicRiskAssessor.determine_incident_status(
        fusion.active_evidence_state, haz.hazard_level, is_corroborated=fusion.is_corroborated
    )

    # Active incident is unconfirmed and None (unassessed) severity
    assert status == IncidentStatus.UNCONFIRMED
    assert severity is None
    assert haz.hazard_score == 0.0
    assert haz.hazard_level == DisasterAssessmentLevel.LOW
    assert haz.active_incident_level is None

    # Fire weather danger is independently reported as Extreme
    assert haz.fire_weather_level == "Extreme"
    assert haz.fire_weather_score >= 80.0

    # Overall advisory threat level is capped at MODERATE (Fire Weather Alert)
    assert level == DisasterAssessmentLevel.MODERATE
    assert score <= 40.0
    assert level not in (DisasterAssessmentLevel.HIGH, DisasterAssessmentLevel.CRITICAL)

    # Consequences are LOW because no active fire hazard is present
    assert con.consequence_score == 0.0
    assert con.consequence_tier == DisasterAssessmentLevel.LOW


def test_active_fire_with_supporting_environmental_evidence():
    """Active fire with supporting environmental conditions (uncorroborated) yields SUSPECTED and HIGH severity."""
    cv = _make_cv_evidence(fire=0.88, smoke=0.08, neutral=0.04)
    env = _make_env_evidence(temp=34.0, rh=22.0, fwi=32.0, rating="Very High")
    context = _make_context(features_count=2, settlement_dist=800.0)

    fusion = MultimodalFusionEngine.fuse([cv, env], context)
    level, score, haz, exp, con, _, _ = HeuristicRiskAssessor.evaluate_detailed(DisasterType.WILDFIRE, fusion)
    status, severity = HeuristicRiskAssessor.determine_incident_status(
        fusion.active_evidence_state, haz.hazard_level, is_corroborated=fusion.is_corroborated
    )

    assert status == IncidentStatus.SUSPECTED
    assert severity == DisasterAssessmentLevel.HIGH
    assert haz.fire_weather_level == "Very High"
    assert level == DisasterAssessmentLevel.CRITICAL
    assert con.consequence_tier in (DisasterAssessmentLevel.HIGH, DisasterAssessmentLevel.CRITICAL)


def test_active_incident_with_missing_environmental_data():
    """Active fire is detected even when environmental weather stream is unavailable."""
    cv = _make_cv_evidence(fire=0.90, smoke=0.05, neutral=0.05)
    env = EvidenceCollector.create_unavailable_environmental_evidence("Provider unreachable")
    context = _make_context(features_count=1, settlement_dist=1200.0)

    fusion = MultimodalFusionEngine.fuse([cv, env], context)
    level, score, haz, exp, con, _, _ = HeuristicRiskAssessor.evaluate_detailed(DisasterType.WILDFIRE, fusion)
    status, severity = HeuristicRiskAssessor.determine_incident_status(
        fusion.active_evidence_state, haz.hazard_level, is_corroborated=fusion.is_corroborated
    )

    assert status == IncidentStatus.SUSPECTED
    assert severity == DisasterAssessmentLevel.HIGH
    assert haz.fire_weather_score is None
    assert haz.fire_weather_level is None
    assert "environmental_weather_and_fwi" in fusion.missing_streams
    assert level == DisasterAssessmentLevel.CRITICAL


def test_conflicting_incident_evidence_preserves_highest_severity():
    """
    Requirement 10: Conflicting evidence exists (flames observed during heavy rain).
    Preserves highest credible incident severity without downgrade and flags elevated uncertainty.
    """
    cv = _make_cv_evidence(fire=0.85, smoke=0.10, neutral=0.05)
    env = _make_env_evidence(temp=18.0, rh=92.0, fwi=1.0, rating="Low", rain=15.0)
    context = _make_context(features_count=2, settlement_dist=900.0)

    fusion = MultimodalFusionEngine.fuse([cv, env], context)
    assert len(fusion.conflicting_streams) > 0

    level, score, haz, exp, con, has_conflicts, uncertainty_qual = HeuristicRiskAssessor.evaluate_detailed(
        DisasterType.WILDFIRE, fusion
    )
    status, severity = HeuristicRiskAssessor.determine_incident_status(
        fusion.active_evidence_state, haz.hazard_level, is_corroborated=fusion.is_corroborated
    )

    assert has_conflicts is True
    assert status == IncidentStatus.SUSPECTED
    assert severity == DisasterAssessmentLevel.HIGH
    assert level == DisasterAssessmentLevel.CRITICAL
    assert uncertainty_qual is not None
    assert "ELEVATED_UNCERTAINTY" in uncertainty_qual
    assert "without downgrade" in uncertainty_qual


def test_fire_weather_danger_never_independently_produces_high_or_critical_severity():
    """Weather-only data (even extreme FWI=60) with missing imagery must NEVER produce HIGH or CRITICAL incident severity."""
    cv = EvidenceCollector.create_unavailable_cv_evidence("No image uploaded")
    env = _make_env_evidence(temp=42.0, rh=8.0, fwi=60.0, rating="Extreme")
    context = _make_context(features_count=3, settlement_dist=500.0)

    fusion = MultimodalFusionEngine.fuse([cv, env], context)
    level, score, haz, exp, con, _, _ = HeuristicRiskAssessor.evaluate_detailed(DisasterType.WILDFIRE, fusion)
    status, severity = HeuristicRiskAssessor.determine_incident_status(
        fusion.active_evidence_state, haz.hazard_level, is_corroborated=fusion.is_corroborated
    )

    assert status == IncidentStatus.INSUFFICIENT_EVIDENCE
    assert severity is None
    assert haz.hazard_score == 0.0
    assert haz.hazard_level == DisasterAssessmentLevel.LOW
    assert haz.fire_weather_level == "Extreme"

    # Threat tier is capped at MODERATE (advisory level); NEVER HIGH or CRITICAL
    assert level == DisasterAssessmentLevel.MODERATE
    assert level not in (DisasterAssessmentLevel.HIGH, DisasterAssessmentLevel.CRITICAL)


# ---------------------------------------------------------------------------
# CONCERN C: Geographic Exposure & Null Safety Scenarios
# ---------------------------------------------------------------------------

def test_geographic_features_available_verified_exposure():
    """When geographic features exist nearby, exposure score is computed and verified."""
    cv = _make_cv_evidence(fire=0.80, smoke=0.10, neutral=0.10)
    env = _make_env_evidence(fwi=18.0, rating="High")
    context = _make_context(features_count=3, settlement_dist=800.0, hospital_dist=1500.0)

    fusion = MultimodalFusionEngine.fuse([cv, env], context)
    _, _, _, exp, con, _, _ = HeuristicRiskAssessor.evaluate_detailed(DisasterType.WILDFIRE, fusion)

    assert exp.exposure_score is not None
    assert exp.exposure_score >= 70.0
    assert exp.exposure_level == "CRITICAL"
    assert exp.settlement_distance_meters == 800.0
    assert exp.hospital_distance_meters == 1500.0
    assert con.consequence_score is not None
    assert con.consequence_tier in (DisasterAssessmentLevel.HIGH, DisasterAssessmentLevel.CRITICAL)


def test_verified_low_geographic_exposure():
    """When features are evaluated but no sensitive infrastructure is within reach, exposure is verified LOW."""
    cv = _make_cv_evidence(fire=0.80, smoke=0.10, neutral=0.10)
    env = _make_env_evidence(fwi=18.0, rating="High")
    # 5 features evaluated (e.g. roads, remote points), nearest settlement > 5000m, no hospitals
    context = _make_context(features_count=5, settlement_dist=6000.0, hospital_dist=None)

    fusion = MultimodalFusionEngine.fuse([cv, env], context)
    _, _, _, exp, con, _, _ = HeuristicRiskAssessor.evaluate_detailed(DisasterType.WILDFIRE, fusion)

    assert exp.exposure_score is not None
    assert exp.exposure_score <= 20.0
    assert exp.exposure_level == "LOW"
    assert con.consequence_score is not None
    assert con.consequence_tier in (DisasterAssessmentLevel.LOW, DisasterAssessmentLevel.MODERATE)


def test_no_geographic_features_unverified_exposure():
    """
    When 0 geographic features are evaluated, exposure score must be null (None)
    and exposure level must explicitly state UNVERIFIED (NO_LOCAL_FEATURES).
    """
    cv = _make_cv_evidence(fire=0.80, smoke=0.10, neutral=0.10)
    env = _make_env_evidence(fwi=18.0, rating="High")
    context = _make_context(features_count=0)  # Empty catalog

    fusion = MultimodalFusionEngine.fuse([cv, env], context)
    _, _, _, exp, con, _, _ = HeuristicRiskAssessor.evaluate_detailed(DisasterType.WILDFIRE, fusion)

    # Must NOT become 0.0
    assert exp.exposure_score is None
    assert exp.exposure_level == "UNVERIFIED (NO_LOCAL_FEATURES)"
    assert any("UNVERIFIED" in f for f in exp.factors)


def test_missing_exposure_handled_safely_in_consequences():
    """
    When active hazard is present but exposure is unverified, consequence score must be null (None)
    and tier must be INSUFFICIENT_DATA (not 0.0 or LOW).
    """
    cv = _make_cv_evidence(fire=0.85, smoke=0.10, neutral=0.05)
    env = _make_env_evidence(fwi=20.0, rating="High")
    context = _make_context(features_count=0)  # 0 features

    fusion = MultimodalFusionEngine.fuse([cv, env], context)
    level, score, haz, exp, con, _, _ = HeuristicRiskAssessor.evaluate_detailed(DisasterType.WILDFIRE, fusion)

    assert exp.exposure_score is None
    assert con.consequence_score is None
    assert con.consequence_tier == DisasterAssessmentLevel.INSUFFICIENT_DATA
    assert "UNVERIFIED" in con.rationale
    # Composite risk index should be based directly on active hazard without deflating
    assert score == haz.hazard_score


def test_database_unavailable_error_preservation():
    """When the configured database is unreachable, PostGISUnavailableError must be raised (HTTP 503)."""
    service = MultimodalIntelligenceService()

    # Mock geospatial service to raise PostGISUnavailableError
    service.geospatial.service.analyze_exposure = MagicMock(
        side_effect=PostGISUnavailableError("Connection to 127.0.0.1:5432 lost")
    )

    obs = IncidentObservationInput(
        disaster_type=DisasterType.WILDFIRE,
        latitude=30.3256,
        longitude=78.0422,
        search_radius_meters=5000.0,
    )

    fake_db = MagicMock()
    with pytest.raises(PostGISUnavailableError) as exc_info:
        service.analyze_observation(observation=obs, db=fake_db)

    assert "Connection to 127.0.0.1:5432 lost" in str(exc_info.value)


# ---------------------------------------------------------------------------
# API Response Schema & Serialization Verification
# ---------------------------------------------------------------------------

def test_api_response_schema_distinct_semantic_fields_and_json_serialization():
    """Requirement 8: Verifies that the full API response schema contains all distinct fields and serializes missing severity as null in JSON."""
    service = MultimodalIntelligenceService()

    # Deterministic mock setup
    service.vision.collect_evidence = MagicMock(return_value=_make_cv_evidence(0.01, 0.02, 0.97))
    service.environmental.collect_evidence = MagicMock(return_value=_make_env_evidence(temp=38.0, rh=15.0, fwi=44.0, rating="Extreme"))
    service.geospatial.collect_evidence = MagicMock(return_value=(
        EvidenceCollector.create_geospatial_evidence({}, 0, "local_vector_catalog"),
        _make_context(features_count=0),
    ))

    obs = IncidentObservationInput(
        disaster_type=DisasterType.WILDFIRE,
        latitude=30.3256,
        longitude=78.0422,
        search_radius_meters=5000.0,
    )

    assessment: MultimodalIntelligenceAssessment = service.analyze_observation(observation=obs)

    # 1. Inspect Python model attributes
    assert assessment.incident_status == IncidentStatus.UNCONFIRMED
    assert assessment.incident_severity is None  # Unassessed / unavailable (None in Python, null in JSON)
    assert assessment.fire_weather_danger == "Extreme"
    assert assessment.fire_weather_score >= 80.0
    assert assessment.geographic_exposure == "UNVERIFIED (NO_LOCAL_FEATURES)"
    assert assessment.potential_consequences == DisasterAssessmentLevel.LOW
    assert assessment.exposure_assessment.exposure_score is None
    assert assessment.consequence_assessment.consequence_score == 0.0  # s_haz is 0
    assert assessment.evidence_summary is not None
    assert "UNCONFIRMED" in assessment.evidence_summary
    assert "Extreme" in assessment.evidence_summary
    assert "UNASSESSED" in assessment.evidence_summary

    # 2. Verify JSON serialization and roundtrip
    json_bytes = assessment.model_dump_json()
    data = json.loads(json_bytes)

    # Check root fields in serialized JSON
    assert data["incident_status"] == "UNCONFIRMED"
    assert data["incident_severity"] is None  # Serialized as null in JSON!
    assert ('"incident_severity": null' in json_bytes) or ('"incident_severity":null' in json_bytes)
    assert data["fire_weather_danger"] == "Extreme"
    assert data["fire_weather_score"] >= 80.0
    assert data["geographic_exposure"] == "UNVERIFIED (NO_LOCAL_FEATURES)"
    assert data["potential_consequences"] == "LOW"
    assert data["exposure_assessment"]["exposure_score"] is None  # null in JSON!
    assert "evidence_summary" in data
    assert "uncertainty" in data
