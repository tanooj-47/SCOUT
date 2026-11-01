from datetime import date, datetime, timezone
from unittest.mock import MagicMock
import pytest

from app.environmental.cache import EnvironmentalCache
from app.environmental.exceptions import ProviderTimeoutError
from app.environmental.schemas import (
    EnvironmentalIngestRequest,
    EnvironmentalObservationItem,
    EnvironmentalTypology,
    LocationType,
)
from app.environmental.services import EnvironmentalService


@pytest.fixture
def mock_open_meteo():
    client = MagicMock()
    client.get_current_conditions.return_value = {
        "latitude": 28.625,
        "longitude": 77.25,
        "current": {
            "time": "2026-10-31T08:00",
            "temperature_2m": 31.0,
            "relative_humidity_2m": 45.0,
            "wind_speed_10m": 4.0,
            "wind_direction_10m": 120.0,
            "precipitation": 0.0,
            "surface_pressure": 1010.0,
        },
    }
    client.get_weather_forecast.return_value = {
        "latitude": 28.625,
        "longitude": 77.25,
        "hourly": {
            "time": ["2026-10-31T08:00", "2026-10-31T09:00"],
            "temperature_2m": [31.0, 31.5],
            "relative_humidity_2m": [45.0, 44.0],
            "wind_speed_10m": [4.0, 4.2],
            "wind_direction_10m": [120.0, 125.0],
            "precipitation": [0.0, 0.0],
            "surface_pressure": [1010.0, 1009.8],
        },
    }
    client.check_health.return_value = True
    return client


@pytest.fixture
def mock_nasa_power():
    client = MagicMock()
    client.get_historical_weather.return_value = {
        "geometry": {"type": "Point", "coordinates": [77.25, 28.625, 200.0]},
        "properties": {
            "parameter": {
                "T2M": {"2026051500": 28.0},
                "RH2M": {"2026051500": 50.0},
                "WS10M": {"2026051500": 3.0},
                "WD10M": {"2026051500": 90.0},
                "PRECTOTCORR": {"2026051500": 0.0},
                "PS": {"2026051500": 101.0},
            }
        },
    }
    client.check_health.return_value = True
    return client


class TestEnvironmentalService:

    def test_get_current_conditions_caches_and_returns(self, mock_open_meteo):
        cache = EnvironmentalCache()
        service = EnvironmentalService(
            db_session=None,
            cache=cache,
            open_meteo_client=mock_open_meteo,
        )

        item, is_stale = service.get_current_conditions(latitude=28.6139, longitude=77.2090)
        assert item.temperature_celsius == 31.0
        assert item.typology == EnvironmentalTypology.MODEL_ANALYSIS
        assert is_stale is False
        assert mock_open_meteo.get_current_conditions.call_count == 1

        # Second call should hit cache and NOT call provider again
        item2, is_stale2 = service.get_current_conditions(latitude=28.6139, longitude=77.2090)
        assert item2.temperature_celsius == 31.0
        assert is_stale2 is False
        assert mock_open_meteo.get_current_conditions.call_count == 1

    def test_stale_fallback_when_provider_fails(self, mock_open_meteo):
        cache = EnvironmentalCache()
        service = EnvironmentalService(
            db_session=None,
            cache=cache,
            open_meteo_client=mock_open_meteo,
        )

        # First request populates cache
        item, _ = service.get_current_conditions(latitude=28.6139, longitude=77.2090)

        # Manually expire the cache entry
        key = cache.generate_cache_key(
            provider="open-meteo",
            dataset_or_model="best_match",
            typology="model_analysis",
            lat=28.6139,
            lon=77.2090,
            time_window="current",
        )
        cache.set(key, [item], EnvironmentalTypology.MODEL_ANALYSIS, custom_ttl_seconds=-1)

        # Make provider fail
        mock_open_meteo.get_current_conditions.side_effect = ProviderTimeoutError(
            provider="open-meteo",
            timeout_seconds=5.0,
        )

        # Call service - should return stale item
        stale_item, is_stale = service.get_current_conditions(latitude=28.6139, longitude=77.2090)
        assert is_stale is True
        assert stale_item.is_stale is True
        assert stale_item.temperature_celsius == 31.0

    def test_get_weather_forecast(self, mock_open_meteo):
        cache = EnvironmentalCache()
        service = EnvironmentalService(
            db_session=None,
            cache=cache,
            open_meteo_client=mock_open_meteo,
        )

        items, is_stale = service.get_weather_forecast(latitude=28.6139, longitude=77.2090, forecast_days=2)
        assert len(items) == 2
        assert items[0].typology == EnvironmentalTypology.FORECAST
        assert is_stale is False

    def test_get_historical_reanalysis_nasa_power(self, mock_nasa_power):
        cache = EnvironmentalCache()
        service = EnvironmentalService(
            db_session=None,
            cache=cache,
            nasa_power_client=mock_nasa_power,
        )

        items, is_stale = service.get_historical_reanalysis(
            latitude=28.6139,
            longitude=77.2090,
            start_date=date(2026, 5, 15),
            end_date=date(2026, 5, 15),
            provider="nasa-power",
        )
        assert len(items) == 1
        assert items[0].provider == "nasa-power"
        assert items[0].surface_pressure_hpa == 1010.0
        assert is_stale is False

    def test_ingest_data_current(self, mock_open_meteo):
        cache = EnvironmentalCache()
        service = EnvironmentalService(
            db_session=None,
            cache=cache,
            open_meteo_client=mock_open_meteo,
        )

        req = EnvironmentalIngestRequest(
            latitude=28.6139,
            longitude=77.2090,
            typology=EnvironmentalTypology.MODEL_ANALYSIS,
        )
        res = service.ingest_data(req)
        assert res.count == 1
        assert res.typology == EnvironmentalTypology.MODEL_ANALYSIS
        assert res.is_stale is False

    def test_check_health(self, mock_open_meteo, mock_nasa_power):
        service = EnvironmentalService(
            db_session=None,
            open_meteo_client=mock_open_meteo,
            nasa_power_client=mock_nasa_power,
        )
        health = service.check_health()
        assert health["status"] == "healthy"
        assert health["providers"]["open_meteo"] == "operational"
        assert health["providers"]["nasa_power"] == "operational"
