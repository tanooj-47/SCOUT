"""
backend/tests/unit/geospatial/test_risk_assessment.py
Unit tests for disaster-specific geographic risk assessors.
"""

import pytest
import shapely.geometry

from app.geospatial.context import GeographicContextCatalog
from app.geospatial.exposure import ExposureEngine
from app.geospatial.risk import (
    EarthquakeRiskAssessor,
    FloodRiskAssessor,
    WildfireRiskAssessor,
    get_risk_assessor,
)
from app.geospatial.schemas import FeatureCategory


@pytest.fixture
def mock_wildfire_catalog() -> GeographicContextCatalog:
    cat = GeographicContextCatalog()
    cat.add_feature(
        feature_id="set-01",
        name="Mountain Valley Village",
        category=FeatureCategory.SETTLEMENT,
        geometry=shapely.geometry.Point(-120.0, 38.0),
        source_dataset="authoritative_places",
    )
    cat.add_feature(
        feature_id="veg-01",
        name="Dense Pine Stand",
        category=FeatureCategory.VEGETATION,
        geometry=shapely.geometry.Point(-120.01, 38.01),
        source_dataset="authoritative_fuel",
    )
    cat.add_feature(
        feature_id="road-01",
        name="County Route 4",
        category=FeatureCategory.ROAD,
        geometry=shapely.geometry.Point(-120.005, 38.005),
        source_dataset="authoritative_roads",
    )
    return cat


class TestRiskAssessors:
    """Tests for disaster-specific risk assessment evaluation and explanations."""

    def test_get_risk_assessor_factory(self):
        w_assessor = get_risk_assessor("wildfire")
        assert isinstance(w_assessor, WildfireRiskAssessor)

        f_assessor = get_risk_assessor("flood")
        assert isinstance(f_assessor, FloodRiskAssessor)

        e_assessor = get_risk_assessor("earthquake")
        assert isinstance(e_assessor, EarthquakeRiskAssessor)

        # Unknown disaster type defaults safely to Wildfire
        unknown_assessor = get_risk_assessor("volcano")
        assert isinstance(unknown_assessor, WildfireRiskAssessor)

    def test_wildfire_risk_assessor_evaluation(self, mock_wildfire_catalog):
        assessor = WildfireRiskAssessor()
        engine = ExposureEngine(mock_wildfire_catalog)

        lat = 38.0
        lon = -120.0
        radius_m = 5000.0

        features = mock_wildfire_catalog.query_nearby_features(lat, lon, radius_m)
        summary = engine.analyze_exposure(lat, lon, radius_m)

        assessment = assessor.evaluate(
            latitude=lat,
            longitude=lon,
            search_radius_meters=radius_m,
            features=features,
            exposure_summary=summary,
            catalog=mock_wildfire_catalog,
        )

        assert assessment.incident_context.disaster_type == "wildfire"
        assert assessment.exposure_summary.total_features_found >= 3

        # Contributing factors must be human-readable and explainable
        factors_text = " ".join(assessment.contributing_factors)
        assert "Mountain Valley Village" in factors_text
        assert "forest/vegetation" in factors_text
        assert "roadway" in factors_text

        # Missing indicators
        assert "hydrology_and_water_body_layer_unavailable" in assessment.missing_data_indicators
        assert "critical_infrastructure_layer_unavailable" in assessment.missing_data_indicators

        # Scientific limitations must explicitly disclaim spread rate simulation
        limits_text = " ".join(assessment.assessment_limitations)
        assert "does NOT simulate wildfire rate of spread" in limits_text

    def test_flood_risk_assessor_limitations(self, mock_wildfire_catalog):
        assessor = FloodRiskAssessor()
        engine = ExposureEngine(mock_wildfire_catalog)

        lat = 38.0
        lon = -120.0
        radius_m = 2000.0

        features = mock_wildfire_catalog.query_nearby_features(lat, lon, radius_m)
        summary = engine.analyze_exposure(lat, lon, radius_m)

        assessment = assessor.evaluate(
            latitude=lat,
            longitude=lon,
            search_radius_meters=radius_m,
            features=features,
            exposure_summary=summary,
            catalog=mock_wildfire_catalog,
        )

        assert assessment.incident_context.disaster_type == "flood"
        assert "digital_elevation_model_raster_unavailable" in assessment.missing_data_indicators
        limits_text = " ".join(assessment.assessment_limitations)
        assert "Hydraulic flow modeling" in limits_text
