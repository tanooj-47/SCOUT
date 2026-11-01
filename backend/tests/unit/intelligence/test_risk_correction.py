"""
backend/tests/unit/intelligence/test_risk_correction.py
Unit tests for Milestone 11 Correction A (Hazard/Exposure Separation),
Correction B (Neutral Classification Semantics & 5 Visual Evidence States),
Correction C (Empty Catalog Unverified Exposure),
and Correction D (Contradiction and Conflict Handling).
"""

import pytest

from app.geospatial.schemas import FeatureCategory, GeographicFeatureItem, SpatialRelationship
from app.intelligence.context import ContextAggregator
from app.intelligence.evidence import EvidenceCollector
from app.intelligence.fusion import MultimodalFusionEngine
from app.intelligence.risk import HeuristicRiskAssessor
from app.intelligence.schemas import (
    ContextSummary,
    DisasterAssessmentLevel,
    VisualEvidenceState,
)
from app.schemas.incident import DisasterType


def _make_context(settlement_dist: float = 800.0, hosp_dist: float = 1200.0, water: bool = False) -> ContextSummary:
    features = [
        GeographicFeatureItem(
            id="feat-settlement",
            name="Dehradun Settlement",
            category=FeatureCategory.SETTLEMENT,
            distance_meters=settlement_dist,
            relationship=SpatialRelationship.WITHIN_RADIUS,
            source_dataset="natural_earth",
        ),
        GeographicFeatureItem(
            id="feat-hosp",
            name="City Hospital",
            category=FeatureCategory.INFRASTRUCTURE,
            distance_meters=hosp_dist,
            relationship=SpatialRelationship.WITHIN_RADIUS,
            source_dataset="osm_hospitals",
        ),
    ]
    if water:
        features.append(
            GeographicFeatureItem(
                id="feat-river",
                name="Ganga Canal",
                category=FeatureCategory.WATER_BODY,
                distance_meters=400.0,
                relationship=SpatialRelationship.WITHIN_RADIUS,
                source_dataset="osm_water",
            )
        )
    return ContextAggregator.aggregate(features)


def test_scenario_1_high_exposure_zero_hazard():
    """1. High exposure + negligible hazard -> LOW threat (Proximity never creates wildfire hazard)."""
    cv = EvidenceCollector.create_cv_evidence(
        probabilities={"fire": 0.01, "smoke": 0.01, "neutral": 0.98},
        model_name="BaselineCNN",
        checkpoint_path="baseline_cnn_best.pt",
    )
    env = EvidenceCollector.create_environmental_evidence(
        weather_data={
            "temperature_c": 15.0,
            "relative_humidity_pct": 85.0,
            "fwi_indices": {"fire_weather_index_fwi": 0.5, "danger_rating": "Low"},
        },
        provider="open-meteo",
        model_or_dataset="best_match",
        is_stale=False,
    )
    # Very high exposure: settlement at 300m, hospital at 500m
    context = _make_context(settlement_dist=300.0, hosp_dist=500.0)
    fusion = MultimodalFusionEngine.fuse([cv, env], context)

    level, score, haz, exp, con, _, _ = HeuristicRiskAssessor.evaluate_detailed(DisasterType.WILDFIRE, fusion)
    assert haz.hazard_level == DisasterAssessmentLevel.LOW
    assert haz.hazard_score <= 2.0
    assert exp.exposure_score >= 70.0
    assert exp.exposure_level == "CRITICAL"
    assert con.consequence_tier == DisasterAssessmentLevel.LOW
    assert level == DisasterAssessmentLevel.LOW
    assert score <= 2.0


def test_scenario_2_high_exposure_moderate_hazard():
    """2. High exposure + moderate hazard -> MODERATE threat with consequence qualification."""
    cv = EvidenceCollector.create_cv_evidence(
        probabilities={"fire": 0.25, "smoke": 0.35, "neutral": 0.40},
        model_name="BaselineCNN",
        checkpoint_path="baseline_cnn_best.pt",
    )
    env = EvidenceCollector.create_environmental_evidence(
        weather_data={
            "temperature_c": 28.0,
            "relative_humidity_pct": 40.0,
            "fwi_indices": {"fire_weather_index_fwi": 12.0, "danger_rating": "High"},
        },
        provider="open-meteo",
        model_or_dataset="best_match",
        is_stale=False,
    )
    context = _make_context(settlement_dist=600.0, hosp_dist=900.0)
    fusion = MultimodalFusionEngine.fuse([cv, env], context)

    level, score, haz, exp, con, _, _ = HeuristicRiskAssessor.evaluate_detailed(DisasterType.WILDFIRE, fusion)
    assert haz.hazard_level in (DisasterAssessmentLevel.MODERATE, DisasterAssessmentLevel.HIGH)
    assert exp.exposure_level == "CRITICAL"
    assert con.consequence_tier in (DisasterAssessmentLevel.MODERATE, DisasterAssessmentLevel.HIGH)
    assert level == DisasterAssessmentLevel.MODERATE
    assert 25.0 <= score < 50.0


def test_scenario_3_high_exposure_high_hazard():
    """3. High exposure + high hazard -> CRITICAL threat."""
    cv = EvidenceCollector.create_cv_evidence(
        probabilities={"fire": 0.82, "smoke": 0.12, "neutral": 0.06},
        model_name="BaselineCNN",
        checkpoint_path="baseline_cnn_best.pt",
    )
    env = EvidenceCollector.create_environmental_evidence(
        weather_data={
            "temperature_c": 38.0,
            "relative_humidity_pct": 18.0,
            "fwi_indices": {"fire_weather_index_fwi": 35.0, "danger_rating": "Very High"},
        },
        provider="open-meteo",
        model_or_dataset="best_match",
        is_stale=False,
    )
    context = _make_context(settlement_dist=700.0, hosp_dist=1100.0)
    fusion = MultimodalFusionEngine.fuse([cv, env], context)

    level, score, haz, exp, con, _, _ = HeuristicRiskAssessor.evaluate_detailed(DisasterType.WILDFIRE, fusion)
    assert haz.hazard_level in (DisasterAssessmentLevel.HIGH, DisasterAssessmentLevel.CRITICAL)
    assert exp.exposure_level == "CRITICAL"
    assert con.consequence_tier == DisasterAssessmentLevel.CRITICAL
    assert level == DisasterAssessmentLevel.CRITICAL
    assert score >= 75.0


def test_scenario_4_low_exposure_high_hazard():
    """4. Low exposure + high hazard -> HIGH hazard, LOW exposure, contained consequence."""
    cv = EvidenceCollector.create_cv_evidence(
        probabilities={"fire": 0.80, "smoke": 0.15, "neutral": 0.05},
        model_name="BaselineCNN",
        checkpoint_path="baseline_cnn_best.pt",
    )
    env = EvidenceCollector.create_environmental_evidence(
        weather_data={
            "temperature_c": 34.0,
            "relative_humidity_pct": 22.0,
            "fwi_indices": {"fire_weather_index_fwi": 28.0, "danger_rating": "Very High"},
        },
        provider="open-meteo",
        model_or_dataset="best_match",
        is_stale=False,
    )
    # Remote wilderness: 10 features surveyed, no settlements/hospitals nearby
    surveyed_context = ContextSummary(
        settlements_found=0,
        closest_settlement_distance_meters=None,
        hospitals_found=0,
        closest_hospital_distance_meters=None,
        fire_stations_found=0,
        road_corridors_found=0,
        water_bodies_found=0,
        total_features_evaluated=10,
    )
    fusion = MultimodalFusionEngine.fuse([cv, env], surveyed_context)

    level, score, haz, exp, con, _, _ = HeuristicRiskAssessor.evaluate_detailed(DisasterType.WILDFIRE, fusion)
    assert haz.hazard_level in (DisasterAssessmentLevel.HIGH, DisasterAssessmentLevel.CRITICAL)
    assert exp.exposure_level == "LOW"
    assert con.consequence_tier == DisasterAssessmentLevel.LOW
    # Threat is high due to intense fire, but consequence is low
    assert level == DisasterAssessmentLevel.HIGH


def test_scenario_5_zero_hazard_hospital_present():
    """5. Zero hazard + hospital present -> LOW threat."""
    cv = EvidenceCollector.create_cv_evidence(
        probabilities={"fire": 0.00, "smoke": 0.00, "neutral": 1.00},
        model_name="BaselineCNN",
        checkpoint_path="baseline_cnn_best.pt",
    )
    env = EvidenceCollector.create_environmental_evidence(
        weather_data={
            "temperature_c": 12.0,
            "relative_humidity_pct": 90.0,
            "fwi_indices": {"fire_weather_index_fwi": 0.2, "danger_rating": "Low"},
        },
        provider="open-meteo",
        model_or_dataset="best_match",
        is_stale=False,
    )
    # Hospital directly adjacent (150m away)
    features = [
        GeographicFeatureItem(
            id="f-hosp",
            name="District General Hospital",
            category=FeatureCategory.INFRASTRUCTURE,
            distance_meters=150.0,
            relationship=SpatialRelationship.WITHIN_RADIUS,
            source_dataset="osm_hospitals",
        )
    ]
    context = ContextAggregator.aggregate(features)
    fusion = MultimodalFusionEngine.fuse([cv, env], context)

    level, score, haz, exp, con, _, _ = HeuristicRiskAssessor.evaluate_detailed(DisasterType.WILDFIRE, fusion)
    assert haz.hazard_level == DisasterAssessmentLevel.LOW
    assert haz.hazard_score <= 2.0
    assert level == DisasterAssessmentLevel.LOW
    assert score <= 2.0


def test_scenario_6_visual_only_neutral_image_high_exposure():
    """6. Visual-only neutral image + high exposure -> LOW threat."""
    cv = EvidenceCollector.create_cv_evidence(
        probabilities={"fire": 0.02, "smoke": 0.03, "neutral": 0.95},
        model_name="BaselineCNN",
        checkpoint_path="baseline_cnn_best.pt",
    )
    unavail_env = EvidenceCollector.create_unavailable_environmental_evidence("Weather service down")
    context = _make_context(settlement_dist=400.0, hosp_dist=600.0)
    fusion = MultimodalFusionEngine.fuse([cv, unavail_env], context)

    level, score, haz, exp, con, _, _ = HeuristicRiskAssessor.evaluate_detailed(DisasterType.WILDFIRE, fusion)
    assert haz.hazard_score == 0.0
    assert haz.hazard_level == DisasterAssessmentLevel.LOW
    assert level == DisasterAssessmentLevel.LOW
    assert score == 0.0


def test_scenario_7_environmental_only_extreme_fwi_low_exposure():
    """7. Environmental-only extreme FWI + low exposure -> Active hazard 0.0, elevated fire weather, MODERATE threat."""
    unavail_cv = EvidenceCollector.create_unavailable_cv_evidence("No image available")
    env = EvidenceCollector.create_environmental_evidence(
        weather_data={
            "temperature_c": 42.0,
            "relative_humidity_pct": 12.0,
            "fwi_indices": {"fire_weather_index_fwi": 38.0, "danger_rating": "Extreme"},
        },
        provider="open-meteo",
        model_or_dataset="best_match",
        is_stale=False,
    )
    surveyed_context = ContextSummary(
        settlements_found=0,
        closest_settlement_distance_meters=None,
        hospitals_found=0,
        closest_hospital_distance_meters=None,
        fire_stations_found=0,
        road_corridors_found=0,
        water_bodies_found=0,
        total_features_evaluated=10,
    )
    fusion = MultimodalFusionEngine.fuse([unavail_cv, env], surveyed_context)

    level, score, haz, exp, con, _, _ = HeuristicRiskAssessor.evaluate_detailed(DisasterType.WILDFIRE, fusion)
    # Active physical incident hazard is 0.0: weather alone never establishes an active fire!
    assert haz.hazard_score == 0.0
    assert haz.hazard_level == DisasterAssessmentLevel.LOW
    assert haz.fire_weather_score >= 80.0
    assert haz.fire_weather_level == "Extreme"
    assert exp.exposure_level == "LOW"
    assert con.consequence_score == 0.0
    assert con.consequence_tier == DisasterAssessmentLevel.LOW
    # Threat is MODERATE fire weather alert/watch (NOT HIGH or CRITICAL active disaster)
    assert level == DisasterAssessmentLevel.MODERATE
    assert 25.0 <= score <= 40.0


def test_scenario_8_critical_override():
    """8. Critical override: visual fire >= 0.85 + settlement <= 1000m -> CRITICAL."""
    cv = EvidenceCollector.create_cv_evidence(
        probabilities={"fire": 0.88, "smoke": 0.08, "neutral": 0.04},
        model_name="BaselineCNN",
        checkpoint_path="baseline_cnn_best.pt",
    )
    env = EvidenceCollector.create_environmental_evidence(
        weather_data={
            "temperature_c": 22.0,
            "relative_humidity_pct": 60.0,
            "fwi_indices": {"fire_weather_index_fwi": 8.0, "danger_rating": "Moderate"},
        },
        provider="open-meteo",
        model_or_dataset="best_match",
        is_stale=False,
    )
    context = _make_context(settlement_dist=950.0)
    fusion = MultimodalFusionEngine.fuse([cv, env], context)

    level, score = HeuristicRiskAssessor.evaluate(DisasterType.WILDFIRE, fusion)
    assert level == DisasterAssessmentLevel.CRITICAL
    assert score >= 75.0


def test_scenario_9_non_wildfire_insufficient_data():
    """9. Non-wildfire disaster types -> INSUFFICIENT_DATA."""
    context = _make_context()
    fusion = MultimodalFusionEngine.fuse([], context)

    level_f, score_f = HeuristicRiskAssessor.evaluate(DisasterType.FLOOD, fusion)
    assert level_f == DisasterAssessmentLevel.INSUFFICIENT_DATA
    assert score_f is None

    level_e, score_e = HeuristicRiskAssessor.evaluate(DisasterType.EARTHQUAKE, fusion)
    assert level_e == DisasterAssessmentLevel.INSUFFICIENT_DATA
    assert score_e is None


def test_neutral_camera_plus_extreme_fwi_separates_hazard_and_fire_weather():
    """Neutral classifier view gives 0.0 active hazard; fire weather danger is tracked independently."""
    cv = EvidenceCollector.create_cv_evidence(
        probabilities={"fire": 0.01, "smoke": 0.01, "neutral": 0.98},
        model_name="BaselineCNN",
        checkpoint_path="baseline_cnn_best.pt",
    )
    env = EvidenceCollector.create_environmental_evidence(
        weather_data={
            "temperature_c": 41.0,
            "relative_humidity_pct": 14.0,
            "fwi_indices": {"fire_weather_index_fwi": 36.0, "danger_rating": "Very High"},
        },
        provider="open-meteo",
        model_or_dataset="best_match",
        is_stale=False,
    )
    context = _make_context(settlement_dist=1200.0)
    fusion = MultimodalFusionEngine.fuse([cv, env], context)

    assert fusion.visual_evidence_state == VisualEvidenceState.NO_SUPPORTING_EVIDENCE

    level, score, haz, exp, con, _, _ = HeuristicRiskAssessor.evaluate_detailed(DisasterType.WILDFIRE, fusion)
    # Weather-only data (even extreme FWI) must NEVER establish an active wildfire incident
    assert haz.hazard_score == 0.0
    assert haz.hazard_level == DisasterAssessmentLevel.LOW
    assert haz.visual_evidence_state == VisualEvidenceState.NO_SUPPORTING_EVIDENCE
    assert "no_supporting_visual_evidence" in haz.visual_explanation
    # But fire weather danger is tracked independently
    assert haz.fire_weather_score is not None
    assert haz.fire_weather_score >= 80.0
    assert haz.fire_weather_level == "Very High"
    # Overall threat tier is MODERATE fire weather watch, NOT HIGH or CRITICAL active wildfire
    assert level == DisasterAssessmentLevel.MODERATE
    assert score <= 40.0


def test_missing_imagery_visual_evidence_state():
    """Missing imagery must be classified as MISSING_EVIDENCE and not confused with neutral."""
    unavail_cv = EvidenceCollector.create_unavailable_cv_evidence("No image uploaded")
    env = EvidenceCollector.create_environmental_evidence(
        weather_data={
            "temperature_c": 32.0,
            "relative_humidity_pct": 25.0,
            "fwi_indices": {"fire_weather_index_fwi": 18.0, "danger_rating": "High"},
        },
        provider="open-meteo",
        model_or_dataset="best_match",
        is_stale=False,
    )
    context = _make_context()
    fusion = MultimodalFusionEngine.fuse([unavail_cv, env], context)

    assert fusion.visual_evidence_state == VisualEvidenceState.MISSING_EVIDENCE

    _, _, haz, _, _, _, _ = HeuristicRiskAssessor.evaluate_detailed(DisasterType.WILDFIRE, fusion)
    assert haz.visual_evidence_state == VisualEvidenceState.MISSING_EVIDENCE


def test_empty_catalog_unverified_exposure():
    """When catalog holds 0 features, exposure must be marked UNVERIFIED (NO_LOCAL_FEATURES)."""
    cv = EvidenceCollector.create_cv_evidence(
        probabilities={"fire": 0.70, "smoke": 0.20, "neutral": 0.10},
        model_name="BaselineCNN",
        checkpoint_path="baseline_cnn_best.pt",
    )
    env = EvidenceCollector.create_environmental_evidence(
        weather_data={
            "temperature_c": 30.0,
            "relative_humidity_pct": 30.0,
            "fwi_indices": {"fire_weather_index_fwi": 20.0, "danger_rating": "High"},
        },
        provider="open-meteo",
        model_or_dataset="best_match",
        is_stale=False,
    )
    empty_context = ContextSummary(
        settlements_found=0,
        closest_settlement_distance_meters=None,
        hospitals_found=0,
        closest_hospital_distance_meters=None,
        fire_stations_found=0,
        road_corridors_found=0,
        water_bodies_found=0,
        total_features_evaluated=0,
    )
    fusion = MultimodalFusionEngine.fuse([cv, env], empty_context)

    _, _, haz, exp, con, _, _ = HeuristicRiskAssessor.evaluate_detailed(DisasterType.WILDFIRE, fusion)
    assert exp.exposure_score is None
    assert exp.exposure_level == "UNVERIFIED (NO_LOCAL_FEATURES)"
    assert con.consequence_score is None
    assert con.consequence_tier == DisasterAssessmentLevel.INSUFFICIENT_DATA
    assert "UNVERIFIED" in con.rationale


def test_correction_d_conflicting_evidence_preserves_critical_severity():
    """TASK 3: Cross-modal contradiction must NOT suppress or downgrade CRITICAL life-safety warning."""
    # Conflict: visual fire detected (0.82) near settlement (500m) while heavy rainfall recorded (15mm)
    cv = EvidenceCollector.create_cv_evidence(
        probabilities={"fire": 0.82, "smoke": 0.10, "neutral": 0.08},
        model_name="BaselineCNN",
        checkpoint_path="baseline_cnn_best.pt",
    )
    env = EvidenceCollector.create_environmental_evidence(
        weather_data={
            "temperature_c": 18.0,
            "precipitation_mm": 15.0,  # Heavy rain
            "fwi_indices": {"fire_weather_index_fwi": 2.0, "danger_rating": "Low"},
        },
        provider="open-meteo",
        model_or_dataset="best_match",
        is_stale=False,
    )
    context = _make_context(settlement_dist=500.0)  # High exposure
    fusion = MultimodalFusionEngine.fuse([cv, env], context)

    assert len(fusion.conflicting_streams) >= 1

    level, score, _, _, _, has_conflicts, uncertainty_qual = HeuristicRiskAssessor.evaluate_detailed(
        DisasterType.WILDFIRE, fusion
    )
    assert has_conflicts is True
    assert uncertainty_qual is not None
    assert "ELEVATED_UNCERTAINTY" in uncertainty_qual
    # Life-safety policy: Highest credible severity (CRITICAL) is preserved without downgrade!
    assert level == DisasterAssessmentLevel.CRITICAL


def test_independent_satellite_thermal_anomaly_evidence():
    """TASK 2: Independent satellite thermal-anomaly evidence establishes active hazard without camera."""
    sat = EvidenceCollector.create_satellite_evidence(
        satellite_data={"thermal_anomaly": True, "confidence": 92.0},
        source_name="VIIRS_S-NPP",
        brightness_temp_k=365.2,
        frp_mw=45.8,
    )
    env = EvidenceCollector.create_environmental_evidence(
        weather_data={
            "temperature_c": 32.0,
            "relative_humidity_pct": 25.0,
            "fwi_indices": {"fire_weather_index_fwi": 22.0, "danger_rating": "Very High"},
        },
        provider="open-meteo",
        model_or_dataset="best_match",
        is_stale=False,
    )
    context = _make_context(settlement_dist=1500.0)
    fusion = MultimodalFusionEngine.fuse([sat, env], context)

    assert fusion.has_satellite is True
    assert fusion.active_evidence_state == VisualEvidenceState.SATELLITE_THERMAL_ANOMALY

    level, score, haz, exp, con, _, _ = HeuristicRiskAssessor.evaluate_detailed(DisasterType.WILDFIRE, fusion)
    assert haz.hazard_score >= 80.0
    assert haz.hazard_level == DisasterAssessmentLevel.CRITICAL
    assert haz.active_incident_evidence == VisualEvidenceState.SATELLITE_THERMAL_ANOMALY
    assert level == DisasterAssessmentLevel.CRITICAL


def test_independent_field_confirmed_evidence():
    """TASK 2: Field-confirmed incident by emergency personnel establishes CRITICAL hazard."""
    field = EvidenceCollector.create_field_evidence(
        report_data={"location": "Forest Sector 4", "is_confirmed": True, "reported_by": "Ranger Team B"},
        source_name="Uttarakhand_Forest_Guard",
        is_confirmed=True,
    )
    context = _make_context(settlement_dist=800.0)
    fusion = MultimodalFusionEngine.fuse([field], context)

    assert fusion.has_field_report is True
    assert fusion.active_evidence_state == VisualEvidenceState.FIELD_CONFIRMED

    level, score, haz, exp, con, _, _ = HeuristicRiskAssessor.evaluate_detailed(DisasterType.WILDFIRE, fusion)
    assert haz.hazard_score >= 90.0
    assert haz.hazard_level == DisasterAssessmentLevel.CRITICAL
    assert level == DisasterAssessmentLevel.CRITICAL


def test_raw_class_scores_and_heuristic_decision_threshold_metadata():
    """TASK 4: Softmax probabilities preserved as raw scores; 0.50 documented as engineering heuristic."""
    probs = {"fire": 0.52, "smoke": 0.28, "neutral": 0.20}
    item = EvidenceCollector.create_cv_evidence(
        probabilities=probs,
        model_name="BaselineCNN",
        checkpoint_path="artifacts/checkpoints/m07_phase7c_v2/baseline_cnn_best.pt",
    )
    prov = item.provenance
    assert "raw_class_scores" in prov
    assert prov["raw_class_scores"]["fire"] == 0.52
    assert prov["raw_class_scores"]["smoke"] == 0.28
    assert prov["raw_class_scores"]["neutral"] == 0.20
    assert prov["decision_threshold"] == 0.50
    assert prov["decision_threshold_status"] == "uncalibrated_engineering_heuristic"
    assert any("uncalibrated model score" in c for c in item.caveats)
    assert any("engineering heuristic" in c for c in item.caveats)


def test_neutral_classification_with_nearby_settlement_low_threat():
    """TASK 2: Neutral image near settlement yields S_haz=0.0, S_con=0.0, threat LOW (no active hazard)."""
    cv = EvidenceCollector.create_cv_evidence(
        probabilities={"fire": 0.01, "smoke": 0.02, "neutral": 0.97},
        model_name="BaselineCNN",
        checkpoint_path="baseline_cnn_best.pt",
    )
    env = EvidenceCollector.create_environmental_evidence(
        weather_data={
            "temperature_c": 22.0,
            "relative_humidity_pct": 55.0,
            "fwi_indices": {"fire_weather_index_fwi": 4.5, "danger_rating": "Low"},
        },
        provider="open-meteo",
        model_or_dataset="best_match",
        is_stale=False,
    )
    context = _make_context(settlement_dist=300.0, hosp_dist=500.0)  # Extreme exposure
    fusion = MultimodalFusionEngine.fuse([cv, env], context)

    level, score, haz, exp, con, _, _ = HeuristicRiskAssessor.evaluate_detailed(DisasterType.WILDFIRE, fusion)
    assert haz.hazard_score == 0.0
    assert haz.hazard_level == DisasterAssessmentLevel.LOW
    assert exp.exposure_level == "CRITICAL"
    assert con.consequence_score == 0.0
    assert con.consequence_tier == DisasterAssessmentLevel.LOW
    assert level == DisasterAssessmentLevel.LOW
    assert score == 0.0

