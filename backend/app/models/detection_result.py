import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class DetectionResult(Base):
    """
    Inference outcomes produced by computer vision models evaluating uploaded media.
    """
    __tablename__ = "detection_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    media_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("uploaded_media.id", ondelete="RESTRICT"),
        nullable=False,
    )
    classification: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    bounding_boxes: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    model_name: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    model_version: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    inference_latency_ms: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    media: Mapped["UploadedMedia"] = relationship(
        "UploadedMedia",
        back_populates="detection_results",
    )

    __table_args__ = (
        CheckConstraint(
            "classification IN ('fire', 'smoke', 'neutral', 'floodwater')",
            name="ck_detection_results_classification",
        ),
        CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="ck_detection_results_confidence",
        ),
        CheckConstraint(
            "inference_latency_ms >= 0",
            name="ck_detection_results_inference_latency_ms",
        ),
        Index("ix_detection_results_media_id", "media_id"),
        Index("ix_detection_results_classification", "classification"),
        Index("ix_detection_results_created_at", "created_at"),
    )
