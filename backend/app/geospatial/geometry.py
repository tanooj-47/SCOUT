"""
backend/app/geospatial/geometry.py
Geometry construction, topological operations, validation, metric buffering, and serialization.
Powered by Shapely and PyProj.
"""

import math
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    import shapely
    import shapely.geometry
    import shapely.ops
    import shapely.validation
    import shapely.wkt
    HAS_SHAPELY = True
except ImportError:
    shapely = None
    HAS_SHAPELY = False

from app.geospatial.coordinates import (
    WGS84_SRID,
    get_utm_epsg_for_coordinate,
    geodesic_distance_meters,
    haversine_distance_meters,
    transform_coordinates,
    validate_coordinates,
)
from app.geospatial.exceptions import InvalidGeometryError


def ensure_shapely():
    """Guarantees Shapely is available."""
    if not HAS_SHAPELY:
        raise InvalidGeometryError("Shapely is required for geometry operations but is not installed.")


def create_point(latitude: float, longitude: float) -> "shapely.geometry.Point":
    """
    Constructs a validated Shapely Point geometry in WGS 84.
    Follows GeoJSON / GIS standard axis convention: Point(x=longitude, y=latitude).
    """
    ensure_shapely()
    coord = validate_coordinates(latitude, longitude)
    point = shapely.geometry.Point(coord.longitude, coord.latitude)
    if point.is_empty:
        raise InvalidGeometryError("Constructed point is empty.")
    return point


def create_polygon_from_coordinates(
    coordinates: List[Tuple[float, float]],
) -> "shapely.geometry.Polygon":
    """
    Constructs a validated Shapely Polygon from a list of (latitude, longitude) tuples.
    Automatically closes the linear ring if the first and last vertices differ.
    Validates topology and repairs self-intersections via make_valid if needed.

    Args:
        coordinates: List of (lat, lon) vertices. Minimum 3 distinct vertices.

    Returns:
        Valid Shapely Polygon (with vertices ordered as (lon, lat)).
    """
    ensure_shapely()
    if len(coordinates) < 3:
        raise InvalidGeometryError(
            message=f"Polygon requires at least 3 coordinates, got {len(coordinates)}.",
            geometry_type="Polygon",
        )

    # Validate each coordinate and convert to (lon, lat)
    lon_lat_coords = []
    for i, c in enumerate(coordinates):
        if len(c) != 2:
            raise InvalidGeometryError(
                message=f"Coordinate at index {i} must be a (lat, lon) pair, got {c}",
                geometry_type="Polygon",
            )
        coord = validate_coordinates(c[0], c[1])
        lon_lat_coords.append((coord.longitude, coord.latitude))

    # Close the ring if not already closed
    if lon_lat_coords[0] != lon_lat_coords[-1]:
        lon_lat_coords.append(lon_lat_coords[0])

    try:
        poly = shapely.geometry.Polygon(lon_lat_coords)
    except Exception as e:
        raise InvalidGeometryError(
            message=f"Failed to create Polygon: {e}",
            geometry_type="Polygon",
            details={"original_error": str(e)},
        )

    if poly.is_empty:
        raise InvalidGeometryError("Constructed Polygon is empty.", geometry_type="Polygon")

    if not poly.is_valid:
        # Repair self-intersections or bowtie rings
        poly = shapely.make_valid(poly)
        if isinstance(poly, shapely.geometry.MultiPolygon):
            # If split into multipolygon, pick the union or keep valid multipolygon
            pass

    return poly


def create_metric_buffer_polygon(
    latitude: float,
    longitude: float,
    radius_meters: float,
    num_segments: int = 64,
) -> "shapely.geometry.Polygon":
    """
    Constructs a true metric circular buffer around a WGS84 point.

    Important scientific design:
    Buffering directly in geographic degrees (e.g. point.buffer(0.01)) is invalid because
    one degree of longitude varies from ~111 km at the equator to 0 km at the poles.
    
    This function computes the local UTM projection for the coordinates, transforms the point
    to metric UTM space, performs the buffer in exact meters, and transforms the resulting
    polygon back to WGS 84.
    """
    ensure_shapely()
    coord = validate_coordinates(latitude, longitude)
    if radius_meters <= 0:
        raise InvalidGeometryError(f"Buffer radius must be strictly positive, got {radius_meters}m")

    utm_srid = get_utm_epsg_for_coordinate(coord.latitude, coord.longitude)

    # 1. Transform center point to UTM (meters)
    utm_x, utm_y = transform_coordinates(
        coord.longitude, coord.latitude, source_crs="EPSG:4326", target_crs=f"EPSG:{utm_srid}"
    )

    # 2. Buffer in exact planar metric space
    utm_point = shapely.geometry.Point(utm_x, utm_y)
    utm_poly = utm_point.buffer(radius_meters, quad_segs=num_segments // 4)

    # 3. Transform buffered polygon boundary back to WGS 84
    exterior_coords = []
    for px, py in utm_poly.exterior.coords:
        lon, lat = transform_coordinates(
            px, py, source_crs=f"EPSG:{utm_srid}", target_crs="EPSG:4326"
        )
        exterior_coords.append((lon, lat))

    return shapely.geometry.Polygon(exterior_coords)


def calculate_polygon_area_hectares(polygon: "shapely.geometry.Polygon") -> float:
    """
    Calculates the true ground surface area of a WGS 84 polygon in hectares.
    Projects the polygon into its local UTM zone to compute planar area in square meters,
    then converts to hectares (1 hectare = 10,000 square meters).

    Avoids degree-squared area calculation!
    """
    ensure_shapely()
    if polygon.is_empty:
        return 0.0

    # Determine centroid for UTM zone selection
    centroid = polygon.centroid
    utm_srid = get_utm_epsg_for_coordinate(centroid.y, centroid.x)

    # Transform exterior to UTM
    utm_exterior = [
        transform_coordinates(x, y, source_crs="EPSG:4326", target_crs=f"EPSG:{utm_srid}")
        for x, y in polygon.exterior.coords
    ]

    # Transform interiors (holes) if present
    utm_interiors = []
    for interior in polygon.interiors:
        utm_hole = [
            transform_coordinates(x, y, source_crs="EPSG:4326", target_crs=f"EPSG:{utm_srid}")
            for x, y in interior.coords
        ]
        utm_interiors.append(utm_hole)

    utm_poly = shapely.geometry.Polygon(utm_exterior, utm_interiors)
    area_sq_meters = utm_poly.area
    return float(area_sq_meters / 10000.0)


def geometry_to_geojson_dict(geom: "shapely.geometry.base.BaseGeometry") -> dict:
    """Serializes a Shapely geometry to a standard GeoJSON geometry dictionary."""
    ensure_shapely()
    if geom is None or geom.is_empty:
        return {"type": "GeometryCollection", "geometries": []}
    return shapely.geometry.mapping(geom)


def geojson_dict_to_geometry(geojson_dict: dict) -> "shapely.geometry.base.BaseGeometry":
    """Parses a GeoJSON geometry dictionary into a validated Shapely geometry."""
    ensure_shapely()
    if not isinstance(geojson_dict, dict) or "type" not in geojson_dict:
        raise InvalidGeometryError(
            message="Invalid GeoJSON geometry structure. Must be a dict with a 'type' field."
        )
    try:
        geom = shapely.geometry.shape(geojson_dict)
        if not geom.is_valid:
            geom = shapely.make_valid(geom)
        return geom
    except Exception as e:
        raise InvalidGeometryError(
            message=f"Failed to parse GeoJSON geometry: {e}",
            details={"original_error": str(e)},
        )


def geometry_to_wkt(geom: "shapely.geometry.base.BaseGeometry") -> str:
    """Serializes a Shapely geometry to Well-Known Text (WKT)."""
    ensure_shapely()
    return shapely.to_wkt(geom)


def wkt_to_geometry(wkt_string: str) -> "shapely.geometry.base.BaseGeometry":
    """Parses a WKT string into a validated Shapely geometry."""
    ensure_shapely()
    try:
        geom = shapely.from_wkt(wkt_string)
        if not geom.is_valid:
            geom = shapely.make_valid(geom)
        return geom
    except Exception as e:
        raise InvalidGeometryError(
            message=f"Failed to parse WKT string: {e}",
            details={"original_error": str(e)},
        )


def compute_geodesic_distance_to_geometry(
    origin_lat: float,
    origin_lon: float,
    target_geom: "shapely.geometry.base.BaseGeometry",
) -> float:
    """
    Computes the shortest geodesic ground distance (in meters) from a WGS84 point
    to any Shapely geometry (Point, LineString, Polygon, MultiPolygon).
    """
    ensure_shapely()
    if target_geom.is_empty:
        return float("inf")

    # If target is Point
    if isinstance(target_geom, shapely.geometry.Point):
        return geodesic_distance_meters(origin_lat, origin_lon, target_geom.y, target_geom.x)

    # Origin point as Shapely point (lon, lat)
    origin_pt = shapely.geometry.Point(origin_lon, origin_lat)

    # If origin point is inside the target polygon/multipolygon, distance is 0.0
    if target_geom.contains(origin_pt) or target_geom.intersects(origin_pt):
        return 0.0

    # Nearest point on target geometry
    nearest_target_pt = shapely.ops.nearest_points(origin_pt, target_geom)[1]
    return geodesic_distance_meters(
        origin_lat, origin_lon, nearest_target_pt.y, nearest_target_pt.x
    )
