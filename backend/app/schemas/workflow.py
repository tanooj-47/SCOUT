"""
backend/app/schemas/workflow.py
Pydantic schemas for Disaster Response Workflow public API endpoints (Milestone 12.5).
Covers workflow execution requests/responses, state queries, listing/pagination,
and the human approval lifecycle.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.agents.schemas import (
    DisasterResponseWorkflowRequest,
    HumanApprovalStatus,
    WorkflowStage,
    WorkflowStatus,
)


class WorkflowCreateRequest(DisasterResponseWorkflowRequest):
    """Alias/extension of DisasterResponseWorkflowRequest for API consistency."""
    pass


class WorkflowCreateResponse(BaseModel):
    """Response returned upon initiating a disaster response workflow."""

    model_config = ConfigDict(extra="forbid")

    workflow_id: str = Field(..., description="Unique workflow execution identifier")
    request_id: str = Field(..., description="Unique source request identifier")
    disaster_type: str = Field(..., description="Disaster hazard type (e.g. wildfire)")
    status: WorkflowStatus = Field(..., description="Current workflow lifecycle status")
    stage: WorkflowStage = Field(..., description="Current active workflow stage")
    location: Dict[str, float] = Field(..., description="Target coordinates: latitude and longitude")
    search_radius_meters: float = Field(..., description="Geospatial search radius in meters")
    approval_status: str = Field(..., description="Human approval gate status (e.g. pending)")
    execution_records_count: int = Field(..., description="Number of agent execution records produced")
    has_coordinator_report: bool = Field(..., description="Whether coordinator synthesis report is present")
    created_at: datetime = Field(..., description="Creation timestamp in UTC")
    updated_at: datetime = Field(..., description="Last update timestamp in UTC")


class WorkflowSummaryItem(BaseModel):
    """Compact workflow record for list and pagination responses."""

    model_config = ConfigDict(extra="forbid")

    workflow_id: str
    request_id: str
    disaster_type: str
    workflow_status: str
    workflow_stage: str
    approval_status: str
    latitude: float
    longitude: float
    search_radius_meters: float
    version: int
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None


class WorkflowListResponse(BaseModel):
    """Paginated collection of workflow summary items."""

    model_config = ConfigDict(extra="forbid")

    total: int = Field(..., ge=0, description="Total number of matching records")
    skip: int = Field(..., ge=0, description="Number of skipped items")
    limit: int = Field(..., ge=1, description="Page limit applied")
    items: List[WorkflowSummaryItem] = Field(default_factory=list)


class WorkflowDetailResponse(BaseModel):
    """Comprehensive details of an executed or active disaster workflow."""

    model_config = ConfigDict(extra="forbid")

    workflow_id: str
    request_id: str
    disaster_type: str
    workflow_status: str
    workflow_stage: str
    location: Dict[str, float]
    search_radius_meters: float
    source_description: Optional[str] = None
    approval_status: str
    version: int
    intelligence_assessment: Optional[Dict[str, Any]] = None
    weather_interpretation: Optional[Dict[str, Any]] = None
    geospatial_context: Optional[Dict[str, Any]] = None
    risk_assessment: Optional[Dict[str, Any]] = None
    response_plan: Optional[Dict[str, Any]] = None
    coordinator_report: Optional[Dict[str, Any]] = None
    execution_records: List[Dict[str, Any]] = Field(default_factory=list)
    errors: List[Dict[str, Any]] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None


class PendingApprovalItem(BaseModel):
    """Advisory response plan awaiting human review."""

    model_config = ConfigDict(extra="forbid")

    workflow_id: str
    plan_id: str
    disaster_type: str
    location: Dict[str, float]
    threat_level: str
    incident_status: str
    approval_status: str
    recommendations_count: int
    requires_approval: bool
    created_at: datetime


class WorkflowApprovalRequest(BaseModel):
    """Request payload for submitting a human review decision."""

    model_config = ConfigDict(extra="forbid")

    decision: HumanApprovalStatus = Field(
        ...,
        description="Explicit review decision: approved, rejected, or needs_revision",
    )
    reviewer_comments: Optional[str] = Field(
        None,
        max_length=2000,
        description="Optional operational notes or review context",
    )
    rejection_or_revision_reason: Optional[str] = Field(
        None,
        max_length=2000,
        description="Mandatory written justification if rejecting or requesting revision",
    )


class WorkflowApprovalResponse(BaseModel):
    """Response returned upon recording a human approval decision."""

    model_config = ConfigDict(extra="forbid")

    workflow_id: str
    plan_id: str
    previous_status: str
    new_status: str
    workflow_status: str
    reviewer_id: str
    reviewer_comments: Optional[str] = None
    rejection_or_revision_reason: Optional[str] = None
    decided_at: datetime


class ApprovalHistoryItem(BaseModel):
    """Single auditable record of an approval lifecycle transition."""

    model_config = ConfigDict(extra="forbid")

    id: str
    workflow_id: str
    plan_id: str
    previous_status: str
    new_status: str
    reviewer_id: str
    reviewer_comments: Optional[str] = None
    rejection_or_revision_reason: Optional[str] = None
    decision_type: Optional[str] = None
    created_at: datetime


class ApprovalHistoryResponse(BaseModel):
    """Complete chronological audit history of human review decisions."""

    model_config = ConfigDict(extra="forbid")

    workflow_id: str
    total_decisions: int
    history: List[ApprovalHistoryItem] = Field(default_factory=list)
