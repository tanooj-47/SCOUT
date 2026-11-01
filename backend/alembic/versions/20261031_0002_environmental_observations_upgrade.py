"""environmental_observations_upgrade

Revision ID: 0002_environmental_observations_upgrade
Revises: 0001_initial_schema
Create Date: 2026-10-31 14:15:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import geoalchemy2

# revision identifiers, used by Alembic.
revision: str = "0002_environmental_observations_upgrade"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 0. Widen alembic_version.version_num to support descriptive migration revision IDs (> 32 chars)
    op.execute("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(64);")

    # 1. Alter environmental_observations.incident_id to nullable=True
    op.alter_column(
        "environmental_observations",
        "incident_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )

    # 2. Add new columns to environmental_observations
    op.add_column(
        "environmental_observations",
        sa.Column("location_type", sa.String(length=32), nullable=False, server_default="grid"),
    )
    op.add_column(
        "environmental_observations",
        sa.Column("location_id", sa.String(length=128), nullable=False, server_default=""),
    )
    op.add_column(
        "environmental_observations",
        sa.Column("requested_latitude", sa.Float(), nullable=False, server_default="0.0"),
    )
    op.add_column(
        "environmental_observations",
        sa.Column("requested_longitude", sa.Float(), nullable=False, server_default="0.0"),
    )
    op.add_column(
        "environmental_observations",
        sa.Column("resolved_latitude", sa.Float(), nullable=False, server_default="0.0"),
    )
    op.add_column(
        "environmental_observations",
        sa.Column("resolved_longitude", sa.Float(), nullable=False, server_default="0.0"),
    )
    op.add_column(
        "environmental_observations",
        sa.Column(
            "location",
            geoalchemy2.types.Geometry(
                geometry_type="POINT",
                srid=4326,
                spatial_index=False,
                from_text="ST_GeomFromEWKT",
                name="geometry",
            ),
            nullable=True,
        ),
    )
    op.add_column(
        "environmental_observations",
        sa.Column("typology", sa.String(length=32), nullable=False, server_default="model_analysis"),
    )
    op.add_column(
        "environmental_observations",
        sa.Column("provider", sa.String(length=64), nullable=False, server_default="open-meteo"),
    )
    op.add_column(
        "environmental_observations",
        sa.Column("dataset_or_model", sa.String(length=64), nullable=False, server_default="best_match"),
    )
    op.add_column(
        "environmental_observations",
        sa.Column(
            "valid_time_utc",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.add_column(
        "environmental_observations",
        sa.Column("surface_pressure_hpa", sa.Float(), nullable=True),
    )
    op.add_column(
        "environmental_observations",
        sa.Column("init_time_utc", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "environmental_observations",
        sa.Column("lead_time_hours", sa.Float(), nullable=True),
    )
    op.add_column(
        "environmental_observations",
        sa.Column("algorithm_name", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "environmental_observations",
        sa.Column("algorithm_version", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "environmental_observations",
        sa.Column("source_fingerprint", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "environmental_observations",
        sa.Column(
            "retrieved_at_utc",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # 3. Add Check Constraints
    op.create_check_constraint(
        "ck_env_obs_surface_pressure_hpa",
        "environmental_observations",
        "surface_pressure_hpa IS NULL OR (surface_pressure_hpa >= 300.0 AND surface_pressure_hpa <= 1100.0)",
    )
    op.create_check_constraint(
        "ck_env_obs_forecast_metadata",
        "environmental_observations",
        "typology != 'forecast' OR (init_time_utc IS NOT NULL AND lead_time_hours >= 0.0)",
    )
    op.create_check_constraint(
        "ck_env_obs_derived_metadata",
        "environmental_observations",
        "typology != 'derived' OR (algorithm_name IS NOT NULL AND algorithm_version IS NOT NULL AND source_fingerprint IS NOT NULL)",
    )

    # 4. Add Indexes
    op.create_index(
        "ix_environmental_observations_valid_time_utc",
        "environmental_observations",
        ["valid_time_utc"],
        unique=False,
    )
    op.create_index(
        "ix_environmental_observations_location_id",
        "environmental_observations",
        ["location_id"],
        unique=False,
    )
    op.create_index(
        "ix_environmental_observations_typology",
        "environmental_observations",
        ["typology"],
        unique=False,
    )

    # Partial Unique Indexes
    op.create_index(
        "uq_env_obs_ground_and_reanalysis",
        "environmental_observations",
        ["location_type", "location_id", "provider", "dataset_or_model", "typology", "valid_time_utc"],
        unique=True,
        postgresql_where=sa.text("typology IN ('station_observed', 'reanalysis')"),
    )
    op.create_index(
        "uq_env_obs_model_analysis",
        "environmental_observations",
        ["location_type", "location_id", "provider", "dataset_or_model", "valid_time_utc"],
        unique=True,
        postgresql_where=sa.text("typology = 'model_analysis'"),
    )
    op.create_index(
        "uq_env_obs_forecast",
        "environmental_observations",
        ["location_type", "location_id", "provider", "dataset_or_model", "valid_time_utc", "init_time_utc", "lead_time_hours"],
        unique=True,
        postgresql_where=sa.text("typology = 'forecast'"),
    )
    op.create_index(
        "uq_env_obs_derived",
        "environmental_observations",
        ["location_type", "location_id", "algorithm_name", "algorithm_version", "valid_time_utc", "source_fingerprint"],
        unique=True,
        postgresql_where=sa.text("typology = 'derived'"),
    )

    # 5. Create association table: incident_environmental_observations
    op.create_table(
        "incident_environmental_observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("observation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("association_type", sa.String(length=32), nullable=False, server_default="spatial_proximity"),
        sa.Column("distance_meters", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["incident_id"],
            ["incidents.id"],
            name=op.f("fk_incident_env_obs_incident_id_incidents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["observation_id"],
            ["environmental_observations.id"],
            name=op.f("fk_incident_env_obs_observation_id_environmental_observations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_incident_environmental_observations")),
        sa.UniqueConstraint("incident_id", "observation_id", name="uq_incident_env_obs"),
    )
    op.create_index(
        "ix_incident_env_obs_incident",
        "incident_environmental_observations",
        ["incident_id"],
        unique=False,
    )
    op.create_index(
        "ix_incident_env_obs_observation",
        "incident_environmental_observations",
        ["observation_id"],
        unique=False,
    )


def downgrade() -> None:
    # 1. Drop association table
    op.drop_index("ix_incident_env_obs_observation", table_name="incident_environmental_observations")
    op.drop_index("ix_incident_env_obs_incident", table_name="incident_environmental_observations")
    op.drop_table("incident_environmental_observations")

    # 2. Drop partial unique indexes
    op.drop_index("uq_env_obs_derived", table_name="environmental_observations")
    op.drop_index("uq_env_obs_forecast", table_name="environmental_observations")
    op.drop_index("uq_env_obs_model_analysis", table_name="environmental_observations")
    op.drop_index("uq_env_obs_ground_and_reanalysis", table_name="environmental_observations")

    # 3. Drop standard indexes
    op.drop_index("ix_environmental_observations_typology", table_name="environmental_observations")
    op.drop_index("ix_environmental_observations_location_id", table_name="environmental_observations")
    op.drop_index("ix_environmental_observations_valid_time_utc", table_name="environmental_observations")

    # 4. Drop check constraints
    op.drop_constraint("ck_env_obs_derived_metadata", "environmental_observations", type_="check")
    op.drop_constraint("ck_env_obs_forecast_metadata", "environmental_observations", type_="check")
    op.drop_constraint("ck_env_obs_surface_pressure_hpa", "environmental_observations", type_="check")

    # 5. Drop added columns
    op.drop_column("environmental_observations", "retrieved_at_utc")
    op.drop_column("environmental_observations", "source_fingerprint")
    op.drop_column("environmental_observations", "algorithm_version")
    op.drop_column("environmental_observations", "algorithm_name")
    op.drop_column("environmental_observations", "lead_time_hours")
    op.drop_column("environmental_observations", "init_time_utc")
    op.drop_column("environmental_observations", "surface_pressure_hpa")
    op.drop_column("environmental_observations", "valid_time_utc")
    op.drop_column("environmental_observations", "dataset_or_model")
    op.drop_column("environmental_observations", "provider")
    op.drop_column("environmental_observations", "typology")
    op.drop_column("environmental_observations", "location")
    op.drop_column("environmental_observations", "resolved_longitude")
    op.drop_column("environmental_observations", "resolved_latitude")
    op.drop_column("environmental_observations", "requested_longitude")
    op.drop_column("environmental_observations", "requested_latitude")
    op.drop_column("environmental_observations", "location_id")
    op.drop_column("environmental_observations", "location_type")

    # 6. Revert incident_id nullable
    op.alter_column(
        "environmental_observations",
        "incident_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
