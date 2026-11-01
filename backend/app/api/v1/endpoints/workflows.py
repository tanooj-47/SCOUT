"""
backend/app/api/v1/endpoints/workflows.py
Public REST API endpoints for SCOUT Disaster Response Multi-Agent Workflows (Milestone 12.5).
Exposes workflow initiation, status retrieval, pagination, filtering, pending approval queue,
authenticated approval decision submission, and full audit history.
"""

from datetime import datetime
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.agents.schemas import HumanApprovalStatus, WorkflowStage, WorkflowStatus
from app.agents.services.workflow_service import DisasterWorkflowService
from app.core.auth import get_authenticated_reviewer
from app.db.session import get_db
from app.schemas.workflow import (
    ApprovalHistoryItem,
    ApprovalHistoryResponse,
    PendingApprovalItem,
    WorkflowApprovalRequest,
    WorkflowApprovalResponse,
    WorkflowCreateRequest,
    WorkflowCreateResponse,
    WorkflowDetailResponse,
    WorkflowListResponse,
    WorkflowSummaryItem,
)

logger = logging.getLogger(__name__)

router = APIRouter()
_workflow_service = DisasterWorkflowService()


# ---------------------------------------------------------------------------
# 1. Create and Execute Workflow
# ---------------------------------------------------------------------------

@router.post(
    "",
    response_model=WorkflowCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Initiate Disaster Response Workflow",
    description=(
        "Submits a disaster observation request, executes the LangGraph multi-agent "
        "intelligence and response planning pipeline, and persists the resulting workflow record."
    ),
)
def create_workflow(
    request: WorkflowCreateRequest,
    db: Session = Depends(get_db),
) -> WorkflowCreateResponse:
    """
    Launches end-to-end multi-agent disaster response workflow from an observation request.
    """
    logger.info("Initiating disaster response workflow for hazard '%s'", request.disaster_type.value)
    record = _workflow_service.create_and_run_workflow(request=request, db=db)

    exec_records = record.execution_state.get("records", []) if record.execution_state else []

    return WorkflowCreateResponse(
        workflow_id=record.workflow_id,
        request_id=record.request_id,
        disaster_type=record.disaster_type,
        status=WorkflowStatus(record.workflow_status),
        stage=WorkflowStage(record.workflow_stage),
        location={"latitude": record.latitude, "longitude": record.longitude},
        search_radius_meters=record.search_radius_meters,
        approval_status=record.approval_status,
        execution_records_count=len(exec_records),
        has_coordinator_report=record.coordinator_report is not None,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


# ---------------------------------------------------------------------------
# 2. Retrieve Pending Approvals (Must precede /{workflow_id})
# ---------------------------------------------------------------------------

@router.get(
    "/pending-approvals",
    response_model=List[PendingApprovalItem],
    status_code=status.HTTP_200_OK,
    summary="Retrieve Pending Human Approvals",
    description="Returns all response plans awaiting review by an authorized incident commander.",
)
def list_pending_approvals(
    db: Session = Depends(get_db),
) -> List[PendingApprovalItem]:
    """
    Lists workflows halted at the human review gate awaiting authorized decision.
    """
    records = _workflow_service.list_pending_approvals(db=db)
    items: List[PendingApprovalItem] = []

    for rec in records:
        plan = rec.response_plan or {}
        recs = plan.get("recommendations", [])
        items.append(
            PendingApprovalItem(
                workflow_id=rec.workflow_id,
                plan_id=plan.get("plan_id", "unassigned"),
                disaster_type=rec.disaster_type,
                location={"latitude": rec.latitude, "longitude": rec.longitude},
                threat_level=plan.get("assessed_threat_level", "UNKNOWN"),
                incident_status=plan.get("incident_status", "UNKNOWN"),
                approval_status=rec.approval_status,
                recommendations_count=len(recs),
                requires_approval=True,
                created_at=rec.created_at,
            )
        )
    return items


# ---------------------------------------------------------------------------
# 3. List Workflows (Paginated with Filters)
# ---------------------------------------------------------------------------

@router.get(
    "",
    response_model=WorkflowListResponse,
    status_code=status.HTTP_200_OK,
    summary="List Disaster Workflows",
    description="Returns a paginated list of workflow records with optional hazard and status filters.",
)
def list_workflows(
    skip: int = Query(0, ge=0, description="Items to skip"),
    limit: int = Query(50, ge=1, le=100, description="Page limit (max 100)"),
    disaster_type: Optional[str] = Query(None, description="Filter by disaster type (e.g. wildfire)"),
    workflow_status: Optional[str] = Query(None, description="Filter by workflow status"),
    approval_status: Optional[str] = Query(None, description="Filter by approval status"),
    start_date: Optional[datetime] = Query(None, description="Filter records created on or after UTC datetime"),
    end_date: Optional[datetime] = Query(None, description="Filter records created on or before UTC datetime"),
    db: Session = Depends(get_db),
) -> WorkflowListResponse:
    """
    Retrieves filtered and paginated workflow summaries.
    """
    # Normalize params when invoked directly as python function
    clean_skip = skip if isinstance(skip, int) else 0
    clean_limit = limit if isinstance(limit, int) else 50
    clean_disaster = disaster_type if isinstance(disaster_type, str) else None
    clean_wf_status = workflow_status if isinstance(workflow_status, str) else None
    clean_appr_status = approval_status if isinstance(approval_status, str) else None
    clean_start_date = start_date if isinstance(start_date, datetime) else None
    clean_end_date = end_date if isinstance(end_date, datetime) else None

    total, records = _workflow_service.list_workflows(
        db=db,
        skip=clean_skip,
        limit=clean_limit,
        disaster_type=clean_disaster,
        workflow_status=clean_wf_status,
        approval_status=clean_appr_status,
        start_date=clean_start_date,
        end_date=clean_end_date,
    )

    items = [
        WorkflowSummaryItem(
            workflow_id=rec.workflow_id,
            request_id=rec.request_id,
            disaster_type=rec.disaster_type,
            workflow_status=rec.workflow_status,
            workflow_stage=rec.workflow_stage,
            approval_status=rec.approval_status,
            latitude=rec.latitude,
            longitude=rec.longitude,
            search_radius_meters=rec.search_radius_meters,
            version=rec.version,
            created_at=rec.created_at,
            updated_at=rec.updated_at,
            completed_at=rec.completed_at,
        )
        for rec in records
    ]

    return WorkflowListResponse(
        total=total,
        skip=clean_skip,
        limit=clean_limit,
        items=items,
    )


# ---------------------------------------------------------------------------
# 4. Retrieve Workflow Details
# ---------------------------------------------------------------------------

@router.get(
    "/{workflow_id}",
    response_model=WorkflowDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve Disaster Workflow Details",
    description="Returns complete execution state, agent outputs, and approval status for a specific workflow.",
)
def get_workflow_details(
    workflow_id: str,
    db: Session = Depends(get_db),
) -> WorkflowDetailResponse:
    """
    Retrieves full workflow detail record by workflow_id.
    """
    record = _workflow_service.get_workflow_by_id(workflow_id=workflow_id, db=db)

    exec_state = record.execution_state or {}
    exec_records = exec_state.get("records", [])
    errors = exec_state.get("errors", [])
    warnings = exec_state.get("warnings", [])

    return WorkflowDetailResponse(
        workflow_id=record.workflow_id,
        request_id=record.request_id,
        disaster_type=record.disaster_type,
        workflow_status=record.workflow_status,
        workflow_stage=record.workflow_stage,
        location={"latitude": record.latitude, "longitude": record.longitude},
        search_radius_meters=record.search_radius_meters,
        source_description=record.request_payload.get("source_description") if record.request_payload else None,
        approval_status=record.approval_status,
        version=record.version,
        intelligence_assessment=record.intelligence_assessment,
        weather_interpretation=record.weather_interpretation,
        geospatial_context=record.geospatial_context,
        risk_assessment=record.risk_assessment,
        response_plan=record.response_plan,
        coordinator_report=record.coordinator_report,
        execution_records=exec_records,
        errors=errors,
        warnings=warnings,
        created_at=record.created_at,
        updated_at=record.updated_at,
        completed_at=record.completed_at,
    )


# ---------------------------------------------------------------------------
# 5. Submit Human Approval Decision
# ---------------------------------------------------------------------------

@router.post(
    "/{workflow_id}/approval",
    response_model=WorkflowApprovalResponse,
    status_code=status.HTTP_200_OK,
    summary="Submit Human Approval Decision",
    description=(
        "Applies an authorized human approval, rejection, or revision decision. "
        "Reviewer identity is strictly authenticated from request security headers. "
        "Approving a plan does NOT trigger autonomous dispatch or alert execution."
    ),
)
def submit_approval_decision(
    workflow_id: str,
    payload: WorkflowApprovalRequest,
    reviewer_id: str = Depends(get_authenticated_reviewer),
    db: Session = Depends(get_db),
) -> WorkflowApprovalResponse:
    """
    Records an authorized human review decision at the approval gate.
    """
    # Enforce mandatory explanation when rejecting or requesting revision
    if payload.decision in (HumanApprovalStatus.REJECTED, HumanApprovalStatus.NEEDS_REVISION):
        if not payload.rejection_or_revision_reason or not payload.rejection_or_revision_reason.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Rejection or revision reason is mandatory when decision is '{payload.decision.value}'.",
            )

    record, history = _workflow_service.apply_persistent_approval(
        workflow_id=workflow_id,
        decision=payload.decision,
        reviewer_id=reviewer_id,
        reviewer_comments=payload.reviewer_comments,
        rejection_or_revision_reason=payload.rejection_or_revision_reason,
        db=db,
    )

    return WorkflowApprovalResponse(
        workflow_id=record.workflow_id,
        plan_id=history.plan_id,
        previous_status=history.previous_status,
        new_status=history.new_status,
        workflow_status=record.workflow_status,
        reviewer_id=history.reviewer_id,
        reviewer_comments=history.reviewer_comments,
        rejection_or_revision_reason=history.rejection_or_revision_reason,
        decided_at=history.created_at,
    )


# ---------------------------------------------------------------------------
# 6. Retrieve Approval History
# ---------------------------------------------------------------------------

@router.get(
    "/{workflow_id}/approval-history",
    response_model=ApprovalHistoryResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve Approval Audit History",
    description="Returns the complete chronological sequence of review decisions recorded for a workflow.",
)
def get_approval_history(
    workflow_id: str,
    db: Session = Depends(get_db),
) -> ApprovalHistoryResponse:
    """
    Retrieves immutable audit trail of human review actions for a workflow.
    """
    history_records = _workflow_service.get_approval_history(workflow_id=workflow_id, db=db)

    items = [
        ApprovalHistoryItem(
            id=str(h.id),
            workflow_id=h.workflow_id,
            plan_id=h.plan_id,
            previous_status=h.previous_status,
            new_status=h.new_status,
            reviewer_id=h.reviewer_id,
            reviewer_comments=h.reviewer_comments,
            rejection_or_revision_reason=h.rejection_or_revision_reason,
            decision_type=h.decision_type,
            created_at=h.created_at,
        )
        for h in history_records
    ]

    return ApprovalHistoryResponse(
        workflow_id=workflow_id,
        total_decisions=len(items),
        history=items,
    )
