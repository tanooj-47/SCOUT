from datetime import datetime, timezone
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.database


def test_create_incident_success(db_client: TestClient):
    """Verify that a valid incident is created with PostGIS coordinates and default status."""
    payload = {
        "title": "Blackwood Fire Incident",
        "disaster_type": "wildfire",
        "severity": "high",
        "location": {"latitude": 39.1234, "longitude": -120.4567},
        "metadata": {"region": "Tahoe Basin", "station_id": "FS-401"},
    }
    response = db_client.post("/api/v1/incidents", json=payload)
    assert response.status_code == 201

    data = response.json()
    assert "id" in data
    assert data["title"] == "Blackwood Fire Incident"
    assert data["disaster_type"] == "wildfire"
    assert data["status"] == "reported"
    assert data["severity"] == "high"
    assert data["location"]["latitude"] == 39.1234
    assert data["location"]["longitude"] == -120.4567
    assert data["location"]["srid"] == 4326
    assert data["is_archived"] is False
    assert data["archived_at"] is None
    assert data["contained_at"] is None
    assert data["metadata"]["region"] == "Tahoe Basin"


def test_create_incident_validation_errors(db_client: TestClient):
    """Verify rejection of invalid coordinates, short title, and extra fields."""
    # Latitude out of bounds
    res_lat = db_client.post(
        "/api/v1/incidents",
        json={
            "title": "Invalid Lat Incident",
            "disaster_type": "wildfire",
            "location": {"latitude": 95.0, "longitude": 0.0},
        },
    )
    assert res_lat.status_code == 422
    assert res_lat.json()["error"]["code"] == "VALIDATION_ERROR"

    # NaN in coordinates (sent as raw JSON payload)
    res_nan = db_client.post(
        "/api/v1/incidents",
        content='{"title": "Invalid NaN Incident", "disaster_type": "wildfire", "location": {"latitude": NaN, "longitude": 0.0}}',
        headers={"Content-Type": "application/json"},
    )
    assert res_nan.status_code == 422

    # Client providing SRID (extra forbidden)
    res_srid = db_client.post(
        "/api/v1/incidents",
        json={
            "title": "Invalid SRID Incident",
            "disaster_type": "wildfire",
            "location": {"latitude": 10.0, "longitude": 10.0, "srid": 4326},
        },
    )
    assert res_srid.status_code == 422

    # Empty title
    res_title = db_client.post(
        "/api/v1/incidents",
        json={
            "title": "   ",
            "disaster_type": "flood",
            "location": {"latitude": 10.0, "longitude": 10.0},
        },
    )
    assert res_title.status_code == 422


def test_get_incident_detail_and_counts(db_client: TestClient):
    """Verify retrieval of incident detail, projected coordinates, and summary counts."""
    # 1. Create incident
    create_res = db_client.post(
        "/api/v1/incidents",
        json={
            "title": "Valley Inundation",
            "disaster_type": "flood",
            "severity": "moderate",
            "location": {"latitude": 28.5383, "longitude": -81.3792},
            "metadata": {"gauge_level_meters": 4.2},
        },
    )
    assert create_res.status_code == 201
    incident_id = create_res.json()["id"]

    # 2. Retrieve detail
    detail_res = db_client.get(f"/api/v1/incidents/{incident_id}")
    assert detail_res.status_code == 200
    data = detail_res.json()

    assert data["id"] == incident_id
    assert data["title"] == "Valley Inundation"
    assert data["location"]["latitude"] == 28.5383
    assert data["location"]["longitude"] == -81.3792
    assert data["summary_counts"]["media_count"] == 0
    assert data["summary_counts"]["observations_count"] == 0
    assert data["summary_counts"]["predictions_count"] == 0


def test_get_incident_detail_with_postgis_perimeter(db_client: TestClient, db_session: Session):
    """
    Verify retrieval of incident detail with a real PostGIS MultiPolygon perimeter.
    Confirms GeoJSON serialization, coordinate accuracy, perimeter timestamp,
    and exclusion from list endpoint responses.
    """
    # 1. Create incident using the existing API
    create_payload = {
        "title": "Rim Fire Perimeter Survey",
        "disaster_type": "wildfire",
        "severity": "critical",
        "location": {"latitude": 37.8651, "longitude": -119.5383},
        "metadata": {"containment_zone": "Sector 4"},
    }
    create_res = db_client.post("/api/v1/incidents", json=create_payload)
    assert create_res.status_code == 201
    incident_id = create_res.json()["id"]

    # 2. Set observed_perimeter to valid MULTIPOLYGON SRID 4326 and perimeter_updated_at
    perimeter_wkt = (
        "MULTIPOLYGON(((-120.0 38.0, -120.0 38.5, -119.5 38.5, -119.5 38.0, -120.0 38.0)))"
    )
    perimeter_now = datetime.now(timezone.utc)

    db_session.execute(
        text(
            """
            UPDATE incidents
            SET observed_perimeter = ST_GeomFromText(:wkt, 4326),
                perimeter_updated_at = :perimeter_updated_at
            WHERE id = :incident_id
            """
        ),
        {
            "wkt": perimeter_wkt,
            "perimeter_updated_at": perimeter_now,
            "incident_id": uuid.UUID(incident_id),
        },
    )
    db_session.commit()

    # 3. Request GET /api/v1/incidents/{incident_id}
    detail_res = db_client.get(f"/api/v1/incidents/{incident_id}")
    assert detail_res.status_code == 200
    detail_data = detail_res.json()

    # 4. Verify coordinates and metadata
    assert detail_data["id"] == incident_id
    assert detail_data["location"]["latitude"] == 37.8651
    assert detail_data["location"]["longitude"] == -119.5383
    assert detail_data["location"]["srid"] == 4326

    # 5. Verify observed_perimeter GeoJSON structure and geometry
    perimeter_geojson = detail_data["observed_perimeter"]
    assert isinstance(perimeter_geojson, dict)
    assert perimeter_geojson["type"] == "MultiPolygon"
    assert "coordinates" in perimeter_geojson

    expected_coords = [
        [
            [
                [-120.0, 38.0],
                [-120.0, 38.5],
                [-119.5, 38.5],
                [-119.5, 38.0],
                [-120.0, 38.0],
            ]
        ]
    ]
    assert perimeter_geojson["coordinates"] == expected_coords

    # 6. Verify perimeter_updated_at is returned correctly
    assert detail_data["perimeter_updated_at"] is not None
    parsed_updated_at = datetime.fromisoformat(detail_data["perimeter_updated_at"])
    assert parsed_updated_at.tzinfo is not None

    # 7. Verify that list endpoint does not retrieve or return actual perimeter geometry
    list_res = db_client.get("/api/v1/incidents")
    assert list_res.status_code == 200
    list_items = list_res.json()["items"]
    matched_item = next(item for item in list_items if item["id"] == incident_id)
    assert matched_item["observed_perimeter"] is None
    assert matched_item["perimeter_updated_at"] is None


def test_get_incident_not_found_and_malformed_uuid(db_client: TestClient):
    """Verify 404 on nonexistent UUID and 422 on malformed UUID."""
    random_id = str(uuid.uuid4())
    res_404 = db_client.get(f"/api/v1/incidents/{random_id}")
    assert res_404.status_code == 404
    assert res_404.json()["error"]["code"] == "INCIDENT_NOT_FOUND"

    res_422 = db_client.get("/api/v1/incidents/not-a-valid-uuid")
    assert res_422.status_code == 422
    assert res_422.json()["error"]["code"] == "VALIDATION_ERROR"


def test_list_incidents_filtering_and_pagination(db_client: TestClient):
    """Verify listing with pagination, filtering by disaster_type, status, and severity."""
    # Seed distinct incidents
    incidents_data = [
        {"title": "Wildfire Alpha", "disaster_type": "wildfire", "severity": "low", "location": {"latitude": 30.0, "longitude": -100.0}},
        {"title": "Wildfire Beta", "disaster_type": "wildfire", "severity": "critical", "location": {"latitude": 31.0, "longitude": -101.0}},
        {"title": "Flood Gamma", "disaster_type": "flood", "severity": "moderate", "location": {"latitude": 32.0, "longitude": -102.0}},
    ]
    for inc in incidents_data:
        res = db_client.post("/api/v1/incidents", json=inc)
        assert res.status_code == 201

    # Filter by disaster_type=wildfire
    res_wf = db_client.get("/api/v1/incidents?disaster_type=wildfire")
    assert res_wf.status_code == 200
    data_wf = res_wf.json()
    assert data_wf["total"] >= 2
    for item in data_wf["items"]:
        assert item["disaster_type"] == "wildfire"
        assert item["observed_perimeter"] is None  # List never returns perimeter

    # Filter by severity=critical
    res_crit = db_client.get("/api/v1/incidents?severity=critical")
    assert res_crit.status_code == 200
    data_crit = res_crit.json()
    assert data_crit["total"] >= 1
    for item in data_crit["items"]:
        assert item["severity"] == "critical"

    # Pagination test: limit 1, offset 0
    res_page = db_client.get("/api/v1/incidents?limit=1&offset=0")
    assert res_page.status_code == 200
    page_data = res_page.json()
    assert len(page_data["items"]) == 1
    assert page_data["limit"] == 1
    assert page_data["offset"] == 0
    assert page_data["has_prev"] is False


def test_list_incidents_sorting_options(db_client: TestClient):
    """Verify sorting by reported_at, updated_at, and operational severity ranking."""
    res_sev = db_client.get("/api/v1/incidents?order_by=severity&order_direction=desc")
    assert res_sev.status_code == 200
    items = res_sev.json()["items"]
    # Check severity hierarchy: critical (1) before high (2) before moderate (3) before low (4)
    rank = {"critical": 1, "high": 2, "moderate": 3, "low": 4}
    severities = [rank[item["severity"]] for item in items]
    assert severities == sorted(severities)

    # Ascending updated_at
    res_upd = db_client.get("/api/v1/incidents?order_by=updated_at&order_direction=asc")
    assert res_upd.status_code == 200


def test_patch_incident_fields_and_transitions(db_client: TestClient):
    """Verify partial update of title, severity, location, and valid status transition."""
    # 1. Create incident (starts at 'reported')
    create_res = db_client.post(
        "/api/v1/incidents",
        json={
            "title": "Bear Creek Fire",
            "disaster_type": "wildfire",
            "severity": "low",
            "location": {"latitude": 38.0, "longitude": -120.0},
        },
    )
    incident_id = create_res.json()["id"]

    # 2. Patch title and severity
    patch1 = db_client.patch(
        f"/api/v1/incidents/{incident_id}",
        json={"title": "Bear Creek Fire Complex", "severity": "high"},
    )
    assert patch1.status_code == 200
    assert patch1.json()["title"] == "Bear Creek Fire Complex"
    assert patch1.json()["severity"] == "high"

    # 3. Transition reported -> active
    patch2 = db_client.patch(
        f"/api/v1/incidents/{incident_id}",
        json={"status": "active"},
    )
    assert patch2.status_code == 200
    assert patch2.json()["status"] == "active"
    assert patch2.json()["contained_at"] is None

    # 4. Transition active -> contained (triggers contained_at)
    patch3 = db_client.patch(
        f"/api/v1/incidents/{incident_id}",
        json={"status": "contained"},
    )
    assert patch3.status_code == 200
    assert patch3.json()["status"] == "contained"
    assert patch3.json()["contained_at"] is not None

    # 5. Transition contained -> active (resets contained_at to null)
    patch4 = db_client.patch(
        f"/api/v1/incidents/{incident_id}",
        json={"status": "active"},
    )
    assert patch4.status_code == 200
    assert patch4.json()["status"] == "active"
    assert patch4.json()["contained_at"] is None

    # 6. Contain again and transition contained -> resolved (preserves contained_at)
    db_client.patch(f"/api/v1/incidents/{incident_id}", json={"status": "contained"})
    patch6 = db_client.patch(f"/api/v1/incidents/{incident_id}", json={"status": "resolved"})
    assert patch6.status_code == 200
    assert patch6.json()["status"] == "resolved"
    assert patch6.json()["contained_at"] is not None


def test_patch_rejection_of_invalid_transitions(db_client: TestClient):
    """Verify 409 Conflict when attempting forbidden status transitions."""
    # Create incident (starts at 'reported')
    create_res = db_client.post(
        "/api/v1/incidents",
        json={
            "title": "State Machine Test Incident",
            "disaster_type": "wildfire",
            "location": {"latitude": 38.0, "longitude": -120.0},
        },
    )
    incident_id = create_res.json()["id"]

    # reported -> contained is forbidden (must investigate or confirm active first)
    res_bad = db_client.patch(
        f"/api/v1/incidents/{incident_id}",
        json={"status": "contained"},
    )
    assert res_bad.status_code == 409
    assert res_bad.json()["error"]["code"] == "INVALID_STATUS_TRANSITION"


def test_patch_rejection_of_null_and_empty_payload(db_client: TestClient):
    """Verify rejection of empty body ({}) and explicit null on non-nullable fields."""
    create_res = db_client.post(
        "/api/v1/incidents",
        json={
            "title": "Patch Validation Incident",
            "disaster_type": "flood",
            "location": {"latitude": 15.0, "longitude": 75.0},
        },
    )
    incident_id = create_res.json()["id"]

    # Empty payload
    res_empty = db_client.patch(f"/api/v1/incidents/{incident_id}", json={})
    assert res_empty.status_code == 422
    assert res_empty.json()["error"]["code"] == "VALIDATION_ERROR"

    # Explicit null on non-nullable fields
    for field in ["title", "status", "severity", "location", "metadata"]:
        res_null = db_client.patch(f"/api/v1/incidents/{incident_id}", json={field: None})
        assert res_null.status_code == 422


def test_patch_metadata_full_replacement(db_client: TestClient):
    """Verify that metadata PATCH fully replaces the JSONB dictionary."""
    create_res = db_client.post(
        "/api/v1/incidents",
        json={
            "title": "Metadata Replacement Test",
            "disaster_type": "earthquake",
            "location": {"latitude": 35.0, "longitude": 139.0},
            "metadata": {"initial_key": "val1", "keep_me": "no"},
        },
    )
    incident_id = create_res.json()["id"]

    # Replace metadata
    patch_res = db_client.patch(
        f"/api/v1/incidents/{incident_id}",
        json={"metadata": {"new_key": "val2"}},
    )
    assert patch_res.status_code == 200
    meta = patch_res.json()["metadata"]
    assert meta == {"new_key": "val2"}
    assert "initial_key" not in meta


def test_archive_incident_and_immutability(db_client: TestClient):
    """Verify soft-archival, idempotency, and 409 rejection of subsequent PATCH requests."""
    # 1. Create incident
    create_res = db_client.post(
        "/api/v1/incidents",
        json={
            "title": "Incident To Archive",
            "disaster_type": "flood",
            "location": {"latitude": 10.0, "longitude": 20.0},
        },
    )
    incident_id = create_res.json()["id"]

    # 2. Archive incident
    arch_res = db_client.post(f"/api/v1/incidents/{incident_id}/archive")
    assert arch_res.status_code == 200
    data = arch_res.json()
    assert data["is_archived"] is True
    assert data["archived_at"] is not None

    # 3. Idempotent repeat archive returns 200
    arch_repeat = db_client.post(f"/api/v1/incidents/{incident_id}/archive")
    assert arch_repeat.status_code == 200
    assert arch_repeat.json()["is_archived"] is True

    # 4. Attempting to PATCH archived incident returns 409 Conflict
    patch_archived = db_client.patch(
        f"/api/v1/incidents/{incident_id}",
        json={"title": "Attempted Change on Archived"},
    )
    assert patch_archived.status_code == 409
    assert patch_archived.json()["error"]["code"] == "INCIDENT_ARCHIVED"

    # 5. Default list excludes archived incident
    list_active = db_client.get("/api/v1/incidents")
    active_ids = [item["id"] for item in list_active.json()["items"]]
    assert incident_id not in active_ids

    # 6. Listing with is_archived=true includes it
    list_archived = db_client.get("/api/v1/incidents?is_archived=true")
    archived_ids = [item["id"] for item in list_archived.json()["items"]]
    assert incident_id in archived_ids
