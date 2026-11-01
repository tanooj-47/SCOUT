"""
backend/app/geospatial/exceptions.py
Domain exceptions for the SCOUT Geospatial Intelligence Engine.
Integrates with SCOUTException for uniform JSON error responses.
"""

from typing import Any, Dict, Optional
from app.core.exceptions import SCOUTException


class GeospatialError(SCOUTException):
    """Base exception for all geospatial domain errors."""

    def __init__(
        self,
        code: str = "GEOSPATIAL_ERROR",
        message: str = "A geospatial processing error occurred.",
        status_code: int = 400,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            code=code,
            message=message,
            status_code=status_code,
            details=details or {},
        )


class InvalidCoordinateError(GeospatialError):
    """Raised when coordinates fail physical bounds, format, or finiteness checks."""

    def __init__(
        self,
        message: str,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        det = details or {}
        if latitude is not None:
            det["latitude"] = latitude
        if longitude is not None:
            det["longitude"] = longitude
        super().__init__(
            code="INVALID_COORDINATES",
            message=message,
            status_code=422,
            details=det,
        )


class InvalidGeometryError(GeospatialError):
    """Raised when geometry is malformed, self-intersecting, or of an unsupported type."""

    def __init__(
        self,
        message: str,
        geometry_type: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        det = details or {}
        if geometry_type:
            det["geometry_type"] = geometry_type
        super().__init__(
            code="INVALID_GEOMETRY",
            message=message,
            status_code=422,
            details=det,
        )


class CoordinateTransformationError(GeospatialError):
    """Raised when projecting coordinates between reference systems fails."""

    def __init__(
        self,
        message: str,
        source_crs: str,
        target_crs: str,
        details: Optional[Dict[str, Any]] = None,
    ):
        det = details or {}
        det["source_crs"] = source_crs
        det["target_crs"] = target_crs
        super().__init__(
            code="COORDINATE_TRANSFORMATION_ERROR",
            message=message,
            status_code=400,
            details=det,
        )


class RadiusOutOfBoundsError(GeospatialError):
    """Raised when a spatial query radius falls outside allowable operational limits."""

    def __init__(
        self,
        radius_meters: float,
        min_allowed: float,
        max_allowed: float,
    ):
        super().__init__(
            code="RADIUS_OUT_OF_BOUNDS",
            message=(
                f"Requested search radius {radius_meters}m is out of bounds. "
                f"Allowable range is [{min_allowed}m, {max_allowed}m]."
            ),
            status_code=422,
            details={
                "radius_meters": radius_meters,
                "min_allowed_meters": min_allowed,
                "max_allowed_meters": max_allowed,
            },
        )


class SpatialQueryError(GeospatialError):
    """Raised when a spatial query execution fails."""

    def __init__(
        self,
        message: str,
        query_type: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        det = details or {}
        if query_type:
            det["query_type"] = query_type
        super().__init__(
            code="SPATIAL_QUERY_ERROR",
            message=message,
            status_code=500,
            details=det,
        )


class GeospatialDataUnavailableError(GeospatialError):
    """Raised when requested geographic data layer or layer feature is unavailable."""

    def __init__(
        self,
        layer_name: str,
        message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        msg = message or f"Geographic data for layer '{layer_name}' is currently unavailable."
        det = details or {}
        det["layer_name"] = layer_name
        super().__init__(
            code="GEOSPATIAL_DATA_UNAVAILABLE",
            message=msg,
            status_code=503,
            details=det,
        )


class PostGISUnavailableError(GeospatialError):
    """Raised when a database spatial query is attempted but PostGIS is disconnected."""

    def __init__(
        self,
        message: str = "PostGIS database infrastructure is currently disconnected or unavailable.",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            code="POSTGIS_UNAVAILABLE",
            message=message,
            status_code=503,
            details=details or {},
        )
