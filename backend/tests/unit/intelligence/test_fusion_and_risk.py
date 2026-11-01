"""
backend/tests/unit/intelligence/test_fusion_and_risk.py
Unit tests for Milestone 11 Fusion, Heuristic Risk, and Explainability generators.
"""

from datetime import datetime, timezone
import pytest

from app.geospatial.schemas import FeatureCategory, GeographicFeatureItem, SpatialRelationship
from app.intelligence.context import ContextAggregator
from app.intelligence.evidence import EvidenceCollector
from app.intelligence.explanations import ExplanationGenerator
from app.intelligence.fusion import MultimodalFusionEngine
from app.intelligence.risk import HeuristicRiskAssessor
from app.intelligence.schemas import (
    ContextSummary,
    CoordinateLocation,
    DisasterAssessmentLevel,
    EvidenceCategory,
    EvidenceStatus,
)
from app.schemas.incident import DisasterType


def _make_dummy_context(settlement_dist: float = 1200.0, hosp_dist: float = 2500.0) -> ContextSummary:
    features = [
        GeographicFeatureItem(
            id="f-1",
            name="Dehradun",
            category=FeatureCategory.SETTLEMENT,
            distance_meters=settlement_dist,
            relationship=SpatialRelationship.WITHIN_RADIUS,
            source_dataset="natural_earth",
        ),
        GeographicFeatureItem(
            id="f-2",
            name="City Hospital",
            category=FeatureCategory.INFRASTRUCTURE,
            distance_meters=hosp_dist,
            relationship=SpatialRelationship.WITHIN_RADIUS,
            source_dataset="osm_hospitals",
        ),
    ]
    return ContextAggregator.aggregate(features)


def test_fusion_all_modalities_present():
    cv = EvidenceCollector.create_cv_evidence(
        probabilities={"fire": 0.85, "smoke": 0.10, "neutral": 0.05},
        model_name="BaselineCNN",
        checkpoint_path="baseline_cnn_best.pt",
    )
    env = EvidenceCollector.create_environmental_evidence(
        weather_data={
            "temperature_c": 35.0,
            "relative_humidity_pct": 20.0,
            "fwi_indices": {"fire_weather_index_fwi": 28.5, "danger_rating": "Very High"},
        },
        provider="open-meteo",
        model_or_dataset="best_match",
        is_stale=False,
    )
    context = _make_dummy_context()
    geo = EvidenceCollector.create_geospatial_evidence(
        summary_dict={"settlements_found": 1}, features_count=1, source="local_vector_catalog"
    )

    fusion = MultimodalFusionEngine.fuse([cv, env, geo], context)
    assert fusion.has_visual is True
    assert fusion.has_environmental is True
    assert fusion.has_geospatial is True
    assert len(fusion.missing_streams) == 0
    assert fusion.visual_fire_probability == 0.85
    assert fusion.environmental_fwi == 28.5


def test_fusion_missing_visual():
    unavail_cv = EvidenceCollector.create_unavailable_cv_evidence("No image provided")
    env = EvidenceCollector.create_environmental_evidence(
        weather_data={"temperature_c": 25.0, "fwi_indices": {"fire_weather_index_fwi": 10.0, "danger_rating": "Moderate"}},
        provider="open-meteo",
        model_or_dataset="best_match",
        is_stale=False,
    )
    context = _make_dummy_context()

    fusion = MultimodalFusionEngine.fuse([unavail_cv, env], context)
    assert fusion.has_visual is False
    assert "computer_vision_imagery" in fusion.missing_streams


def test_fusion_cross_modal_conflict_detection():
    # Flame detection > 0.80 while heavy rain
    cv = EvidenceCollector.create_cv_evidence(
        probabilities={"fire": 0.90, "smoke": 0.05, "neutral": 0.05},
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
    context = _make_dummy_context()

    fusion = MultimodalFusionEngine.fuse([cv, env], context)
    assert len(fusion.conflicting_streams) >= 1
    assert "rainfall" in fusion.conflicting_streams[0]


def test_risk_assessor_critical_wildfire():
    cv = EvidenceCollector.create_cv_evidence(
        probabilities={"fire": 0.92, "smoke": 0.05, "neutral": 0.03},
        model_name="BaselineCNN",
        checkpoint_path="baseline_cnn_best.pt",
    )
    env = EvidenceCollector.create_environmental_evidence(
        weather_data={
            "temperature_c": 38.0,
            "relative_humidity_pct": 15.0,
            "fwi_indices": {"fire_weather_index_fwi": 42.0, "danger_rating": "Extreme"},
        },
        provider="open-meteo",
        model_or_dataset="best_match",
        is_stale=False,
    )
    context = _make_dummy_context(settlement_dist=800.0)
    fusion = MultimodalFusionEngine.fuse([cv, env], context)

    level, score = HeuristicRiskAssessor.evaluate(DisasterType.WILDFIRE, fusion)
    assert level == DisasterAssessmentLevel.CRITICAL
    assert score is not None
    assert score >= 75.0


def test_risk_assessor_low_wildfire():
    cv = EvidenceCollector.create_cv_evidence(
        probabilities={"fire": 0.02, "smoke": 0.03, "neutral": 0.95},
        model_name="BaselineCNN",
        checkpoint_path="baseline_cnn_best.pt",
    )
    env = EvidenceCollector.create_environmental_evidence(
        weather_data={
            "temperature_c": 12.0,
            "relative_humidity_pct": 80.0,
            "fwi_indices": {"fire_weather_index_fwi": 1.5, "danger_rating": "Low"},
        },
        provider="open-meteo",
        model_or_dataset="best_match",
        is_stale=False,
    )
    context = _make_dummy_context(settlement_dist=6000.0)
    fusion = MultimodalFusionEngine.fuse([cv, env], context)

    level, score = HeuristicRiskAssessor.evaluate(DisasterType.WILDFIRE, fusion)
    assert level == DisasterAssessmentLevel.LOW
    assert score is not None
    assert score < 25.0


def test_risk_assessor_insufficient_data():
    unavail_cv = EvidenceCollector.create_unavailable_cv_evidence("No image")
    unavail_env = EvidenceCollector.create_unavailable_environmental_evidence("Offline")
    context = _make_dummy_context()

    fusion = MultimodalFusionEngine.fuse([unavail_cv, unavail_env], context)
    level, score = HeuristicRiskAssessor.evaluate(DisasterType.WILDFIRE, fusion)
    assert level == DisasterAssessmentLevel.INSUFFICIENT_DATA
    assert score is None


def test_risk_assessor_unsupported_disasters():
    context = _make_dummy_context()
    fusion = MultimodalFusionEngine.fuse([], context)

    # Flood
    level_f, score_f = HeuristicRiskAssessor.evaluate(DisasterType.FLOOD, fusion)
    assert level_f == DisasterAssessmentLevel.INSUFFICIENT_DATA
    assert score_f is None

    # Earthquake
    level_e, score_e = HeuristicRiskAssessor.evaluate(DisasterType.EARTHQUAKE, fusion)
    assert level_e == DisasterAssessmentLevel.INSUFFICIENT_DATA
    assert score_e is None


def test_explanation_generator():
    cv = EvidenceCollector.create_cv_evidence(
        probabilities={"fire": 0.88, "smoke": 0.08, "neutral": 0.04},
        model_name="BaselineCNN",
        checkpoint_path="baseline_cnn_best.pt",
    )
    env = EvidenceCollector.create_environmental_evidence(
        weather_data={"temperature_c": 36.0, "fwi_indices": {"fire_weather_index_fwi": 25.0, "danger_rating": "High"}},
        provider="open-meteo",
        model_or_dataset="best_match",
        is_stale=False,
    )
    context = _make_dummy_context(settlement_dist=1200.0)
    fusion = MultimodalFusionEngine.fuse([cv, env], context)

    level, score = HeuristicRiskAssessor.evaluate(DisasterType.WILDFIRE, fusion)
    rationale = ExplanationGenerator.generate_rationale(DisasterType.WILDFIRE, level, score, fusion)
    assert "CRITICAL" in rationale or "HIGH" in rationale
    assert str(score) in rationale

    contributing = ExplanationGenerator.generate_contributing_factors(DisasterType.WILDFIRE, fusion)
    assert len(contributing) >= 2

    caveats = ExplanationGenerator.generate_caveats(DisasterType.WILDFIRE, fusion)
    assert any("heuristic" in c.lower() for c in caveats)
    assert any("canadian" in c.lower() for c in caveats)
