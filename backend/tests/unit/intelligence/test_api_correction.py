"""
backend/tests/unit/intelligence/test_api_correction.py
Unit tests for Milestone 11 Correction E (Multipart Image Upload Hardening).
Verifies strict 10MB limit enforcement, chunked streaming, magic number validation,
empty payload rejection, and verifies vision inference is NEVER invoked on rejected uploads.
"""

from datetime import datetime, timezone
from io import BytesIO
from unittest.mock import MagicMock, patch
from fastapi import HTTPException
from PIL import Image
import pytest

from app.api.v1.endpoints.intelligence import analyze_with_image_endpoint
from app.core.config import settings
from app.environmental.schemas import EnvironmentalObservationItem, EnvironmentalTypology
from app.schemas.incident import DisasterType


def _dummy_env_obs():
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
        temperature_celsius=32.0,
        relative_humidity=25.0,
        wind_speed_mps=4.0,
        precipitation_mm=0.0,
    )


@patch("app.api.v1.endpoints.intelligence.intelligence_service.analyze_observation")
def test_upload_empty_image_raises_400(mock_analyze):
    """An uploaded empty file (0 bytes) must be rejected with HTTP 400 and downstream inference never called."""
    mock_upload = MagicMock()
    mock_upload.file.read.return_value = b""

    with pytest.raises(HTTPException) as exc_info:
        analyze_with_image_endpoint(
            latitude=30.3165,
            longitude=78.0322,
            disaster_type=DisasterType.WILDFIRE,
            image=mock_upload,
            db=None,
        )

    assert exc_info.value.status_code == 400
    assert "empty" in exc_info.value.detail.lower()
    mock_analyze.assert_not_called()


@patch("app.api.v1.endpoints.intelligence.intelligence_service.analyze_observation")
def test_upload_unsupported_magic_signature_raises_400(mock_analyze):
    """An arbitrary binary or non-image header must be rejected with HTTP 400 and downstream inference never called."""
    mock_upload = MagicMock()
    # Mock returning an executable or random binary header
    mock_upload.file.read.return_value = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00"

    with pytest.raises(HTTPException) as exc_info:
        analyze_with_image_endpoint(
            latitude=30.3165,
            longitude=78.0322,
            disaster_type=DisasterType.WILDFIRE,
            image=mock_upload,
            db=None,
        )

    assert exc_info.value.status_code == 400
    assert "unsupported image format" in exc_info.value.detail.lower()
    mock_analyze.assert_not_called()


@patch("app.api.v1.endpoints.intelligence.intelligence_service.analyze_observation")
def test_upload_oversized_image_raises_413(mock_analyze):
    """A payload exceeding MAX_UPLOAD_SIZE_BYTES (10MB) must be rejected with HTTP 413 and downstream inference never called."""
    mock_upload = MagicMock()
    # JPEG magic header + 11MB of synthetic data
    header = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01"
    chunk_size = 64 * 1024
    first_chunk = header + b"X" * (chunk_size - len(header))
    large_chunk = b"X" * chunk_size

    # Stream more than 10MB (165 chunks of 64KB = 10.5 MB)
    chunks = [first_chunk] + [large_chunk] * 170 + [b""]
    mock_upload.file.read.side_effect = chunks

    with pytest.raises(HTTPException) as exc_info:
        analyze_with_image_endpoint(
            latitude=30.3165,
            longitude=78.0322,
            disaster_type=DisasterType.WILDFIRE,
            image=mock_upload,
            db=None,
        )

    assert exc_info.value.status_code == 413
    assert "exceeds" in exc_info.value.detail.lower()
    assert str(settings.MAX_UPLOAD_SIZE_BYTES) in exc_info.value.detail
    mock_analyze.assert_not_called()


@patch("app.intelligence.adapters.environmental_adapter.EnvironmentalService.get_current_conditions")
def test_upload_valid_jpeg_under_limit_succeeds(mock_env_get):
    """A valid JPEG under 10MB succeeds through the chunked streaming pipeline."""
    mock_env_get.return_value = (_dummy_env_obs(), False)

    buf = BytesIO()
    Image.new("RGB", (128, 128), color=(200, 50, 10)).save(buf, format="JPEG")
    valid_bytes = buf.getvalue()

    mock_upload = MagicMock()
    mock_upload.file.read.side_effect = [valid_bytes, b""]

    assessment = analyze_with_image_endpoint(
        latitude=30.3165,
        longitude=78.0322,
        disaster_type=DisasterType.WILDFIRE,
        image=mock_upload,
        db=None,
    )

    assert assessment.disaster_type == "wildfire"
    assert assessment.hazard_assessment is not None
    assert assessment.exposure_assessment is not None
    assert assessment.consequence_assessment is not None
