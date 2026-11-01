"""
backend/tests/unit/intelligence/test_schemas.py
Unit tests for Milestone 11 intelligence domain schemas and evidence models.
"""

from datetime import datetime, timedelta, timezone
import pytest
from pydantic import ValidationError

from app.geospatial.schemas import FeatureCategory, GeographicFeatureItem, SpatialRelationship
from app.intelligence.context import ContextAggregator
from app.intelligence.evidence import EvidenceCollector
from app.intelligence.exceptions import (
    InsufficientDataError,
    InvalidEvidenceError,
    ProviderUnavailableError,
    StaleDataError,
    UnsupportedDisasterTypeError,
)
from app.intelligence.schemas import (
    ContextSummary,
    CoordinateLocation,
    DisasterAssessmentLevel,
    EvidenceCategory,
    EvidenceItem,
    EvidenceQuality,
    EvidenceStatus,
    IncidentObservationInput,
    MultimodalIntelligenceAssessment,
)
from app.schemas.incident import DisasterType


def test_coordinate_location_valid():
    loc = CoordinateLocation(latitude=30.3165, longitude=78.0322)
    assert loc.latitude == 30.3165
    assert loc.longitude == 78.0322
    assert loc.srid == 4326


def test_coordinate_location_invalid_bounds():
    with pytest.raises(ValidationError):
        CoordinateLocation(latitude=95.0, longitude=78.0)
    with pytest.raises(ValidationError):
        CoordinateLocation(latitude=30.0, longitude=185.0)


def test_evidence_quality_creation():
    eq = EvidenceQuality(
        is_stale=False,
        age_seconds=120.5,
        has_confidence_measure=True,
        confidence_scale="softmax_probability [0,1]",
        provider_type="deep_learning_model",
    )
    assert eq.is_stale is False
    assert eq.has_confidence_measure is True


def test_evidence_collector_cv_evidence_success():
    probs = {"fire": 0.88, "smoke": 0.08, "neutral": 0.04}
    item = EvidenceCollector.create_cv_evidence(
        probabilities=probs,
        model_name="BaselineCNN",
        checkpoint_path="artifacts/checkpoints/baseline_cnn_best.pt",
        location=CoordinateLocation(latitude=30.0, longitude=78.0),
    )
    assert item.category == EvidenceCategory.COMPUTER_VISION
    assert item.status == EvidenceStatus.VALID
    assert item.confidence == 0.88
    assert item.quality.has_confidence_measure is True
    assert "BaselineCNN" in item.source_name
    assert len(item.caveats) >= 1


def test_evidence_collector_cv_evidence_invalid_prob_sum():
    probs = {"fire": 0.40, "smoke": 0.10, "neutral": 0.10}  # Sum = 0.60 != 1.0
    with pytest.raises(InvalidEvidenceError):
        EvidenceCollector.create_cv_evidence(
            probabilities=probs,
            model_name="BaselineCNN",
            checkpoint_path="artifacts/checkpoints/baseline_cnn_best.pt",
        )


def test_evidence_collector_freshness_evaluation():
    now = datetime.now(timezone.utc)
    fresh_time = now - timedelta(hours=1)
    stale_time = now - timedelta(hours=5)

    is_stale_fresh, age_fresh = EvidenceCollector.evaluate_freshness(
        fresh_time, EvidenceCategory.COMPUTER_VISION, now_time=now
    )
    assert is_stale_fresh is False
    assert 3500 < age_fresh < 3700

    is_stale_old, age_old = EvidenceCollector.evaluate_freshness(
        stale_time, EvidenceCategory.COMPUTER_VISION, now_time=now
    )
    assert is_stale_old is True
    assert age_old > 14000


def test_evidence_collector_unavailable_items():
    unavail_cv = EvidenceCollector.create_unavailable_cv_evidence("No image provided")
    assert unavail_cv.category == EvidenceCategory.COMPUTER_VISION
    assert unavail_cv.status == EvidenceStatus.UNAVAILABLE
    assert unavail_cv.confidence is None

    unavail_env = EvidenceCollector.create_unavailable_environmental_evidence("Timeout from API")
    assert unavail_env.category == EvidenceCategory.ENVIRONMENTAL
    assert unavail_env.status == EvidenceStatus.UNAVAILABLE


def test_context_aggregator():
    features = [
        GeographicFeatureItem(
            id="feat-1",
            name="Dehradun City",
            category=FeatureCategory.SETTLEMENT,
            distance_meters=1250.0,
            relationship=SpatialRelationship.WITHIN_RADIUS,
            source_dataset="natural_earth",
        ),
        GeographicFeatureItem(
            id="feat-2",
            name="City Hospital",
            category=FeatureCategory.INFRASTRUCTURE,
            distance_meters=450.0,
            relationship=SpatialRelationship.WITHIN_RADIUS,
            source_dataset="osm_hospitals",
        ),
        GeographicFeatureItem(
            id="feat-3",
            name="Fire Station Sector 4",
            category=FeatureCategory.INFRASTRUCTURE,
            distance_meters=900.0,
            relationship=SpatialRelationship.WITHIN_RADIUS,
            source_dataset="osm_fire_stations",
        ),
    ]

    summary = ContextAggregator.aggregate(features, missing_layers=["dem_elevation_raster"])
    assert summary.settlements_found == 1
    assert summary.closest_settlement_distance_meters == 1250.0
    assert summary.closest_settlement_name == "Dehradun City"
    assert summary.hospitals_found == 1
    assert summary.closest_hospital_distance_meters == 450.0
    assert summary.fire_stations_found == 1
    assert summary.closest_fire_station_distance_meters == 900.0
    assert summary.total_features_evaluated == 3
    assert any("dem_elevation_raster" in note for note in summary.spatial_coverage_notes)


def test_incident_observation_input_defaults():
    payload = IncidentObservationInput(
        latitude=30.3165,
        longitude=78.0322,
    )
    assert payload.disaster_type == DisasterType.WILDFIRE
    assert payload.search_radius_meters == 5000.0
    assert payload.observation_timestamp is not None
    assert payload.image_path is None


def test_domain_exceptions():
    with pytest.raises(UnsupportedDisasterTypeError) as exc:
        raise UnsupportedDisasterTypeError("tornado", ["wildfire", "flood", "earthquake"])
    assert "tornado" in str(exc.value)

    with pytest.raises(ProviderUnavailableError) as exc:
        raise ProviderUnavailableError("open-meteo", "503 Service Unavailable")
    assert "503" in str(exc.value)

    with pytest.raises(StaleDataError) as exc:
        raise StaleDataError("weather", 8.0, 3.0)
    assert "8.0h old" in str(exc.value)

    with pytest.raises(InsufficientDataError) as exc:
        raise InsufficientDataError(["weather", "imagery"], "Cannot determine risk.")
    assert "weather" in str(exc.value)
