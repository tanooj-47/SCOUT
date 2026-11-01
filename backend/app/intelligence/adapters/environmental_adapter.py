"""
backend/app/intelligence/adapters/environmental_adapter.py
Environmental Subsystem Adapter for Milestone 09 Weather & Canadian FWI Engine.
Collects current atmospheric parameters, computes Canadian FWI indices,
and tracks data freshness and model provenance.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, Optional
from uuid import UUID

from app.environmental.exceptions import EnvironmentalException
from app.environmental.fwi.engine import FWIEngine
from app.environmental.services import EnvironmentalService
from app.intelligence.evidence import EvidenceCollector
from app.intelligence.schemas import CoordinateLocation, EvidenceItem

logger = logging.getLogger(__name__)


class EnvironmentalModelAdapter:
    """
    Adapter encapsulating atmospheric conditions retrieval and Fire Weather Index calculation.
    """

    def __init__(self, service: Optional[EnvironmentalService] = None) -> None:
        self.service = service or EnvironmentalService()

    def collect_evidence(
        self,
        latitude: float,
        longitude: float,
        incident_id: Optional[UUID] = None,
        provider: str = "open-meteo",
        dataset_or_model: str = "best_match",
    ) -> EvidenceItem:
        """
        Retrieves current atmospheric observations and computes corresponding FWI indices.
        Returns a typed EvidenceItem with status VALID or STALE, or UNAVAILABLE on provider failure.
        """
        location = CoordinateLocation(latitude=latitude, longitude=longitude)

        try:
            obs_item, is_stale = self.service.get_current_conditions(
                latitude=latitude,
                longitude=longitude,
                incident_id=incident_id,
                provider=provider,
                dataset_or_model=dataset_or_model,
            )

            # Extract meteorological parameters without unscientific default constants
            temp_c = float(obs_item.temperature_celsius) if obs_item.temperature_celsius is not None else None
            rh_pct = float(obs_item.relative_humidity) if obs_item.relative_humidity is not None else None
            wind_mps = float(obs_item.wind_speed_mps) if obs_item.wind_speed_mps is not None else None
            wind_kmh = round(wind_mps * 3.6, 2) if wind_mps is not None else None  # CFS-FWI requires wind in km/h
            rain_mm = float(obs_item.precipitation_mm) if obs_item.precipitation_mm is not None else None
            wind_dir = float(obs_item.wind_direction_degrees) if obs_item.wind_direction_degrees is not None else None

            # Detect missing meteorological variables
            missing_vars = []
            if temp_c is None:
                missing_vars.append("temperature_celsius")
            if rh_pct is None:
                missing_vars.append("relative_humidity")
            if wind_mps is None:
                missing_vars.append("wind_speed_mps")
            if rain_mm is None:
                missing_vars.append("precipitation_mm")

            fwi_indices: Optional[Dict[str, Any]] = None
            fwi_available = False

            # Only compute Canadian Forest Fire Weather Index if all required parameters are present
            if not missing_vars and temp_c is not None and rh_pct is not None and wind_kmh is not None and rain_mm is not None:
                obs_dt = obs_item.valid_time_utc or datetime.now(timezone.utc)
                month = obs_dt.month

                ffmc = round(FWIEngine.calculate_ffmc(temp_c, rh_pct, wind_kmh, rain_mm, prev_ffmc=85.0), 2)
                dmc = round(FWIEngine.calculate_dmc(temp_c, rh_pct, rain_mm, prev_dmc=6.0, lat=latitude, month=month), 2)
                dc = round(FWIEngine.calculate_dc(temp_c, rain_mm, prev_dc=15.0, lat=latitude, month=month), 2)
                isi = round(FWIEngine.calculate_isi(wind_kmh, ffmc), 2)
                bui = round(FWIEngine.calculate_bui(dmc, dc), 2)
                fwi = round(FWIEngine.calculate_fwi(isi, bui), 2)
                dsr = round(FWIEngine.calculate_dsr(fwi), 2)
                danger_rating = FWIEngine.get_danger_rating(fwi)

                fwi_indices = {
                    "fine_fuel_moisture_code_ffmc": ffmc,
                    "duff_moisture_code_dmc": dmc,
                    "drought_code_dc": dc,
                    "initial_spread_index_isi": isi,
                    "buildup_index_bui": bui,
                    "fire_weather_index_fwi": fwi,
                    "daily_severity_rating_dsr": dsr,
                    "danger_rating": danger_rating,
                }
                fwi_available = True

            payload: Dict[str, Any] = {
                "temperature_c": temp_c,
                "relative_humidity_pct": rh_pct,
                "wind_speed_kmh": wind_kmh,
                "wind_direction_deg": wind_dir,
                "precipitation_mm": rain_mm,
                "fwi_indices": fwi_indices,
                "fwi_available": fwi_available,
                "missing_meteorological_variables": missing_vars,
                "fwi_methodology": (
                    "instantaneous_weather_indicator (experimental_uninitialized_fwi)"
                    if fwi_available
                    else "fwi_unavailable_due_to_missing_variables"
                ),
                "observation_typology": (
                    obs_item.typology.value
                    if hasattr(obs_item.typology, "value")
                    else str(obs_item.typology)
                ),
            }

            return EvidenceCollector.create_environmental_evidence(
                weather_data=payload,
                provider=provider,
                model_or_dataset=dataset_or_model,
                is_stale=is_stale,
                observation_time=obs_item.valid_time_utc,
                location=location,
            )
        except Exception as exc:
            logger.warning(f"Environmental conditions query failed; recording unavailable evidence: {exc}")
            return EvidenceCollector.create_unavailable_environmental_evidence(str(exc))
