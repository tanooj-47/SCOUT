import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional

from geoalchemy2 import Geometry
from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Incident(Base):
    """
    Central aggregate root representing an authoritative disaster event
    in physical space and time.
    """
    __tablename__ = "incidents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    disaster_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="reported",
    )
    severity: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="low",
    )
    location: Mapped[Any] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=False),
        nullable=False,
    )
    observed_perimeter: Mapped[Optional[Any]] = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=4326, spatial_index=False),
        nullable=True,
    )
    perimeter_updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    reported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    contained_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    is_archived: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    archived_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    # Database column name is 'metadata'; mapped via incident_metadata to avoid
    # colliding with SQLAlchemy DeclarativeBase.metadata namespace.
    incident_metadata: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
    )

    # Relationships (Strict RESTRICT policy - no cascading deletions)
    uploaded_media: Mapped[List["UploadedMedia"]] = relationship(
        "UploadedMedia",
        back_populates="incident",
        passive_deletes="all",
    )
    environmental_observations: Mapped[List["EnvironmentalObservation"]] = relationship(
        "EnvironmentalObservation",
        back_populates="incident",
        passive_deletes="all",
    )
    observation_associations: Mapped[List["IncidentEnvironmentalObservation"]] = relationship(
        "IncidentEnvironmentalObservation",
        back_populates="incident",
        cascade="all, delete-orphan",
    )
    hazard_predictions: Mapped[List["HazardPrediction"]] = relationship(
        "HazardPrediction",
        back_populates="incident",
        passive_deletes="all",
    )

    __table_args__ = (
        CheckConstraint(
            "disaster_type IN ('wildfire', 'flood', 'earthquake')",
            name="ck_incidents_disaster_type",
        ),
        CheckConstraint(
            "status IN ('reported', 'investigating', 'active', 'contained', 'resolved', 'false_alarm')",
            name="ck_incidents_status",
        ),
        CheckConstraint(
            "severity IN ('low', 'moderate', 'high', 'critical')",
            name="ck_incidents_severity",
        ),
        CheckConstraint(
            "(is_archived = false AND archived_at IS NULL) OR (is_archived = true AND archived_at IS NOT NULL)",
            name="ck_incidents_archival_consistency",
        ),
        Index("ix_incidents_location", "location", postgresql_using="gist"),
        Index(
            "ix_incidents_location_geography",
            text("(location::geography)"),
            postgresql_using="gist",
        ),
        Index("ix_incidents_observed_perimeter", "observed_perimeter", postgresql_using="gist"),
        Index("ix_incidents_status_is_archived", "status", "is_archived"),
    )
