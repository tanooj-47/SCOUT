import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional

from geoalchemy2 import Geometry
from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class UploadedMedia(Base):
    """
    Metadata for visual and remote sensing assets (drone images, satellite scenes, field camera frames).
    Actual binary payloads reside outside PostgreSQL in local storage or object stores.
    """
    __tablename__ = "uploaded_media"

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
    storage_path: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
    )
    media_format: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    source_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    file_size_bytes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    capture_location: Mapped[Optional[Any]] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=False),
        nullable=True,
    )
    captured_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    incident: Mapped[Optional["Incident"]] = relationship(
        "Incident",
        back_populates="uploaded_media",
    )
    detection_results: Mapped[List["DetectionResult"]] = relationship(
        "DetectionResult",
        back_populates="media",
        passive_deletes="all",
    )

    __table_args__ = (
        CheckConstraint(
            "file_size_bytes >= 0",
            name="ck_uploaded_media_file_size_bytes",
        ),
        Index("ix_uploaded_media_incident_id", "incident_id"),
        Index("ix_uploaded_media_captured_at", "captured_at"),
        Index("ix_uploaded_media_capture_location", "capture_location", postgresql_using="gist"),
    )
