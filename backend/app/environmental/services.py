from datetime import date, datetime, timezone
import logging
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy.orm import Session

from app.environmental.cache import EnvironmentalCache, environmental_cache
from app.environmental.exceptions import (
    EnvironmentalException,
    ProviderAPIError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    TimeRangeUnavailableError,
)
from app.environmental.normalizer import EnvironmentalNormalizer
from app.environmental.providers.base import BaseWeatherProvider
from app.environmental.providers.nasa_power import NasaPowerProvider
from app.environmental.providers.open_meteo import OpenMeteoProvider
from app.environmental.repository import EnvironmentalRepository
from app.environmental.schemas import (
    EnvironmentalIngestRequest,
    EnvironmentalIngestResponse,
    EnvironmentalObservationItem,
    EnvironmentalTypology,
    LocationType,
)

logger = logging.getLogger(__name__)


class EnvironmentalService:
    """
    Orchestration service for environmental observations:
    Validates requests, manages multi-provider dispatch, coordinates caching with stale fallback,
    and handles idempotent database persistence.
    """

    def __init__(
        self,
        db_session: Optional[Session] = None,
        cache: Optional[EnvironmentalCache] = None,
        open_meteo_client: Optional[OpenMeteoProvider] = None,
        nasa_power_client: Optional[NasaPowerProvider] = None,
    ):
        self.db_session = db_session
        self.repository = EnvironmentalRepository(db_session) if db_session else None
        self.cache = cache or environmental_cache
        self.open_meteo = open_meteo_client or OpenMeteoProvider()
        self.nasa_power = nasa_power_client or NasaPowerProvider()

    def _get_provider_client(self, provider_name: str) -> BaseWeatherProvider:
        clean = provider_name.lower().replace("_", "-").strip()
        if clean in ("open-meteo", "openmeteo"):
            return self.open_meteo
        elif clean in ("nasa-power", "nasapower", "power"):
            return self.nasa_power
        else:
            raise ValueError(f"Unsupported weather provider: '{provider_name}'")

    def get_current_conditions(
        self,
        latitude: float,
        longitude: float,
        incident_id: Optional[UUID] = None,
        provider: str = "open-meteo",
        dataset_or_model: str = "best_match",
    ) -> Tuple[EnvironmentalObservationItem, bool]:
        """
        Retrieves current atmospheric conditions at the target coordinates.
        Returns (item, is_stale).
        Classified strictly as MODEL_ANALYSIS.
        """
        typology = EnvironmentalTypology.MODEL_ANALYSIS
        cache_key = self.cache.generate_cache_key(
            provider=provider,
            dataset_or_model=dataset_or_model,
            typology=typology.value,
            lat=latitude,
            lon=longitude,
            time_window="current",
        )

        cached_items, is_stale = self.cache.get(cache_key, allow_stale=False)
        if cached_items and len(cached_items) > 0:
            return cached_items[0], False

        client = self._get_provider_client(provider)
        try:
            raw_payload = client.get_current_conditions(latitude=latitude, longitude=longitude)
            item = EnvironmentalNormalizer.normalize_open_meteo_current(
                raw_payload=raw_payload,
                requested_lat=latitude,
                requested_lon=longitude,
                incident_id=incident_id,
                model_name=dataset_or_model,
            )
            # Update cache
            self.cache.set(cache_key, [item], typology)

            # Persist to DB if session available
            if self.repository:
                self.repository.save_batch([item], incident_id=incident_id)

            return item, False
        except (ProviderAPIError, ProviderTimeoutError, ProviderRateLimitError) as exc:
            # Fallback to stale cached data if present
            stale_items, _ = self.cache.get(cache_key, allow_stale=True)
            if stale_items and len(stale_items) > 0:
                logger.warning(f"Returning stale fallback observation due to provider error: {str(exc)}")
                return stale_items[0], True
            raise

    def get_weather_forecast(
        self,
        latitude: float,
        longitude: float,
        forecast_days: int = 7,
        incident_id: Optional[UUID] = None,
        provider: str = "open-meteo",
        dataset_or_model: str = "best_match",
    ) -> Tuple[List[EnvironmentalObservationItem], bool]:
        """
        Retrieves hourly weather forecast projections.
        Returns (items, is_stale).
        """
        typology = EnvironmentalTypology.FORECAST
        time_window = f"f_{forecast_days}d"
        cache_key = self.cache.generate_cache_key(
            provider=provider,
            dataset_or_model=dataset_or_model,
            typology=typology.value,
            lat=latitude,
            lon=longitude,
            time_window=time_window,
        )

        cached_items, _ = self.cache.get(cache_key, allow_stale=False)
        if cached_items:
            return cached_items, False

        client = self._get_provider_client(provider)
        try:
            raw_payload = client.get_weather_forecast(
                latitude=latitude,
                longitude=longitude,
                forecast_days=forecast_days,
            )
            items = EnvironmentalNormalizer.normalize_open_meteo_hourly(
                raw_payload=raw_payload,
                requested_lat=latitude,
                requested_lon=longitude,
                typology=typology,
                model_name=dataset_or_model,
                incident_id=incident_id,
            )
            self.cache.set(cache_key, items, typology)

            if self.repository:
                self.repository.save_batch(items, incident_id=incident_id)

            return items, False
        except (ProviderAPIError, ProviderTimeoutError, ProviderRateLimitError) as exc:
            stale_items, _ = self.cache.get(cache_key, allow_stale=True)
            if stale_items:
                logger.warning(f"Returning stale fallback forecast due to provider error: {str(exc)}")
                return stale_items, True
            raise

    def get_historical_reanalysis(
        self,
        latitude: float,
        longitude: float,
        start_date: date,
        end_date: date,
        incident_id: Optional[UUID] = None,
        provider: str = "open-meteo",
        dataset_or_model: Optional[str] = None,
    ) -> Tuple[List[EnvironmentalObservationItem], bool]:
        """
        Retrieves historical reanalysis data (ERA5 or MERRA-2).
        Returns (items, is_stale).
        """
        typology = EnvironmentalTypology.REANALYSIS
        model_name = dataset_or_model or ("era5" if provider == "open-meteo" else "merra2")
        time_window = f"{start_date.isoformat()}_{end_date.isoformat()}"
        cache_key = self.cache.generate_cache_key(
            provider=provider,
            dataset_or_model=model_name,
            typology=typology.value,
            lat=latitude,
            lon=longitude,
            time_window=time_window,
        )

        cached_items, _ = self.cache.get(cache_key, allow_stale=False)
        if cached_items:
            return cached_items, False

        client = self._get_provider_client(provider)
        try:
            raw_payload = client.get_historical_weather(
                latitude=latitude,
                longitude=longitude,
                start_date=start_date,
                end_date=end_date,
            )

            if provider in ("nasa-power", "nasapower"):
                items = EnvironmentalNormalizer.normalize_nasa_power_hourly(
                    raw_payload=raw_payload,
                    requested_lat=latitude,
                    requested_lon=longitude,
                    incident_id=incident_id,
                    model_name=model_name,
                )
            else:
                items = EnvironmentalNormalizer.normalize_open_meteo_hourly(
                    raw_payload=raw_payload,
                    requested_lat=latitude,
                    requested_lon=longitude,
                    typology=typology,
                    model_name=model_name,
                    incident_id=incident_id,
                )

            self.cache.set(cache_key, items, typology)

            if self.repository:
                self.repository.save_batch(items, incident_id=incident_id)

            return items, False
        except (ProviderAPIError, ProviderTimeoutError, ProviderRateLimitError) as exc:
            stale_items, _ = self.cache.get(cache_key, allow_stale=True)
            if stale_items:
                logger.warning(f"Returning stale fallback historical data due to error: {str(exc)}")
                return stale_items, True
            raise

    def ingest_data(self, request: EnvironmentalIngestRequest) -> EnvironmentalIngestResponse:
        """
        Top-level ingestion handler supporting on-demand data retrieval and persistence.
        """
        provider = request.provider or "open-meteo"
        dataset_or_model = request.dataset_or_model or ("best_match" if provider == "open-meteo" else "merra2")

        if request.typology == EnvironmentalTypology.MODEL_ANALYSIS:
            item, is_stale = self.get_current_conditions(
                latitude=request.latitude,
                longitude=request.longitude,
                incident_id=request.incident_id,
                provider=provider,
                dataset_or_model=dataset_or_model,
            )
            items = [item]
        elif request.typology == EnvironmentalTypology.FORECAST:
            items, is_stale = self.get_weather_forecast(
                latitude=request.latitude,
                longitude=request.longitude,
                forecast_days=request.forecast_days or 7,
                incident_id=request.incident_id,
                provider=provider,
                dataset_or_model=dataset_or_model,
            )
        elif request.typology == EnvironmentalTypology.REANALYSIS:
            if not request.start_time_utc or not request.end_time_utc:
                raise ValueError("start_time_utc and end_time_utc are required for reanalysis ingestion")
            items, is_stale = self.get_historical_reanalysis(
                latitude=request.latitude,
                longitude=request.longitude,
                start_date=request.start_time_utc.date(),
                end_date=request.end_time_utc.date(),
                incident_id=request.incident_id,
                provider=provider,
                dataset_or_model=dataset_or_model,
            )
        else:
            raise ValueError(f"Direct ingestion for typology '{request.typology}' is unsupported")

        location_id = items[0].location_id if items else "unknown"
        return EnvironmentalIngestResponse(
            count=len(items),
            location_id=location_id,
            provider=provider,
            dataset_or_model=dataset_or_model,
            typology=request.typology,
            cached=False,
            is_stale=is_stale,
            items=items,
        )

    def check_health(self) -> Dict[str, Any]:
        """Checks upstream provider liveness and health."""
        open_meteo_ok = self.open_meteo.check_health()
        nasa_power_ok = self.nasa_power.check_health()
        return {
            "status": "healthy" if (open_meteo_ok or nasa_power_ok) else "degraded",
            "providers": {
                "open_meteo": "operational" if open_meteo_ok else "unreachable",
                "nasa_power": "operational" if nasa_power_ok else "unreachable",
            },
            "cache_entries": self.cache.size(),
        }
