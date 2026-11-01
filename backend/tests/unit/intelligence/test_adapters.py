"""
backend/tests/unit/intelligence/test_adapters.py
Unit tests for Milestone 11 subsystem adapters (Vision, Environmental, Geospatial).
"""

from datetime import datetime, timezone
from io import BytesIO
from unittest.mock import MagicMock, patch
from PIL import Image
import pytest

from app.environmental.schemas import EnvironmentalObservationItem, EnvironmentalTypology
from app.geospatial.schemas import (
    ExposureSummary,
    FeatureCategory,
    GeographicFeatureItem,
    GeospatialAssessmentResponse,
    IncidentSpatialContext,
    SpatialRelationship,
)
from app.intelligence.adapters.environmental_adapter import EnvironmentalModelAdapter
from app.intelligence.adapters.geospatial_adapter import GeospatialModelAdapter
from app.intelligence.adapters.vision_adapter import VisionModelAdapter
from app.intelligence.schemas import (
    CoordinateLocation,
    EvidenceCategory,
    EvidenceStatus,
)


# ---------------------------------------------------------------------------
# Vision Adapter Tests
# ---------------------------------------------------------------------------

def test_vision_adapter_real_checkpoint_inference():
    adapter = VisionModelAdapter()
    test_img = Image.new("RGB", (250, 180), color=(220, 80, 20))

    probs = adapter.predict_image(test_img)
    assert "fire" in probs
    assert "smoke" in probs
    assert "neutral" in probs
    assert abs(sum(probs.values()) - 1.0) < 0.05

    evidence = adapter.collect_evidence(
        image_input=test_img,
        location=CoordinateLocation(latitude=30.3, longitude=78.0),
    )
    assert evidence.category == EvidenceCategory.COMPUTER_VISION
    assert evidence.status == EvidenceStatus.VALID
    assert evidence.confidence is not None
    assert "BaselineCNN" in evidence.source_name


def test_vision_adapter_bytes_input():
    adapter = VisionModelAdapter()
    buf = BytesIO()
    Image.new("RGB", (100, 100), color=(10, 10, 10)).save(buf, format="JPEG")
    img_bytes = buf.getvalue()

    probs = adapter.predict_image(img_bytes)
    assert "fire" in probs
    assert "neutral" in probs


def test_vision_adapter_missing_image():
    adapter = VisionModelAdapter()
    evidence = adapter.collect_evidence(image_input=None)
    assert evidence.category == EvidenceCategory.COMPUTER_VISION
    assert evidence.status == EvidenceStatus.UNAVAILABLE
    assert evidence.confidence is None


def test_vision_adapter_corrupt_file(tmp_path):
    bad_file = tmp_path / "corrupt.jpg"
    bad_file.write_bytes(b"not a real jpeg file")

    adapter = VisionModelAdapter()
    evidence = adapter.collect_evidence(image_input=str(bad_file))
    assert evidence.status == EvidenceStatus.UNAVAILABLE
    assert "error" in evidence.raw_value


# ---------------------------------------------------------------------------
# Environmental Adapter Tests
# ---------------------------------------------------------------------------

def test_environmental_adapter_mocked_success():
    now_utc = datetime.now(timezone.utc)
    mock_service = MagicMock()
    mock_obs = EnvironmentalObservationItem(
        location_type="point",
        location_id="point:30.3000:78.0000",
        requested_latitude=30.3,
        requested_longitude=78.0,
        resolved_latitude=30.3,
        resolved_longitude=78.0,
        valid_time_utc=now_utc,
        recorded_at=now_utc,
        typology=EnvironmentalTypology.MODEL_ANALYSIS,
        source="open_meteo_api",
        provider="open-meteo",
        dataset_or_model="best_match",
        temperature_celsius=32.5,
        relative_humidity=25.0,
        wind_speed_mps=6.67,  # ~24 km/h
        wind_direction_degrees=180.0,
        precipitation_mm=0.0,
    )
    mock_service.get_current_conditions.return_value = (mock_obs, False)

    adapter = EnvironmentalModelAdapter(service=mock_service)
    evidence = adapter.collect_evidence(latitude=30.3, longitude=78.0)

    assert evidence.category == EvidenceCategory.ENVIRONMENTAL
    assert evidence.status == EvidenceStatus.VALID
    assert evidence.quality.is_stale is False

    raw = evidence.raw_value
    assert raw["temperature_c"] == 32.5
    assert raw["relative_humidity_pct"] == 25.0
    assert "fwi_indices" in raw
    fwi_dict = raw["fwi_indices"]
    assert "fire_weather_index_fwi" in fwi_dict
    assert "danger_rating" in fwi_dict
    assert fwi_dict["fine_fuel_moisture_code_ffmc"] > 0


def test_environmental_adapter_stale_fallback():
    now_utc = datetime.now(timezone.utc)
    mock_service = MagicMock()
    mock_obs = EnvironmentalObservationItem(
        location_type="point",
        location_id="point:30.3000:78.0000",
        requested_latitude=30.3,
        requested_longitude=78.0,
        resolved_latitude=30.3,
        resolved_longitude=78.0,
        valid_time_utc=now_utc,
        recorded_at=now_utc,
        typology=EnvironmentalTypology.MODEL_ANALYSIS,
        source="open_meteo_api",
        provider="open-meteo",
        dataset_or_model="best_match",
        temperature_celsius=28.0,
        relative_humidity=40.0,
        wind_speed_mps=4.17,  # ~15 km/h
        precipitation_mm=0.0,
    )
    mock_service.get_current_conditions.return_value = (mock_obs, True)  # Stale

    adapter = EnvironmentalModelAdapter(service=mock_service)
    evidence = adapter.collect_evidence(latitude=30.3, longitude=78.0)

    assert evidence.status == EvidenceStatus.STALE
    assert evidence.quality.is_stale is True


def test_environmental_adapter_provider_error():
    mock_service = MagicMock()
    mock_service.get_current_conditions.side_effect = RuntimeError("Open-Meteo connection timeout")

    adapter = EnvironmentalModelAdapter(service=mock_service)
    evidence = adapter.collect_evidence(latitude=30.3, longitude=78.0)

    assert evidence.status == EvidenceStatus.UNAVAILABLE
    assert "error" in evidence.raw_value


# ---------------------------------------------------------------------------
# Geospatial Adapter Tests
# ---------------------------------------------------------------------------

def test_geospatial_adapter_success():
    mock_service = MagicMock()
    mock_resp = GeospatialAssessmentResponse(
        assessment_id="assess-geo-123",
        incident_context=IncidentSpatialContext(
            disaster_type="wildfire",
            latitude=30.3,
            longitude=78.0,
            srid=4326,
            utm_epsg=32644,
            search_radius_meters=5000.0,
        ),
        exposure_summary=ExposureSummary(
            total_features_found=2,
            category_counts={"settlement": 1, "infrastructure": 1},
            closest_feature_distance_meters=800.0,
            closest_feature_name="Dehradun",
        ),
        features=[
            GeographicFeatureItem(
                id="feat-1",
                name="Dehradun",
                category=FeatureCategory.SETTLEMENT,
                distance_meters=800.0,
                relationship=SpatialRelationship.WITHIN_RADIUS,
                source_dataset="natural_earth",
            ),
            GeographicFeatureItem(
                id="feat-2",
                name="Doon Hospital",
                category=FeatureCategory.INFRASTRUCTURE,
                distance_meters=1500.0,
                relationship=SpatialRelationship.WITHIN_RADIUS,
                source_dataset="osm_hospitals",
            ),
        ],
        contributing_factors=["1 settlement found"],
        missing_data_indicators=["fire_station_layer_partial"],
        assessment_limitations=["Static proximity only"],
        data_provider="local_vector_catalog",
    )
    mock_service.analyze_exposure.return_value = mock_resp

    adapter = GeospatialModelAdapter(service=mock_service)
    evidence, summary = adapter.collect_evidence(latitude=30.3, longitude=78.0)

    assert evidence.category == EvidenceCategory.GEOSPATIAL_CONTEXT
    assert evidence.status == EvidenceStatus.VALID
    assert summary.settlements_found == 1
    assert summary.closest_settlement_name == "Dehradun"
    assert summary.hospitals_found == 1
    assert summary.closest_hospital_distance_meters == 1500.0
