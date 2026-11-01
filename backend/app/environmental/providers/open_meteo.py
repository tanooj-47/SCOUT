"""
backend/app/environmental/providers/open_meteo.py
Open-Meteo Weather API client implementation for SCOUT.
Handles current nowcasts, numerical forecasts, and ERA5 historical reanalysis.
"""

from datetime import date
import logging
from typing import Any, Dict, Optional
import httpx

from app.core.config import settings
from app.environmental.exceptions import TimeRangeUnavailableError
from app.environmental.providers.base import BaseWeatherProvider
from app.geospatial.coordinates import validate_coordinates

logger = logging.getLogger(__name__)

OPEN_METEO_ATTRIBUTION = "Weather data by Open-Meteo.com (CC BY 4.0)"
CANONICAL_VARIABLES = (
    "temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m,precipitation,surface_pressure"
)


class OpenMeteoProvider(BaseWeatherProvider):
    """
    Open-Meteo API integration client.
    Note on provenance:
    - Current conditions are derived from NWP model analysis/nowcasts (ECMWF, GFS, ICON).
      They are strictly classified as MODEL_ANALYSIS, never physical station observations.
    - Historical queries pull from ECMWF ERA5 / ERA5-Land reanalysis grids.
    - Forecast queries pull forward numerical weather prediction model runs.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        archive_url: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        max_retries: Optional[int] = None,
        backoff_factor: Optional[float] = None,
        transport: Optional[httpx.BaseTransport] = None,
        sleep_func: Optional[Any] = None,
    ):
        super().__init__(
            name="open_meteo",
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            backoff_factor=backoff_factor,
            transport=transport,
            sleep_func=sleep_func,
        )
        self.base_url = (base_url or settings.OPEN_METEO_BASE_URL).rstrip("/")
        self.archive_url = (archive_url or settings.OPEN_METEO_ARCHIVE_URL).rstrip("/")

    def get_current_conditions(self, latitude: float, longitude: float) -> Dict[str, Any]:
        """
        Retrieves current atmospheric model analysis conditions.
        Classified internally as MODEL_ANALYSIS.
        """
        coord = validate_coordinates(latitude, longitude)
        url = f"{self.base_url}/forecast"
        params = {
            "latitude": coord.latitude,
            "longitude": coord.longitude,
            "current": CANONICAL_VARIABLES,
            "wind_speed_unit": "ms",
            "timeformat": "iso8601",
            "timezone": "UTC",
        }

        payload = self.execute_request_with_retry("GET", url, params=params)

        # Enforce metadata provenance
        payload["scout_provenance"] = {
            "provider": "open_meteo",
            "attribution": OPEN_METEO_ATTRIBUTION,
            "typology": "model_analysis",
            "requested_latitude": coord.latitude,
            "requested_longitude": coord.longitude,
            "resolved_latitude": payload.get("latitude"),
            "resolved_longitude": payload.get("longitude"),
            "elevation_m": payload.get("elevation"),
            "timezone": payload.get("timezone", "UTC"),
            "model_or_dataset": payload.get("current_units", {}).get("model", "best_match"),
        }
        return payload

    def get_historical_weather(
        self,
        latitude: float,
        longitude: float,
        start_date: date,
        end_date: date,
    ) -> Dict[str, Any]:
        """
        Retrieves historical gridded reanalysis (ERA5 / ERA5-Land).
        Classified internally as REANALYSIS.
        """
        coord = validate_coordinates(latitude, longitude)
        if start_date > end_date:
            raise TimeRangeUnavailableError(
                provider="open_meteo",
                message=f"start_date ({start_date}) cannot be after end_date ({end_date}).",
            )

        url = f"{self.archive_url}/archive"
        params = {
            "latitude": coord.latitude,
            "longitude": coord.longitude,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "hourly": CANONICAL_VARIABLES,
            "wind_speed_unit": "ms",
            "timeformat": "iso8601",
            "timezone": "UTC",
        }

        payload = self.execute_request_with_retry("GET", url, params=params)

        payload["scout_provenance"] = {
            "provider": "open_meteo",
            "attribution": OPEN_METEO_ATTRIBUTION,
            "typology": "reanalysis",
            "model_or_dataset": "era5_reanalysis",
            "requested_latitude": coord.latitude,
            "requested_longitude": coord.longitude,
            "resolved_latitude": payload.get("latitude"),
            "resolved_longitude": payload.get("longitude"),
            "elevation_m": payload.get("elevation"),
            "timezone": payload.get("timezone", "UTC"),
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        }
        return payload

    def get_weather_forecast(
        self,
        latitude: float,
        longitude: float,
        forecast_days: int = 7,
    ) -> Dict[str, Any]:
        """
        Retrieves forward numerical weather prediction forecast sequence.
        Classified internally as FORECAST.
        """
        coord = validate_coordinates(latitude, longitude)
        days = max(1, min(16, int(forecast_days)))

        url = f"{self.base_url}/forecast"
        params = {
            "latitude": coord.latitude,
            "longitude": coord.longitude,
            "forecast_days": days,
            "hourly": CANONICAL_VARIABLES,
            "wind_speed_unit": "ms",
            "timeformat": "iso8601",
            "timezone": "UTC",
        }

        payload = self.execute_request_with_retry("GET", url, params=params)

        payload["scout_provenance"] = {
            "provider": "open_meteo",
            "attribution": OPEN_METEO_ATTRIBUTION,
            "typology": "forecast",
            "model_or_dataset": "ecmwf_ifs_blend",
            "requested_latitude": coord.latitude,
            "requested_longitude": coord.longitude,
            "resolved_latitude": payload.get("latitude"),
            "resolved_longitude": payload.get("longitude"),
            "elevation_m": payload.get("elevation"),
            "timezone": payload.get("timezone", "UTC"),
            "forecast_days": days,
        }
        return payload

    def check_health(self) -> Dict[str, Any]:
        """Executes a live probe for Open-Meteo endpoint availability."""
        try:
            # Query coordinates (0.0, 0.0) with minimal payload
            url = f"{self.base_url}/forecast"
            params = {"latitude": 0.0, "longitude": 0.0, "current": "temperature_2m"}
            resp = self.execute_request_with_retry("GET", url, params=params)
            return {
                "status": "operational",
                "provider": "open_meteo",
                "base_url": self.base_url,
                "generation_time_ms": resp.get("generationtime_ms"),
                "attribution": OPEN_METEO_ATTRIBUTION,
            }
        except Exception as exc:
            logger.warning("[open_meteo] Health probe failed: %s", exc)
            return {
                "status": "degraded",
                "provider": "open_meteo",
                "base_url": self.base_url,
                "error": str(exc),
            }
