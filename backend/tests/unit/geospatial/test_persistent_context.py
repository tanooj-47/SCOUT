"""
backend/tests/unit/geospatial/test_persistent_context.py
Unit tests for PersistentGeospatialContextService and feature_to_domain_item mapper.
"""

from unittest.mock import MagicMock
import uuid
import pytest
from geoalchemy2.elements import WKTElement

from app.geospatial.persistent_context import (
    PersistentGeospatialContextService,
    feature_to_domain_item,
    EXPECTED_CANONICAL_LAYERS,
)
from app.geospatial.schemas import (
    FeatureCategory,
    SpatialRelationship,
)
from app.models.geospatial import GeographicDataSource, GeographicFeature


class TestPersistentGeospatialContext:
    """Verifies domain mapping and persistent exposure analysis."""

    @pytest.fixture
    def sample_source(self):
        return GeographicDataSource(
            id=uuid.uuid4(),
            provider="openstreetmap",
            dataset_name="osm_critical_facilities",
            license_identifier="ODbL-1.0",
            attribution_text="Data © OpenStreetMap contributors",
            source_crs="EPSG:4326",
        )

    @pytest.fixture
    def sample_feature(self, sample_source):
        feat = GeographicFeature(
            id=uuid.uuid4(),
            source_id=sample_source.id,
            source=sample_source,
            layer_name="critical_facilities",
            category="infrastructure",
            source_feature_id="osm_node_1001",
            name="Doon Hospital",
            properties={"amenity": "hospital", "emergency": "yes"},
            geometry=WKTElement("POINT(78.0340 30.3204)", srid=4326),
            geometry_type="Point",
            hazard_relevance=["wildfire", "flood", "earthquake"],
        )
        return feat

    def test_feature_to_domain_item_topological_relationships(self, sample_feature):
        # 0.0m distance -> INTERSECTS
        item_intersect = feature_to_domain_item(sample_feature, distance_meters=0.0, radius_meters=5000.0)
        assert item_intersect.relationship == SpatialRelationship.INTERSECTS

        # 2500m distance <= 5000m -> WITHIN_RADIUS
        item_within = feature_to_domain_item(sample_feature, distance_meters=2500.0, radius_meters=5000.0)
        assert item_within.relationship == SpatialRelationship.WITHIN_RADIUS

        # 5200m distance <= 5000 * 1.1 = 5500m -> ADJACENT
        item_adj = feature_to_domain_item(sample_feature, distance_meters=5200.0, radius_meters=5000.0)
        assert item_adj.relationship == SpatialRelationship.ADJACENT

        # 7000m distance > 5500m -> DISJOINT
        item_disjoint = feature_to_domain_item(sample_feature, distance_meters=7000.0, radius_meters=5000.0)
        assert item_disjoint.relationship == SpatialRelationship.DISJOINT

    def test_feature_to_domain_item_properties_and_coords(self, sample_feature):
        item = feature_to_domain_item(
            sample_feature,
            distance_meters=345.678,
            radius_meters=5000.0,
            include_geometry=True,
        )
        assert item.name == "Doon Hospital"
        assert item.category == FeatureCategory.INFRASTRUCTURE
        assert item.distance_meters == 345.68
        assert item.source_dataset == "osm_critical_facilities"
        assert item.geometry is not None
        assert item.geometry.type == "Point"
        assert item.latitude == pytest.approx(30.3204, rel=1e-4)
        assert item.longitude == pytest.approx(78.0340, rel=1e-4)

    def test_persistent_context_analyze_exposure_wildfire(self, sample_feature):
        mock_db = MagicMock()
        service = PersistentGeospatialContextService(mock_db)

        # Mock query_within_radius returning sample_feature at 450m
        mock_db.execute.return_value.all.return_value = [
            (sample_feature, 450.0)
        ]
        # Mock available layers: critical_facilities only
        mock_db.execute.return_value.all.side_effect = [
            [(sample_feature, 450.0)],  # radius query
            [("critical_facilities", 1)],  # list_layers
        ]
        mock_db.scalars.return_value.all.return_value = ["infrastructure"]

        summary, features, factors, missing = service.analyze_exposure(
            latitude=30.3200,
            longitude=78.0340,
            radius_meters=5000.0,
            disaster_type="wildfire",
        )

        assert summary.total_features_found == 1
        assert summary.closest_feature_name == "Doon Hospital"
        assert summary.closest_feature_distance_meters == 450.0
        assert len(features) == 1

        # Check missing indicators (hydrology, transportation, land_cover, settlements missing)
        assert len(missing) >= 4
        assert any("hydrology" in m for m in missing)
        assert any("land_cover" in m for m in missing)

        # Check explainable contributing factors
        assert any("critical infrastructure assets" in f for f in factors)
