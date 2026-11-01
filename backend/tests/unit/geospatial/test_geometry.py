"""
backend/tests/unit/geospatial/test_geometry.py
Unit tests for geometry construction, metric buffering, area calculations, and serialization.
"""

import math
import pytest
import shapely.geometry

from app.geospatial.coordinates import geodesic_distance_meters
from app.geospatial.exceptions import InvalidGeometryError
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


class TestGeometryConstruction:
    """Tests for Shapely geometry construction and validation."""

    def test_create_point_valid(self):
        pt = create_point(37.7749, -122.4194)
        assert isinstance(pt, shapely.geometry.Point)
        # Shapely Point is (x, y) = (lon, lat)
        assert pt.x == -122.4194
        assert pt.y == 37.7749
        assert pt.is_valid
        assert not pt.is_empty

    def test_create_polygon_from_coordinates(self):
        # Triangle in San Francisco
        coords = [
            (37.77, -122.42),
            (37.78, -122.42),
            (37.78, -122.41),
        ]
        poly = create_polygon_from_coordinates(coords)
        assert isinstance(poly, shapely.geometry.Polygon)
        assert poly.is_valid
        assert not poly.is_empty
        # Verify ring was auto-closed
        assert len(poly.exterior.coords) == 4

    def test_create_polygon_too_few_coords_raises(self):
        with pytest.raises(InvalidGeometryError) as exc_info:
            create_polygon_from_coordinates([(37.7, -122.4), (37.8, -122.5)])
        assert "requires at least 3 coordinates" in str(exc_info.value)

    def test_create_polygon_with_self_intersection_repairs_via_make_valid(self):
        # Self-intersecting bowtie polygon
        coords = [
            (0.0, 0.0),
            (1.0, 1.0),
            (0.0, 1.0),
            (1.0, 0.0),
        ]
        poly = create_polygon_from_coordinates(coords)
        assert poly.is_valid


class TestMetricBufferAndArea:
    """Tests for metric UTM buffering and planar area calculation."""

    def test_metric_buffer_polygon(self):
        lat = 37.7749
        lon = -122.4194
        radius_m = 1000.0  # 1 km buffer

        poly = create_metric_buffer_polygon(lat, lon, radius_m)
        assert isinstance(poly, shapely.geometry.Polygon)
        assert poly.is_valid
        assert not poly.is_empty

        # Center point must be inside polygon
        center_pt = shapely.geometry.Point(lon, lat)
        assert poly.contains(center_pt)

        # Exterior points should all be ~1,000m from origin
        for ex_lon, ex_lat in list(poly.exterior.coords)[:8]:
            d = geodesic_distance_meters(lat, lon, ex_lat, ex_lon)
            assert 950.0 < d < 1050.0

    def test_polygon_area_hectares(self):
        # A circular buffer of radius 1,000m has area:
        # Area = pi * r^2 = pi * (1,000)^2 = 3,141,592.6 m^2 = ~314.16 hectares
        poly = create_metric_buffer_polygon(37.7749, -122.4194, 1000.0)
        area_ha = calculate_polygon_area_hectares(poly)
        assert 310.0 < area_ha < 318.0

    def test_invalid_buffer_radius_raises(self):
        with pytest.raises(InvalidGeometryError):
            create_metric_buffer_polygon(37.7749, -122.4194, -50.0)


class TestSerialization:
    """Tests for WKT and GeoJSON serialization and deserialization."""

    def test_wkt_roundtrip(self):
        pt = create_point(34.0522, -118.2437)
        wkt = geometry_to_wkt(pt)
        assert "POINT (-118.2437 34.0522)" in wkt

        geom = wkt_to_geometry(wkt)
        assert isinstance(geom, shapely.geometry.Point)
        assert abs(geom.x - (-118.2437)) < 1e-6
        assert abs(geom.y - 34.0522) < 1e-6

    def test_geojson_roundtrip(self):
        poly = create_polygon_from_coordinates([
            (10.0, 10.0),
            (10.0, 11.0),
            (11.0, 11.0),
            (11.0, 10.0),
        ])
        g_dict = geometry_to_geojson_dict(poly)
        assert g_dict["type"] == "Polygon"
        assert len(g_dict["coordinates"][0]) >= 4

        restored_geom = geojson_dict_to_geometry(g_dict)
        assert isinstance(restored_geom, shapely.geometry.Polygon)
        assert restored_geom.is_valid

    def test_distance_to_polygon_geometry(self):
        # Target polygon: box from lon 0 to 1, lat 0 to 1
        poly = create_polygon_from_coordinates([
            (0.0, 0.0),
            (0.0, 1.0),
            (1.0, 1.0),
            (1.0, 0.0),
        ])
        # Origin inside polygon: distance must be 0.0
        assert compute_geodesic_distance_to_geometry(0.5, 0.5, poly) == 0.0

        # Origin outside polygon: 1 degree North (lat 2.0, lon 0.5)
        # Distance to border (lat 1.0, lon 0.5) is ~111 km
        d_out = compute_geodesic_distance_to_geometry(2.0, 0.5, poly)
        assert 110000.0 < d_out < 112000.0
