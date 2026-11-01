"""
backend/tests/unit/geospatial/test_coordinates.py
Unit tests for coordinate validation, geodesic distances, and CRS transformations.
"""

import math
import pytest

from app.geospatial.coordinates import (
    Coordinate,
    geodesic_distance_meters,
    get_utm_epsg_for_coordinate,
    haversine_distance_meters,
    transform_coordinates,
    validate_coordinates,
)
from app.geospatial.exceptions import (
    CoordinateTransformationError,
    InvalidCoordinateError,
)


class TestCoordinateValidation:
    """Tests for physical boundary validation and type safety."""

    def test_valid_standard_coordinates(self):
        coord = validate_coordinates(37.7749, -122.4194)
        assert isinstance(coord, Coordinate)
        assert coord.latitude == 37.7749
        assert coord.longitude == -122.4194
        assert coord.srid == 4326

    def test_boundary_coordinates(self):
        # Exact boundaries
        c_north = validate_coordinates(90.0, 0.0)
        assert c_north.latitude == 90.0

        c_south = validate_coordinates(-90.0, 0.0)
        assert c_south.latitude == -90.0

        c_east = validate_coordinates(0.0, 180.0)
        assert c_east.longitude == 180.0

        c_west = validate_coordinates(0.0, -180.0)
        assert c_west.longitude == -180.0

        c_equator = validate_coordinates(0.0, 0.0)
        assert c_equator.latitude == 0.0
        assert c_equator.longitude == 0.0

    def test_out_of_bounds_latitude_rejected(self):
        with pytest.raises(InvalidCoordinateError) as exc_info:
            validate_coordinates(90.0001, 10.0)
        assert "Latitude 90.0001 is out of bounds" in str(exc_info.value)

        with pytest.raises(InvalidCoordinateError) as exc_info:
            validate_coordinates(-91.0, 10.0)
        assert "Latitude -91.0 is out of bounds" in str(exc_info.value)

    def test_out_of_bounds_longitude_rejected(self):
        with pytest.raises(InvalidCoordinateError) as exc_info:
            validate_coordinates(10.0, 180.0001)
        assert "Longitude 180.0001 is out of bounds" in str(exc_info.value)

        with pytest.raises(InvalidCoordinateError) as exc_info:
            validate_coordinates(10.0, -185.0)
        assert "Longitude -185.0 is out of bounds" in str(exc_info.value)

    def test_non_finite_nan_and_inf_rejected(self):
        with pytest.raises(InvalidCoordinateError):
            validate_coordinates(float("nan"), 10.0)

        with pytest.raises(InvalidCoordinateError):
            validate_coordinates(10.0, float("nan"))

        with pytest.raises(InvalidCoordinateError):
            validate_coordinates(float("inf"), 10.0)

        with pytest.raises(InvalidCoordinateError):
            validate_coordinates(10.0, float("-inf"))

    def test_non_numeric_types_rejected(self):
        with pytest.raises(InvalidCoordinateError):
            validate_coordinates("37.77", -122.41)  # type: ignore

        with pytest.raises(InvalidCoordinateError):
            validate_coordinates(None, -122.41)  # type: ignore

    def test_coordinate_tuple_conversions(self):
        coord = validate_coordinates(45.5, -73.5)
        assert coord.to_tuple_lat_lon() == (45.5, -73.5)
        assert coord.to_tuple_lon_lat() == (-73.5, 45.5)
        assert coord.to_dict() == {"latitude": 45.5, "longitude": -73.5, "srid": 4326}


class TestDistanceCalculations:
    """Tests for Haversine and geodesic ellipsoidal distance calculations."""

    def test_identical_points_return_zero(self):
        d_hav = haversine_distance_meters(37.7749, -122.4194, 37.7749, -122.4194)
        assert d_hav == 0.0

        d_geo = geodesic_distance_meters(37.7749, -122.4194, 37.7749, -122.4194)
        assert d_geo == 0.0

    def test_known_london_to_paris_distance(self):
        # London (51.5074, -0.1278) to Paris (48.8566, 2.3522)
        # Expected great circle distance: ~343 to 344 km
        d_hav = haversine_distance_meters(51.5074, -0.1278, 48.8566, 2.3522)
        d_geo = geodesic_distance_meters(51.5074, -0.1278, 48.8566, 2.3522)

        assert 340000.0 < d_hav < 346000.0
        assert 340000.0 < d_geo < 346000.0
        # Haversine and WGS84 geodesic should agree within 0.5%
        assert abs(d_hav - d_geo) / d_geo < 0.005

    def test_equatorial_degree_distance(self):
        # 1 degree of longitude at the equator is ~111.32 km
        d = geodesic_distance_meters(0.0, 0.0, 0.0, 1.0)
        assert 111000.0 < d < 112000.0


class TestUTMAndTransformations:
    """Tests for UTM zone determination and PyProj transformations."""

    def test_utm_zone_determination(self):
        # San Francisco: lon -122.4 -> zone 10 North (32610)
        assert get_utm_epsg_for_coordinate(37.7749, -122.4194) == 32610

        # Sydney, Australia: lat -33.86, lon 151.2 -> zone 56 South (32756)
        assert get_utm_epsg_for_coordinate(-33.8688, 151.2093) == 32756

        # Tokyo, Japan: lat 35.67, lon 139.65 -> zone 54 North (32654)
        assert get_utm_epsg_for_coordinate(35.6762, 139.6503) == 32654

        # Prime meridian: lon 0.0 -> zone 31 North (32631)
        assert get_utm_epsg_for_coordinate(51.4769, 0.0) == 32631

    def test_coordinate_transformation_wgs84_to_web_mercator(self):
        # (0, 0) in WGS84 should transform to (0, 0) in Web Mercator EPSG:3857
        x, y = transform_coordinates(0.0, 0.0, source_crs="EPSG:4326", target_crs="EPSG:3857")
        assert abs(x) < 1e-6
        assert abs(y) < 1e-6

    def test_coordinate_transformation_wgs84_to_utm(self):
        # Transform San Francisco to UTM Zone 10N
        x, y = transform_coordinates(-122.4194, 37.7749, source_crs=4326, target_crs=32610)
        # UTM Easting is typically around 500,000m, Northing around 4,180,000m
        assert 500000.0 < x < 600000.0
        assert 4100000.0 < y < 4200000.0

    def test_invalid_crs_raises_transformation_error(self):
        with pytest.raises(CoordinateTransformationError):
            transform_coordinates(0.0, 0.0, source_crs="EPSG:999999", target_crs="EPSG:4326")
