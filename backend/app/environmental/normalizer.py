import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from app.environmental.exceptions import NormalizationError
from app.environmental.schemas import (
    CanonicalWeatherVariables,
    EnvironmentalObservationItem,
    EnvironmentalTypology,
    LocationType,
)


class EnvironmentalNormalizer:
    """
    Normalizes heterogeneous API responses from Open-Meteo and NASA POWER
    into canonical SI/WMO-standard EnvironmentalObservationItem objects.
    """

    @staticmethod
    def format_grid_location_id(provider: str, model: str, lat: float, lon: float) -> str:
        """
        Builds canonical deterministic grid-cell location ID formatted to 4 decimal places (~11m).
        Format: grid:{provider}:{model}:{lat_4dp}_{lon_4dp}
        """
        clean_provider = provider.lower().replace("-", "_").strip()
        clean_model = model.lower().replace("-", "_").strip()
        return f"grid:{clean_provider}:{clean_model}:{lat:.4f}_{lon:.4f}"

    @classmethod
    def normalize_open_meteo_current(
        cls,
        raw_payload: Dict[str, Any],
        requested_lat: float,
        requested_lon: float,
        incident_id: Optional[UUID] = None,
        model_name: str = "best_match",
    ) -> EnvironmentalObservationItem:
        """
        Normalizes Open-Meteo 'current' payload.
        Enforces MODEL_ANALYSIS typology (never station_observed).
        """
        try:
            resolved_lat = float(raw_payload.get("latitude", requested_lat))
            resolved_lon = float(raw_payload.get("longitude", requested_lon))
            current = raw_payload.get("current")
            if not current:
                raise NormalizationError("Missing 'current' object in Open-Meteo response", provider="open-meteo")

            raw_time = current.get("time")
            if not raw_time:
                raise NormalizationError("Missing timestamp in Open-Meteo current object", provider="open-meteo")

            # Parse time string: e.g. "2026-10-31T08:00"
            valid_time = datetime.fromisoformat(raw_time)
            if valid_time.tzinfo is None:
                valid_time = valid_time.replace(tzinfo=timezone.utc)

            location_id = cls.format_grid_location_id("open_meteo", model_name, resolved_lat, resolved_lon)

            # Extract atmospheric variables
            t2m = current.get("temperature_2m")
            rh2m = current.get("relative_humidity_2m")
            ws10m = current.get("wind_speed_10m")
            wd10m = current.get("wind_direction_10m")
            precip = current.get("precipitation")
            press = current.get("surface_pressure")

            return EnvironmentalObservationItem(
                incident_id=incident_id,
                location_type=LocationType.GRID,
                location_id=location_id,
                requested_latitude=requested_lat,
                requested_longitude=requested_lon,
                resolved_latitude=resolved_lat,
                resolved_longitude=resolved_lon,
                typology=EnvironmentalTypology.MODEL_ANALYSIS,
                valid_time_utc=valid_time,
                recorded_at=valid_time,
                source="open-meteo",
                provider="open-meteo",
                dataset_or_model=model_name,
                temperature_celsius=float(t2m) if t2m is not None else None,
                relative_humidity=float(rh2m) if rh2m is not None else None,
                wind_speed_mps=float(ws10m) if ws10m is not None else None,
                wind_direction_degrees=float(wd10m) if wd10m is not None else None,
                precipitation_mm=float(precip) if precip is not None else None,
                surface_pressure_hpa=float(press) if press is not None else None,
                retrieved_at_utc=datetime.now(timezone.utc),
                metrics_payload={"raw_interval": current.get("interval")},
            )
        except (ValueError, TypeError) as e:
            raise NormalizationError(f"Failed to normalize Open-Meteo current conditions: {str(e)}", provider="open-meteo")

    @classmethod
    def normalize_open_meteo_hourly(
        cls,
        raw_payload: Dict[str, Any],
        requested_lat: float,
        requested_lon: float,
        typology: EnvironmentalTypology,
        model_name: str,
        incident_id: Optional[UUID] = None,
        init_time_utc: Optional[datetime] = None,
    ) -> List[EnvironmentalObservationItem]:
        """
        Normalizes Open-Meteo 'hourly' series (reanalysis or forecast).
        """
        try:
            resolved_lat = float(raw_payload.get("latitude", requested_lat))
            resolved_lon = float(raw_payload.get("longitude", requested_lon))
            hourly = raw_payload.get("hourly")
            if not hourly or not isinstance(hourly, dict):
                raise NormalizationError("Missing or invalid 'hourly' object in Open-Meteo response", provider="open-meteo")

            times = hourly.get("time", [])
            t2m_list = hourly.get("temperature_2m", [])
            rh_list = hourly.get("relative_humidity_2m", [])
            ws_list = hourly.get("wind_speed_10m", [])
            wd_list = hourly.get("wind_direction_10m", [])
            precip_list = hourly.get("precipitation", [])
            press_list = hourly.get("surface_pressure", [])

            num_records = len(times)
            if num_records == 0:
                return []

            location_id = cls.format_grid_location_id("open_meteo", model_name, resolved_lat, resolved_lon)
            retrieved_at = datetime.now(timezone.utc)

            # Determine baseline init_time for forecast if not passed
            if typology == EnvironmentalTypology.FORECAST and init_time_utc is None:
                first_time = datetime.fromisoformat(times[0])
                if first_time.tzinfo is None:
                    first_time = first_time.replace(tzinfo=timezone.utc)
                init_time_utc = first_time

            items: List[EnvironmentalObservationItem] = []
            for i in range(num_records):
                v_time = datetime.fromisoformat(times[i])
                if v_time.tzinfo is None:
                    v_time = v_time.replace(tzinfo=timezone.utc)

                lead_hours: Optional[float] = None
                if typology == EnvironmentalTypology.FORECAST and init_time_utc is not None:
                    diff_seconds = (v_time - init_time_utc).total_seconds()
                    lead_hours = max(0.0, diff_seconds / 3600.0)

                t2m = t2m_list[i] if i < len(t2m_list) else None
                rh = rh_list[i] if i < len(rh_list) else None
                ws = ws_list[i] if i < len(ws_list) else None
                wd = wd_list[i] if i < len(wd_list) else None
                pr = precip_list[i] if i < len(precip_list) else None
                ps = press_list[i] if i < len(press_list) else None

                item = EnvironmentalObservationItem(
                    incident_id=incident_id,
                    location_type=LocationType.GRID,
                    location_id=location_id,
                    requested_latitude=requested_lat,
                    requested_longitude=requested_lon,
                    resolved_latitude=resolved_lat,
                    resolved_longitude=resolved_lon,
                    typology=typology,
                    valid_time_utc=v_time,
                    recorded_at=v_time,
                    source="open-meteo",
                    provider="open-meteo",
                    dataset_or_model=model_name,
                    init_time_utc=init_time_utc if typology == EnvironmentalTypology.FORECAST else None,
                    lead_time_hours=lead_hours,
                    temperature_celsius=float(t2m) if t2m is not None else None,
                    relative_humidity=float(rh) if rh is not None else None,
                    wind_speed_mps=float(ws) if ws is not None else None,
                    wind_direction_degrees=float(wd) if wd is not None else None,
                    precipitation_mm=float(pr) if pr is not None else None,
                    surface_pressure_hpa=float(ps) if ps is not None else None,
                    retrieved_at_utc=retrieved_at,
                )
                items.append(item)

            return items
        except (ValueError, TypeError) as e:
            raise NormalizationError(f"Failed to normalize Open-Meteo hourly data: {str(e)}", provider="open-meteo")

    @classmethod
    def normalize_nasa_power_hourly(
        cls,
        raw_payload: Dict[str, Any],
        requested_lat: float,
        requested_lon: float,
        incident_id: Optional[UUID] = None,
        model_name: str = "merra2",
    ) -> List[EnvironmentalObservationItem]:
        """
        Normalizes NASA POWER hourly point payload.
        Handles:
        - Pressure conversion from kPa to hPa (x 10.0)
        - Filtering NASA fill/missing values (-999.0, -999)
        - Timestamp formatting YYYYMMDDHH to ISO UTC datetime
        """
        try:
            geometry = raw_payload.get("geometry", {})
            coords = geometry.get("coordinates", [requested_lon, requested_lat, 0.0])
            resolved_lon = float(coords[0])
            resolved_lat = float(coords[1])

            props = raw_payload.get("properties", {})
            param = props.get("parameter", {})
            if not param:
                raise NormalizationError("Missing 'properties.parameter' in NASA POWER payload", provider="nasa-power")

            t2m_map = param.get("T2M", {})
            rh_map = param.get("RH2M", {})
            ws_map = param.get("WS10M", {})
            wd_map = param.get("WD10M", {})
            pr_map = param.get("PRECTOTCORR", {})
            ps_map = param.get("PS", {})  # in kPa

            timestamps = sorted(t2m_map.keys())
            if not timestamps:
                return []

            location_id = cls.format_grid_location_id("nasa_power", model_name, resolved_lat, resolved_lon)
            retrieved_at = datetime.now(timezone.utc)
            items: List[EnvironmentalObservationItem] = []

            for ts_str in timestamps:
                # Format: YYYYMMDDHH
                if len(ts_str) < 10:
                    continue
                year = int(ts_str[0:4])
                month = int(ts_str[4:6])
                day = int(ts_str[6:8])
                hour = int(ts_str[8:10])
                v_time = datetime(year, month, day, hour, 0, 0, tzinfo=timezone.utc)

                def parse_val(val: Any) -> Optional[float]:
                    if val is None:
                        return None
                    try:
                        f = float(val)
                        if f <= -990.0:  # NASA fill value threshold
                            return None
                        return f
                    except (ValueError, TypeError):
                        return None

                t2m = parse_val(t2m_map.get(ts_str))
                rh = parse_val(rh_map.get(ts_str))
                ws = parse_val(ws_map.get(ts_str))
                wd = parse_val(wd_map.get(ts_str))
                pr = parse_val(pr_map.get(ts_str))
                
                # Surface pressure: NASA POWER provides PS in kPa, convert to hPa
                ps_kpa = parse_val(ps_map.get(ts_str))
                ps_hpa = (ps_kpa * 10.0) if ps_kpa is not None else None

                item = EnvironmentalObservationItem(
                    incident_id=incident_id,
                    location_type=LocationType.GRID,
                    location_id=location_id,
                    requested_latitude=requested_lat,
                    requested_longitude=requested_lon,
                    resolved_latitude=resolved_lat,
                    resolved_longitude=resolved_lon,
                    typology=EnvironmentalTypology.REANALYSIS,
                    valid_time_utc=v_time,
                    recorded_at=v_time,
                    source="nasa-power",
                    provider="nasa-power",
                    dataset_or_model=model_name,
                    temperature_celsius=t2m,
                    relative_humidity=rh,
                    wind_speed_mps=ws,
                    wind_direction_degrees=wd,
                    precipitation_mm=pr,
                    surface_pressure_hpa=ps_hpa,
                    retrieved_at_utc=retrieved_at,
                    metrics_payload={"time_standard": "UTC"},
                )
                items.append(item)

            return items
        except (ValueError, TypeError) as e:
            raise NormalizationError(f"Failed to normalize NASA POWER hourly data: {str(e)}", provider="nasa-power")
