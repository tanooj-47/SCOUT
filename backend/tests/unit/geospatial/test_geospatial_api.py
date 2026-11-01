"""
backend/tests/unit/geospatial/test_geospatial_api.py
Unit tests for geospatial API endpoints and service request handling.
"""

import pytest

from app.api.v1.endpoints.geospatial import (
    analyze_exposure_endpoint,
    get_geospatial_health,
    get_nearby_features_endpoint,
    validate_coordinate_endpoint,
)
from app.geospatial.context import GeographicContextCatalog
from app.geospatial.exceptions import InvalidCoordinateError, RadiusOutOfBoundsError
from app.geospatial.schemas import (
    CoordinateValidationRequest,
    ExposureAnalysisRequest,
    FeatureCategory,
)
from app.services.geospatial_service import GeospatialService


class TestGeospatialEndpoints:
    """Unit tests for FastAPI geospatial endpoint handlers."""

    def test_health_endpoint(self):
        # When db is None, should still return HTTP 200 with degraded or operational status
        res = get_geospatial_health(db=None)
        assert res.status in ("operational", "degraded")
        assert res.postgis_connected is False
        assert "EPSG:4326 (WGS 84)" in res.supported_crs

    def test_validate_coordinate_endpoint_valid(self):
        req = CoordinateValidationRequest(latitude=37.7749, longitude=-122.4194)
        res = validate_coordinate_endpoint(req)
        assert res.is_valid is True
        assert res.latitude == 37.7749
        assert res.longitude == -122.4194
        assert res.srid == 4326
        assert res.utm_epsg == 32610
        assert res.error_message is None

    def test_validate_coordinate_endpoint_invalid_bounds(self):
        # We can construct the request with out-of-bounds latitude (within float range)
        # Note: Pydantic schema allows raw validation
        service = GeospatialService()
        req = CoordinateValidationRequest(latitude=95.0, longitude=0.0)
        res = service.validate_coordinate(req)
        assert res.is_valid is False
        assert res.utm_epsg is None
        assert "Latitude 95.0 is out of bounds" in res.error_message

    def test_get_nearby_features_endpoint(self):
        # Query nearby features from endpoint
        features = get_nearby_features_endpoint(
            latitude=37.7749,
            longitude=-122.4194,
            radius_meters=5000.0,
            categories=None,
            limit=10,
            include_geometry=False,
        )
        assert isinstance(features, list)

    def test_analyze_exposure_endpoint_explicit_coords(self):
        req = ExposureAnalysisRequest(
            latitude=37.7749,
            longitude=-122.4194,
            search_radius_meters=3000.0,
            disaster_type="wildfire",
            include_geometry=False,
        )
        assessment = analyze_exposure_endpoint(req, db=None)
        assert assessment.incident_context.disaster_type == "wildfire"
        assert assessment.incident_context.latitude == 37.7749
        assert assessment.incident_context.longitude == -122.4194
        assert len(assessment.assessment_limitations) >= 1
        assert "local_vector_catalog" in assessment.data_provider

    def test_analyze_exposure_endpoint_invalid_radius_raises(self):
        # Pydantic schema validation rejects radius below 100m
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            ExposureAnalysisRequest(
                latitude=37.7749,
                longitude=-122.4194,
                search_radius_meters=50.0,  # Below 100m minimum
                disaster_type="wildfire",
            )

    def test_analyze_exposure_missing_coords_and_incident_raises(self):
        req = ExposureAnalysisRequest(
            search_radius_meters=2000.0,
            disaster_type="wildfire",
        )
        with pytest.raises(InvalidCoordinateError):
            analyze_exposure_endpoint(req, db=None)
