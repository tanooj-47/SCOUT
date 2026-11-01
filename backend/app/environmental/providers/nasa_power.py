"""
backend/app/environmental/providers/nasa_power.py
NASA POWER (Prediction Of Worldwide Energy Resources) API client implementation.
Handles retrospective gridded reanalysis (MERRA-2) with strict UTC temporal standards.
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

NASA_POWER_ATTRIBUTION = "NASA Langley Research Center POWER Project / MERRA-2 Assimilation (US Public Domain)"
NASA_POWER_HOURLY_EARLIEST_DATE = date(2001, 1, 1)
NASA_POWER_DAILY_EARLIEST_DATE = date(1981, 1, 1)
NASA_POWER_PARAMETERS = "T2M,RH2M,WS10M,WD10M,PRECTOTCORR,PS"


class NasaPowerProvider(BaseWeatherProvider):
    """
    NASA POWER API integration client.
    Note on provenance:
    - Sourced from NASA GMAO MERRA-2 assimilation model and CERES satellite processing.
    - It is gridded retrospective assimilation (REANALYSIS), not independent ground-truth station observations.
    - Default time standard is LST; this client strictly enforces time-standard=UTC.
    - Surface pressure is reported in kPa (requires conversion: hPa = kPa * 10.0).
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        max_retries: Optional[int] = None,
        backoff_factor: Optional[float] = None,
        transport: Optional[httpx.BaseTransport] = None,
        sleep_func: Optional[Any] = None,
    ):
        super().__init__(
            name="nasa_power",
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            backoff_factor=backoff_factor,
            transport=transport,
            sleep_func=sleep_func,
        )
        self.base_url = (base_url or settings.NASA_POWER_BASE_URL).rstrip("/")

    def get_current_conditions(self, latitude: float, longitude: float) -> Dict[str, Any]:
        """
        NASA POWER carries a 2-3 day latency and does not support real-time current conditions.
        Raises TimeRangeUnavailableError directing caller to appropriate provider.
        """
        raise TimeRangeUnavailableError(
            provider="nasa_power",
            message="NASA POWER does not provide real-time current conditions due to 2-3 day MERRA-2 processing latency. Use Open-Meteo for current model analysis.",
        )

    def get_historical_weather(
        self,
        latitude: float,
        longitude: float,
        start_date: date,
        end_date: date,
        hourly: bool = True,
    ) -> Dict[str, Any]:
        """
        Retrieves retrospective gridded observations (MERRA-2) over a time range.
        Classified internally as REANALYSIS.
        """
        coord = validate_coordinates(latitude, longitude)
        if start_date > end_date:
            raise TimeRangeUnavailableError(
                provider="nasa_power",
                message=f"start_date ({start_date}) cannot be after end_date ({end_date}).",
            )

        # Enforce parameter and temporal coverage limits
        if hourly:
            if start_date < NASA_POWER_HOURLY_EARLIEST_DATE:
                raise TimeRangeUnavailableError(
                    provider="nasa_power",
                    message=f"NASA POWER Hourly API coverage begins on {NASA_POWER_HOURLY_EARLIEST_DATE.isoformat()}. Requested start date {start_date.isoformat()} is unavailable.",
                    details={"earliest_date": NASA_POWER_HOURLY_EARLIEST_DATE.isoformat(), "start_date": start_date.isoformat()},
                )
            endpoint = f"{self.base_url}/hourly/point"
        else:
            if start_date < NASA_POWER_DAILY_EARLIEST_DATE:
                raise TimeRangeUnavailableError(
                    provider="nasa_power",
                    message=f"NASA POWER Daily API coverage begins on {NASA_POWER_DAILY_EARLIEST_DATE.isoformat()}. Requested start date {start_date.isoformat()} is unavailable.",
                    details={"earliest_date": NASA_POWER_DAILY_EARLIEST_DATE.isoformat(), "start_date": start_date.isoformat()},
                )
            endpoint = f"{self.base_url}/daily/point"

        params = {
            "parameters": NASA_POWER_PARAMETERS,
            "community": "AG",
            "longitude": coord.longitude,
            "latitude": coord.latitude,
            "start": start_date.strftime("%Y%m%d"),
            "end": end_date.strftime("%Y%m%d"),
            "format": "JSON",
            "time-standard": "UTC",  # Strictly enforce UTC (defaults to LST)
        }

        payload = self.execute_request_with_retry("GET", endpoint, params=params)

        geometry = payload.get("geometry", {})
        coords = geometry.get("coordinates", [coord.longitude, coord.latitude, 0.0])
        resolved_lon = coords[0] if len(coords) > 0 else coord.longitude
        resolved_lat = coords[1] if len(coords) > 1 else coord.latitude
        elevation = coords[2] if len(coords) > 2 else None

        payload["scout_provenance"] = {
            "provider": "nasa_power",
            "attribution": NASA_POWER_ATTRIBUTION,
            "typology": "reanalysis",
            "model_or_dataset": "merra2_assimilation",
            "requested_latitude": coord.latitude,
            "requested_longitude": coord.longitude,
            "resolved_latitude": resolved_lat,
            "resolved_longitude": resolved_lon,
            "elevation_m": elevation,
            "time_standard": "UTC",
            "temporal_resolution": "hourly" if hourly else "daily",
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
        """NASA POWER does not support forward predictive weather forecasts."""
        raise TimeRangeUnavailableError(
            provider="nasa_power",
            message="NASA POWER is a retrospective reanalysis archive and does not provide forward numerical weather prediction forecasts. Use Open-Meteo for forecasts.",
        )

    def check_health(self) -> Dict[str, Any]:
        """Executes a diagnostic check against NASA POWER daily endpoint."""
        try:
            url = f"{self.base_url}/daily/point"
            params = {
                "parameters": "T2M",
                "community": "AG",
                "longitude": 0.0,
                "latitude": 0.0,
                "start": "20230101",
                "end": "20230101",
                "format": "JSON",
                "time-standard": "UTC",
            }
            resp = self.execute_request_with_retry("GET", url, params=params)
            return {
                "status": "operational",
                "provider": "nasa_power",
                "base_url": self.base_url,
                "header": resp.get("header", {}).get("title"),
                "attribution": NASA_POWER_ATTRIBUTION,
            }
        except Exception as exc:
            logger.warning("[nasa_power] Health probe failed: %s", exc)
            return {
                "status": "degraded",
                "provider": "nasa_power",
                "base_url": self.base_url,
                "error": str(exc),
            }
