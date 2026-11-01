"""
backend/app/geospatial/__init__.py
Public exports for the SCOUT Geospatial Intelligence package.
"""

from app.geospatial.coordinates import (
    Coordinate,
    geodesic_distance_meters,
    get_utm_epsg_for_coordinate,
    haversine_distance_meters,
    transform_coordinates,
    validate_coordinates,
)
from app.geospatial.geometry import (
    calculate_polygon_area_hectares,
    compute_geodesic_distance_to_geometry,
    create_metric_buffer_polygon,
    create_point,
    create_polygon_from_coordinates,
    geojson_dict_to_geometry,
    geometry_to_geojson_dict,
    geometry_to_wkt,
    wkt_to_geometry,
)
from app.geospatial.context import (
    GeographicContextCatalog,
    default_context_catalog,
)
from app.geospatial.exposure import ExposureEngine
from app.geospatial.risk import (
    BaseRiskAssessor,
    EarthquakeRiskAssessor,
    FloodRiskAssessor,
    WildfireRiskAssessor,
    get_risk_assessor,
)
from app.geospatial.schemas import (
    CoordinateValidationRequest,
    CoordinateValidationResponse,
    ExposureAnalysisRequest,
    ExposureSummary,
    FeatureCategory,
    GeographicFeatureItem,
    GeospatialAssessmentResponse,
    GeospatialHealthResponse,
    NearbyFeaturesQuery,
    SpatialRelationship,
)
from app.geospatial.exceptions import (
    CoordinateTransformationError,
    GeospatialDataUnavailableError,
    GeospatialError,
    InvalidCoordinateError,
    InvalidGeometryError,
    PostGISUnavailableError,
    RadiusOutOfBoundsError,
    SpatialQueryError,
)

__all__ = [
    # Coordinates
    "Coordinate",
    "validate_coordinates",
    "haversine_distance_meters",
    "geodesic_distance_meters",
    "get_utm_epsg_for_coordinate",
    "transform_coordinates",
    # Geometry
    "create_point",
    "create_polygon_from_coordinates",
    "create_metric_buffer_polygon",
    "calculate_polygon_area_hectares",
    "geometry_to_geojson_dict",
    "geojson_dict_to_geometry",
    "geometry_to_wkt",
    "wkt_to_geometry",
    "compute_geodesic_distance_to_geometry",
    # Context & Exposure
    "GeographicContextCatalog",
    "default_context_catalog",
    "ExposureEngine",
    # Risk
    "BaseRiskAssessor",
    "WildfireRiskAssessor",
    "FloodRiskAssessor",
    "EarthquakeRiskAssessor",
    "get_risk_assessor",
    # Schemas
    "CoordinateValidationRequest",
    "CoordinateValidationResponse",
    "NearbyFeaturesQuery",
    "ExposureAnalysisRequest",
    "ExposureSummary",
    "GeospatialAssessmentResponse",
    "GeospatialHealthResponse",
    "GeographicFeatureItem",
    "FeatureCategory",
    "SpatialRelationship",
    # Exceptions
    "GeospatialError",
    "InvalidCoordinateError",
    "InvalidGeometryError",
    "CoordinateTransformationError",
    "RadiusOutOfBoundsError",
    "SpatialQueryError",
    "GeospatialDataUnavailableError",
    "PostGISUnavailableError",
]
