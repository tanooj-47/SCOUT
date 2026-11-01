"""
backend/tests/unit/geospatial/test_spatial_queries.py
Unit tests for spatial query radius validation and PostGIS availability checks.
"""

import pytest

from app.geospatial.exceptions import (
    PostGISUnavailableError,
    RadiusOutOfBoundsError,
    SpatialQueryError,
)
from app.geospatial.spatial_queries import (
    MAX_QUERY_RADIUS_METERS,
    MIN_QUERY_RADIUS_METERS,
    check_postgis_availability,
    validate_query_radius,
)


class TestSpatialQueryValidation:
    """Tests for spatial query constraints and radius bounds."""

    def test_valid_query_radius(self):
        assert validate_query_radius(100.0) == 100.0
        assert validate_query_radius(5000.0) == 5000.0
        assert validate_query_radius(100000.0) == 100000.0

    def test_radius_below_minimum_rejected(self):
        with pytest.raises(RadiusOutOfBoundsError) as exc_info:
            validate_query_radius(50.0)
        assert "is out of bounds" in str(exc_info.value)
        assert exc_info.value.status_code == 422

    def test_radius_above_maximum_rejected(self):
        with pytest.raises(RadiusOutOfBoundsError) as exc_info:
            validate_query_radius(150000.0)
        assert "is out of bounds" in str(exc_info.value)
        assert exc_info.value.status_code == 422

    def test_negative_radius_rejected(self):
        with pytest.raises(RadiusOutOfBoundsError):
            validate_query_radius(-500.0)

    def test_check_postgis_availability_with_none_session(self):
        # When no active DB session is supplied, must safely return False without crashing
        assert check_postgis_availability(None) is False
