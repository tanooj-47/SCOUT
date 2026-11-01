"""
backend/app/models/geospatial.py
SQLAlchemy models for persistent real-world geographic data, sources, and ingestion tracking.
Milestone 10: Persistent Geospatial Data Integration.
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from geoalchemy2 import Geometry
from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.models.base import Base


class GeographicDataSource(Base):
    """
    Registers provenance, licensing, and metadata for external geographic data providers.
    Ensures ODbL and CC BY 4.0 attribution terms are preserved across all ingested features.
    """
    __tablename__ = "geographic_data_sources"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False)
    provider = Column(String(64), nullable=False, index=True)  # e.g. "openstreetmap", "esa_worldcover", "ghsl"
    dataset_name = Column(String(128), nullable=False)        # e.g. "osm_critical_facilities", "ghsl_built_up"
    dataset_version = Column(String(32), nullable=True)       # e.g. "2024-Q3", "v2.0"
    source_url = Column(String(512), nullable=True)          # e.g. "https://download.geofabrik.de/asia/india.html"
    license_identifier = Column(String(64), nullable=False)   # e.g. "ODbL-1.0", "CC-BY-4.0"
    attribution_text = Column(String(512), nullable=False)    # e.g. "Data © OpenStreetMap contributors, ODbL 1.0"
    source_crs = Column(String(32), nullable=False, default="EPSG:4326")
    metadata_payload = Column(JSONB, nullable=True, default=dict)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    # Relationships
    ingestion_runs = relationship("GeographicIngestionRun", back_populates="source", cascade="all, delete-orphan")
    features = relationship("GeographicFeature", back_populates="source", cascade="all, delete-orphan")


class GeographicIngestionRun(Base):
    """
    Audits and tracks each geospatial ingestion operation.
    Records file checksums, counts, processing duration, and error summaries.
    """
    __tablename__ = "geographic_ingestion_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False)
    source_id = Column(
        UUID(as_uuid=True),
        ForeignKey("geographic_data_sources.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    layer_name = Column(String(64), nullable=False, index=True)  # e.g. "hospitals", "water_bodies"
    area_of_interest = Column(String(128), nullable=True, index=True)  # e.g. "in_dehradun_basin"
    source_file_name = Column(String(256), nullable=True)
    source_checksum = Column(String(64), nullable=True)  # SHA-256 of source file
    started_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    total_features = Column(Integer, nullable=False, default=0)
    inserted_features = Column(Integer, nullable=False, default=0)
    updated_features = Column(Integer, nullable=False, default=0)
    skipped_features = Column(Integer, nullable=False, default=0)
    rejected_features = Column(Integer, nullable=False, default=0)
    status = Column(String(32), nullable=False, default="in_progress")  # "in_progress", "completed", "failed", "dry_run"
    error_summary = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    source = relationship("GeographicDataSource", back_populates="ingestion_runs")
    features = relationship("GeographicFeature", back_populates="ingestion_run")


class GeographicFeature(Base):
    """
    Persistent real-world spatial entity stored in PostgreSQL/PostGIS.
    Indexed with spatial GiST indexes on geometry and B-tree indexes on category/layer.
    """
    __tablename__ = "geographic_features"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False)
    source_id = Column(
        UUID(as_uuid=True),
        ForeignKey("geographic_data_sources.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    ingestion_run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("geographic_ingestion_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    layer_name = Column(String(64), nullable=False, index=True)  # e.g. "hospitals", "water_bodies", "roads"
    category = Column(String(64), nullable=False, index=True)    # Canonical FeatureCategory enum string
    source_feature_id = Column(String(128), nullable=False)      # Stable upstream feature ID (e.g. "way/12345", "node/67890")
    name = Column(String(256), nullable=False, default="Unnamed Feature")
    properties = Column(JSONB, nullable=False, default=dict)    # Original source attributes preserved verbatim
    geometry = Column(
        Geometry(geometry_type="GEOMETRY", srid=4326, spatial_index=True),
        nullable=False,
    )
    geometry_type = Column(String(32), nullable=False)          # "Point", "LineString", "Polygon", "MultiPolygon"
    source_crs = Column(String(32), nullable=False, default="EPSG:4326")
    hazard_relevance = Column(JSONB, nullable=False, default=list)  # e.g. ["wildfire", "flood", "earthquake"]
    valid_from = Column(DateTime(timezone=True), nullable=True)
    valid_to = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    # Constraints and Compound Indexes
    __table_args__ = (
        UniqueConstraint("source_id", "source_feature_id", "layer_name", name="uq_geo_features_source_feature_layer"),
        Index("ix_geo_features_layer_category", "layer_name", "category"),
    )

    # Relationships
    source = relationship("GeographicDataSource", back_populates="features")
    ingestion_run = relationship("GeographicIngestionRun", back_populates="features")
