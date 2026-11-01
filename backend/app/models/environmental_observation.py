import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional

from geoalchemy2 import Geometry
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class EnvironmentalObservation(Base):
    """
    Environmental and meteorological observations representing atmospheric state bundles.
    Can be tied directly to an incident (incident_id) or exist independently and associated
    many-to-many via IncidentEnvironmentalObservation.
    """
    __tablename__ = "environmental_observations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    incident_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("incidents.id", ondelete="RESTRICT"),
        nullable=True,
    )
    location_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="grid",
    )
    location_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
    )
    requested_latitude: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )
    requested_longitude: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )
    resolved_latitude: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )
    resolved_longitude: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )
    location: Mapped[Optional[Any]] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=False),
        nullable=True,
    )
    typology: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="model_analysis",
    )
    provider: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="open-meteo",
    )
    dataset_or_model: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="best_match",
    )
    valid_time_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    source: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    temperature_celsius: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    relative_humidity: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    wind_speed_mps: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    wind_direction_degrees: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    precipitation_mm: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    surface_pressure_hpa: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    init_time_utc: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    lead_time_hours: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    algorithm_name: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
    )
    algorithm_version: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
    )
    source_fingerprint: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
    )
    retrieved_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    metrics_payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    incident: Mapped[Optional["Incident"]] = relationship(
        "Incident",
        back_populates="environmental_observations",
    )
    incident_associations: Mapped[List["IncidentEnvironmentalObservation"]] = relationship(
        "IncidentEnvironmentalObservation",
        back_populates="observation",
        cascade="all, delete-orphan",
    )
    hazard_predictions: Mapped[List["HazardPrediction"]] = relationship(
        "HazardPrediction",
        back_populates="primary_observation",
        passive_deletes="all",
    )

    __table_args__ = (
        CheckConstraint(
            "relative_humidity IS NULL OR (relative_humidity >= 0.0 AND relative_humidity <= 100.0)",
            name="ck_env_obs_relative_humidity",
        ),
        CheckConstraint(
            "wind_speed_mps IS NULL OR wind_speed_mps >= 0.0",
            name="ck_env_obs_wind_speed_mps",
        ),
        CheckConstraint(
            "wind_direction_degrees IS NULL OR (wind_direction_degrees >= 0.0 AND wind_direction_degrees <= 360.0)",
            name="ck_env_obs_wind_direction_degrees",
        ),
        CheckConstraint(
            "precipitation_mm IS NULL OR precipitation_mm >= 0.0",
            name="ck_env_obs_precipitation_mm",
        ),
        CheckConstraint(
            "surface_pressure_hpa IS NULL OR (surface_pressure_hpa >= 300.0 AND surface_pressure_hpa <= 1100.0)",
            name="ck_env_obs_surface_pressure_hpa",
        ),
        CheckConstraint(
            "typology != 'forecast' OR (init_time_utc IS NOT NULL AND lead_time_hours >= 0.0)",
            name="ck_env_obs_forecast_metadata",
        ),
        CheckConstraint(
            "typology != 'derived' OR (algorithm_name IS NOT NULL AND algorithm_version IS NOT NULL AND source_fingerprint IS NOT NULL)",
            name="ck_env_obs_derived_metadata",
        ),
        Index("ix_environmental_observations_incident_id", "incident_id"),
        Index("ix_environmental_observations_recorded_at", "recorded_at"),
        Index("ix_environmental_observations_valid_time_utc", "valid_time_utc"),
        Index("ix_environmental_observations_location_id", "location_id"),
        Index("ix_environmental_observations_typology", "typology"),
        Index(
            "ix_environmental_observations_incident_recorded",
            "incident_id",
            text("recorded_at DESC"),
        ),
        Index(
            "uq_env_obs_ground_and_reanalysis",
            "location_type",
            "location_id",
            "provider",
            "dataset_or_model",
            "typology",
            "valid_time_utc",
            unique=True,
            postgresql_where=text("typology IN ('station_observed', 'reanalysis')"),
        ),
        Index(
            "uq_env_obs_model_analysis",
            "location_type",
            "location_id",
            "provider",
            "dataset_or_model",
            "valid_time_utc",
            unique=True,
            postgresql_where=text("typology = 'model_analysis'"),
        ),
        Index(
            "uq_env_obs_forecast",
            "location_type",
            "location_id",
            "provider",
            "dataset_or_model",
            "valid_time_utc",
            "init_time_utc",
            "lead_time_hours",
            unique=True,
            postgresql_where=text("typology = 'forecast'"),
        ),
        Index(
            "uq_env_obs_derived",
            "location_type",
            "location_id",
            "algorithm_name",
            "algorithm_version",
            "valid_time_utc",
            "source_fingerprint",
            unique=True,
            postgresql_where=text("typology = 'derived'"),
        ),
    )


class IncidentEnvironmentalObservation(Base):
    """
    Many-to-many association mapping incidents to environmental observations.
    Allows independent grid or station observations to be shared across incidents.
    """
    __tablename__ = "incident_environmental_observations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
    )
    observation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("environmental_observations.id", ondelete="CASCADE"),
        nullable=False,
    )
    association_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="spatial_proximity",
    )
    distance_meters: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    incident: Mapped["Incident"] = relationship(
        "Incident",
        back_populates="observation_associations",
    )
    observation: Mapped["EnvironmentalObservation"] = relationship(
        "EnvironmentalObservation",
        back_populates="incident_associations",
    )

    __table_args__ = (
        UniqueConstraint("incident_id", "observation_id", name="uq_incident_env_obs"),
        Index("ix_incident_env_obs_incident", "incident_id"),
        Index("ix_incident_env_obs_observation", "observation_id"),
    )
