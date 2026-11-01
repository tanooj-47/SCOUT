from datetime import datetime, timezone
import math
from pathlib import Path
import uuid
from PIL import Image
import pytest

from app.core.exceptions import (
    InvalidCoordinatesError,
    InvalidSourceTypeError,
    UnsupportedMediaFormatError,
)
from app.schemas.incident import CoordinatePoint
from app.schemas.media import MediaFormat, MediaResponse, MediaSourceType
from app.services.media_service import (
    detect_image_format,
    validate_coordinates,
    validate_image_content,
    validate_source_type,
)

MINIMAL_JPEG = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00"
    b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t"
    b"\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a"
    b"\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342"
    b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00"
    b"\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00"
    b"\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b"
    b"\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9"
)

VALID_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x02\x00\x00\x00\x02"
    b"\x08\x02\x00\x00\x00\xfd\xd4\x9as\x00\x00\x00\x10IDATx\x9cc\xfc\xcf"
    b"\x00\x02L`\x92\x01\x00\r\x1d\x01\x03\x82\xc9q\xff\x00\x00\x00\x00IEND\xaeB`\x82"
)

VALID_WEBP = (
    b"RIFF<\x00\x00\x00WEBPVP8 0\x00\x00\x00\xd0\x01\x00\x9d\x01*\x02\x00\x02\x00"
    b"\x01@&%\xa0\x02t\xba\x01\xf8\x00\x03\xb0\x00\xfe\xf2\xeb\x7f\xfc\xd8\x15"
    b"\xcds\xef\xf7\xff\xd2\xe0\xfd.\x0f\xd2\xe0\xff\xd2\x90\x00\x00"
)


def test_magic_byte_format_detection():
    """Verify magic byte detection for JPEG, PNG, and WebP raster images."""
    assert detect_image_format(MINIMAL_JPEG) == "jpeg"
    assert detect_image_format(VALID_PNG) == "png"
    assert detect_image_format(VALID_WEBP) == "webp"

    # Unsupported or corrupted formats
    assert detect_image_format(b"%PDF-1.5 fake document") is None
    assert detect_image_format(b"MZ\x90\x00 executable payload") is None
    assert detect_image_format(b"GIF89a invalid") is None
    assert detect_image_format(b"") is None
    assert detect_image_format(b"short") is None


def test_validate_coordinates_valid():
    """Verify that valid or omitted coordinates pass validation."""
    validate_coordinates(None, None)
    validate_coordinates(34.0522, -118.2437)
    validate_coordinates(0.0, 0.0)
    validate_coordinates(-90.0, -180.0)
    validate_coordinates(90.0, 180.0)


def test_validate_coordinates_single_coordinate_rejected():
    """Verify that supplying only latitude or only longitude is rejected."""
    with pytest.raises(InvalidCoordinatesError) as exc1:
        validate_coordinates(34.0, None)
    assert "together" in str(exc1.value)

    with pytest.raises(InvalidCoordinatesError) as exc2:
        validate_coordinates(None, -118.0)
    assert "together" in str(exc2.value)


def test_validate_coordinates_bounds_and_nan():
    """Verify rejection of out-of-bounds coordinates, NaN, and +/-Infinities."""
    with pytest.raises(InvalidCoordinatesError):
        validate_coordinates(90.1, 0.0)

    with pytest.raises(InvalidCoordinatesError):
        validate_coordinates(-90.1, 0.0)

    with pytest.raises(InvalidCoordinatesError):
        validate_coordinates(0.0, 180.1)

    with pytest.raises(InvalidCoordinatesError):
        validate_coordinates(0.0, -180.1)

    with pytest.raises(InvalidCoordinatesError):
        validate_coordinates(float("nan"), 0.0)

    with pytest.raises(InvalidCoordinatesError):
        validate_coordinates(0.0, float("inf"))

    with pytest.raises(InvalidCoordinatesError):
        validate_coordinates(float("-inf"), 0.0)


def test_media_response_schema():
    """Verify MediaResponse schema construction and coordinate mapping."""
    media_id = uuid.uuid4()
    incident_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    resp = MediaResponse(
        id=media_id,
        incident_id=incident_id,
        storage_path="media/2026/10/photo.jpg",
        media_format="jpeg",
        source_type="drone",
        file_size_bytes=1024,
        capture_location=CoordinatePoint(latitude=37.77, longitude=-122.41, srid=4326),
        captured_at=now,
        created_at=now,
    )

    data = resp.model_dump()
    assert data["id"] == media_id
    assert data["incident_id"] == incident_id
    assert data["media_format"] == "jpeg"
    assert data["source_type"] == "drone"
    assert data["file_size_bytes"] == 1024
    assert data["capture_location"]["latitude"] == 37.77
    assert data["capture_location"]["srid"] == 4326


def test_validate_source_type_valid_and_defaults():
    """Verify that valid or omitted source types return valid strings."""
    assert validate_source_type(None) == "other"
    assert validate_source_type("drone") == "drone"
    assert validate_source_type("  satellite  ") == "satellite"
    assert validate_source_type("sensor_payload_flir") == "sensor_payload_flir"
    assert validate_source_type("x" * 32) == "x" * 32


def test_validate_source_type_rejected():
    """Verify that empty, whitespace-only, or overly long source types are rejected."""
    with pytest.raises(InvalidSourceTypeError) as exc1:
        validate_source_type("")
    assert "empty" in str(exc1.value).lower()

    with pytest.raises(InvalidSourceTypeError) as exc2:
        validate_source_type("   \t  ")
    assert "whitespace" in str(exc2.value).lower()

    with pytest.raises(InvalidSourceTypeError) as exc3:
        validate_source_type("x" * 33)
    assert "exceeds maximum permitted length" in str(exc3.value).lower()


def test_validate_image_content_valid_formats(tmp_path: Path):
    """Verify that valid JPEG, PNG, and WebP raster images pass deep verification."""
    # JPEG
    jpg_path = tmp_path / "valid.jpg"
    jpg_path.write_bytes(MINIMAL_JPEG)
    fmt, w, h = validate_image_content(jpg_path)
    assert fmt == "jpeg"
    assert w == 1
    assert h == 1

    # PNG
    png_path = tmp_path / "valid.png"
    png_path.write_bytes(VALID_PNG)
    fmt, w, h = validate_image_content(png_path)
    assert fmt == "png"
    assert w == 2
    assert h == 2

    # WebP
    webp_path = tmp_path / "valid.webp"
    webp_path.write_bytes(VALID_WEBP)
    fmt, w, h = validate_image_content(webp_path)
    assert fmt == "webp"
    assert w == 2
    assert h == 2


def test_validate_image_content_rejected(tmp_path: Path):
    """Verify that invalid headers, truncated bytes, and corrupted payloads are rejected."""
    # 1. JPEG signature followed by random invalid data
    bad_jpg = tmp_path / "bad.jpg"
    bad_jpg.write_bytes(b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"Corrupted invalid byte stream")
    with pytest.raises(UnsupportedMediaFormatError) as exc1:
        validate_image_content(bad_jpg)
    assert "corrupted" in str(exc1.value).lower() or "malformed" in str(exc1.value).lower()

    # 2. Truncated PNG
    trunc_png = tmp_path / "trunc.png"
    trunc_png.write_bytes(VALID_PNG[:30])
    with pytest.raises(UnsupportedMediaFormatError) as exc2:
        validate_image_content(trunc_png)
    assert "corrupted" in str(exc2.value).lower() or "malformed" in str(exc2.value).lower()

    # 3. Invalid WebP structure
    bad_webp = tmp_path / "bad.webp"
    bad_webp.write_bytes(b"RIFF\x1a\x00\x00\x00WEBPVP8 \x0e\x00\x00\x00corrupt")
    with pytest.raises(UnsupportedMediaFormatError) as exc3:
        validate_image_content(bad_webp)
    assert "corrupted" in str(exc3.value).lower() or "malformed" in str(exc3.value).lower()

    # 4. Excessive image dimension mock
    huge_img = Image.new("RGB", (20, 20), color="red")
    huge_path = tmp_path / "huge.png"
    huge_img.save(huge_path, format="PNG")
    # Monkeypatch MAX_IMAGE_DIMENSION to test rejection threshold
    from app.services import media_service
    media_service.MAX_IMAGE_DIMENSION = 10
    try:
        with pytest.raises(UnsupportedMediaFormatError) as exc4:
            validate_image_content(huge_path)
        assert "dimension" in str(exc4.value).lower()
    finally:
        media_service.MAX_IMAGE_DIMENSION = 16384
