"""persistent_geospatial_features

Revision ID: 0003_persistent_geospatial_features
Revises: 0002_environmental_observations_upgrade
Create Date: 2026-10-31 16:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import geoalchemy2

# revision identifiers, used by Alembic.
revision: str = "0003_persistent_geospatial_features"
down_revision: Union[str, None] = "0002_environmental_observations_upgrade"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create geographic_data_sources table
    op.create_table(
        "geographic_data_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("dataset_name", sa.String(length=128), nullable=False),
        sa.Column("dataset_version", sa.String(length=32), nullable=True),
        sa.Column("source_url", sa.String(length=512), nullable=True),
        sa.Column("license_identifier", sa.String(length=64), nullable=False),
        sa.Column("attribution_text", sa.String(length=512), nullable=False),
        sa.Column("source_crs", sa.String(length=32), nullable=False, server_default="EPSG:4326"),
        sa.Column("metadata_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_geographic_data_sources")),
    )
    op.create_index(
        op.f("ix_geographic_data_sources_provider"),
        "geographic_data_sources",
        ["provider"],
        unique=False,
    )

    # 2. Create geographic_ingestion_runs table
    op.create_table(
        "geographic_ingestion_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("geographic_data_sources.id", ondelete="RESTRICT", name=op.f("fk_geographic_ingestion_runs_source_id_geographic_data_sources")),
            nullable=False,
        ),
        sa.Column("layer_name", sa.String(length=64), nullable=False),
        sa.Column("area_of_interest", sa.String(length=128), nullable=True),
        sa.Column("source_file_name", sa.String(length=256), nullable=True),
        sa.Column("source_checksum", sa.String(length=64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_features", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("inserted_features", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_features", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_features", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rejected_features", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="in_progress"),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_geographic_ingestion_runs")),
    )
    op.create_index(
        op.f("ix_geographic_ingestion_runs_source_id"),
        "geographic_ingestion_runs",
        ["source_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_geographic_ingestion_runs_layer_name"),
        "geographic_ingestion_runs",
        ["layer_name"],
        unique=False,
    )
    op.create_index(
        op.f("ix_geographic_ingestion_runs_area_of_interest"),
        "geographic_ingestion_runs",
        ["area_of_interest"],
        unique=False,
    )

    # 3. Create geographic_features table
    op.create_table(
        "geographic_features",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("geographic_data_sources.id", ondelete="RESTRICT", name=op.f("fk_geographic_features_source_id_geographic_data_sources")),
            nullable=False,
        ),
        sa.Column(
            "ingestion_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("geographic_ingestion_runs.id", ondelete="SET NULL", name=op.f("fk_geographic_features_ingestion_run_id_geographic_ingestion_runs")),
            nullable=True,
        ),
        sa.Column("layer_name", sa.String(length=64), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("source_feature_id", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False, server_default="Unnamed Feature"),
        sa.Column("properties", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "geometry",
            geoalchemy2.types.Geometry(
                geometry_type="GEOMETRY",
                srid=4326,
                spatial_index=False,
                from_text="ST_GeomFromEWKT",
                name="geometry",
            ),
            nullable=False,
        ),
        sa.Column("geometry_type", sa.String(length=32), nullable=False),
        sa.Column("source_crs", sa.String(length=32), nullable=False, server_default="EPSG:4326"),
        sa.Column("hazard_relevance", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_geographic_features")),
        sa.UniqueConstraint("source_id", "source_feature_id", "layer_name", name="uq_geo_features_source_feature_layer"),
    )
    op.create_index(
        op.f("ix_geographic_features_source_id"),
        "geographic_features",
        ["source_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_geographic_features_ingestion_run_id"),
        "geographic_features",
        ["ingestion_run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_geographic_features_layer_name"),
        "geographic_features",
        ["layer_name"],
        unique=False,
    )
    op.create_index(
        op.f("ix_geographic_features_category"),
        "geographic_features",
        ["category"],
        unique=False,
    )
    op.create_index(
        "ix_geo_features_layer_category",
        "geographic_features",
        ["layer_name", "category"],
        unique=False,
    )
    op.create_index(
        "ix_geographic_features_geometry",
        "geographic_features",
        ["geometry"],
        unique=False,
        postgresql_using="gist",
    )
    op.create_index(
        "ix_geographic_features_hazard_relevance",
        "geographic_features",
        ["hazard_relevance"],
        unique=False,
        postgresql_using="gin",
    )


def downgrade() -> None:
    # Drop in reverse order
    op.drop_index("ix_geographic_features_hazard_relevance", table_name="geographic_features", postgresql_using="gin")
    op.drop_index("ix_geographic_features_geometry", table_name="geographic_features", postgresql_using="gist")
    op.drop_index("ix_geo_features_layer_category", table_name="geographic_features")
    op.drop_index(op.f("ix_geographic_features_category"), table_name="geographic_features")
    op.drop_index(op.f("ix_geographic_features_layer_name"), table_name="geographic_features")
    op.drop_index(op.f("ix_geographic_features_ingestion_run_id"), table_name="geographic_features")
    op.drop_index(op.f("ix_geographic_features_source_id"), table_name="geographic_features")
    op.drop_table("geographic_features")

    op.drop_index(op.f("ix_geographic_ingestion_runs_area_of_interest"), table_name="geographic_ingestion_runs")
    op.drop_index(op.f("ix_geographic_ingestion_runs_layer_name"), table_name="geographic_ingestion_runs")
    op.drop_index(op.f("ix_geographic_ingestion_runs_source_id"), table_name="geographic_ingestion_runs")
    op.drop_table("geographic_ingestion_runs")

    op.drop_index(op.f("ix_geographic_data_sources_provider"), table_name="geographic_data_sources")
    op.drop_table("geographic_data_sources")
