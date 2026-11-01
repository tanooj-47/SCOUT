"""
backend/tests/unit/geospatial/test_persistent_models.py
Unit tests verifying persistent geospatial model schemas, column types,
constraints, and foreign key configurations for Milestone 10.
"""

import uuid
import pytest
from geoalchemy2 import Geometry
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.models.geospatial import (
    GeographicDataSource,
    GeographicIngestionRun,
    GeographicFeature,
)


class TestPersistentGeospatialModels:
    """Verifies schema definitions for GeographicDataSource, GeographicIngestionRun, and GeographicFeature."""

    def test_geographic_data_source_schema(self):
        table = GeographicDataSource.__table__
        assert table.name == "geographic_data_sources"

        pk_col = table.primary_key.columns[0]
        assert pk_col.name == "id"
        assert isinstance(pk_col.type, UUID)

        assert table.columns["provider"].nullable is False
        assert table.columns["dataset_name"].nullable is False
        assert table.columns["license_identifier"].nullable is False
        assert table.columns["attribution_text"].nullable is False
        assert table.columns["source_crs"].nullable is False

        # Verify JSONB metadata
        assert isinstance(table.columns["metadata_payload"].type, JSONB)

    def test_geographic_ingestion_run_schema(self):
        table = GeographicIngestionRun.__table__
        assert table.name == "geographic_ingestion_runs"

        pk_col = table.primary_key.columns[0]
        assert pk_col.name == "id"
        assert isinstance(pk_col.type, UUID)

        assert table.columns["layer_name"].nullable is False
        assert table.columns["status"].nullable is False
        assert table.columns["total_features"].nullable is False
        assert table.columns["inserted_features"].nullable is False
        assert table.columns["updated_features"].nullable is False
        assert table.columns["skipped_features"].nullable is False
        assert table.columns["rejected_features"].nullable is False

        # Verify foreign key to geographic_data_sources with RESTRICT
        fk = list(table.foreign_keys)[0]
        assert fk.column.table.name == "geographic_data_sources"
        assert fk.ondelete.upper() == "RESTRICT"

    def test_geographic_feature_schema_and_spatial_columns(self):
        table = GeographicFeature.__table__
        assert table.name == "geographic_features"

        pk_col = table.primary_key.columns[0]
        assert pk_col.name == "id"
        assert isinstance(pk_col.type, UUID)

        # Spatial geometry column
        geom_col = table.columns["geometry"]
        assert isinstance(geom_col.type, Geometry)
        assert geom_col.type.geometry_type == "GEOMETRY"
        assert geom_col.type.srid == 4326
        assert geom_col.nullable is False

        # Required fields
        assert table.columns["layer_name"].nullable is False
        assert table.columns["category"].nullable is False
        assert table.columns["source_feature_id"].nullable is False
        assert table.columns["geometry_type"].nullable is False

        # JSONB attributes
        assert isinstance(table.columns["properties"].type, JSONB)
        assert isinstance(table.columns["hazard_relevance"].type, JSONB)

        # Unique constraint on (source_id, source_feature_id, layer_name)
        uq_names = [c.name for c in table.constraints if c.name == "uq_geo_features_source_feature_layer"]
        assert len(uq_names) == 1

        # Compound index on (layer_name, category)
        idx_names = [idx.name for idx in table.indexes if idx.name == "ix_geo_features_layer_category"]
        assert len(idx_names) == 1

    def test_geographic_feature_foreign_keys(self):
        table = GeographicFeature.__table__
        fks = {fk.column.table.name: fk for fk in table.foreign_keys}

        assert "geographic_data_sources" in fks
        assert fks["geographic_data_sources"].ondelete.upper() == "RESTRICT"

        assert "geographic_ingestion_runs" in fks
        assert fks["geographic_ingestion_runs"].ondelete.upper() == "SET NULL"
