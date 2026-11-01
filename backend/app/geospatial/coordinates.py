"""
backend/app/geospatial/coordinates.py
Coordinate management, validation, reference systems, and distance calculations.
"""

import math
from typing import NamedTuple, Optional, Tuple, Union

try:
    import pyproj
    HAS_PYPROJ = True
except ImportError:
    pyproj = None
    HAS_PYPROJ = False

from app.geospatial.exceptions import (
    CoordinateTransformationError,
    InvalidCoordinateError,
)

# Constants
WGS84_SRID = 4326
WEB_MERCATOR_SRID = 3857
EARTH_RADIUS_METERS_WGS84_EQUATORIAL = 6378137.0
EARTH_RADIUS_METERS_WGS84_POLAR = 6356752.3142
WGS84_FLATTENING = 1.0 / 298.257223563


class Coordinate(NamedTuple):
    """
    Immutable representation of a geographic coordinate point on WGS 84 (EPSG:4326).
    """
    latitude: float
    longitude: float
    srid: int = WGS84_SRID

    def to_tuple_lat_lon(self) -> Tuple[float, float]:
        """Returns (latitude, longitude)."""
        return self.latitude, self.longitude

    def to_tuple_lon_lat(self) -> Tuple[float, float]:
        """Returns (longitude, latitude), conforming to GeoJSON / GIS standard axis order."""
        return self.longitude, self.latitude

    def to_dict(self) -> dict:
        return {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "srid": self.srid,
        }


def validate_coordinates(
    latitude: Union[float, int],
    longitude: Union[float, int],
) -> Coordinate:
    """
    Validates latitude and longitude values against physical Earth boundaries and data types.

    Requirements:
    1. Rejects None, non-numeric, NaN, and +/- infinite values.
    2. Enforces latitude in [-90.0, 90.0].
    3. Enforces longitude in [-180.0, 180.0].
    4. Returns a typed immutable Coordinate(latitude, longitude, srid=4326).

    Raises:
        InvalidCoordinateError: If validation fails.
    """
    # Type checking
    if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
        raise InvalidCoordinateError(
            message=f"Coordinates must be numeric, got lat={type(latitude).__name__}, lon={type(longitude).__name__}",
        )

    lat_val = float(latitude)
    lon_val = float(longitude)

    # Reject non-finite values (NaN, +inf, -inf)
    if not math.isfinite(lat_val):
        raise InvalidCoordinateError(
            message=f"Latitude must be a finite number, got {latitude}",
            latitude=lat_val,
            longitude=lon_val if math.isfinite(lon_val) else None,
        )

    if not math.isfinite(lon_val):
        raise InvalidCoordinateError(
            message=f"Longitude must be a finite number, got {longitude}",
            latitude=lat_val,
            longitude=lon_val,
        )

    # Physical latitude bounds [-90, +90]
    if lat_val < -90.0 or lat_val > 90.0:
        raise InvalidCoordinateError(
            message=f"Latitude {lat_val} is out of bounds. Must be within [-90.0, 90.0].",
            latitude=lat_val,
            longitude=lon_val,
        )

    # Physical longitude bounds [-180, +180]
    if lon_val < -180.0 or lon_val > 180.0:
        raise InvalidCoordinateError(
            message=f"Longitude {lon_val} is out of bounds. Must be within [-180.0, 180.0].",
            latitude=lat_val,
            longitude=lon_val,
        )

    return Coordinate(latitude=lat_val, longitude=lon_val, srid=WGS84_SRID)


def haversine_distance_meters(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """
    Calculates great-circle distance between two WGS 84 points using the Haversine formula.
    Accurate to within ~0.5% globally. Suitable for fast distance thresholding and sorting.

    Args:
        lat1, lon1: Coordinates of first point in decimal degrees.
        lat2, lon2: Coordinates of second point in decimal degrees.

    Returns:
        Distance in meters.
    """
    # Short-circuit identical points
    if lat1 == lat2 and lon1 == lon2:
        return 0.0

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    # Clamp 'a' to [0, 1] to guard against floating-point precision anomalies
    a = min(1.0, max(0.0, a))
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

    # Mean Earth radius (IUGG spherical radius)
    r_mean = 6371008.8
    return r_mean * c


def geodesic_distance_meters(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """
    Calculates exact geodesic distance along the WGS 84 ellipsoid surface.
    Uses Karney's algorithms via PyProj Geod when available, with graceful
    fallback to spherical Haversine if PyProj is uninstalled.

    Returns:
        Distance in meters along the ellipsoid.
    """
    if lat1 == lat2 and lon1 == lon2:
        return 0.0

    if HAS_PYPROJ:
        try:
            geod = pyproj.Geod(ellps="WGS84")
            # geod.inv accepts (lon1, lat1, lon2, lat2)
            _, _, distance_m = geod.inv(lon1, lat1, lon2, lat2)
            return float(abs(distance_m))
        except Exception:
            # Fallback if PyProj throws internal exception
            pass

    return haversine_distance_meters(lat1, lon1, lat2, lon2)


def get_utm_epsg_for_coordinate(latitude: float, longitude: float) -> int:
    """
    Determines the appropriate Universal Transverse Mercator (UTM) EPSG code
    for a given WGS 84 coordinate.
    
    Formula:
        Zone = int((longitude + 180) / 6) + 1
        Northern Hemisphere: EPSG: 32600 + Zone
        Southern Hemisphere: EPSG: 32700 + Zone
    """
    zone = int((longitude + 180.0) / 6.0) + 1
    zone = max(1, min(60, zone))
    if latitude >= 0.0:
        return 32600 + zone
    return 32700 + zone


def transform_coordinates(
    x: float,
    y: float,
    source_crs: Union[str, int] = "EPSG:4326",
    target_crs: Union[str, int] = "EPSG:3857",
) -> Tuple[float, float]:
    """
    Transforms a coordinate pair between reference coordinate systems using PyProj.
    Uses always_xy=True to guarantee (x, y) = (longitude, latitude) convention for EPSG:4326.

    Args:
        x: First coordinate (longitude in EPSG:4326, easting in projected CRS).
        y: Second coordinate (latitude in EPSG:4326, northing in projected CRS).
        source_crs: Authority string or integer EPSG code of source.
        target_crs: Authority string or integer EPSG code of target.

    Returns:
        Transformed (target_x, target_y).

    Raises:
        CoordinateTransformationError: If transformation fails.
    """
    src_str = f"EPSG:{source_crs}" if isinstance(source_crs, int) else str(source_crs)
    tgt_str = f"EPSG:{target_crs}" if isinstance(target_crs, int) else str(target_crs)

    if src_str == tgt_str:
        return x, y

    if not HAS_PYPROJ:
        raise CoordinateTransformationError(
            message="PyProj is required for coordinate transformations.",
            source_crs=src_str,
            target_crs=tgt_str,
        )

    try:
        transformer = pyproj.Transformer.from_crs(src_str, tgt_str, always_xy=True)
        tx, ty = transformer.transform(x, y)
        if not (math.isfinite(tx) and math.isfinite(ty)):
            raise ValueError(f"Projected coordinates are non-finite: ({tx}, {ty})")
        return float(tx), float(ty)
    except Exception as e:
        raise CoordinateTransformationError(
            message=f"Failed to transform coordinates from {src_str} to {tgt_str}: {e}",
            source_crs=src_str,
            target_crs=tgt_str,
            details={"original_error": str(e)},
        )
