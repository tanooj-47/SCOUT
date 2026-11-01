"""disaster_workflow_records

Revision ID: 0004_disaster_workflow_records
Revises: 0003_persistent_geospatial_features
Create Date: 2026-11-01 10:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0004_disaster_workflow_records"
down_revision: Union[str, None] = "0003_persistent_geospatial_features"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create disaster_workflow_records table
    op.create_table(
        "disaster_workflow_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("workflow_id", sa.String(length=64), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("disaster_type", sa.String(length=32), nullable=False),
        sa.Column("workflow_status", sa.String(length=32), nullable=False, server_default="initialized"),
        sa.Column("workflow_stage", sa.String(length=64), nullable=False, server_default="initialized"),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("search_radius_meters", sa.Float(), nullable=False, server_default="5000.0"),
        sa.Column("request_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("execution_state", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("intelligence_assessment", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("weather_interpretation", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("geospatial_context", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("risk_assessment", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("response_plan", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("coordinator_report", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("approval_status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_disaster_workflow_records")),
        sa.UniqueConstraint("workflow_id", name=op.f("uq_disaster_workflow_records_workflow_id")),
    )

    op.create_index(
        op.f("ix_disaster_workflow_records_workflow_id"),
        "disaster_workflow_records",
        ["workflow_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_disaster_workflow_records_request_id"),
        "disaster_workflow_records",
        ["request_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_disaster_workflow_records_disaster_type"),
        "disaster_workflow_records",
        ["disaster_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_disaster_workflow_records_workflow_status"),
        "disaster_workflow_records",
        ["workflow_status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_disaster_workflow_records_approval_status"),
        "disaster_workflow_records",
        ["approval_status"],
        unique=False,
    )
    op.create_index(
        "ix_disaster_workflow_records_status_approval",
        "disaster_workflow_records",
        ["workflow_status", "approval_status"],
        unique=False,
    )
    op.create_index(
        "ix_disaster_workflow_records_created_at",
        "disaster_workflow_records",
        ["created_at"],
        unique=False,
    )

    # 2. Create workflow_approval_history table
    op.create_table(
        "workflow_approval_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("workflow_id", sa.String(length=64), nullable=False),
        sa.Column("plan_id", sa.String(length=64), nullable=False),
        sa.Column("previous_status", sa.String(length=32), nullable=False),
        sa.Column("new_status", sa.String(length=32), nullable=False),
        sa.Column("reviewer_id", sa.String(length=128), nullable=False),
        sa.Column("reviewer_comments", sa.Text(), nullable=True),
        sa.Column("rejection_or_revision_reason", sa.Text(), nullable=True),
        sa.Column("decision_type", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workflow_approval_history")),
    )

    op.create_index(
        op.f("ix_workflow_approval_history_workflow_id"),
        "workflow_approval_history",
        ["workflow_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_workflow_approval_history_plan_id"),
        "workflow_approval_history",
        ["plan_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_workflow_approval_history_reviewer_id"),
        "workflow_approval_history",
        ["reviewer_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_workflow_approval_history_created_at"),
        "workflow_approval_history",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    # 1. Drop workflow_approval_history
    op.drop_index(op.f("ix_workflow_approval_history_created_at"), table_name="workflow_approval_history")
    op.drop_index(op.f("ix_workflow_approval_history_reviewer_id"), table_name="workflow_approval_history")
    op.drop_index(op.f("ix_workflow_approval_history_plan_id"), table_name="workflow_approval_history")
    op.drop_index(op.f("ix_workflow_approval_history_workflow_id"), table_name="workflow_approval_history")
    op.drop_table("workflow_approval_history")

    # 2. Drop disaster_workflow_records
    op.drop_index("ix_disaster_workflow_records_created_at", table_name="disaster_workflow_records")
    op.drop_index("ix_disaster_workflow_records_status_approval", table_name="disaster_workflow_records")
    op.drop_index(op.f("ix_disaster_workflow_records_approval_status"), table_name="disaster_workflow_records")
    op.drop_index(op.f("ix_disaster_workflow_records_workflow_status"), table_name="disaster_workflow_records")
    op.drop_index(op.f("ix_disaster_workflow_records_disaster_type"), table_name="disaster_workflow_records")
    op.drop_index(op.f("ix_disaster_workflow_records_request_id"), table_name="disaster_workflow_records")
    op.drop_index(op.f("ix_disaster_workflow_records_workflow_id"), table_name="disaster_workflow_records")
    op.drop_table("disaster_workflow_records")
