from datetime import datetime, timezone
from pathlib import Path
from typing import Generator
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.core.config import settings
from app.core.storage import storage_manager

pytestmark = pytest.mark.database

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

MINIMAL_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x02\x00\x00\x00\x02"
    b"\x08\x02\x00\x00\x00\xfd\xd4\x9as\x00\x00\x00\x10IDATx\x9cc\xfc\xcf"
    b"\x00\x02L`\x92\x01\x00\r\x1d\x01\x03\x82\xc9q\xff\x00\x00\x00\x00IEND\xaeB`\x82"
)

MINIMAL_WEBP = (
    b"RIFF\x1a\x00\x00\x00WEBPVP8 \x0e\x00\x00\x00\x30\x01\x00\x9d\x01\x2a"
    b"\x01\x00\x01\x00\x02\x00\x34\x25\xa0\x02\x74\x00\x00\x00"
)


@pytest.fixture(autouse=True)
def isolated_media_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """
    Ensures tests execute against an isolated temporary directory,
    guaranteeing that actual development media storage is never polluted.
    """
    test_media_dir = tmp_path / "media_store"
    test_temp_dir = tmp_path / "temp_store"
    monkeypatch.setattr(storage_manager, "base_dir", test_media_dir.resolve())
    monkeypatch.setattr(storage_manager, "temp_dir", test_temp_dir.resolve())
    yield


def _create_test_incident(db_client: TestClient) -> str:
    """Helper to register a real incident in the transactional test context."""
    res = db_client.post(
        "/api/v1/incidents",
        json={
            "title": "Media Association Test Fire",
            "disaster_type": "wildfire",
            "severity": "high",
            "location": {"latitude": 37.7749, "longitude": -122.4194},
        },
    )
    assert res.status_code == 201
    return res.json()["id"]


# ==============================================================================
# 1. SUCCESSFUL UPLOADS
# ==============================================================================

def test_upload_jpeg_with_incident_and_coordinates(db_client: TestClient):
    """Verify successful JPEG ingestion linked to an existing incident with coordinates."""
    incident_id = _create_test_incident(db_client)

    files = {"file": ("drone_survey.jpg", MINIMAL_JPEG, "image/jpeg")}
    data = {
        "incident_id": incident_id,
        "source_type": "drone",
        "latitude": 37.7750,
        "longitude": -122.4195,
        "captured_at": "2026-10-30T10:00:00Z",
    }
    response = db_client.post("/api/v1/media", files=files, data=data)
    assert response.status_code == 201
    res_data = response.json()

    assert "id" in res_data
    assert res_data["incident_id"] == incident_id
    assert res_data["media_format"] == "jpeg"
    assert res_data["source_type"] == "drone"
    assert res_data["file_size_bytes"] == len(MINIMAL_JPEG)
    assert res_data["capture_location"]["latitude"] == 37.7750
    assert res_data["capture_location"]["longitude"] == -122.4195
    assert res_data["capture_location"]["srid"] == 4326
    assert res_data["captured_at"] is not None
    assert "created_at" in res_data

    # Verify physical file existence in storage
    rel_path = res_data["storage_path"]
    assert storage_manager.file_exists(rel_path)
    assert storage_manager.get_file_size(rel_path) == len(MINIMAL_JPEG)

    # Verify absolute path is NOT exposed
    assert not str(rel_path).startswith("C:")
    assert not str(rel_path).startswith("/")


def test_upload_png_without_incident(db_client: TestClient):
    """Verify successful PNG ingestion without an associated incident (incident_id is nullable)."""
    files = {"file": ("satellite_patch.png", MINIMAL_PNG, "image/png")}
    data = {"source_type": "satellite"}

    response = db_client.post("/api/v1/media", files=files, data=data)
    assert response.status_code == 201
    res_data = response.json()

    assert res_data["incident_id"] is None
    assert res_data["media_format"] == "png"
    assert res_data["source_type"] == "satellite"
    assert res_data["capture_location"] is None
    assert storage_manager.file_exists(res_data["storage_path"])


def test_upload_webp_format(db_client: TestClient):
    """Verify WebP image ingestion."""
    files = {"file": ("field_camera.webp", MINIMAL_WEBP, "image/webp")}
    response = db_client.post("/api/v1/media", files=files)
    assert response.status_code == 201
    res_data = response.json()

    assert res_data["media_format"] == "webp"
    assert res_data["source_type"] == "other"  # default fallback
    assert storage_manager.file_exists(res_data["storage_path"])


# ==============================================================================
# 2. VALIDATION & ERROR HANDLING
# ==============================================================================

def test_upload_empty_file_rejected(db_client: TestClient):
    """Verify that an empty file (0 bytes) is rejected with HTTP 400."""
    files = {"file": ("empty.jpg", b"", "image/jpeg")}
    response = db_client.post("/api/v1/media", files=files)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "EMPTY_FILE"


def test_upload_disguised_fake_bytes_rejected(db_client: TestClient):
    """Verify that a text or binary payload disguised with .jpg filename is rejected with HTTP 415."""
    fake_payload = b"Hello, I am a plain text file pretending to be JPEG!"
    files = {"file": ("impostor.jpg", fake_payload, "image/jpeg")}
    response = db_client.post("/api/v1/media", files=files)
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "UNSUPPORTED_MEDIA_FORMAT"


def test_upload_unsupported_format_pdf_rejected(db_client: TestClient):
    """Verify that documents such as PDFs are rejected with HTTP 415."""
    pdf_payload = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
    files = {"file": ("document.pdf", pdf_payload, "application/pdf")}
    response = db_client.post("/api/v1/media", files=files)
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "UNSUPPORTED_MEDIA_FORMAT"


def test_upload_oversized_file_rejected(db_client: TestClient, monkeypatch: pytest.MonkeyPatch):
    """Verify that files exceeding MAX_UPLOAD_SIZE_BYTES are rejected with HTTP 413."""
    # Temporarily set max upload size to 256 bytes for this test
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE_BYTES", 256)

    oversized_jpeg = MINIMAL_JPEG + (b"\x00" * 300)
    files = {"file": ("large.jpg", oversized_jpeg, "image/jpeg")}
    response = db_client.post("/api/v1/media", files=files)
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"

    # Ensure no lingering staging files remain
    temp_files = list(storage_manager.temp_dir.glob("*.tmp"))
    assert len(temp_files) == 0


def test_upload_single_coordinate_rejected(db_client: TestClient):
    """Verify that supplying latitude without longitude (or vice versa) returns HTTP 400."""
    files = {"file": ("test.jpg", MINIMAL_JPEG, "image/jpeg")}
    res_lat_only = db_client.post("/api/v1/media", files=files, data={"latitude": 34.0})
    assert res_lat_only.status_code == 400
    assert res_lat_only.json()["error"]["code"] == "INVALID_COORDINATES"

    res_lon_only = db_client.post("/api/v1/media", files=files, data={"longitude": -118.0})
    assert res_lon_only.status_code == 400
    assert res_lon_only.json()["error"]["code"] == "INVALID_COORDINATES"


def test_upload_out_of_bounds_coordinates_rejected(db_client: TestClient):
    """Verify boundary checks on latitude [-90, 90] and longitude [-180, 180]."""
    files = {"file": ("test.jpg", MINIMAL_JPEG, "image/jpeg")}
    res_bad_lat = db_client.post("/api/v1/media", files=files, data={"latitude": 95.0, "longitude": 0.0})
    assert res_bad_lat.status_code == 400

    res_bad_lon = db_client.post("/api/v1/media", files=files, data={"latitude": 0.0, "longitude": 185.0})
    assert res_bad_lon.status_code == 400


def test_upload_nonexistent_incident_id_returns_404(db_client: TestClient):
    """Verify that providing an unknown incident UUID returns HTTP 404."""
    random_id = str(uuid.uuid4())
    files = {"file": ("test.jpg", MINIMAL_JPEG, "image/jpeg")}
    response = db_client.post("/api/v1/media", files=files, data={"incident_id": random_id})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "INCIDENT_NOT_FOUND"


# ==============================================================================
# 3. RETRIEVAL & LISTING
# ==============================================================================

def test_get_media_by_id_and_not_found(db_client: TestClient):
    """Verify fetching existing media metadata and 404 for unknown media UUID."""
    # Ingest
    files = {"file": ("recon.jpg", MINIMAL_JPEG, "image/jpeg")}
    create_res = db_client.post("/api/v1/media", files=files, data={"source_type": "field_camera"})
    assert create_res.status_code == 201
    media_id = create_res.json()["id"]

    # Retrieve
    get_res = db_client.get(f"/api/v1/media/{media_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == media_id
    assert get_res.json()["source_type"] == "field_camera"

    # Nonexistent
    unknown_id = str(uuid.uuid4())
    res_404 = db_client.get(f"/api/v1/media/{unknown_id}")
    assert res_404.status_code == 404
    assert res_404.json()["error"]["code"] == "MEDIA_NOT_FOUND"


def test_list_media_filtering_and_pagination(db_client: TestClient):
    """Verify listing media with incident filter, source_type filter, and pagination."""
    incident_id = _create_test_incident(db_client)

    # Upload 2 media items linked to the incident, and 1 unlinked
    db_client.post(
        "/api/v1/media",
        files={"file": ("img1.jpg", MINIMAL_JPEG, "image/jpeg")},
        data={"incident_id": incident_id, "source_type": "drone"},
    )
    db_client.post(
        "/api/v1/media",
        files={"file": ("img2.png", MINIMAL_PNG, "image/png")},
        data={"incident_id": incident_id, "source_type": "satellite"},
    )
    db_client.post(
        "/api/v1/media",
        files={"file": ("img3.webp", MINIMAL_WEBP, "image/webp")},
        data={"source_type": "ground_team"},
    )

    # 1. Filter by incident_id
    res_inc = db_client.get(f"/api/v1/media?incident_id={incident_id}")
    assert res_inc.status_code == 200
    inc_data = res_inc.json()
    assert inc_data["total"] >= 2
    for item in inc_data["items"]:
        assert item["incident_id"] == incident_id

    # 2. Filter by source_type
    res_src = db_client.get("/api/v1/media?source_type=drone")
    assert res_src.status_code == 200
    src_data = res_src.json()
    assert src_data["total"] >= 1
    for item in src_data["items"]:
        assert item["source_type"] == "drone"

    # 3. Pagination
    res_page = db_client.get("/api/v1/media?limit=1&offset=0")
    assert res_page.status_code == 200
    page_data = res_page.json()
    assert len(page_data["items"]) == 1
    assert page_data["limit"] == 1
    assert page_data["offset"] == 0


# ==============================================================================
# 4. FAILURE AND CLEANUP (ATOMICITY)
# ==============================================================================

def test_failed_database_flush_cleans_up_file(db_client: TestClient, monkeypatch: pytest.MonkeyPatch):
    """
    Simulate a database failure during flush/commit.
    Guarantees that the finalized physical file is deleted and no orphaned file remains.
    """
    from sqlalchemy.orm import Session as SASession

    original_flush = SASession.flush

    def failing_flush(self, *args, **kwargs):
        raise OperationalError("Simulated database failure during flush", {}, None)

    monkeypatch.setattr(SASession, "flush", failing_flush)

    files = {"file": ("atomicity_test.jpg", MINIMAL_JPEG, "image/jpeg")}
    response = db_client.post("/api/v1/media", files=files)
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_SERVER_ERROR"

    # Verify that no media file remains in storage
    all_stored_files = list(storage_manager.base_dir.rglob("*.jpg"))
    assert len(all_stored_files) == 0

    # Verify no temp files remain
    temp_files = list(storage_manager.temp_dir.glob("*.tmp"))
    assert len(temp_files) == 0


# ==============================================================================
# 5. IMAGE CONTENT & SOURCE TYPE VALIDATION ENDPOINTS
# ==============================================================================

def test_upload_jpeg_with_corrupt_body_rejected(db_client: TestClient):
    """Verify that a JPEG header followed by invalid body data is rejected (HTTP 415)."""
    corrupt_jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"Corrupted invalid byte sequence"
    files = {"file": ("corrupt.jpg", corrupt_jpeg, "image/jpeg")}
    response = db_client.post("/api/v1/media", files=files)
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "UNSUPPORTED_MEDIA_FORMAT"

    # Confirms zero orphaned files in storage
    assert len(list(storage_manager.base_dir.rglob("*.jpg"))) == 0
    assert len(list(storage_manager.temp_dir.glob("*.tmp"))) == 0


def test_upload_truncated_png_rejected(db_client: TestClient):
    """Verify that a truncated PNG file is rejected (HTTP 415)."""
    truncated_png = MINIMAL_PNG[:25]
    files = {"file": ("truncated.png", truncated_png, "image/png")}
    response = db_client.post("/api/v1/media", files=files)
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "UNSUPPORTED_MEDIA_FORMAT"

    assert len(list(storage_manager.base_dir.rglob("*.png"))) == 0
    assert len(list(storage_manager.temp_dir.glob("*.tmp"))) == 0


def test_upload_invalid_webp_structure_rejected(db_client: TestClient):
    """Verify that an invalid WebP structure is rejected (HTTP 415)."""
    fake_webp = b"RIFF\x1a\x00\x00\x00WEBPVP8 \x0e\x00\x00\x00corrupt_payload"
    files = {"file": ("malformed.webp", fake_webp, "image/webp")}
    response = db_client.post("/api/v1/media", files=files)
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "UNSUPPORTED_MEDIA_FORMAT"

    assert len(list(storage_manager.base_dir.rglob("*.webp"))) == 0
    assert len(list(storage_manager.temp_dir.glob("*.tmp"))) == 0


def test_upload_source_type_empty_or_whitespace_rejected(db_client: TestClient):
    """Verify that empty or whitespace-only source_type is rejected with HTTP 400."""
    files = {"file": ("test.jpg", MINIMAL_JPEG, "image/jpeg")}
    response = db_client.post("/api/v1/media", files=files, data={"source_type": "   "})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_SOURCE_TYPE"

    assert len(list(storage_manager.base_dir.rglob("*.jpg"))) == 0
    assert len(list(storage_manager.temp_dir.glob("*.tmp"))) == 0


def test_upload_source_type_too_long_rejected(db_client: TestClient):
    """Verify that source_type exceeding 32 characters is rejected with HTTP 400."""
    files = {"file": ("test.jpg", MINIMAL_JPEG, "image/jpeg")}
    response = db_client.post("/api/v1/media", files=files, data={"source_type": "x" * 33})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_SOURCE_TYPE"

    assert len(list(storage_manager.base_dir.rglob("*.jpg"))) == 0
    assert len(list(storage_manager.temp_dir.glob("*.tmp"))) == 0


def test_upload_source_type_custom_extensible_accepted(db_client: TestClient):
    """Verify that a valid extensible custom source string (<= 32 chars) is accepted."""
    files = {"file": ("custom.jpg", MINIMAL_JPEG, "image/jpeg")}
    response = db_client.post("/api/v1/media", files=files, data={"source_type": "flir_thermal_pod"})
    assert response.status_code == 201
    assert response.json()["source_type"] == "flir_thermal_pod"


# ==============================================================================
# 6. TRANSACTION & RECOVERY BEHAVIOR
# ==============================================================================

def test_commit_failure_fresh_session_finds_no_record_preserves_file_and_returns_503(
    db_client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    """
    Verify Scenario 3: Commit raises an exception and fresh session finds no record.
    - Promoted image file MUST remain present in storage (no unlinking on uncertain outcome).
    - Returns controlled HTTP 503 SERVICE_UNAVAILABLE.
    - details contains only media_id.
    - No absolute paths or database internals are leaked.
    """
    from sqlalchemy.orm import Session as SASession

    def failing_commit(self, *args, **kwargs):
        raise OperationalError("Simulated lost connection on commit", {}, None)

    monkeypatch.setattr(SASession, "commit", failing_commit)

    files = {"file": ("uncertain_commit.jpg", MINIMAL_JPEG, "image/jpeg")}
    response = db_client.post("/api/v1/media", files=files)

    # 1. Controlled HTTP 503 response
    assert response.status_code == 503
    err_data = response.json()["error"]
    assert err_data["code"] == "SERVICE_UNAVAILABLE"
    assert "persistence could not be verified" in err_data["message"].lower()
    assert "media_id" in err_data["details"]

    # 2. Evidence preservation: Promoted image file MUST remain present in storage
    stored_files = list(storage_manager.base_dir.rglob("*.jpg"))
    assert len(stored_files) == 1

    # 3. Temp file cleaned up
    assert len(list(storage_manager.temp_dir.glob("*.tmp"))) == 0

    # 4. No absolute paths or SQL details in response
    resp_text = response.text
    assert "media_store" not in resp_text
    assert "temp_store" not in resp_text
    assert "C:\\" not in resp_text
    assert "SELECT" not in resp_text


def test_commit_uncertainty_db_unreachable_preserves_file_and_returns_503(
    db_client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    """
    Verify Scenario 4: Commit raises an exception and fresh session inquiry itself fails.
    - Promoted file MUST be preserved in storage to prevent disaster intelligence loss.
    - Returns controlled HTTP 503 SERVICE_UNAVAILABLE.
    """
    from sqlalchemy.orm import Session as SASession
    from app.services import media_service

    def failing_commit(self, *args, **kwargs):
        raise OperationalError("Simulated lost connection on commit", {}, None)

    class BrokenSessionContext:
        def __enter__(self):
            raise OperationalError("Database completely unreachable during reconciliation query", {}, None)
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    monkeypatch.setattr(SASession, "commit", failing_commit)
    monkeypatch.setattr(media_service, "SessionLocal", lambda: BrokenSessionContext())

    files = {"file": ("uncertain_unreachable.jpg", MINIMAL_JPEG, "image/jpeg")}
    response = db_client.post("/api/v1/media", files=files)

    assert response.status_code == 503
    err_data = response.json()["error"]
    assert err_data["code"] == "SERVICE_UNAVAILABLE"
    assert "media_id" in err_data["details"]

    # The promoted file MUST be preserved
    stored_files = list(storage_manager.base_dir.rglob("*.jpg"))
    assert len(stored_files) == 1
    # Temp file must still be cleaned up
    assert len(list(storage_manager.temp_dir.glob("*.tmp"))) == 0


def test_commit_failure_but_record_persisted_preserves_file(
    db_client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    """
    Verify Scenario 2: Commit raises an exception, but the record is verified to exist
    and be consistent in a fresh session.
    - The image file remains present.
    - Returns HTTP 201 with response object.
    """
    from sqlalchemy.orm import Session as SASession
    from app.models.uploaded_media import UploadedMedia
    from app.services import media_service

    def failing_commit(self, *args, **kwargs):
        raise OperationalError("ACK timeout on commit", {}, None)

    class MockPersistedRecord:
        def __init__(self):
            self.id = None
            self.storage_path = None
            self.media_format = "jpeg"

    class MockFreshSession:
        def __init__(self):
            self.record = MockPersistedRecord()
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass
        def get(self, model, ident):
            if model == UploadedMedia:
                self.record.id = ident
                files = list(storage_manager.base_dir.rglob("*.jpg"))
                if files:
                    self.record.storage_path = str(files[0].relative_to(storage_manager.base_dir)).replace("\\", "/")
                return self.record
            return None

    monkeypatch.setattr(SASession, "commit", failing_commit)
    monkeypatch.setattr(media_service, "SessionLocal", lambda: MockFreshSession())

    files = {"file": ("reconciled.jpg", MINIMAL_JPEG, "image/jpeg")}
    response = db_client.post("/api/v1/media", files=files)
    # Returns HTTP 201 with established consistency
    assert response.status_code == 201
    assert response.json()["media_format"] == "jpeg"

    # Stored file must be preserved
    stored_files = list(storage_manager.base_dir.rglob("*.jpg"))
    assert len(stored_files) == 1


def test_post_promotion_wkt_failure_rolls_back_and_cleans_file(
    db_client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    """
    Verify that an exception during WKTElement construction after file promotion
    rolls back the uncommitted transaction, cleans up the promoted file,
    and returns HTTP 500.
    """
    from app.services import media_service

    def failing_wkt(*args, **kwargs):
        raise ValueError("Simulated spatial WKT construction failure")

    monkeypatch.setattr(media_service, "WKTElement", failing_wkt)

    files = {"file": ("wkt_fail.jpg", MINIMAL_JPEG, "image/jpeg")}
    data = {"latitude": 37.7749, "longitude": -122.4194}
    response = db_client.post("/api/v1/media", files=files, data=data)
    assert response.status_code == 500

    # Promoted file must be cleaned up
    assert len(list(storage_manager.base_dir.rglob("*.jpg"))) == 0
    assert len(list(storage_manager.temp_dir.glob("*.tmp"))) == 0


def test_post_promotion_orm_flush_failure_rolls_back_and_cleans_file(
    db_client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    """
    Verify that an exception during database flush after file promotion
    rolls back the transaction, cleans up the promoted file, and returns HTTP 500.
    """
    from sqlalchemy.orm import Session as SASession
    from sqlalchemy.exc import OperationalError

    def failing_flush(self, *args, **kwargs):
        raise OperationalError("Simulated database failure during flush", {}, None)

    monkeypatch.setattr(SASession, "flush", failing_flush)

    files = {"file": ("flush_fail.jpg", MINIMAL_JPEG, "image/jpeg")}
    response = db_client.post("/api/v1/media", files=files)
    assert response.status_code == 500

    # Promoted file must be cleaned up
    assert len(list(storage_manager.base_dir.rglob("*.jpg"))) == 0
    assert len(list(storage_manager.temp_dir.glob("*.tmp"))) == 0


def test_pre_commit_cleanup_failure_logs_critical_without_masking_original_error(
    db_client: TestClient, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    """
    Verify that if promoted file deletion fails during pre-commit rollback:
    1. A CRITICAL CLEANUP_PENDING log is emitted containing media_id and relative path.
    2. The original exception / HTTP 500 error is returned without being masked or swallowed.
    """
    import logging
    from app.services import media_service

    def failing_response_transform(row):
        raise ValueError("Pre-commit serialization failure")

    def failing_delete(relative_path):
        return False

    monkeypatch.setattr(media_service, "_row_to_media_response", failing_response_transform)
    monkeypatch.setattr(storage_manager, "delete_file", failing_delete)

    with caplog.at_level(logging.CRITICAL):
        files = {"file": ("cleanup_crit.jpg", MINIMAL_JPEG, "image/jpeg")}
        response = db_client.post("/api/v1/media", files=files)

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_SERVER_ERROR"

    crit_logs = [r for r in caplog.records if r.levelno >= logging.CRITICAL and "CLEANUP_PENDING" in r.message]
    assert len(crit_logs) >= 1
    assert "storage_path=" in crit_logs[0].message
    assert "media_id=" in crit_logs[0].message


def test_sanitized_image_validation_errors(db_client: TestClient):
    """
    Verify that corrupted or malformed image uploads return generic, sanitized
    error messages that never expose raw Pillow exception strings ({exc}) or internal paths.
    """
    corrupted_bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 20 + b"MALFORMED_GARBAGE_PAYLOAD"
    files = {"file": ("corrupt.jpg", corrupted_bytes, "image/jpeg")}
    response = db_client.post("/api/v1/media", files=files)

    assert response.status_code == 415
    data = response.json()
    assert data["error"]["code"] == "UNSUPPORTED_MEDIA_FORMAT"
    assert data["error"]["message"] == "Corrupted or malformed image content."
    assert "Traceback" not in response.text
    assert "Pillow" not in response.text
    assert "UnidentifiedImageError" not in response.text
    assert "SyntaxError" not in response.text


def test_recovery_error_never_accidentally_deletes_image(
    db_client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    """
    Verify Scenario 6: A recovery/reconciliation error never accidentally deletes
    a potentially committed image.
    """
    from sqlalchemy.orm import Session as SASession
    from app.services import media_service

    def failing_commit(self, *args, **kwargs):
        raise OperationalError("Lost DB connection during commit", {}, None)

    class CrashingReconciliationSession:
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass
        def get(self, model, ident):
            raise RuntimeError("Unexpected internal crash inside session.get during reconciliation")

    monkeypatch.setattr(SASession, "commit", failing_commit)
    monkeypatch.setattr(media_service, "SessionLocal", lambda: CrashingReconciliationSession())

    files = {"file": ("crash_recovery.jpg", MINIMAL_JPEG, "image/jpeg")}
    response = db_client.post("/api/v1/media", files=files)

    # Must preserve file and return 503
    assert response.status_code == 503
    assert len(list(storage_manager.base_dir.rglob("*.jpg"))) == 1


def test_pre_commit_serialization_failure_rolls_back_and_cleans_file(
    db_client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    """
    Verify that a failure during response pre-construction (before commit is called)
    rolls back the uncommitted transaction and deletes the promoted file.
    """
    from app.services import media_service

    def failing_response_transform(row):
        raise ValueError("Simulated serialization bug prior to commit")

    monkeypatch.setattr(media_service, "_row_to_media_response", failing_response_transform)

    files = {"file": ("precommit_fail.jpg", MINIMAL_JPEG, "image/jpeg")}
    response = db_client.post("/api/v1/media", files=files)
    assert response.status_code == 500

    # Promoted file must be cleaned up
    assert len(list(storage_manager.base_dir.rglob("*.jpg"))) == 0
    assert len(list(storage_manager.temp_dir.glob("*.tmp"))) == 0


def test_client_facing_error_responses_contain_no_internal_details(
    db_client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    """
    Verify Scenario 7: Client-facing error responses contain no absolute paths,
    SQL statements, credentials, or raw database exception details.
    """
    from sqlalchemy.orm import Session as SASession

    def failing_commit(self, *args, **kwargs):
        raise OperationalError(
            "FATAL: password authentication failed for user 'scout_admin' in SELECT * FROM uploaded_media",
            {},
            None,
        )

    monkeypatch.setattr(SASession, "commit", failing_commit)

    files = {"file": ("leak_check.jpg", MINIMAL_JPEG, "image/jpeg")}
    response = db_client.post("/api/v1/media", files=files)

    assert response.status_code == 503
    resp_text = response.text

    assert "scout_admin" not in resp_text
    assert "password" not in resp_text
    assert "FATAL" not in resp_text
    assert "SELECT" not in resp_text
    assert "uploaded_media" not in resp_text
    assert "media_store" not in resp_text
    assert "temp_store" not in resp_text
    assert "C:\\" not in resp_text


def test_safe_error_messages_contain_no_internal_paths(
    db_client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    """
    Verify that storage failures return safe generic error messages
    that never leak server directories or operating system paths to clients.
    """
    from app.core.exceptions import StorageError

    def failing_finalize(temp_path, relative_dest_path):
        raise StorageError("Failed to store media file on server.")

    monkeypatch.setattr(storage_manager, "finalize_upload", failing_finalize)

    files = {"file": ("path_leak_test.jpg", MINIMAL_JPEG, "image/jpeg")}
    response = db_client.post("/api/v1/media", files=files)
    assert response.status_code == 500

    raw_response_text = response.text
    # Must not contain common internal path patterns
    assert "media_store" not in raw_response_text
    assert "temp_store" not in raw_response_text
    assert "C:\\" not in raw_response_text
    assert "/home/" not in raw_response_text
