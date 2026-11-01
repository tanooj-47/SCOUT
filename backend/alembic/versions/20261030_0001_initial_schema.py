"""create_initial_schema

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-10-30 11:55:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import geoalchemy2

# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create table: incidents
    op.create_table(
        "incidents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("disaster_type", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column(
            "location",
            geoalchemy2.types.Geometry(
                geometry_type="POINT",
                srid=4326,
                spatial_index=False,
                from_text="ST_GeomFromEWKT",
                name="geometry",
            ),
            nullable=False,
        ),
        sa.Column(
            "observed_perimeter",
            geoalchemy2.types.Geometry(
                geometry_type="MULTIPOLYGON",
                srid=4326,
                spatial_index=False,
                from_text="ST_GeomFromEWKT",
                name="geometry",
            ),
            nullable=True,
        ),
        sa.Column("perimeter_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("contained_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_archived", sa.Boolean(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            "disaster_type IN ('wildfire', 'flood', 'earthquake')",
            name="ck_incidents_disaster_type",
        ),
        sa.CheckConstraint(
            "status IN ('reported', 'investigating', 'active', 'contained', 'resolved', 'false_alarm')",
            name="ck_incidents_status",
        ),
        sa.CheckConstraint(
            "severity IN ('low', 'moderate', 'high', 'critical')",
            name="ck_incidents_severity",
        ),
        sa.CheckConstraint(
            "(is_archived = false AND archived_at IS NULL) OR (is_archived = true AND archived_at IS NOT NULL)",
            name="ck_incidents_archival_consistency",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_incidents")),
    )
    op.create_index(
        "ix_incidents_location",
        "incidents",
        ["location"],
        unique=False,
        postgresql_using="gist",
    )
    op.create_index(
        "ix_incidents_location_geography",
        "incidents",
        [sa.text("(location::geography)")],
        unique=False,
        postgresql_using="gist",
    )
    op.create_index(
        "ix_incidents_observed_perimeter",
        "incidents",
        ["observed_perimeter"],
        unique=False,
        postgresql_using="gist",
    )
    op.create_index(
        "ix_incidents_status_is_archived",
        "incidents",
        ["status", "is_archived"],
        unique=False,
    )

    # 2. Create table: uploaded_media
    op.create_table(
        "uploaded_media",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("storage_path", sa.String(length=512), nullable=False),
        sa.Column("media_format", sa.String(length=32), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column(
            "capture_location",
            geoalchemy2.types.Geometry(
                geometry_type="POINT",
                srid=4326,
                spatial_index=False,
                from_text="ST_GeomFromEWKT",
                name="geometry",
            ),
            nullable=True,
        ),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "file_size_bytes >= 0",
            name="ck_uploaded_media_file_size_bytes",
        ),
        sa.ForeignKeyConstraint(
            ["incident_id"],
            ["incidents.id"],
            name=op.f("fk_uploaded_media_incident_id_incidents"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_uploaded_media")),
    )
    op.create_index(
        "ix_uploaded_media_incident_id",
        "uploaded_media",
        ["incident_id"],
        unique=False,
    )
    op.create_index(
        "ix_uploaded_media_captured_at",
        "uploaded_media",
        ["captured_at"],
        unique=False,
    )
    op.create_index(
        "ix_uploaded_media_capture_location",
        "uploaded_media",
        ["capture_location"],
        unique=False,
        postgresql_using="gist",
    )

    # 3. Create table: detection_results
    op.create_table(
        "detection_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("media_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("classification", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("bounding_boxes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("model_name", sa.String(length=64), nullable=False),
        sa.Column("model_version", sa.String(length=32), nullable=False),
        sa.Column("inference_latency_ms", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "classification IN ('fire', 'smoke', 'neutral', 'floodwater')",
            name="ck_detection_results_classification",
        ),
        sa.CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="ck_detection_results_confidence",
        ),
        sa.CheckConstraint(
            "inference_latency_ms >= 0",
            name="ck_detection_results_inference_latency_ms",
        ),
        sa.ForeignKeyConstraint(
            ["media_id"],
            ["uploaded_media.id"],
            name=op.f("fk_detection_results_media_id_uploaded_media"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_detection_results")),
    )
    op.create_index(
        "ix_detection_results_media_id",
        "detection_results",
        ["media_id"],
        unique=False,
    )
    op.create_index(
        "ix_detection_results_classification",
        "detection_results",
        ["classification"],
        unique=False,
    )
    op.create_index(
        "ix_detection_results_created_at",
        "detection_results",
        ["created_at"],
        unique=False,
    )

    # 4. Create table: environmental_observations
    op.create_table(
        "environmental_observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("temperature_celsius", sa.Float(), nullable=True),
        sa.Column("relative_humidity", sa.Float(), nullable=True),
        sa.Column("wind_speed_mps", sa.Float(), nullable=True),
        sa.Column("wind_direction_degrees", sa.Float(), nullable=True),
        sa.Column("precipitation_mm", sa.Float(), nullable=True),
        sa.Column("metrics_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "relative_humidity IS NULL OR (relative_humidity >= 0.0 AND relative_humidity <= 100.0)",
            name="ck_env_obs_relative_humidity",
        ),
        sa.CheckConstraint(
            "wind_speed_mps IS NULL OR wind_speed_mps >= 0.0",
            name="ck_env_obs_wind_speed_mps",
        ),
        sa.CheckConstraint(
            "wind_direction_degrees IS NULL OR (wind_direction_degrees >= 0.0 AND wind_direction_degrees <= 360.0)",
            name="ck_env_obs_wind_direction_degrees",
        ),
        sa.CheckConstraint(
            "precipitation_mm IS NULL OR precipitation_mm >= 0.0",
            name="ck_env_obs_precipitation_mm",
        ),
        sa.ForeignKeyConstraint(
            ["incident_id"],
            ["incidents.id"],
            name=op.f("fk_environmental_observations_incident_id_incidents"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_environmental_observations")),
    )
    op.create_index(
        "ix_environmental_observations_incident_id",
        "environmental_observations",
        ["incident_id"],
        unique=False,
    )
    op.create_index(
        "ix_environmental_observations_recorded_at",
        "environmental_observations",
        ["recorded_at"],
        unique=False,
    )
    op.create_index(
        "ix_environmental_observations_incident_recorded",
        "environmental_observations",
        ["incident_id", sa.text("recorded_at DESC")],
        unique=False,
    )

    # 5. Create table: hazard_predictions
    op.create_table(
        "hazard_predictions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("primary_observation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("forecast_horizon_hours", sa.Float(), nullable=False),
        sa.Column("projected_area_hectares", sa.Float(), nullable=False),
        sa.Column(
            "predicted_footprint",
            geoalchemy2.types.Geometry(
                geometry_type="MULTIPOLYGON",
                srid=4326,
                spatial_index=False,
                from_text="ST_GeomFromEWKT",
                name="geometry",
            ),
            nullable=False,
        ),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("model_name", sa.String(length=64), nullable=False),
        sa.Column("model_version", sa.String(length=32), nullable=False),
        sa.Column("input_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "forecast_horizon_hours > 0.0",
            name="ck_hazard_predictions_forecast_horizon_hours",
        ),
        sa.CheckConstraint(
            "projected_area_hectares >= 0.0",
            name="ck_hazard_predictions_projected_area_hectares",
        ),
        sa.CheckConstraint(
            "risk_level IN ('low', 'moderate', 'high', 'critical')",
            name="ck_hazard_predictions_risk_level",
        ),
        sa.ForeignKeyConstraint(
            ["incident_id"],
            ["incidents.id"],
            name=op.f("fk_hazard_predictions_incident_id_incidents"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["primary_observation_id"],
            ["environmental_observations.id"],
            name=op.f("fk_hazard_predictions_primary_observation_id_environmental_observations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_hazard_predictions")),
    )
    op.create_index(
        "ix_hazard_predictions_incident_id",
        "hazard_predictions",
        ["incident_id"],
        unique=False,
    )
    op.create_index(
        "ix_hazard_predictions_primary_observation_id",
        "hazard_predictions",
        ["primary_observation_id"],
        unique=False,
    )
    op.create_index(
        "ix_hazard_predictions_created_at",
        "hazard_predictions",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_hazard_predictions_risk_level",
        "hazard_predictions",
        ["risk_level"],
        unique=False,
    )
    op.create_index(
        "ix_hazard_predictions_incident_horizon",
        "hazard_predictions",
        ["incident_id", "forecast_horizon_hours"],
        unique=False,
    )
    op.create_index(
        "ix_hazard_predictions_predicted_footprint",
        "hazard_predictions",
        ["predicted_footprint"],
        unique=False,
        postgresql_using="gist",
    )
    op.create_index(
        "ix_hazard_predictions_footprint_geography",
        "hazard_predictions",
        [sa.text("(predicted_footprint::geography)")],
        unique=False,
        postgresql_using="gist",
    )


def downgrade() -> None:
    # Drop tables in exact reverse dependency order
    op.drop_table("hazard_predictions")
    op.drop_table("environmental_observations")
    op.drop_table("detection_results")
    op.drop_table("uploaded_media")
    op.drop_table("incidents")
