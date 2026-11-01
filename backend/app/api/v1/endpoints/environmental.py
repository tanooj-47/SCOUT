from datetime import date, datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.environmental.fwi.engine import FWIEngine
from app.environmental.schemas import (
    EnvironmentalIngestRequest,
    EnvironmentalIngestResponse,
    EnvironmentalObservationItem,
    EnvironmentalTypology,
    FWICalculateRequest,
    FWICalculateResponse,
)
from app.environmental.services import EnvironmentalService

router = APIRouter()


def get_environmental_service(db: Session = Depends(get_db)) -> EnvironmentalService:
    """Dependency provider injecting repository session into EnvironmentalService."""
    return EnvironmentalService(db_session=db)


@router.get(
    "/health",
    status_code=status.HTTP_200_OK,
    summary="Environmental subsystem provider health check",
)
def get_health(
    service: EnvironmentalService = Depends(get_environmental_service),
) -> Dict[str, Any]:
    """
    Checks operational reachability of upstream external weather providers
    and returns in-memory cache statistics.
    """
    return service.check_health()


@router.get(
    "/current",
    response_model=EnvironmentalObservationItem,
    status_code=status.HTTP_200_OK,
    summary="Retrieve current atmospheric conditions",
)
def get_current_conditions(
    latitude: float = Query(..., ge=-90.0, le=90.0, description="Latitude [-90.0, 90.0]"),
    longitude: float = Query(..., ge=-180.0, le=180.0, description="Longitude [-180.0, 180.0]"),
    incident_id: Optional[UUID] = Query(None, description="Optional incident to associate observation with"),
    provider: str = Query("open-meteo", description="Provider (open-meteo or nasa-power)"),
    dataset_or_model: str = Query("best_match", description="NWP model name"),
    service: EnvironmentalService = Depends(get_environmental_service),
) -> EnvironmentalObservationItem:
    """
    Retrieves current atmospheric conditions (temperature, humidity, wind, pressure).
    Strictly classified as MODEL_ANALYSIS.
    """
    item, is_stale = service.get_current_conditions(
        latitude=latitude,
        longitude=longitude,
        incident_id=incident_id,
        provider=provider,
        dataset_or_model=dataset_or_model,
    )
    return item.model_copy(update={"is_stale": is_stale})


@router.get(
    "/forecast",
    response_model=List[EnvironmentalObservationItem],
    status_code=status.HTTP_200_OK,
    summary="Retrieve numerical weather prediction forecast",
)
def get_forecast(
    latitude: float = Query(..., ge=-90.0, le=90.0),
    longitude: float = Query(..., ge=-180.0, le=180.0),
    forecast_days: int = Query(7, ge=1, le=16, description="Horizon in days [1..16]"),
    incident_id: Optional[UUID] = Query(None),
    provider: str = Query("open-meteo"),
    dataset_or_model: str = Query("best_match"),
    service: EnvironmentalService = Depends(get_environmental_service),
) -> List[EnvironmentalObservationItem]:
    """
    Retrieves hourly weather forecast time series.
    """
    items, is_stale = service.get_weather_forecast(
        latitude=latitude,
        longitude=longitude,
        forecast_days=forecast_days,
        incident_id=incident_id,
        provider=provider,
        dataset_or_model=dataset_or_model,
    )
    return [it.model_copy(update={"is_stale": is_stale}) for it in items]


@router.get(
    "/historical",
    response_model=List[EnvironmentalObservationItem],
    status_code=status.HTTP_200_OK,
    summary="Retrieve historical atmospheric reanalysis",
)
def get_historical(
    latitude: float = Query(..., ge=-90.0, le=90.0),
    longitude: float = Query(..., ge=-180.0, le=180.0),
    start_date: date = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: date = Query(..., description="End date (YYYY-MM-DD)"),
    incident_id: Optional[UUID] = Query(None),
    provider: str = Query("open-meteo"),
    dataset_or_model: Optional[str] = Query(None),
    service: EnvironmentalService = Depends(get_environmental_service),
) -> List[EnvironmentalObservationItem]:
    """
    Retrieves historical reanalysis data (ERA5 from Open-Meteo or MERRA-2 from NASA POWER).
    """
    items, is_stale = service.get_historical_reanalysis(
        latitude=latitude,
        longitude=longitude,
        start_date=start_date,
        end_date=end_date,
        incident_id=incident_id,
        provider=provider,
        dataset_or_model=dataset_or_model,
    )
    return [it.model_copy(update={"is_stale": is_stale}) for it in items]


@router.post(
    "/ingest",
    response_model=EnvironmentalIngestResponse,
    status_code=status.HTTP_200_OK,
    summary="Ingest and persist on-demand environmental observations",
)
def ingest_data(
    payload: EnvironmentalIngestRequest,
    service: EnvironmentalService = Depends(get_environmental_service),
) -> EnvironmentalIngestResponse:
    """
    Executes an on-demand retrieval, validation, normalization, and database persistence
    run for the requested coordinates and typology.
    """
    return service.ingest_data(payload)


@router.get(
    "/observations",
    response_model=List[EnvironmentalObservationItem],
    status_code=status.HTTP_200_OK,
    summary="Query stored environmental observations",
)
def query_observations(
    incident_id: Optional[UUID] = Query(None, description="Filter by incident UUID"),
    location_id: Optional[str] = Query(None, description="Filter by canonical location ID"),
    typology: Optional[EnvironmentalTypology] = Query(None, description="Filter by provenance typology"),
    provider: Optional[str] = Query(None, description="Filter by provider"),
    start_time_utc: Optional[datetime] = Query(None, description="Filter by start time"),
    end_time_utc: Optional[datetime] = Query(None, description="Filter by end time"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    service: EnvironmentalService = Depends(get_environmental_service),
) -> List[EnvironmentalObservationItem]:
    """
    Queries stored environmental observations from the database repository.
    """
    if not service.repository:
        return []
    records = service.repository.query_observations(
        location_id=location_id,
        incident_id=incident_id,
        typology=typology.value if typology else None,
        provider=provider,
        start_time_utc=start_time_utc,
        end_time_utc=end_time_utc,
        limit=limit,
        offset=offset,
    )
    return [EnvironmentalObservationItem.model_validate(r) for r in records]


@router.post(
    "/fwi/calculate",
    response_model=FWICalculateResponse,
    status_code=status.HTTP_200_OK,
    summary="Calculate Canadian Forest Fire Weather Index (FWI)",
)
def calculate_fwi(
    payload: FWICalculateRequest,
) -> FWICalculateResponse:
    """
    Calculates the 6 CFS-FWI fuel moisture and fire behavior codes
    (FFMC, DMC, DC, ISI, BUI, FWI, DSR) from a sequence of daily noon weather readings.
    """
    records = FWIEngine.calculate_series(
        readings=payload.readings,
        lat=payload.latitude,
        initial_ffmc=payload.initial_ffmc,
        initial_dmc=payload.initial_dmc,
        initial_dc=payload.initial_dc,
    )
    spinup_warning = len(payload.readings) < 30
    return FWICalculateResponse(
        records=records,
        total_days=len(records),
        spinup_warning=spinup_warning,
    )
