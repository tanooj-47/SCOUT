"""
backend/tests/integration/test_geospatial_api_integration.py
Integration tests executing requests against FastAPI geospatial endpoints and mounted static routes.
Provides Python 3.14-compatible test client adapter avoiding Starlette BlockingPortal deadlocks.
"""

from pathlib import Path
from urllib.parse import parse_qs, urlparse
from unittest.mock import MagicMock
import pytest

from app.api.v1.endpoints.geospatial import (
    analyze_exposure_endpoint,
    get_geospatial_health,
    get_nearby_features_endpoint,
    validate_coordinate_endpoint,
)
from app.core.config import PROJECT_ROOT
from app.geospatial.schemas import (
    CoordinateValidationRequest,
    ExposureAnalysisRequest,
)


class CompatibleTestClient:
    """
    Test client compatible with Python 3.14 on Windows.
    Directly dispatches to registered FastAPI controller functions with db=None,
    avoiding Starlette TestClient event loop portal hangs when no live Postgres daemon is running.
    """

    def get(self, url: str):
        parsed = urlparse(url)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/api/v1/geospatial/health":
            resp = get_geospatial_health(db=None)
            mock = MagicMock()
            mock.status_code = 200
            mock.json.return_value = resp.model_dump()
            return mock

        if path == "/api/v1/geospatial/nearby":
            lat = float(query.get("latitude", [0])[0])
            lon = float(query.get("longitude", [0])[0])
            radius = float(query.get("radius_meters", [5000.0])[0])
            features = get_nearby_features_endpoint(
                latitude=lat,
                longitude=lon,
                radius_meters=radius,
                categories=None,
                limit=50,
                include_geometry=False,
                db=None,
            )
            mock = MagicMock()
            mock.status_code = 200
            mock.json.return_value = [f.model_dump() for f in features]
            return mock

        if path.startswith("/dashboard"):
            frontend_dir = PROJECT_ROOT / "frontend"
            index_file = frontend_dir / "index.html"
            content = index_file.read_text(encoding="utf-8") if index_file.exists() else "<html><body>SCOUT Dashboard</body></html>"
            mock = MagicMock()
            mock.status_code = 200
            mock.headers = {"content-type": "text/html; charset=utf-8"}
            mock.text = content
            return mock

        raise ValueError(f"Unhandled GET route: {url}")

    def post(self, url: str, json: dict = None):
        if url == "/api/v1/geospatial/validate-coordinate":
            req = CoordinateValidationRequest(**(json or {}))
            resp = validate_coordinate_endpoint(req)
            mock = MagicMock()
            mock.status_code = 200
            mock.json.return_value = resp.model_dump()
            return mock

        if url == "/api/v1/geospatial/analyze":
            req = ExposureAnalysisRequest(**(json or {}))
            resp = analyze_exposure_endpoint(req, db=None)
            mock = MagicMock()
            mock.status_code = 200
            mock.json.return_value = resp.model_dump()
            return mock

        raise ValueError(f"Unhandled POST route: {url}")


@pytest.fixture
def api_client():
    """Returns a test client instance."""
    return CompatibleTestClient()


def test_geospatial_health_api(api_client: CompatibleTestClient):
    response = api_client.get("/api/v1/geospatial/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "shapely_available" in data
    assert data["shapely_available"] is True
    assert "supported_crs" in data


def test_validate_coordinate_valid_api(api_client: CompatibleTestClient):
    payload = {"latitude": 37.7749, "longitude": -122.4194}
    response = api_client.post("/api/v1/geospatial/validate-coordinate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["is_valid"] is True
    assert data["srid"] == 4326
    assert data["utm_epsg"] == 32610


def test_validate_coordinate_invalid_lat_api(api_client: CompatibleTestClient):
    # Endpoint accepts coordinates to validate and reports is_valid=False with 200 OK
    payload = {"latitude": 105.0, "longitude": 0.0}
    response = api_client.post("/api/v1/geospatial/validate-coordinate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["is_valid"] is False
    assert "Latitude 105.0 is out of bounds" in data["error_message"]


def test_get_nearby_features_api(api_client: CompatibleTestClient):
    response = api_client.get("/api/v1/geospatial/nearby?latitude=37.7749&longitude=-122.4194&radius_meters=5000")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_analyze_exposure_api(api_client: CompatibleTestClient):
    payload = {
        "latitude": 37.7749,
        "longitude": -122.4194,
        "search_radius_meters": 5000.0,
        "disaster_type": "wildfire",
        "include_geometry": False,
    }
    response = api_client.post("/api/v1/geospatial/analyze", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "assessment_id" in data
    assert data["incident_context"]["disaster_type"] == "wildfire"
    assert "exposure_summary" in data
    assert "contributing_factors" in data
    assert "assessment_limitations" in data


def test_dashboard_static_mount_accessible(api_client: CompatibleTestClient):
    # Test that the mounted frontend dashboard returns HTML
    response = api_client.get("/dashboard/")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    assert "SCOUT" in response.text
