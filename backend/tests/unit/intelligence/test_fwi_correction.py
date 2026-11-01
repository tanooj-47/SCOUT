"""
backend/tests/unit/intelligence/test_fwi_correction.py
Unit tests for Milestone 11 Correction B (Scientific FWI & Weather Handling).
Verifies elimination of invalid default constants and proper caveat attribution.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import pytest

from app.environmental.schemas import EnvironmentalObservationItem, EnvironmentalTypology
from app.intelligence.adapters.environmental_adapter import EnvironmentalModelAdapter


def _mock_obs(temp=None, rh=None, wind=None, rain=None):
    now_utc = datetime.now(timezone.utc)
    return EnvironmentalObservationItem(
        location_type="point",
        location_id="point:30.3165:78.0322",
        requested_latitude=30.3165,
        requested_longitude=78.0322,
        resolved_latitude=30.3165,
        resolved_longitude=78.0322,
        valid_time_utc=now_utc,
        recorded_at=now_utc,
        typology=EnvironmentalTypology.MODEL_ANALYSIS,
        source="open_meteo_api",
        provider="open-meteo",
        dataset_or_model="best_match",
        temperature_celsius=temp,
        relative_humidity=rh,
        wind_speed_mps=wind,
        precipitation_mm=rain,
        surface_pressure_hpa=1013.25,
        wind_direction_degrees=180.0,
    )


@patch("app.intelligence.adapters.environmental_adapter.EnvironmentalService.get_current_conditions")
def test_fwi_missing_temperature_no_defaults(mock_get_conditions):
    """When temperature is missing, FWI must NOT compute and NO default 20°C is injected."""
    mock_get_conditions.return_value = (_mock_obs(temp=None, rh=30.0, wind=5.0, rain=0.0), False)

    adapter = EnvironmentalModelAdapter()
    evidence = adapter.collect_evidence(30.3165, 78.0322)

    assert evidence.status == "valid"
    raw = evidence.raw_value
    assert raw["temperature_c"] is None
    assert raw["fwi_indices"] is None
    assert raw["fwi_available"] is False
    assert "temperature_celsius" in raw["missing_meteorological_variables"]
    assert any("not computed" in c.lower() for c in evidence.caveats)


@patch("app.intelligence.adapters.environmental_adapter.EnvironmentalService.get_current_conditions")
def test_fwi_missing_humidity_no_defaults(mock_get_conditions):
    """When relative humidity is missing, FWI must NOT compute and NO default 50% is injected."""
    mock_get_conditions.return_value = (_mock_obs(temp=32.0, rh=None, wind=4.0, rain=0.0), False)

    adapter = EnvironmentalModelAdapter()
    evidence = adapter.collect_evidence(30.3165, 78.0322)

    raw = evidence.raw_value
    assert raw["relative_humidity_pct"] is None
    assert raw["fwi_indices"] is None
    assert raw["fwi_available"] is False
    assert "relative_humidity" in raw["missing_meteorological_variables"]


@patch("app.intelligence.adapters.environmental_adapter.EnvironmentalService.get_current_conditions")
def test_fwi_missing_wind_no_defaults(mock_get_conditions):
    """When wind is missing, FWI must NOT compute and NO default 3 m/s is injected."""
    mock_get_conditions.return_value = (_mock_obs(temp=32.0, rh=40.0, wind=None, rain=0.0), False)

    adapter = EnvironmentalModelAdapter()
    evidence = adapter.collect_evidence(30.3165, 78.0322)

    raw = evidence.raw_value
    assert raw["wind_speed_kmh"] is None
    assert raw["fwi_indices"] is None
    assert raw["fwi_available"] is False
    assert "wind_speed_mps" in raw["missing_meteorological_variables"]


@patch("app.intelligence.adapters.environmental_adapter.EnvironmentalService.get_current_conditions")
def test_fwi_missing_rain_no_defaults(mock_get_conditions):
    """When precipitation is missing, FWI must NOT compute and NO default 0 mm is injected."""
    mock_get_conditions.return_value = (_mock_obs(temp=32.0, rh=40.0, wind=4.0, rain=None), False)

    adapter = EnvironmentalModelAdapter()
    evidence = adapter.collect_evidence(30.3165, 78.0322)

    raw = evidence.raw_value
    assert raw["precipitation_mm"] is None
    assert raw["fwi_indices"] is None
    assert raw["fwi_available"] is False
    assert "precipitation_mm" in raw["missing_meteorological_variables"]


@patch("app.intelligence.adapters.environmental_adapter.EnvironmentalService.get_current_conditions")
def test_fwi_complete_weather_instantaneous_indicator(mock_get_conditions):
    """When all variables are present, computes FWI and labels as instantaneous indicator with caveats."""
    mock_get_conditions.return_value = (_mock_obs(temp=35.0, rh=25.0, wind=6.0, rain=0.0), False)

    adapter = EnvironmentalModelAdapter()
    evidence = adapter.collect_evidence(30.3165, 78.0322)

    raw = evidence.raw_value
    assert raw["fwi_available"] is True
    assert raw["fwi_indices"] is not None
    assert "fire_weather_index_fwi" in raw["fwi_indices"]
    assert "danger_rating" in raw["fwi_indices"]
    assert "instantaneous_weather_indicator" in raw["fwi_methodology"]

    # Verify explicit caveats are present
    assert any("instantaneous single-reading" in c.lower() for c in evidence.caveats)
    assert any("12:00 lst" in c.lower() for c in evidence.caveats)
    assert any("not been calibrated for indian forest" in c.lower() for c in evidence.caveats)
