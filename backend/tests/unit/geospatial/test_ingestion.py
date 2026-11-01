"""
backend/tests/unit/geospatial/test_ingestion.py
Unit tests for the persistent geospatial ingestion pipeline, GeoJSON normalizer,
category inference, and conflict resolution logic.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock
import uuid
import pytest

from app.geospatial.schemas import FeatureCategory
from app.geospatial.ingestion import (
    ConflictPolicy,
    FeatureNormalizationError,
    GeospatialIngestionError,
    GeospatialIngestionPipeline,
    IngestionOptions,
    IngestionStatus,
    SourceRegistrationCreate,
    infer_feature_category,
    infer_hazard_relevance,
    normalize_feature,
    validate_and_transform_geometry,
)
from app.models.geospatial import GeographicDataSource, GeographicFeature


class TestFeatureNormalization:
    """Verifies parsing, category inference, and hazard classification of GeoJSON features."""

    def test_infer_category_infrastructure(self):
        cat = infer_feature_category({"amenity": "hospital"})
        assert cat == FeatureCategory.INFRASTRUCTURE

        cat2 = infer_feature_category({"healthcare": "clinic"})
        assert cat2 == FeatureCategory.INFRASTRUCTURE

        cat3 = infer_feature_category({"emergency": "fire_station"})
        assert cat3 == FeatureCategory.INFRASTRUCTURE

    def test_infer_category_road(self):
        cat = infer_feature_category({"highway": "primary"})
        assert cat == FeatureCategory.ROAD

    def test_infer_category_vegetation(self):
        cat = infer_feature_category({"landuse": "forest"})
        assert cat == FeatureCategory.VEGETATION

        cat2 = infer_feature_category({"natural": "wood"})
        assert cat2 == FeatureCategory.VEGETATION

    def test_infer_category_water_body(self):
        cat = infer_feature_category({"waterway": "river"})
        assert cat == FeatureCategory.WATER_BODY

        cat2 = infer_feature_category({"natural": "water"})
        assert cat2 == FeatureCategory.WATER_BODY

    def test_infer_category_settlement(self):
        cat = infer_feature_category({"landuse": "residential"})
        assert cat == FeatureCategory.SETTLEMENT

    def test_infer_hazard_relevance(self):
        # Vegetation -> wildfire
        rel_veg = infer_hazard_relevance(FeatureCategory.VEGETATION, {})
        assert "wildfire" in rel_veg

        # Water body -> flood
        rel_water = infer_hazard_relevance(FeatureCategory.WATER_BODY, {})
        assert "flood" in rel_water

        # Hospital -> multi-hazard
        rel_hosp = infer_hazard_relevance(FeatureCategory.INFRASTRUCTURE, {"amenity": "hospital"})
        assert "wildfire" in rel_hosp
        assert "flood" in rel_hosp
        assert "earthquake" in rel_hosp

        # Explicit tag preservation
        rel_explicit = infer_hazard_relevance(FeatureCategory.OTHER, {"hazard_relevance": ["flood", "landslide"]})
        assert "flood" in rel_explicit
        assert "landslide" in rel_explicit

    def test_validate_geometry_out_of_bounds_rejected(self):
        # Lat > 90
        invalid_geom = {"type": "Point", "coordinates": [78.0, 95.0]}
        with pytest.raises(FeatureNormalizationError, match="Latitude out of WGS84 bounds"):
            validate_and_transform_geometry(invalid_geom)

        # Lon > 180
        invalid_geom_lon = {"type": "Point", "coordinates": [190.0, 30.0]}
        with pytest.raises(FeatureNormalizationError, match="Longitude out of WGS84 bounds"):
            validate_and_transform_geometry(invalid_geom_lon)

    def test_normalize_valid_point_feature(self):
        raw = {
            "type": "Feature",
            "id": "node/12345",
            "geometry": {"type": "Point", "coordinates": [78.0340, 30.3204]},
            "properties": {"name": "Test Clinic", "amenity": "clinic"},
        }
        norm = normalize_feature(raw, layer_name="critical_facilities")
        assert norm.source_feature_id == "node/12345"
        assert norm.name == "Test Clinic"
        assert norm.category == FeatureCategory.INFRASTRUCTURE
        assert norm.geometry_type == "Point"
        assert "POINT (78.034 30.3204)" in norm.geometry_wkt
        assert norm.bbox_min_lon == 78.0340
        assert norm.bbox_min_lat == 30.3204

    def test_normalize_feature_without_id_generates_uuid5(self):
        raw = {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [78.05, 30.35]},
            "properties": {"highway": "secondary"},
        }
        norm = normalize_feature(raw, layer_name="transportation")
        assert norm.source_feature_id is not None
        assert len(norm.source_feature_id) == 36  # Valid UUID string format
        assert norm.name == "Unnamed Feature"
        assert norm.category == FeatureCategory.ROAD

    def test_normalize_feature_missing_geometry_raises(self):
        raw = {"type": "Feature", "properties": {"name": "No Geom"}}
        with pytest.raises(FeatureNormalizationError, match="Feature lacks a geometry"):
            normalize_feature(raw, layer_name="test")


class TestIngestionPipeline:
    """Verifies pipeline execution, dry-run simulation, and conflict handling."""

    @pytest.fixture
    def mock_db(self):
        session = MagicMock()
        return session

    @pytest.fixture
    def sample_source(self):
        return GeographicDataSource(
            id=uuid.uuid4(),
            provider="openstreetmap",
            dataset_name="osm_features",
            license_identifier="ODbL-1.0",
            attribution_text="Data © OpenStreetMap contributors",
            source_crs="EPSG:4326",
        )

    def test_pipeline_dry_run_simulation(self, mock_db, sample_source):
        mock_db.get.return_value = sample_source
        mock_db.scalars.return_value.first.return_value = None  # No existing features

        pipeline = GeospatialIngestionPipeline(mock_db)
        geojson_data = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": "feat_1",
                    "geometry": {"type": "Point", "coordinates": [78.0, 30.0]},
                    "properties": {"amenity": "hospital", "name": "Hospital One"},
                },
                {
                    "type": "Feature",
                    "id": "feat_2",
                    "geometry": {"type": "Point", "coordinates": [78.1, 30.1]},
                    "properties": {"highway": "primary", "name": "Primary Road"},
                },
            ],
        }

        options = IngestionOptions(
            layer_name="critical_facilities",
            dry_run=True,
            conflict_policy=ConflictPolicy.UPSERT,
        )

        summary = pipeline.ingest_geojson(
            source_id=sample_source.id,
            geojson_source=geojson_data,
            options=options,
        )

        assert summary.status == IngestionStatus.DRY_RUN
        assert summary.total_features == 2
        assert summary.inserted_features == 2
        assert summary.updated_features == 0
        assert summary.rejected_features == 0

        # Verify no commit or database adds occurred during dry run
        mock_db.commit.assert_not_called()
        mock_db.add.assert_not_called()

    def test_pipeline_live_upsert_execution(self, mock_db, sample_source):
        mock_db.get.return_value = sample_source
        # Existing feature for feat_1, None for feat_2
        existing_feat = GeographicFeature(
            id=uuid.uuid4(),
            source_id=sample_source.id,
            source_feature_id="feat_1",
            layer_name="critical_facilities",
            name="Old Name",
            category="infrastructure",
        )
        mock_db.scalars.return_value.first.side_effect = [existing_feat, None]

        pipeline = GeospatialIngestionPipeline(mock_db)
        geojson_data = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": "feat_1",
                    "geometry": {"type": "Point", "coordinates": [78.0, 30.0]},
                    "properties": {"amenity": "hospital", "name": "Updated Hospital"},
                },
                {
                    "type": "Feature",
                    "id": "feat_2",
                    "geometry": {"type": "Point", "coordinates": [78.1, 30.1]},
                    "properties": {"amenity": "clinic", "name": "New Clinic"},
                },
            ],
        }

        options = IngestionOptions(
            layer_name="critical_facilities",
            dry_run=False,
            conflict_policy=ConflictPolicy.UPSERT,
        )

        summary = pipeline.ingest_geojson(
            source_id=sample_source.id,
            geojson_source=geojson_data,
            options=options,
        )

        assert summary.status == IngestionStatus.COMPLETED
        assert summary.total_features == 2
        assert summary.inserted_features == 1
        assert summary.updated_features == 1
        assert summary.rejected_features == 0
        assert existing_feat.name == "Updated Hospital"
        mock_db.commit.assert_called()

    def test_pipeline_rejects_malformed_features_gracefully(self, mock_db, sample_source):
        mock_db.get.return_value = sample_source
        mock_db.scalars.return_value.first.return_value = None

        pipeline = GeospatialIngestionPipeline(mock_db)
        geojson_data = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": "invalid_1",
                    "geometry": {"type": "Point", "coordinates": [250.0, 30.0]},  # Lon > 180
                    "properties": {"name": "Bad Coords"},
                },
                {
                    "type": "Feature",
                    "id": "valid_1",
                    "geometry": {"type": "Point", "coordinates": [78.0, 30.0]},
                    "properties": {"name": "Good Coords", "highway": "trunk"},
                },
            ],
        }

        options = IngestionOptions(
            layer_name="transportation",
            dry_run=True,
        )

        summary = pipeline.ingest_geojson(
            source_id=sample_source.id,
            geojson_source=geojson_data,
            options=options,
        )

        assert summary.total_features == 2
        assert summary.inserted_features == 1
        assert summary.rejected_features == 1
        assert summary.error_summary is not None
        assert "Longitude out of WGS84 bounds" in summary.error_summary
