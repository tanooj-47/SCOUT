from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from app.environmental.exceptions import NormalizationError
from app.environmental.normalizer import EnvironmentalNormalizer
from app.environmental.schemas import (
    EnvironmentalObservationItem,
    EnvironmentalTypology,
    LocationType,
)


class TestEnvironmentalNormalizer:

    def test_open_meteo_current_normalization(self):
        payload = {
            "latitude": 28.625,
            "longitude": 77.25,
            "elevation": 216.0,
            "current": {
                "time": "2026-10-31T08:00",
                "interval": 900,
                "temperature_2m": 31.4,
                "relative_humidity_2m": 45.0,
                "wind_speed_10m": 3.8,
                "wind_direction_10m": 120.0,
                "precipitation": 0.0,
                "surface_pressure": 1008.2,
            },
        }

        item = EnvironmentalNormalizer.normalize_open_meteo_current(
            raw_payload=payload,
            requested_lat=28.6139,
            requested_lon=77.2090,
            model_name="best_match",
        )

        assert item.provider == "open-meteo"
        assert item.source == "open-meteo"
        assert item.dataset_or_model == "best_match"
        assert item.typology == EnvironmentalTypology.MODEL_ANALYSIS
        assert item.location_type == LocationType.GRID
        assert item.location_id == "grid:open_meteo:best_match:28.6250_77.2500"
        assert item.resolved_latitude == 28.625
        assert item.resolved_longitude == 77.25
        assert item.requested_latitude == 28.6139
        assert item.requested_longitude == 77.2090
        assert item.temperature_celsius == 31.4
        assert item.relative_humidity == 45.0
        assert item.wind_speed_mps == 3.8
        assert item.wind_direction_degrees == 120.0
        assert item.precipitation_mm == 0.0
        assert item.surface_pressure_hpa == 1008.2
        assert item.valid_time_utc == datetime(2026, 10, 31, 8, 0, tzinfo=timezone.utc)
        assert item.recorded_at == item.valid_time_utc

    def test_open_meteo_hourly_forecast(self):
        payload = {
            "latitude": 28.625,
            "longitude": 77.25,
            "hourly": {
                "time": ["2026-10-31T00:00", "2026-10-31T01:00", "2026-10-31T02:00"],
                "temperature_2m": [22.0, 21.5, 21.0],
                "relative_humidity_2m": [60.0, 62.0, 65.0],
                "wind_speed_10m": [2.5, 2.8, 3.0],
                "wind_direction_10m": [90.0, 95.0, 100.0],
                "precipitation": [0.0, 0.2, 0.5],
                "surface_pressure": [1010.0, 1009.8, 1009.5],
            },
        }

        init_time = datetime(2026, 10, 31, 0, 0, tzinfo=timezone.utc)
        items = EnvironmentalNormalizer.normalize_open_meteo_hourly(
            raw_payload=payload,
            requested_lat=28.6139,
            requested_lon=77.2090,
            typology=EnvironmentalTypology.FORECAST,
            model_name="ecmwf_ifs",
            init_time_utc=init_time,
        )

        assert len(items) == 3
        assert items[0].lead_time_hours == 0.0
        assert items[1].lead_time_hours == 1.0
        assert items[2].lead_time_hours == 2.0
        for it in items:
            assert it.typology == EnvironmentalTypology.FORECAST
            assert it.dataset_or_model == "ecmwf_ifs"
            assert it.init_time_utc == init_time

    def test_nasa_power_hourly_normalization_and_pressure_conversion(self):
        payload = {
            "geometry": {"type": "Point", "coordinates": [77.25, 28.625, 215.0]},
            "properties": {
                "parameter": {
                    "T2M": {"2026051500": 26.5, "2026051501": -999.0},
                    "RH2M": {"2026051500": 55.0, "2026051501": 58.0},
                    "WS10M": {"2026051500": 3.2, "2026051501": 3.0},
                    "WD10M": {"2026051500": 180.0, "2026051501": 185.0},
                    "PRECTOTCORR": {"2026051500": 0.0, "2026051501": 0.0},
                    "PS": {"2026051500": 100.5, "2026051501": 100.4},  # kPa
                }
            },
        }

        items = EnvironmentalNormalizer.normalize_nasa_power_hourly(
            raw_payload=payload,
            requested_lat=28.6139,
            requested_lon=77.2090,
            model_name="merra2",
        )

        assert len(items) == 2
        item0, item1 = items[0], items[1]

        # Check date parsing
        assert item0.valid_time_utc == datetime(2026, 5, 15, 0, 0, tzinfo=timezone.utc)
        assert item0.temperature_celsius == 26.5
        # 100.5 kPa * 10.0 = 1005.0 hPa
        assert item0.surface_pressure_hpa == 1005.0
        assert item0.typology == EnvironmentalTypology.REANALYSIS
        assert item0.provider == "nasa-power"

        # Check fill-value filtering (-999.0 should be None)
        assert item1.valid_time_utc == datetime(2026, 5, 15, 1, 0, tzinfo=timezone.utc)
        assert item1.temperature_celsius is None
        assert item1.relative_humidity == 58.0
        assert item1.surface_pressure_hpa == 1004.0

    def test_forecast_item_requires_lead_time_and_init_time(self):
        # Forecast without init_time_utc or lead_time_hours should fail validation
        with pytest.raises(ValidationError):
            EnvironmentalObservationItem(
                location_id="grid:test:0.0_0.0",
                requested_latitude=0.0,
                requested_longitude=0.0,
                resolved_latitude=0.0,
                resolved_longitude=0.0,
                typology=EnvironmentalTypology.FORECAST,
                valid_time_utc=datetime.now(timezone.utc),
                recorded_at=datetime.now(timezone.utc),
                source="test",
                provider="test",
                dataset_or_model="test",
                # missing init_time_utc and lead_time_hours
            )

    def test_derived_item_requires_algorithm_fields(self):
        # Derived without algorithm fields should fail validation
        with pytest.raises(ValidationError):
            EnvironmentalObservationItem(
                location_id="grid:test:0.0_0.0",
                requested_latitude=0.0,
                requested_longitude=0.0,
                resolved_latitude=0.0,
                resolved_longitude=0.0,
                typology=EnvironmentalTypology.DERIVED,
                valid_time_utc=datetime.now(timezone.utc),
                recorded_at=datetime.now(timezone.utc),
                source="test",
                provider="test",
                dataset_or_model="test",
            )
