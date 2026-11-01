import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from geoalchemy2 import Geometry
from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class HazardPrediction(Base):
    """
    Append-only predictive hazard forecast.
    Preserves historical projected hazard footprints and immutable simulation
    provenance via input_snapshot.
    """
    __tablename__ = "hazard_predictions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("incidents.id", ondelete="RESTRICT"),
        nullable=False,
    )
    primary_observation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("environmental_observations.id", ondelete="RESTRICT"),
        nullable=True,
    )
    forecast_horizon_hours: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    projected_area_hectares: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    predicted_footprint: Mapped[Any] = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=4326, spatial_index=False),
        nullable=False,
    )
    risk_level: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    model_name: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    model_version: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    input_snapshot: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    incident: Mapped["Incident"] = relationship(
        "Incident",
        back_populates="hazard_predictions",
    )
    primary_observation: Mapped[Optional["EnvironmentalObservation"]] = relationship(
        "EnvironmentalObservation",
        back_populates="hazard_predictions",
    )

    __table_args__ = (
        CheckConstraint(
            "forecast_horizon_hours > 0.0",
            name="ck_hazard_predictions_forecast_horizon_hours",
        ),
        CheckConstraint(
            "projected_area_hectares >= 0.0",
            name="ck_hazard_predictions_projected_area_hectares",
        ),
        CheckConstraint(
            "risk_level IN ('low', 'moderate', 'high', 'critical')",
            name="ck_hazard_predictions_risk_level",
        ),
        Index("ix_hazard_predictions_incident_id", "incident_id"),
        Index("ix_hazard_predictions_primary_observation_id", "primary_observation_id"),
        Index("ix_hazard_predictions_created_at", "created_at"),
        Index("ix_hazard_predictions_risk_level", "risk_level"),
        Index(
            "ix_hazard_predictions_incident_horizon",
            "incident_id",
            "forecast_horizon_hours",
        ),
        Index(
            "ix_hazard_predictions_predicted_footprint",
            "predicted_footprint",
            postgresql_using="gist",
        ),
        Index(
            "ix_hazard_predictions_footprint_geography",
            text("(predicted_footprint::geography)"),
            postgresql_using="gist",
        ),
    )
