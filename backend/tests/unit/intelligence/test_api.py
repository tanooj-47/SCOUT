"""
backend/tests/unit/intelligence/test_api.py
API endpoint tests for Milestone 11 Multimodal Intelligence.
Directly exercises FastAPI route controllers and service integration.
"""

import asyncio
from datetime import datetime, timezone
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch
from PIL import Image
import pytest

from app.api.v1.endpoints.intelligence import (
    analyze_observation_endpoint,
    analyze_with_image_endpoint,
    get_intelligence_capabilities,
    get_intelligence_health,
)
from app.environmental.schemas import EnvironmentalObservationItem, EnvironmentalTypology
from app.intelligence.schemas import (
    DisasterAssessmentLevel,
    IncidentObservationInput,
    IntelligenceHealthResponse,
    MultimodalIntelligenceAssessment,
)
from app.schemas.incident import DisasterType


def _make_dummy_obs(temp: float = 30.0, rh: float = 30.0, rain: float = 0.0) -> EnvironmentalObservationItem:
    now_utc = datetime.now(timezone.utc)
    return EnvironmentalObservationItem(
        location_type="point",
        location_id="point:30.3165:78.0322",
        requested_latitude=30.3165,
        requested_longitude=78.0322,
        resolved_latitude=30.3165,
        resolved_longitude=78.0322,
        valid_time_utc=now_utc,
        recorded_at=now_utc,
        typology=EnvironmentalTypology.MODEL_ANALYSIS,
        source="open_meteo_api",
        provider="open-meteo",
        dataset_or_model="best_match",
        temperature_celsius=temp,
        relative_humidity=rh,
        wind_speed_mps=5.0,
        precipitation_mm=rain,
    )


# ---------------------------------------------------------------------------
# Health & Capabilities Endpoint Tests
# ---------------------------------------------------------------------------

def test_intelligence_health_endpoint():
    res: IntelligenceHealthResponse = get_intelligence_health(db=None)
    assert res.status in ("operational", "degraded")
    assert res.cv_model_available is True  # Real BaselineCNN champion loaded
    assert "wildfire" in res.supported_disaster_types
    assert "flood" in res.supported_disaster_types
    assert "earthquake" in res.supported_disaster_types


def test_intelligence_capabilities_endpoint():
    res = get_intelligence_capabilities()
    assert "supported_disaster_types" in res
    assert "calibrated_modalities" in res
    assert "wildfire" in res["calibrated_modalities"]
    assert "core_constraints" in res
    assert len(res["core_constraints"]) >= 2


# ---------------------------------------------------------------------------
# Analyze Endpoint Tests (JSON Payload)
# ---------------------------------------------------------------------------

@patch("app.intelligence.adapters.environmental_adapter.EnvironmentalService.get_current_conditions")
def test_analyze_observation_json_wildfire_no_image(mock_env_get):
    mock_env_get.return_value = (_make_dummy_obs(temp=32.0, rh=25.0), False)

    obs = IncidentObservationInput(
        disaster_type=DisasterType.WILDFIRE,
        latitude=30.3165,
        longitude=78.0322,
        search_radius_meters=5000.0,
        source_description="automated_sensor_trigger",
    )

    assessment: MultimodalIntelligenceAssessment = analyze_observation_endpoint(
        observation=obs,
        db=None,
    )

    assert assessment.disaster_type == "wildfire"
    assert assessment.assessment_level in [
        DisasterAssessmentLevel.LOW,
        DisasterAssessmentLevel.MODERATE,
        DisasterAssessmentLevel.HIGH,
        DisasterAssessmentLevel.CRITICAL,
    ]
    assert assessment.heuristic_risk_index is not None
    assert "computer_vision_imagery" in assessment.missing_evidence
    assert len(assessment.evidence_items) == 3
    assert len(assessment.caveats_and_limitations) >= 1


@patch("app.intelligence.adapters.environmental_adapter.EnvironmentalService.get_current_conditions")
def test_analyze_observation_json_flood_unsupported(mock_env_get):
    mock_env_get.return_value = (_make_dummy_obs(), False)

    obs = IncidentObservationInput(
        disaster_type=DisasterType.FLOOD,
        latitude=30.3165,
        longitude=78.0322,
        search_radius_meters=5000.0,
    )

    assessment: MultimodalIntelligenceAssessment = analyze_observation_endpoint(
        observation=obs,
        db=None,
    )

    assert assessment.disaster_type == "flood"
    assert assessment.assessment_level == DisasterAssessmentLevel.INSUFFICIENT_DATA
    assert assessment.heuristic_risk_index is None
    assert "INSUFFICIENT_DATA" in assessment.assessment_rationale


# ---------------------------------------------------------------------------
# Analyze with Image Endpoint Tests (Multipart Form)
# ---------------------------------------------------------------------------

@patch("app.intelligence.adapters.environmental_adapter.EnvironmentalService.get_current_conditions")
def test_analyze_with_image_multipart_success(mock_env_get):
    mock_env_get.return_value = (_make_dummy_obs(temp=35.0, rh=18.0), False)

    # Generate synthetic JPEG image
    buf = BytesIO()
    Image.new("RGB", (224, 224), color=(240, 60, 10)).save(buf, format="JPEG")
    image_bytes = buf.getvalue()

    mock_upload = MagicMock()
    mock_upload.file.read.return_value = image_bytes

    assessment: MultimodalIntelligenceAssessment = analyze_with_image_endpoint(
        latitude=30.3165,
        longitude=78.0322,
        disaster_type=DisasterType.WILDFIRE,
        search_radius_meters=5000.0,
        source_description="drone_aerial_recon",
        image=mock_upload,
        db=None,
    )

    assert assessment.disaster_type == "wildfire"
    assert "computer_vision_imagery" not in assessment.missing_evidence
    cv_evidence = next((item for item in assessment.evidence_items if item.category == "computer_vision"), None)
    assert cv_evidence is not None
    assert cv_evidence.status == "valid"
    assert cv_evidence.confidence is not None
    assert "BaselineCNN" in cv_evidence.source_name
