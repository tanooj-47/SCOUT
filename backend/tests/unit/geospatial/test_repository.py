"""
backend/tests/unit/geospatial/test_repository.py
Unit tests for GeospatialFeatureRepository data access methods.
"""

from unittest.mock import MagicMock
import uuid
import pytest

from app.geospatial.repository import GeospatialFeatureRepository
from app.models.geospatial import GeographicDataSource, GeographicFeature, GeographicIngestionRun


class TestGeospatialFeatureRepository:
    """Verifies repository query construction, limits, and result handling."""

    @pytest.fixture
    def mock_session(self):
        return MagicMock()

    def test_get_by_id_with_uuid_and_str(self, mock_session):
        repo = GeospatialFeatureRepository(mock_session)
        feat_id = uuid.uuid4()
        fake_feat = GeographicFeature(id=feat_id, name="Test Feature")
        mock_session.get.return_value = fake_feat

        # UUID instance
        res1 = repo.get_by_id(feat_id)
        assert res1 == fake_feat
        mock_session.get.assert_called_with(GeographicFeature, feat_id)

        # String UUID
        res2 = repo.get_by_id(str(feat_id))
        assert res2 == fake_feat
        mock_session.get.assert_called_with(GeographicFeature, feat_id)

    def test_get_by_source_and_feature_id(self, mock_session):
        repo = GeospatialFeatureRepository(mock_session)
        source_id = uuid.uuid4()
        fake_feat = GeographicFeature(id=uuid.uuid4(), source_feature_id="osm_123")
        mock_session.scalars.return_value.first.return_value = fake_feat

        res = repo.get_by_source_and_feature_id(source_id, "osm_123", "critical_facilities")
        assert res == fake_feat
        mock_session.scalars.assert_called_once()

    def test_query_by_bbox_clamps_limit(self, mock_session):
        repo = GeospatialFeatureRepository(mock_session)
        mock_session.scalars.return_value.all.return_value = []

        # Requesting limit 1000 should be clamped to 500
        res = repo.query_by_bbox(
            min_lon=77.9,
            min_lat=30.1,
            max_lon=78.2,
            max_lat=30.4,
            layer_name="hydrology",
            limit=1000,
            offset=10,
        )
        assert res == []
        mock_session.scalars.assert_called_once()

    def test_query_within_radius_clamps_limit(self, mock_session):
        repo = GeospatialFeatureRepository(mock_session)
        mock_session.execute.return_value.all.return_value = []

        res = repo.query_within_radius(
            center_lon=78.034,
            center_lat=30.320,
            radius_meters=5000.0,
            hazard="wildfire",
            limit=-10,  # Negative should be clamped to 1
        )
        assert res == []
        mock_session.execute.assert_called_once()

    def test_list_layers_aggregates_categories(self, mock_session):
        repo = GeospatialFeatureRepository(mock_session)
        # First query returns layer names and counts
        mock_session.execute.return_value.all.return_value = [
            ("critical_facilities", 10),
            ("hydrology", 5),
        ]
        # Category distinct queries
        mock_session.scalars.return_value.all.side_effect = [
            ["infrastructure"],
            ["water_body"],
        ]

        layers = repo.list_layers()
        assert len(layers) == 2
        assert layers[0]["layer_name"] == "critical_facilities"
        assert layers[0]["feature_count"] == 10
        assert layers[0]["categories"] == ["infrastructure"]

        assert layers[1]["layer_name"] == "hydrology"
        assert layers[1]["feature_count"] == 5
        assert layers[1]["categories"] == ["water_body"]

    def test_count_features(self, mock_session):
        repo = GeospatialFeatureRepository(mock_session)
        mock_session.scalar.return_value = 42

        count = repo.count_features(layer_name="settlements")
        assert count == 42
        mock_session.scalar.assert_called_once()
