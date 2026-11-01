"""
backend/app/api/v1/endpoints/geospatial.py
FastAPI routing endpoints for geospatial intelligence, exposure analysis,
spatial queries, and persistent geographic feature catalog.
Milestone 10: Persistent Geospatial Data Integration.
"""

from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.geospatial.coordinates import HAS_PYPROJ
from app.geospatial.geometry import HAS_SHAPELY
from app.geospatial.persistent_context import (
    PersistentGeospatialContextService,
    feature_to_domain_item,
)
from app.geospatial.repository import GeospatialFeatureRepository
from app.geospatial.schemas import (
    CoordinateValidationRequest,
    CoordinateValidationResponse,
    DataSourceItemResponse,
    ExposureAnalysisRequest,
    FeatureCategory,
    FeatureListResponse,
    GeographicFeatureItem,
    GeospatialAssessmentResponse,
    GeospatialHealthResponse,
    IngestionRunItemResponse,
    LayerSummaryResponse,
    NearbyFeaturesQuery,
)
from app.geospatial.spatial_queries import check_postgis_availability
from app.services.geospatial_service import GeospatialService

router = APIRouter()
geospatial_service = GeospatialService()


@router.get(
    "/health",
    response_model=GeospatialHealthResponse,
    summary="Geospatial Engine Health & Capabilities Probe",
    status_code=status.HTTP_200_OK,
)
def get_geospatial_health(db: Optional[Session] = Depends(get_db)) -> GeospatialHealthResponse:
    """
    Returns the operational status of the Geospatial Intelligence Engine,
    including PostGIS connectivity, geometry library availability, and supported projections.
    """
    postgis_ok = False
    try:
        postgis_ok = check_postgis_availability(db)
    except Exception:
        postgis_ok = False

    engine_status = "operational" if (HAS_SHAPELY and HAS_PYPROJ) else "degraded"

    return GeospatialHealthResponse(
        status=engine_status,
        postgis_connected=postgis_ok,
        shapely_available=HAS_SHAPELY,
        pyproj_available=HAS_PYPROJ,
        supported_crs=["EPSG:4326 (WGS 84)", "EPSG:3857 (Web Mercator)", "UTM Zones (EPSG:32601-32660, 32701-32760)"],
    )


@router.post(
    "/validate-coordinate",
    response_model=CoordinateValidationResponse,
    summary="Validate Geographic Coordinates",
    status_code=status.HTTP_200_OK,
)
def validate_coordinate_endpoint(
    request: CoordinateValidationRequest,
) -> CoordinateValidationResponse:
    """
    Validates latitude and longitude values against physical Earth boundaries and data types.
    Resolves the appropriate local UTM projection zone for metric distance operations.
    """
    return geospatial_service.validate_coordinate(request)


@router.get(
    "/nearby",
    response_model=List[GeographicFeatureItem],
    summary="Query Nearby Geographic Features",
    status_code=status.HTTP_200_OK,
)
def get_nearby_features_endpoint(
    latitude: float = Query(..., ge=-90.0, le=90.0, description="Latitude [-90.0, 90.0]"),
    longitude: float = Query(..., ge=-180.0, le=180.0, description="Longitude [-180.0, 180.0]"),
    radius_meters: float = Query(5000.0, ge=100.0, le=100000.0, description="Search radius in meters"),
    categories: Optional[List[FeatureCategory]] = Query(None, description="Filter categories"),
    limit: int = Query(50, ge=1, le=200, description="Maximum results"),
    include_geometry: bool = Query(False, description="Include GeoJSON geometry"),
    db: Optional[Session] = Depends(get_db),
) -> List[GeographicFeatureItem]:
    """
    Queries spatial features surrounding an observation point, computing exact
    geodesic distances and topological relationships. Backed by PostGIS with in-memory fallback.
    """
    query = NearbyFeaturesQuery(
        latitude=latitude,
        longitude=longitude,
        radius_meters=radius_meters,
        categories=categories,
        limit=limit,
        include_geometry=include_geometry,
    )
    return geospatial_service.query_nearby_features(query, db=db)


@router.post(
    "/analyze",
    response_model=GeospatialAssessmentResponse,
    summary="Execute Geographic Exposure & Risk Assessment",
    status_code=status.HTTP_200_OK,
)
def analyze_exposure_endpoint(
    request: ExposureAnalysisRequest,
    db: Optional[Session] = Depends(get_db),
) -> GeospatialAssessmentResponse:
    """
    Executes a structured geospatial risk assessment for an incident or coordinate point.
    Separates verified geographic proximity from predictive disaster simulation.
    """
    return geospatial_service.analyze_exposure(request, db=db)


@router.get(
    "/incidents/{incident_id}/exposure",
    response_model=GeospatialAssessmentResponse,
    summary="Assess Exposure for Registered Incident",
    status_code=status.HTTP_200_OK,
)
def assess_incident_exposure_endpoint(
    incident_id: UUID,
    search_radius_meters: float = Query(5000.0, ge=100.0, le=100000.0),
    include_geometry: bool = Query(False),
    db: Session = Depends(get_db),
) -> GeospatialAssessmentResponse:
    """
    Loads a registered disaster incident by UUID from the database and runs
    a specialized geographic exposure and risk evaluation.
    """
    req = ExposureAnalysisRequest(
        incident_id=incident_id,
        search_radius_meters=search_radius_meters,
        include_geometry=include_geometry,
    )
    return geospatial_service.analyze_exposure(req, db=db)


# ==============================================================================
# Persistent Geospatial Catalog Endpoints (Milestone 10)
# ==============================================================================

@router.get(
    "/layers",
    response_model=List[LayerSummaryResponse],
    summary="List Available Geospatial Layers",
    status_code=status.HTTP_200_OK,
)
def list_layers_endpoint(db: Session = Depends(get_db)) -> List[LayerSummaryResponse]:
    """
    Returns all persistent geographic layers present in PostGIS with feature counts and distinct categories.
    """
    repo = GeospatialFeatureRepository(db)
    layers = repo.list_layers()
    return [LayerSummaryResponse(**item) for item in layers]


@router.get(
    "/features",
    response_model=FeatureListResponse,
    summary="Query Persistent Geographic Features",
    status_code=status.HTTP_200_OK,
)
def list_features_endpoint(
    min_lon: Optional[float] = Query(None, ge=-180.0, le=180.0, description="Bounding box min longitude"),
    min_lat: Optional[float] = Query(None, ge=-90.0, le=90.0, description="Bounding box min latitude"),
    max_lon: Optional[float] = Query(None, ge=-180.0, le=180.0, description="Bounding box max longitude"),
    max_lat: Optional[float] = Query(None, ge=-90.0, le=90.0, description="Bounding box max latitude"),
    latitude: Optional[float] = Query(None, ge=-90.0, le=90.0, description="Center latitude for radius query"),
    longitude: Optional[float] = Query(None, ge=-180.0, le=180.0, description="Center longitude for radius query"),
    radius_meters: Optional[float] = Query(5000.0, ge=100.0, le=100000.0, description="Radius in meters"),
    layer_name: Optional[str] = Query(None, description="Filter by layer name"),
    category: Optional[str] = Query(None, description="Filter by canonical category"),
    hazard: Optional[str] = Query(None, description="Filter by hazard relevance (wildfire, flood, earthquake)"),
    limit: int = Query(50, ge=1, le=200, description="Page limit"),
    offset: int = Query(0, ge=0, description="Page offset"),
    include_geometry: bool = Query(False, description="Include GeoJSON geometry"),
    db: Session = Depends(get_db),
) -> FeatureListResponse:
    """
    Queries persistent geographic features by spatial bounding box envelope or geodesic radius.
    Enforces pagination and spatial bounding to avoid unbounded country-scale loads.
    """
    repo = GeospatialFeatureRepository(db)
    items: List[GeographicFeatureItem] = []

    has_coords = isinstance(latitude, (int, float)) and isinstance(longitude, (int, float))
    has_bbox = (
        isinstance(min_lon, (int, float))
        and isinstance(min_lat, (int, float))
        and isinstance(max_lon, (int, float))
        and isinstance(max_lat, (int, float))
    )

    clean_layer = layer_name if isinstance(layer_name, str) else None
    clean_cat = category if isinstance(category, str) else None
    clean_hazard = hazard if isinstance(hazard, str) else None
    clean_limit = limit if isinstance(limit, int) else 50
    clean_offset = offset if isinstance(offset, int) else 0
    clean_include_geom = bool(include_geometry) if isinstance(include_geometry, bool) else False

    if has_coords:
        radius_m = float(radius_meters) if isinstance(radius_meters, (int, float)) else 5000.0
        records = repo.query_within_radius(
            center_lon=float(longitude),
            center_lat=float(latitude),
            radius_meters=radius_m,
            layer_name=clean_layer,
            category=clean_cat,
            hazard=clean_hazard,
            limit=clean_limit,
            offset=clean_offset,
        )
        for feat, dist in records:
            items.append(
                feature_to_domain_item(
                    feature=feat,
                    distance_meters=dist,
                    radius_meters=radius_m,
                    include_geometry=clean_include_geom,
                )
            )
        total = repo.count_features(layer_name=clean_layer)
    elif has_bbox:
        records = repo.query_by_bbox(
            min_lon=float(min_lon),
            min_lat=float(min_lat),
            max_lon=float(max_lon),
            max_lat=float(max_lat),
            layer_name=clean_layer,
            category=clean_cat,
            hazard=clean_hazard,
            limit=clean_limit,
            offset=clean_offset,
        )
        for feat in records:
            items.append(
                feature_to_domain_item(
                    feature=feat,
                    distance_meters=0.0,
                    radius_meters=0.0,
                    include_geometry=clean_include_geom,
                )
            )
        total = repo.count_features(layer_name=clean_layer)
    else:
        records = repo.query_by_bbox(
            min_lon=-180.0,
            min_lat=-90.0,
            max_lon=180.0,
            max_lat=90.0,
            layer_name=clean_layer,
            category=clean_cat,
            hazard=clean_hazard,
            limit=clean_limit,
            offset=clean_offset,
        )
        for feat in records:
            items.append(
                feature_to_domain_item(
                    feature=feat,
                    distance_meters=0.0,
                    radius_meters=0.0,
                    include_geometry=clean_include_geom,
                )
            )
        total = repo.count_features(layer_name=clean_layer)

    return FeatureListResponse(
        total=total,
        limit=clean_limit,
        offset=clean_offset,
        features=items,
    )


@router.get(
    "/sources",
    response_model=List[DataSourceItemResponse],
    summary="List External Geographic Data Sources",
    status_code=status.HTTP_200_OK,
)
def list_sources_endpoint(db: Session = Depends(get_db)) -> List[DataSourceItemResponse]:
    """
    Lists external data sources registered in SCOUT with full license and attribution metadata.
    """
    repo = GeospatialFeatureRepository(db)
    sources = repo.list_sources()
    return [DataSourceItemResponse.model_validate(s) for s in sources]


@router.get(
    "/ingestion-runs",
    response_model=List[IngestionRunItemResponse],
    summary="List Geospatial Ingestion Audit Runs",
    status_code=status.HTTP_200_OK,
)
def list_ingestion_runs_endpoint(
    limit: int = Query(50, ge=1, le=200, description="Maximum runs to return"),
    db: Session = Depends(get_db),
) -> List[IngestionRunItemResponse]:
    """
    Returns audit history records of batch ingestion operations including checksums and counts.
    """
    repo = GeospatialFeatureRepository(db)
    runs = repo.list_ingestion_runs(limit=limit)
    return [IngestionRunItemResponse.model_validate(r) for r in runs]
