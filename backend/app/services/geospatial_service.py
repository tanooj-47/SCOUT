"""
backend/app/services/geospatial_service.py
Service layer coordinating geospatial validation, database spatial queries,
geographic exposure calculations, and disaster-specific risk assessments.
"""

import logging
from typing import Any, List, Optional
from uuid import UUID
from fastapi.params import Depends as DependsType
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.core.exceptions import IncidentNotFoundError
from app.geospatial.context import GeographicContextCatalog, default_context_catalog
from app.geospatial.coordinates import (
    get_utm_epsg_for_coordinate,
    validate_coordinates,
)
from app.geospatial.exceptions import (
    InvalidCoordinateError,
    PostGISUnavailableError,
)
from app.geospatial.exposure import ExposureEngine
from app.geospatial.persistent_context import PersistentGeospatialContextService
from app.geospatial.risk import get_risk_assessor
from app.geospatial.schemas import (
    CoordinateValidationRequest,
    CoordinateValidationResponse,
    ExposureAnalysisRequest,
    FeatureCategory,
    GeographicFeatureItem,
    GeospatialAssessmentResponse,
    NearbyFeaturesQuery,
)
from app.geospatial.spatial_queries import (
    check_postgis_availability,
    query_nearby_incidents_postgis,
    validate_query_radius,
)

logger = logging.getLogger(__name__)


def _is_usable_session(db: Optional[Any]) -> bool:
    """
    Checks if db is a valid active database session.
    Guards against unresolved FastAPI Depends(get_db) default parameter objects
    when endpoints are called directly in unit tests without dependency injection.
    """
    if db is None:
        return False
    if isinstance(db, DependsType):
        return False
    return True


class GeospatialService:
    """
    Business logic layer for spatial operations across SCOUT.
    Decouples database operations and API controllers from domain calculation logic.
    """

    def __init__(self, catalog: Optional[GeographicContextCatalog] = None):
        self.catalog = catalog or default_context_catalog
        self.exposure_engine = ExposureEngine(self.catalog)

    def validate_coordinate(self, request: CoordinateValidationRequest) -> CoordinateValidationResponse:
        """Validates coordinates and resolves corresponding UTM projection zone."""
        try:
            coord = validate_coordinates(request.latitude, request.longitude)
            utm_zone = get_utm_epsg_for_coordinate(coord.latitude, coord.longitude)
            return CoordinateValidationResponse(
                is_valid=True,
                latitude=coord.latitude,
                longitude=coord.longitude,
                srid=coord.srid,
                utm_epsg=utm_zone,
                error_message=None,
            )
        except InvalidCoordinateError as e:
            return CoordinateValidationResponse(
                is_valid=False,
                latitude=request.latitude,
                longitude=request.longitude,
                srid=4326,
                utm_epsg=None,
                error_message=str(e),
            )

    def query_nearby_features(
        self,
        query: NearbyFeaturesQuery,
        db: Optional[Session] = None,
    ) -> List[GeographicFeatureItem]:
        """Queries geographic entities in the vicinity of coordinates."""
        if _is_usable_session(db):
            try:
                persistent_service = PersistentGeospatialContextService(db)
                return persistent_service.query_nearby(
                    latitude=query.latitude,
                    longitude=query.longitude,
                    radius_meters=query.radius_meters,
                    categories=query.categories,
                    limit=query.limit,
                    include_geometry=query.include_geometry,
                )
            except Exception as exc:
                logger.error(f"Persistent geospatial query failed: {exc}")
                raise PostGISUnavailableError(f"Persistent spatial database query failed: {exc}") from exc

        return self.catalog.query_nearby_features(
            latitude=query.latitude,
            longitude=query.longitude,
            radius_meters=query.radius_meters,
            categories=query.categories,
            limit=query.limit,
            include_geometry=query.include_geometry,
        )

    def analyze_exposure(
        self,
        request: ExposureAnalysisRequest,
        db: Optional[Session] = None,
    ) -> GeospatialAssessmentResponse:
        """
        Executes a comprehensive exposure assessment.
        Supports either an existing registered incident UUID or explicit coordinates.
        Uses persistent PostGIS features when a database session is provided,
        or the local in-memory catalog when db is None.
        """
        lat: float
        lon: float
        disaster_type: str = request.disaster_type or "wildfire"
        incident_uuid: Optional[UUID] = request.incident_id

        # 1. Resolve coordinates from incident if requested
        if incident_uuid is not None:
            if not _is_usable_session(db):
                raise PostGISUnavailableError("Database session required to analyze an incident by ID.")
            
            # Fetch incident coordinates
            sql = text("""
                SELECT 
                    id, 
                    title, 
                    disaster_type, 
                    ST_Y(location::geometry) as latitude, 
                    ST_X(location::geometry) as longitude 
                FROM incidents 
                WHERE id = :id AND is_archived = false
            """)
            row = db.execute(sql, {"id": str(incident_uuid)}).mappings().first()
            if not row:
                raise IncidentNotFoundError(incident_uuid)
            
            lat = float(row["latitude"])
            lon = float(row["longitude"])
            disaster_type = row["disaster_type"]
        else:
            if request.latitude is None or request.longitude is None:
                raise InvalidCoordinateError(
                    "Either 'incident_id' or both 'latitude' and 'longitude' must be provided."
                )
            lat = request.latitude
            lon = request.longitude

        coord = validate_coordinates(lat, lon)
        radius_m = validate_query_radius(request.search_radius_meters)

        # 2. Retrieve features and compute exposure summary
        features: List[GeographicFeatureItem] = []
        exposure_summary: Optional[ExposureSummary] = None
        contributing_factors_override: Optional[List[str]] = None
        missing_indicators_override: Optional[List[str]] = None
        data_provider: str

        if _is_usable_session(db):
            try:
                persistent_service = PersistentGeospatialContextService(db)
                (
                    exposure_summary,
                    features,
                    contributing_factors_override,
                    missing_indicators_override,
                ) = persistent_service.analyze_exposure(
                    latitude=coord.latitude,
                    longitude=coord.longitude,
                    radius_meters=radius_m,
                    disaster_type=disaster_type,
                    include_geometry=request.include_geometry,
                )
                data_provider = "postgis_spatial_db"
            except Exception as exc:
                logger.error(f"Persistent exposure analysis failed: {exc}")
                raise PostGISUnavailableError(f"Persistent spatial database query failed: {exc}") from exc
        else:
            features = self.catalog.query_nearby_features(
                latitude=coord.latitude,
                longitude=coord.longitude,
                radius_meters=radius_m,
                limit=100,
                include_geometry=request.include_geometry,
            )
            exposure_summary = self.exposure_engine.analyze_exposure(
                latitude=coord.latitude,
                longitude=coord.longitude,
                search_radius_meters=radius_m,
                limit=100,
                include_geometry=request.include_geometry,
            )
            data_provider = "local_vector_catalog"

        # 3. Evaluate risk through disaster-specific assessor
        assessor = get_risk_assessor(disaster_type)
        assessment = assessor.evaluate(
            latitude=coord.latitude,
            longitude=coord.longitude,
            search_radius_meters=radius_m,
            features=features,
            exposure_summary=exposure_summary,
            catalog=self.catalog,
            incident_id=incident_uuid,
            data_provider=data_provider,
        )

        if contributing_factors_override:
            merged_factors = list(assessment.contributing_factors)
            for factor in contributing_factors_override:
                if factor not in merged_factors:
                    merged_factors.append(factor)
            assessment.contributing_factors = merged_factors

        if missing_indicators_override is not None:
            assessment.missing_data_indicators = missing_indicators_override

        return assessment

    def query_nearby_incidents(
        self,
        db: Session,
        latitude: float,
        longitude: float,
        radius_meters: float,
        limit: int = 50,
        exclude_incident_id: Optional[UUID] = None,
    ) -> List[dict]:
        """Queries nearby disaster incidents using PostGIS."""
        if not check_postgis_availability(db):
            raise PostGISUnavailableError("PostGIS is unavailable for querying nearby incidents.")
        return query_nearby_incidents_postgis(
            db=db,
            latitude=latitude,
            longitude=longitude,
            radius_meters=radius_meters,
            limit=limit,
            exclude_incident_id=str(exclude_incident_id) if exclude_incident_id else None,
        )

    def correlate_incident_environmental_exposure(
        self,
        latitude: float,
        longitude: float,
        wind_direction_degrees: Optional[float] = None,
        wind_speed_mps: Optional[float] = None,
        search_radius_meters: float = 5000.0,
        db: Optional[Session] = None,
    ) -> dict:
        """
        Correlates atmospheric wind vectors with M08/M10 exposed assets downwind.
        Assets located in the downwind cone (+/- 45 degrees from downwind bearing)
        face elevated wildfire spread or pollutant dispersion exposure.
        """
        import math

        nearby_features: List[GeographicFeatureItem] = []
        if _is_usable_session(db):
            try:
                persistent_service = PersistentGeospatialContextService(db)
                nearby_features = persistent_service.query_nearby(
                    latitude=latitude,
                    longitude=longitude,
                    radius_meters=search_radius_meters,
                    limit=100,
                    include_geometry=False,
                )
            except Exception as exc:
                logger.error(
                    f"Persistent geospatial query failed in correlate_incident_environmental_exposure: {exc}"
                )
                raise PostGISUnavailableError(f"Persistent spatial database query failed: {exc}") from exc
        else:
            nearby_features = self.catalog.query_nearby_features(
                latitude=latitude,
                longitude=longitude,
                radius_meters=search_radius_meters,
                limit=100,
                include_geometry=False,
            )

        downwind_bearing: Optional[float] = None
        if wind_direction_degrees is not None:
            # Wind direction is where wind blows from; downwind is opposite (+180 deg)
            downwind_bearing = (wind_direction_degrees + 180.0) % 360.0

        downwind_features = []
        crosswind_or_upwind_features = []

        lat1_rad = math.radians(latitude)
        lon1_rad = math.radians(longitude)

        for feat in nearby_features:
            if downwind_bearing is None:
                crosswind_or_upwind_features.append(feat)
                continue

            feat_lat = feat.latitude
            feat_lon = feat.longitude
            if feat_lat is None or feat_lon is None:
                crosswind_or_upwind_features.append(feat)
                continue

            # Compute forward azimuth to feature
            lat2_rad = math.radians(feat_lat)
            lon2_rad = math.radians(feat_lon)
            dlon = lon2_rad - lon1_rad

            y = math.sin(dlon) * math.cos(lat2_rad)
            x = math.cos(lat1_rad) * math.sin(lat2_rad) - math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(dlon)
            bearing_deg = (math.degrees(math.atan2(y, x)) + 360.0) % 360.0

            # Angular difference to downwind vector
            ang_diff = abs((bearing_deg - downwind_bearing + 180.0) % 360.0 - 180.0)
            if ang_diff <= 45.0:
                downwind_features.append(feat)
            else:
                crosswind_or_upwind_features.append(feat)

        return {
            "origin": {"latitude": latitude, "longitude": longitude},
            "wind_speed_mps": wind_speed_mps,
            "wind_direction_degrees": wind_direction_degrees,
            "downwind_bearing_degrees": downwind_bearing,
            "search_radius_meters": search_radius_meters,
            "total_features_nearby": len(nearby_features),
            "downwind_features_count": len(downwind_features),
            "downwind_features": downwind_features,
            "elevated_risk": len(downwind_features) > 0 and (wind_speed_mps or 0.0) > 5.0,
        }
