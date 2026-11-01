"""
backend/tests/unit/geospatial/test_geospatial_service_fallback.py
Unit tests verifying rigorous database fallback semantics and geographic data provider attribution.
Covers Conditions A (DB with features), B (DB empty), C (DB failure), and D (Explicit catalog).
"""

from unittest.mock import MagicMock, patch
import pytest
from sqlalchemy.exc import OperationalError

from app.geospatial.context import GeographicContextCatalog
from app.geospatial.exceptions import PostGISUnavailableError
from app.geospatial.risk import (
    EarthquakeRiskAssessor,
    FloodRiskAssessor,
    WildfireRiskAssessor,
)
from app.geospatial.schemas import (
    ExposureAnalysisRequest,
    ExposureSummary,
    FeatureCategory,
    GeographicFeatureItem,
    NearbyFeaturesQuery,
    SpatialRelationship,
)
from app.services.geospatial_service import GeospatialService
import shapely.geometry


@pytest.fixture
def mock_catalog():
    cat = GeographicContextCatalog()
    cat.add_feature(
        feature_id="cat-infra-01",
        name="Catalog Hospital",
        category=FeatureCategory.INFRASTRUCTURE,
        geometry=shapely.geometry.Point(78.0340, 30.3204),
        source_dataset="mock_catalog_data",
    )
    return cat


@pytest.fixture
def sample_feature_item():
    return GeographicFeatureItem(
        id="feat-db-001",
        name="Database Emergency Clinic",
        category=FeatureCategory.INFRASTRUCTURE,
        distance_meters=210.5,
        relationship=SpatialRelationship.WITHIN_RADIUS,
        source_dataset="osm_critical_facilities",
        latitude=30.3200,
        longitude=78.0340,
    )


class TestGeospatialServiceFallbackSemantics:
    """Tests explicit fallback semantics across query_nearby, analyze_exposure, and correlate."""

    # --------------------------------------------------------------------------
    # analyze_exposure tests
    # --------------------------------------------------------------------------

    def test_analyze_exposure_condition_a_db_success_with_features(self, mock_catalog, sample_feature_item):
        """Case A: DB query succeeds and returns features -> data_provider='postgis_spatial_db'."""
        service = GeospatialService(catalog=mock_catalog)
        mock_db = MagicMock()

        summary = ExposureSummary(
            total_features_found=1,
            category_counts={"infrastructure": 1},
            closest_feature_distance_meters=210.5,
            closest_feature_name="Database Emergency Clinic",
            highlighted_exposed_features=[sample_feature_item],
        )

        with patch("app.services.geospatial_service.PersistentGeospatialContextService") as mock_cls:
            mock_inst = mock_cls.return_value
            mock_inst.analyze_exposure.return_value = (
                summary,
                [sample_feature_item],
                ["Detected critical infrastructure."],
                ["Missing geographic layer: hydrology"],
            )

            req = ExposureAnalysisRequest(
                latitude=30.3204,
                longitude=78.0340,
                search_radius_meters=3000.0,
                disaster_type="wildfire",
            )
            assessment = service.analyze_exposure(req, db=mock_db)

            assert assessment.data_provider == "postgis_spatial_db"
            assert assessment.exposure_summary.total_features_found == 1
            assert len(assessment.features) == 1
            assert assessment.features[0].name == "Database Emergency Clinic"
            assert "Missing geographic layer: hydrology" in assessment.missing_data_indicators

    def test_analyze_exposure_condition_b_db_success_empty_results(self, mock_catalog):
        """Case B: DB succeeds but returns zero features -> MUST NOT fall back to catalog."""
        service = GeospatialService(catalog=mock_catalog)
        mock_db = MagicMock()

        empty_summary = ExposureSummary(
            total_features_found=0,
            category_counts={},
            closest_feature_distance_meters=None,
            closest_feature_name=None,
            highlighted_exposed_features=[],
        )

        with patch("app.services.geospatial_service.PersistentGeospatialContextService") as mock_cls:
            mock_inst = mock_cls.return_value
            mock_inst.analyze_exposure.return_value = (
                empty_summary,
                [],
                ["No immediate hazard-specific exposure detected."],
                [],
            )

            req = ExposureAnalysisRequest(
                latitude=30.3204,
                longitude=78.0340,
                search_radius_meters=3000.0,
                disaster_type="wildfire",
            )
            assessment = service.analyze_exposure(req, db=mock_db)

            # Must reflect PostGIS provider and zero features, NOT catalog's 1 feature
            assert assessment.data_provider == "postgis_spatial_db"
            assert assessment.exposure_summary.total_features_found == 0
            assert len(assessment.features) == 0
            assert any("persistent spatial database" in f for f in assessment.contributing_factors)

    def test_analyze_exposure_condition_c_db_failure_raises_postgis_unavailable(self, mock_catalog):
        """Case C: DB query or connection fails -> raises PostGISUnavailableError, never swallows."""
        service = GeospatialService(catalog=mock_catalog)
        mock_db = MagicMock()

        with patch("app.services.geospatial_service.PersistentGeospatialContextService") as mock_cls:
            mock_inst = mock_cls.return_value
            mock_inst.analyze_exposure.side_effect = OperationalError("connection closed", {}, None)

            req = ExposureAnalysisRequest(
                latitude=30.3204,
                longitude=78.0340,
                search_radius_meters=3000.0,
                disaster_type="wildfire",
            )
            with pytest.raises(PostGISUnavailableError) as exc_info:
                service.analyze_exposure(req, db=mock_db)

            assert "connection closed" in str(exc_info.value)
            assert exc_info.value.status_code == 503

    def test_analyze_exposure_condition_d_db_none_uses_catalog(self, mock_catalog):
        """Case D: db=None (in-memory mode) -> queries catalog and sets data_provider='local_vector_catalog'."""
        service = GeospatialService(catalog=mock_catalog)

        req = ExposureAnalysisRequest(
            latitude=30.3204,
            longitude=78.0340,
            search_radius_meters=3000.0,
            disaster_type="wildfire",
        )
        assessment = service.analyze_exposure(req, db=None)

        assert assessment.data_provider == "local_vector_catalog"
        assert assessment.exposure_summary.total_features_found == 1
        assert assessment.features[0].name == "Catalog Hospital"

    # --------------------------------------------------------------------------
    # query_nearby_features tests
    # --------------------------------------------------------------------------

    def test_query_nearby_condition_a_db_success_with_features(self, mock_catalog, sample_feature_item):
        """Case A: DB query succeeds -> returns DB features."""
        service = GeospatialService(catalog=mock_catalog)
        mock_db = MagicMock()

        with patch("app.services.geospatial_service.PersistentGeospatialContextService") as mock_cls:
            mock_inst = mock_cls.return_value
            mock_inst.query_nearby.return_value = [sample_feature_item]

            query = NearbyFeaturesQuery(latitude=30.3204, longitude=78.0340, radius_meters=3000.0)
            res = service.query_nearby_features(query, db=mock_db)

            assert len(res) == 1
            assert res[0].name == "Database Emergency Clinic"

    def test_query_nearby_condition_b_db_success_empty_results(self, mock_catalog):
        """Case B: DB query succeeds with 0 features -> returns empty list, does not fall back to catalog."""
        service = GeospatialService(catalog=mock_catalog)
        mock_db = MagicMock()

        with patch("app.services.geospatial_service.PersistentGeospatialContextService") as mock_cls:
            mock_inst = mock_cls.return_value
            mock_inst.query_nearby.return_value = []

            query = NearbyFeaturesQuery(latitude=30.3204, longitude=78.0340, radius_meters=3000.0)
            res = service.query_nearby_features(query, db=mock_db)

            assert res == []

    def test_query_nearby_condition_c_db_failure_raises_postgis_unavailable(self, mock_catalog):
        """Case C: DB query fails -> raises PostGISUnavailableError."""
        service = GeospatialService(catalog=mock_catalog)
        mock_db = MagicMock()

        with patch("app.services.geospatial_service.PersistentGeospatialContextService") as mock_cls:
            mock_inst = mock_cls.return_value
            mock_inst.query_nearby.side_effect = OperationalError("timeout", {}, None)

            query = NearbyFeaturesQuery(latitude=30.3204, longitude=78.0340, radius_meters=3000.0)
            with pytest.raises(PostGISUnavailableError) as exc_info:
                service.query_nearby_features(query, db=mock_db)

            assert "timeout" in str(exc_info.value)
            assert exc_info.value.status_code == 503

    def test_query_nearby_condition_d_db_none_uses_catalog(self, mock_catalog):
        """Case D: db=None -> uses local catalog."""
        service = GeospatialService(catalog=mock_catalog)
        query = NearbyFeaturesQuery(latitude=30.3204, longitude=78.0340, radius_meters=3000.0)
        res = service.query_nearby_features(query, db=None)

        assert len(res) == 1
        assert res[0].name == "Catalog Hospital"

    # --------------------------------------------------------------------------
    # correlate_incident_environmental_exposure tests
    # --------------------------------------------------------------------------

    def test_correlate_condition_a_db_features(self, mock_catalog, sample_feature_item):
        """Case A: DB query succeeds -> downwind analysis uses DB features."""
        service = GeospatialService(catalog=mock_catalog)
        mock_db = MagicMock()

        with patch("app.services.geospatial_service.PersistentGeospatialContextService") as mock_cls:
            mock_inst = mock_cls.return_value
            mock_inst.query_nearby.return_value = [sample_feature_item]

            result = service.correlate_incident_environmental_exposure(
                latitude=30.3204,
                longitude=78.0340,
                wind_direction_degrees=180.0,
                wind_speed_mps=10.0,
                db=mock_db,
            )
            assert result["total_features_nearby"] == 1

    def test_correlate_condition_b_db_empty_no_catalog_fallback(self, mock_catalog):
        """Case B: DB succeeds with 0 features -> returns 0 features nearby, no catalog fallback."""
        service = GeospatialService(catalog=mock_catalog)
        mock_db = MagicMock()

        with patch("app.services.geospatial_service.PersistentGeospatialContextService") as mock_cls:
            mock_inst = mock_cls.return_value
            mock_inst.query_nearby.return_value = []

            result = service.correlate_incident_environmental_exposure(
                latitude=30.3204,
                longitude=78.0340,
                wind_direction_degrees=180.0,
                wind_speed_mps=10.0,
                db=mock_db,
            )
            assert result["total_features_nearby"] == 0

    def test_correlate_condition_c_db_failure_raises(self, mock_catalog):
        """Case C: DB fails -> raises PostGISUnavailableError."""
        service = GeospatialService(catalog=mock_catalog)
        mock_db = MagicMock()

        with patch("app.services.geospatial_service.PersistentGeospatialContextService") as mock_cls:
            mock_inst = mock_cls.return_value
            mock_inst.query_nearby.side_effect = OperationalError("connection lost", {}, None)

            with pytest.raises(PostGISUnavailableError) as exc_info:
                service.correlate_incident_environmental_exposure(
                    latitude=30.3204,
                    longitude=78.0340,
                    wind_direction_degrees=180.0,
                    wind_speed_mps=10.0,
                    db=mock_db,
                )
            assert "connection lost" in str(exc_info.value)

    def test_correlate_condition_d_db_none_uses_catalog(self, mock_catalog):
        """Case D: db=None -> uses local catalog."""
        service = GeospatialService(catalog=mock_catalog)
        result = service.correlate_incident_environmental_exposure(
            latitude=30.3204,
            longitude=78.0340,
            wind_direction_degrees=180.0,
            wind_speed_mps=10.0,
            db=None,
        )
        assert result["total_features_nearby"] == 1


class TestRiskAssessorDataAttribution:
    """Tests dynamic data_provider attribution across disaster risk assessors."""

    def test_wildfire_risk_assessor_attribution(self, mock_catalog):
        assessor = WildfireRiskAssessor()
        empty_summary = ExposureSummary(
            total_features_found=0,
            category_counts={},
            closest_feature_distance_meters=None,
            closest_feature_name=None,
            highlighted_exposed_features=[],
        )

        res_postgis = assessor.evaluate(
            latitude=30.3204,
            longitude=78.0340,
            search_radius_meters=2000.0,
            features=[],
            exposure_summary=empty_summary,
            catalog=mock_catalog,
            data_provider="postgis_spatial_db",
        )
        assert res_postgis.data_provider == "postgis_spatial_db"
        assert any("persistent spatial database" in f for f in res_postgis.contributing_factors)

        res_catalog = assessor.evaluate(
            latitude=30.3204,
            longitude=78.0340,
            search_radius_meters=2000.0,
            features=[],
            exposure_summary=empty_summary,
            catalog=mock_catalog,
            data_provider="local_vector_catalog",
        )
        assert res_catalog.data_provider == "local_vector_catalog"
        assert any("active catalog" in f for f in res_catalog.contributing_factors)

    def test_flood_risk_assessor_attribution(self, mock_catalog):
        assessor = FloodRiskAssessor()
        empty_summary = ExposureSummary(
            total_features_found=0,
            category_counts={},
            closest_feature_distance_meters=None,
            closest_feature_name=None,
            highlighted_exposed_features=[],
        )

        res_postgis = assessor.evaluate(
            latitude=30.3204,
            longitude=78.0340,
            search_radius_meters=2000.0,
            features=[],
            exposure_summary=empty_summary,
            catalog=mock_catalog,
            data_provider="postgis_spatial_db",
        )
        assert res_postgis.data_provider == "postgis_spatial_db"
        assert any("persistent spatial database" in f for f in res_postgis.contributing_factors)

    def test_earthquake_risk_assessor_attribution(self, mock_catalog):
        assessor = EarthquakeRiskAssessor()
        empty_summary = ExposureSummary(
            total_features_found=0,
            category_counts={},
            closest_feature_distance_meters=None,
            closest_feature_name=None,
            highlighted_exposed_features=[],
        )

        res_postgis = assessor.evaluate(
            latitude=30.3204,
            longitude=78.0340,
            search_radius_meters=2000.0,
            features=[],
            exposure_summary=empty_summary,
            catalog=mock_catalog,
            data_provider="postgis_spatial_db",
        )
        assert res_postgis.data_provider == "postgis_spatial_db"
        assert any("persistent spatial database" in f for f in res_postgis.contributing_factors)
