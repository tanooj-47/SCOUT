"""
backend/app/models/workflow.py
SQLAlchemy ORM models for multi-agent disaster workflow persistence and approval audit history.
Milestone 12.5.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
import uuid

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    Index,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DisasterWorkflowRecord(Base):
    """
    Persistent representation of an executed or active multi-agent disaster response workflow.
    Stores durable snapshot of input parameters, agent outputs, execution state, and lifecycle status.
    Uses version column for optimistic concurrency control during human approval state transitions.
    """
    __tablename__ = "disaster_workflow_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    workflow_id: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
    )
    request_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    disaster_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
    )
    workflow_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
        default="initialized",
    )
    workflow_stage: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="initialized",
    )
    latitude: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    longitude: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    search_radius_meters: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=5000.0,
    )

    # Structured Payloads and State Snapshots
    request_payload: Mapped[Dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
    )
    execution_state: Mapped[Dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
    )

    # Structured Agent Artifacts
    intelligence_assessment: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=True,
    )
    weather_interpretation: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=True,
    )
    geospatial_context: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=True,
    )
    risk_assessment: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=True,
    )
    response_plan: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=True,
    )
    coordinator_report: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=True,
    )

    # Human Review & Approval Metadata
    approval_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending",
        index=True,
    )

    # Optimistic Concurrency Control
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        Index("ix_disaster_workflow_records_status_approval", "workflow_status", "approval_status"),
        Index("ix_disaster_workflow_records_created_at", "created_at"),
    )


class WorkflowApprovalHistory(Base):
    """
    Append-only audit record of every human approval decision or transition
    applied to a response plan within a disaster workflow.
    Guarantees non-repudiation and immutable review audit trail.
    """
    __tablename__ = "workflow_approval_history"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    workflow_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    plan_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    previous_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    new_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    reviewer_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
    )
    reviewer_comments: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    rejection_or_revision_reason: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    decision_type: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
