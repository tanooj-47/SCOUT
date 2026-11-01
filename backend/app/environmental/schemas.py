from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class EnvironmentalTypology(str, Enum):
    """
    Scientific classification of environmental observation provenance.
    Strictly distinguishes ground truth, reanalysis, model analysis, and NWP forecasts.
    """
    STATION_OBSERVED = "station_observed"
    REANALYSIS = "reanalysis"
    MODEL_ANALYSIS = "model_analysis"
    FORECAST = "forecast"
    DERIVED = "derived"


class LocationType(str, Enum):
    """Location discriminator for atmospheric spatial anchoring."""
    STATION = "station"
    GRID = "grid"
    INCIDENT = "incident"
    POINT = "point"


class CanonicalWeatherVariables(BaseModel):
    """
    Standardized atmospheric variables converted strictly to SI / WMO standard units.
    """
    model_config = ConfigDict(extra="forbid")

    temperature_celsius: Optional[float] = Field(
        None,
        ge=-100.0,
        le=70.0,
        description="Air temperature at 2m in degrees Celsius [-100.0, 70.0]",
    )
    relative_humidity: Optional[float] = Field(
        None,
        ge=0.0,
        le=100.0,
        description="Relative humidity at 2m as percentage [0.0, 100.0]",
    )
    wind_speed_mps: Optional[float] = Field(
        None,
        ge=0.0,
        le=150.0,
        description="Wind speed at 10m in meters per second [0.0, 150.0]",
    )
    wind_direction_degrees: Optional[float] = Field(
        None,
        ge=0.0,
        le=360.0,
        description="Wind direction at 10m in compass degrees [0.0, 360.0]",
    )
    precipitation_mm: Optional[float] = Field(
        None,
        ge=0.0,
        le=2000.0,
        description="Accumulated precipitation in millimeters [0.0, 2000.0]",
    )
    surface_pressure_hpa: Optional[float] = Field(
        None,
        ge=300.0,
        le=1100.0,
        description="Atmospheric surface pressure in hectopascals (hPa) [300.0, 1100.0]",
    )


class ModelRunProvenance(BaseModel):
    """
    Metadata recording upstream provider, numerical weather prediction model, cycle, and lead time.
    """
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(..., description="Provider identity (e.g. open-meteo, nasa-power)")
    dataset_or_model: str = Field(..., description="Model or dataset name (e.g. ecmwf_ifs, merra2, era5)")
    init_time_utc: Optional[datetime] = Field(None, description="Model initialization/cycle timestamp in UTC")
    lead_time_hours: Optional[float] = Field(None, ge=0.0, description="Forecast lead time in hours from init_time")
    retrieved_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when payload was fetched from upstream provider",
    )
    algorithm_name: Optional[str] = Field(None, description="Algorithm name if typology is DERIVED (e.g. cfs_fwi)")
    algorithm_version: Optional[str] = Field(None, description="Algorithm specification version if DERIVED")
    source_fingerprint: Optional[str] = Field(None, description="Deterministic hash of input observation IDs if DERIVED")

    @field_validator("retrieved_at_utc", "init_time_utc", mode="after")
    @classmethod
    def ensure_utc(cls, v: Optional[datetime]) -> Optional[datetime]:
        if v is not None and v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v


class EnvironmentalObservationItem(BaseModel):
    """
    Canonical environmental observation entity representing an atmospheric state bundle.
    """
    model_config = ConfigDict(extra="ignore", from_attributes=True)

    id: Optional[UUID] = Field(None, description="Unique primary key UUID")
    incident_id: Optional[UUID] = Field(None, description="Linked incident UUID if directly scoped")
    location_type: LocationType = Field(LocationType.GRID, description="Spatial representation discriminator")
    location_id: str = Field(..., description="Canonical location identifier (e.g. grid:open_meteo:...)")
    requested_latitude: float = Field(..., ge=-90.0, le=90.0)
    requested_longitude: float = Field(..., ge=-180.0, le=180.0)
    resolved_latitude: float = Field(..., ge=-90.0, le=90.0)
    resolved_longitude: float = Field(..., ge=-180.0, le=180.0)
    typology: EnvironmentalTypology = Field(..., description="Scientific provenance classification")
    valid_time_utc: datetime = Field(..., description="Target validity time of observation in UTC")
    recorded_at: datetime = Field(..., description="Backward compatible recording timestamp (= valid_time_utc)")
    source: str = Field(..., description="Provider source identifier")
    provider: str = Field(..., description="Canonical provider name")
    dataset_or_model: str = Field(..., description="NWP model or dataset name")
    
    # Atmospheric variables
    temperature_celsius: Optional[float] = Field(None, ge=-100.0, le=70.0)
    relative_humidity: Optional[float] = Field(None, ge=0.0, le=100.0)
    wind_speed_mps: Optional[float] = Field(None, ge=0.0, le=150.0)
    wind_direction_degrees: Optional[float] = Field(None, ge=0.0, le=360.0)
    precipitation_mm: Optional[float] = Field(None, ge=0.0, le=2000.0)
    surface_pressure_hpa: Optional[float] = Field(None, ge=300.0, le=1100.0)
    
    # Provenance fields
    init_time_utc: Optional[datetime] = None
    lead_time_hours: Optional[float] = None
    algorithm_name: Optional[str] = None
    algorithm_version: Optional[str] = None
    source_fingerprint: Optional[str] = None
    retrieved_at_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    metrics_payload: Dict[str, Any] = Field(default_factory=dict)
    is_stale: bool = Field(default=False, description="True if served from degraded/stale cache fallback")

    @field_validator("valid_time_utc", "recorded_at", "init_time_utc", "retrieved_at_utc", mode="after")
    @classmethod
    def ensure_utc(cls, v: Optional[datetime]) -> Optional[datetime]:
        if v is not None and v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v

    @model_validator(mode="after")
    def validate_typology_integrity(self) -> "EnvironmentalObservationItem":
        if self.typology == EnvironmentalTypology.FORECAST:
            if self.lead_time_hours is None or self.lead_time_hours < 0:
                raise ValueError("Forecast observations require non-negative lead_time_hours")
            if self.init_time_utc is None:
                raise ValueError("Forecast observations require init_time_utc")
        elif self.typology == EnvironmentalTypology.DERIVED:
            if not self.algorithm_name or not self.algorithm_version or not self.source_fingerprint:
                raise ValueError("Derived observations require algorithm_name, algorithm_version, and source_fingerprint")
        return self


class EnvironmentalIngestRequest(BaseModel):
    """Client request schema for triggering an on-demand environmental ingest."""
    model_config = ConfigDict(extra="forbid")

    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    incident_id: Optional[UUID] = Field(None, description="Optional incident to associate observations with")
    provider: Optional[str] = Field("open-meteo", description="Target provider (open-meteo or nasa-power)")
    typology: EnvironmentalTypology = Field(
        EnvironmentalTypology.MODEL_ANALYSIS,
        description="Target observation typology (model_analysis, reanalysis, forecast)"
    )
    dataset_or_model: Optional[str] = Field(None, description="Specific NWP model if requested")
    start_time_utc: Optional[datetime] = Field(None, description="Start date/time for reanalysis or forecast")
    end_time_utc: Optional[datetime] = Field(None, description="End date/time for reanalysis")
    forecast_days: Optional[int] = Field(7, ge=1, le=16, description="Forecast horizon in days")


class EnvironmentalIngestResponse(BaseModel):
    """Response schema summarizing the ingestion outcome."""
    model_config = ConfigDict(extra="forbid")

    count: int = Field(..., ge=0, description="Number of observations retrieved and persisted")
    location_id: str = Field(..., description="Resolved canonical location ID")
    provider: str
    dataset_or_model: str
    typology: EnvironmentalTypology
    cached: bool = Field(False, description="True if response was served from cache")
    is_stale: bool = Field(False, description="True if cache was served as stale fallback")
    items: List[EnvironmentalObservationItem] = Field(default_factory=list)


# --- Fire Weather Index (FWI) Schemas ---

class FWIDailyReading(BaseModel):
    """Single-day meteorological reading taken at local solar noon (~12:00-13:00 LST)."""
    model_config = ConfigDict(extra="forbid")

    date: str = Field(..., description="ISO 8601 Date string (YYYY-MM-DD)")
    temperature_celsius: float = Field(..., ge=-50.0, le=60.0)
    relative_humidity: float = Field(..., ge=0.0, le=100.0)
    wind_speed_kmh: float = Field(..., ge=0.0, le=300.0, description="Wind speed at 10m in km/h")
    precipitation_mm: float = Field(..., ge=0.0, le=500.0, description="24-hour accumulated rainfall in mm")


class FWIOutputRecord(BaseModel):
    """Computed Canadian Forest Fire Weather Index intermediate and final codes."""
    model_config = ConfigDict(extra="forbid")

    date: str
    ffmc: float = Field(..., description="Fine Fuel Moisture Code [0, 101]")
    dmc: float = Field(..., description="Duff Moisture Code [0, inf)")
    dc: float = Field(..., description="Drought Code [0, inf)")
    isi: float = Field(..., description="Initial Spread Index [0, inf)")
    bui: float = Field(..., description="Buildup Index [0, inf)")
    fwi: float = Field(..., description="Fire Weather Index [0, inf)")
    dsr: float = Field(..., description="Daily Severity Rating [0, inf)")
    danger_rating: str = Field(..., description="Danger Class: Low, Moderate, High, Very High, Extreme")


class FWICalculateRequest(BaseModel):
    """Request schema for calculating FWI over a time series of daily noon readings."""
    model_config = ConfigDict(extra="forbid")

    readings: List[FWIDailyReading] = Field(..., min_length=1)
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Latitude for solar day-length adjustment")
    initial_ffmc: float = Field(85.0, ge=0.0, le=101.0, description="Initial FFMC (default standard 85.0)")
    initial_dmc: float = Field(6.0, ge=0.0, description="Initial DMC (default standard 6.0)")
    initial_dc: float = Field(15.0, ge=0.0, description="Initial DC (default standard 15.0)")


class FWICalculateResponse(BaseModel):
    """Response containing computed FWI values across the provided sequence."""
    model_config = ConfigDict(extra="forbid")

    records: List[FWIOutputRecord]
    total_days: int
    spinup_warning: bool = Field(
        False,
        description="True if series has fewer than 30 days of data prior to target date",
    )
