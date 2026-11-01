from datetime import date, datetime, timezone
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient

from app.api.v1.endpoints.environmental import get_environmental_service
from app.environmental.cache import EnvironmentalCache
from app.environmental.schemas import (
    EnvironmentalObservationItem,
    EnvironmentalTypology,
    LocationType,
)
from app.environmental.services import EnvironmentalService
from app.main import app


@pytest.fixture
def mock_service():
    service = MagicMock(spec=EnvironmentalService)

    sample_obs = EnvironmentalObservationItem(
        location_type=LocationType.GRID,
        location_id="grid:open_meteo:best_match:28.6250_77.2500",
        requested_latitude=28.6139,
        requested_longitude=77.2090,
        resolved_latitude=28.6250,
        resolved_longitude=77.2500,
        typology=EnvironmentalTypology.MODEL_ANALYSIS,
        valid_time_utc=datetime(2026, 10, 31, 8, 0, tzinfo=timezone.utc),
        recorded_at=datetime(2026, 10, 31, 8, 0, tzinfo=timezone.utc),
        source="open-meteo",
        provider="open-meteo",
        dataset_or_model="best_match",
        temperature_celsius=31.2,
        relative_humidity=45.0,
        wind_speed_mps=4.0,
        wind_direction_degrees=120.0,
        precipitation_mm=0.0,
        surface_pressure_hpa=1010.0,
        is_stale=False,
    )

    forecast_obs = sample_obs.model_copy(
        update={
            "typology": EnvironmentalTypology.FORECAST,
            "init_time_utc": datetime(2026, 10, 31, 0, 0, tzinfo=timezone.utc),
            "lead_time_hours": 8.0,
        }
    )

    service.check_health.return_value = {
        "status": "healthy",
        "providers": {"open_meteo": "operational", "nasa_power": "operational"},
        "cache_entries": 4,
    }
    service.get_current_conditions.return_value = (sample_obs, False)
    service.get_weather_forecast.return_value = ([forecast_obs], False)
    service.get_historical_reanalysis.return_value = ([sample_obs], False)
    service.ingest_data.return_value = {
        "count": 1,
        "location_id": "grid:open_meteo:best_match:28.6250_77.2500",
        "provider": "open-meteo",
        "dataset_or_model": "best_match",
        "typology": "model_analysis",
        "cached": False,
        "is_stale": False,
        "items": [sample_obs.model_dump(mode="json")],
    }
    service.repository = None
    return service


@pytest.fixture
def client_with_mock_service(mock_service):
    app.dependency_overrides[get_environmental_service] = lambda: mock_service
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_environmental_service, None)


class TestEnvironmentalAPI:

    def test_health_endpoint(self, client_with_mock_service):
        response = client_with_mock_service.get("/api/v1/environmental/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "providers" in data

    def test_get_current_conditions_endpoint(self, client_with_mock_service):
        response = client_with_mock_service.get(
            "/api/v1/environmental/current?latitude=28.6139&longitude=77.2090"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["temperature_celsius"] == 31.2
        assert data["typology"] == "model_analysis"
        assert data["is_stale"] is False

    def test_get_forecast_endpoint(self, client_with_mock_service):
        response = client_with_mock_service.get(
            "/api/v1/environmental/forecast?latitude=28.6139&longitude=77.2090&forecast_days=3"
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["typology"] == "forecast"

    def test_get_historical_endpoint(self, client_with_mock_service):
        response = client_with_mock_service.get(
            "/api/v1/environmental/historical?latitude=28.6139&longitude=77.2090&start_date=2026-05-01&end_date=2026-05-02"
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_ingest_endpoint(self, client_with_mock_service):
        payload = {
            "latitude": 28.6139,
            "longitude": 77.2090,
            "typology": "model_analysis",
            "provider": "open-meteo",
        }
        response = client_with_mock_service.post("/api/v1/environmental/ingest", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["provider"] == "open-meteo"

    def test_fwi_calculate_endpoint(self, client_with_mock_service):
        payload = {
            "latitude": 40.0,
            "readings": [
                {
                    "date": "1985-04-13",
                    "temperature_celsius": 17.0,
                    "relative_humidity": 42.0,
                    "wind_speed_kmh": 25.0,
                    "precipitation_mm": 0.0,
                }
            ],
            "initial_ffmc": 85.0,
            "initial_dmc": 6.0,
            "initial_dc": 15.0,
        }
        response = client_with_mock_service.post("/api/v1/environmental/fwi/calculate", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "records" in data
        assert len(data["records"]) == 1
        assert data["records"][0]["ffmc"] == 87.7
        assert data["records"][0]["danger_rating"] == "Moderate"
        assert data["spinup_warning"] is True  # series < 30 days

    def test_validation_error_invalid_coordinates(self, client_with_mock_service):
        # Latitude 95.0 is out of bounds
        response = client_with_mock_service.get(
            "/api/v1/environmental/current?latitude=95.0&longitude=77.2090"
        )
        assert response.status_code == 422
