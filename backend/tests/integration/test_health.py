from datetime import datetime
from fastapi.testclient import TestClient


def test_health_check_endpoint(client: TestClient):
    """
    Integration test verifying that the liveness probe returns HTTP 200
    and conforms to the expected HealthResponse schema.
    """
    response = client.get("/api/v1/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "healthy"
    assert data["app_name"] == "SCOUT"
    assert "environment" in data
    assert "timestamp" in data

    # Verify timestamp format is ISO-compliant
    parsed_time = datetime.fromisoformat(data["timestamp"])
    assert parsed_time is not None


def test_root_endpoint(client: TestClient):
    """
    Integration test verifying that the root navigational endpoint returns HTTP 200.
    """
    response = client.get("/")
    assert response.status_code == 200

    data = response.json()
    assert "Welcome to SCOUT API" in data["message"]
    assert data["docs_url"] == "/docs"
    assert data["health_endpoint"] == "/api/v1/health"


def test_nonexistent_endpoint(client: TestClient):
    """
    Verify standard 404 response for unknown routes.
    """
    response = client.get("/api/v1/nonexistent")
    assert response.status_code == 404
