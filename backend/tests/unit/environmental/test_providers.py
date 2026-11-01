"""
backend/tests/unit/environmental/test_providers.py
Unit tests for external environmental data providers using mocked HTTP transports.
Verifies response parsing, retry backoff, error handling, and temporal limits without live network calls.
"""

from datetime import date
import json
import pytest
import httpx

from app.environmental.exceptions import (
    ProviderAPIError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    TimeRangeUnavailableError,
)
from app.environmental.providers.open_meteo import OpenMeteoProvider
from app.environmental.providers.nasa_power import (
    NasaPowerProvider,
    NASA_POWER_HOURLY_EARLIEST_DATE,
    NASA_POWER_DAILY_EARLIEST_DATE,
)
from app.geospatial.exceptions import InvalidCoordinateError


# Mock response payloads
MOCK_OPEN_METEO_CURRENT = {
    "latitude": 28.62,
    "longitude": 77.22,
    "generationtime_ms": 0.12,
    "utc_offset_seconds": 0,
    "timezone": "UTC",
    "elevation": 216.0,
    "current_units": {
        "time": "iso8601",
        "temperature_2m": "°C",
        "relative_humidity_2m": "%",
        "wind_speed_10m": "m/s",
        "wind_direction_10m": "°",
        "precipitation": "mm",
        "surface_pressure": "hPa",
    },
    "current": {
        "time": "2026-10-31T12:00:00Z",
        "temperature_2m": 29.5,
        "relative_humidity_2m": 45.0,
        "wind_speed_10m": 4.2,
        "wind_direction_10m": 310.0,
        "precipitation": 0.0,
        "surface_pressure": 1012.3,
    },
}

MOCK_OPEN_METEO_HISTORICAL = {
    "latitude": 28.62,
    "longitude": 77.22,
    "generationtime_ms": 0.35,
    "elevation": 216.0,
    "timezone": "UTC",
    "hourly": {
        "time": ["2026-10-01T00:00", "2026-10-01T01:00"],
        "temperature_2m": [22.1, 21.8],
        "relative_humidity_2m": [70.0, 72.0],
        "wind_speed_10m": [2.1, 1.9],
        "wind_direction_10m": [270.0, 260.0],
        "precipitation": [0.0, 0.0],
        "surface_pressure": [1014.2, 1013.9],
    },
}

MOCK_OPEN_METEO_FORECAST = {
    "latitude": 28.62,
    "longitude": 77.22,
    "generationtime_ms": 0.28,
    "elevation": 216.0,
    "timezone": "UTC",
    "hourly": {
        "time": ["2026-11-01T00:00", "2026-11-01T01:00"],
        "temperature_2m": [24.0, 23.5],
        "relative_humidity_2m": [65.0, 68.0],
        "wind_speed_10m": [3.5, 3.2],
        "wind_direction_10m": [290.0, 295.0],
        "precipitation": [0.0, 0.0],
        "surface_pressure": [1011.5, 1011.8],
    },
}

MOCK_NASA_POWER_HOURLY = {
    "type": "Feature",
    "geometry": {"type": "Point", "coordinates": [77.25, 28.5, 220.0]},
    "header": {"title": "NASA/POWER Hourly Point Data", "api": {"version": "v2.0"}},
    "parameters": {
        "T2M": {"units": "C", "longname": "Temperature at 2 Meters"},
        "RH2M": {"units": "%", "longname": "Relative Humidity at 2 Meters"},
        "WS10M": {"units": "m/s", "longname": "Wind Speed at 10 Meters"},
        "WD10M": {"units": "Degrees", "longname": "Wind Direction at 10 Meters"},
        "PRECTOTCORR": {"units": "mm/hour", "longname": "Precipitation Corrected"},
        "PS": {"units": "kPa", "longname": "Surface Pressure"},
    },
    "properties": {
        "parameter": {
            "T2M": {"2026101500": 21.5, "2026101501": 20.8},
            "RH2M": {"2026101500": 68.0, "2026101501": 71.0},
            "WS10M": {"2026101500": 2.5, "2026101501": 2.2},
            "WD10M": {"2026101500": 280.0, "2026101501": 285.0},
            "PRECTOTCORR": {"2026101500": 0.0, "2026101501": 0.0},
            "PS": {"2026101500": 101.2, "2026101501": 101.1},
        }
    },
}


class TestOpenMeteoProvider:
    """Unit tests for Open-Meteo client."""

    def test_current_conditions_success(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/v1/forecast"
            assert "temperature_2m" in str(request.url)
            assert request.url.params["wind_speed_unit"] == "ms"
            return httpx.Response(200, json=MOCK_OPEN_METEO_CURRENT)

        client = OpenMeteoProvider(transport=httpx.MockTransport(handler), sleep_func=lambda s: None)
        res = client.get_current_conditions(28.6139, 77.2090)

        assert res["current"]["temperature_2m"] == 29.5
        prov = res["scout_provenance"]
        assert prov["provider"] == "open_meteo"
        assert prov["typology"] == "model_analysis"
        assert prov["requested_latitude"] == 28.6139
        assert prov["resolved_latitude"] == 28.62
        assert prov["elevation_m"] == 216.0

    def test_historical_weather_success(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/v1/archive"
            assert request.url.params["start_date"] == "2026-10-01"
            assert request.url.params["end_date"] == "2026-10-02"
            return httpx.Response(200, json=MOCK_OPEN_METEO_HISTORICAL)

        client = OpenMeteoProvider(transport=httpx.MockTransport(handler), sleep_func=lambda s: None)
        res = client.get_historical_weather(28.6139, 77.2090, date(2026, 10, 1), date(2026, 10, 2))

        assert len(res["hourly"]["temperature_2m"]) == 2
        assert res["scout_provenance"]["typology"] == "reanalysis"

    def test_forecast_weather_success(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/v1/forecast"
            assert request.url.params["forecast_days"] == "5"
            return httpx.Response(200, json=MOCK_OPEN_METEO_FORECAST)

        client = OpenMeteoProvider(transport=httpx.MockTransport(handler), sleep_func=lambda s: None)
        res = client.get_weather_forecast(28.6139, 77.2090, forecast_days=5)

        assert res["scout_provenance"]["typology"] == "forecast"
        assert res["scout_provenance"]["forecast_days"] == 5

    def test_invalid_date_range_raises_exception(self):
        client = OpenMeteoProvider(transport=httpx.MockTransport(lambda r: httpx.Response(200)))
        with pytest.raises(TimeRangeUnavailableError, match="start_date .* cannot be after end_date"):
            client.get_historical_weather(28.6, 77.2, date(2026, 10, 5), date(2026, 10, 1))

    def test_invalid_coordinates_rejected(self):
        client = OpenMeteoProvider(transport=httpx.MockTransport(lambda r: httpx.Response(200)))
        with pytest.raises(InvalidCoordinateError):
            client.get_current_conditions(95.0, 77.2)

    def test_retry_on_server_error_and_recovery(self):
        attempts = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                return httpx.Response(502, text="Bad Gateway")
            return httpx.Response(200, json=MOCK_OPEN_METEO_CURRENT)

        client = OpenMeteoProvider(
            transport=httpx.MockTransport(handler),
            max_retries=2,
            sleep_func=lambda s: None,
        )
        res = client.get_current_conditions(28.6, 77.2)
        assert attempts == 2
        assert res["current"]["temperature_2m"] == 29.5

    def test_client_error_400_fails_without_retry(self):
        attempts = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            return httpx.Response(400, text="Bad Request: invalid variable")

        client = OpenMeteoProvider(
            transport=httpx.MockTransport(handler),
            max_retries=2,
            sleep_func=lambda s: None,
        )
        with pytest.raises(ProviderAPIError) as exc_info:
            client.get_current_conditions(28.6, 77.2)
        assert attempts == 1  # 400 must NOT be retried
        assert exc_info.value.status_code == 400

    def test_timeout_retries_and_raises(self):
        attempts = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            raise httpx.ReadTimeout("Read timed out")

        client = OpenMeteoProvider(
            transport=httpx.MockTransport(handler),
            max_retries=2,
            sleep_func=lambda s: None,
        )
        with pytest.raises(ProviderTimeoutError):
            client.get_current_conditions(28.6, 77.2)
        assert attempts == 3  # Initial + 2 retries


class TestNasaPowerProvider:
    """Unit tests for NASA POWER client."""

    def test_hourly_request_success(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/api/temporal/hourly/point"
            assert request.url.params["time-standard"] == "UTC"  # Mandatory UTC check
            assert request.url.params["start"] == "20261015"
            assert request.url.params["end"] == "20261015"
            return httpx.Response(200, json=MOCK_NASA_POWER_HOURLY)

        client = NasaPowerProvider(transport=httpx.MockTransport(handler), sleep_func=lambda s: None)
        res = client.get_historical_weather(28.6139, 77.2090, date(2026, 10, 15), date(2026, 10, 15), hourly=True)

        prov = res["scout_provenance"]
        assert prov["provider"] == "nasa_power"
        assert prov["typology"] == "reanalysis"
        assert prov["time_standard"] == "UTC"
        assert prov["resolved_latitude"] == 28.5
        assert prov["resolved_longitude"] == 77.25

    def test_hourly_rejects_dates_before_2001(self):
        client = NasaPowerProvider(transport=httpx.MockTransport(lambda r: httpx.Response(200)))
        with pytest.raises(TimeRangeUnavailableError, match="Hourly API coverage begins on 2001-01-01"):
            client.get_historical_weather(28.6, 77.2, date(1999, 12, 31), date(2000, 1, 1), hourly=True)

    def test_daily_rejects_dates_before_1981(self):
        client = NasaPowerProvider(transport=httpx.MockTransport(lambda r: httpx.Response(200)))
        with pytest.raises(TimeRangeUnavailableError, match="Daily API coverage begins on 1981-01-01"):
            client.get_historical_weather(28.6, 77.2, date(1975, 1, 1), date(1975, 1, 2), hourly=False)

    def test_current_conditions_unsupported(self):
        client = NasaPowerProvider(transport=httpx.MockTransport(lambda r: httpx.Response(200)))
        with pytest.raises(TimeRangeUnavailableError, match="does not provide real-time current conditions"):
            client.get_current_conditions(28.6, 77.2)

    def test_forecast_unsupported(self):
        client = NasaPowerProvider(transport=httpx.MockTransport(lambda r: httpx.Response(200)))
        with pytest.raises(TimeRangeUnavailableError, match="does not provide forward numerical weather prediction"):
            client.get_weather_forecast(28.6, 77.2)

    def test_rate_limit_429_handling(self):
        attempts = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            return httpx.Response(429, headers={"Retry-After": "1"}, text="Too Many Requests")

        client = NasaPowerProvider(
            transport=httpx.MockTransport(handler),
            max_retries=1,
            sleep_func=lambda s: None,
        )
        with pytest.raises(ProviderRateLimitError) as exc_info:
            client.get_historical_weather(28.6, 77.2, date(2023, 1, 1), date(2023, 1, 2))
        assert attempts == 2
        assert exc_info.value.status_code == 429
