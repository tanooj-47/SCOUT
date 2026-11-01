"""
backend/app/geospatial/spatial_queries.py
Spatial query operations for PostGIS database and in-memory geometric index fallback.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.geospatial.coordinates import (
    WGS84_SRID,
    geodesic_distance_meters,
    validate_coordinates,
)
from app.geospatial.exceptions import (
    PostGISUnavailableError,
    RadiusOutOfBoundsError,
    SpatialQueryError,
)

logger = logging.getLogger(__name__)

MIN_QUERY_RADIUS_METERS = 100.0       # 100 meters
MAX_QUERY_RADIUS_METERS = 100000.0    # 100 kilometers


def validate_query_radius(radius_meters: float) -> float:
    """Enforces operational limits on spatial query radius to prevent runaway scans."""
    if not isinstance(radius_meters, (int, float)):
        raise RadiusOutOfBoundsError(0.0, MIN_QUERY_RADIUS_METERS, MAX_QUERY_RADIUS_METERS)
    r = float(radius_meters)
    if r < MIN_QUERY_RADIUS_METERS or r > MAX_QUERY_RADIUS_METERS:
        raise RadiusOutOfBoundsError(r, MIN_QUERY_RADIUS_METERS, MAX_QUERY_RADIUS_METERS)
    return r


def check_postgis_availability(db: Optional[Session]) -> bool:
    """
    Probes the active database session to verify whether PostgreSQL and PostGIS
    extensions are operational and responding.
    """
    if db is None:
        return False
    try:
        result = db.execute(text("SELECT PostGIS_Version();")).scalar()
        return bool(result)
    except Exception as e:
        logger.debug(f"PostGIS availability check failed: {e}")
        return False


def query_nearby_incidents_postgis(
    db: Session,
    latitude: float,
    longitude: float,
    radius_meters: float,
    limit: int = 50,
    exclude_incident_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Executes a high-performance PostGIS spatial query using the GiST spatial index
    on the incidents table's location column.

    Uses ST_DWithin on geography types for exact ellipsoidal geodesic distance in meters:
    ST_DWithin(location::geography, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, :radius)
    """
    coord = validate_coordinates(latitude, longitude)
    radius_m = validate_query_radius(radius_meters)

    sql = """
        SELECT 
            id,
            title,
            disaster_type,
            status,
            severity,
            ST_Y(location::geometry) AS latitude,
            ST_X(location::geometry) AS longitude,
            ST_Distance(
                location::geography,
                ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography
            ) AS distance_meters
        FROM incidents
        WHERE 
            is_archived = false
            AND ST_DWithin(
                location::geography,
                ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
                :radius
            )
    """
    params: Dict[str, Any] = {
        "lon": coord.longitude,
        "lat": coord.latitude,
        "radius": radius_m,
        "limit": max(1, min(limit, 200)),
    }

    if exclude_incident_id:
        sql += " AND id != :exclude_id"
        params["exclude_id"] = str(exclude_incident_id)

    sql += " ORDER BY distance_meters ASC LIMIT :limit;"

    try:
        rows = db.execute(text(sql), params).mappings().all()
        return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"PostGIS spatial query failed: {e}")
        raise SpatialQueryError(
            message=f"PostGIS query failed: {e}",
            query_type="ST_DWithin_incidents",
            details={"original_error": str(e)},
        )
