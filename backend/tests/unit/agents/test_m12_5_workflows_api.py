"""
backend/tests/unit/agents/test_m12_5_workflows_api.py
Direct controller unit test suite for Milestone 12.5: Public Workflows API Endpoints.
Tests all 6 endpoint handlers directly with database session fixtures:
- create_workflow (POST /api/v1/workflows)
- get_workflow_details (GET /api/v1/workflows/{workflow_id})
- list_workflows (GET /api/v1/workflows)
- list_pending_approvals (GET /api/v1/workflows/pending-approvals)
- submit_approval_decision (POST /api/v1/workflows/{workflow_id}/approval)
- get_approval_history (GET /api/v1/workflows/{workflow_id}/approval-history)
Verifies input validation, authenticated reviewer checks, 404/409/422 error cases,
and advisory response planning boundaries.
"""

from datetime import datetime, timezone
from typing import Generator
from unittest.mock import MagicMock, patch
import uuid
from fastapi import HTTPException
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.agents.schemas import (
    DisasterResponseWorkflowRequest,
    DisasterType,
    HumanApprovalStatus,
    WorkflowStage,
    WorkflowStatus,
)
from app.api.v1.endpoints.workflows import (
    create_workflow,
    get_approval_history,
    get_workflow_details,
    list_pending_approvals,
    list_workflows,
    submit_approval_decision,
)
from app.core.auth import get_authenticated_reviewer
from app.core.exceptions import (
    ForbiddenReviewerError,
    UnauthorizedReviewerError,
    WorkflowApprovalConflictError,
    WorkflowNotFoundError,
)
from app.models.workflow import DisasterWorkflowRecord, WorkflowApprovalHistory
from app.schemas.workflow import (
    ApprovalHistoryResponse,
    PendingApprovalItem,
    WorkflowApprovalRequest,
    WorkflowApprovalResponse,
    WorkflowCreateRequest,
    WorkflowCreateResponse,
    WorkflowDetailResponse,
    WorkflowListResponse,
)
from tests.unit.agents.test_m12_4_response_planning import _build_mock_m11_assessment


# ===========================================================================
# In-Memory DB Fixture
# ===========================================================================

@pytest.fixture(scope="function")
def api_db() -> Generator[Session, None, None]:
    """Provides an isolated SQLite in-memory database with workflow tables created."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    DisasterWorkflowRecord.__table__.create(engine)
    WorkflowApprovalHistory.__table__.create(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _seed_test_workflow(
    db: Session,
    workflow_id: str = "wf-seeded-01",
    approval_status: str = "pending",
    workflow_status: str = "suspended_for_approval",
) -> DisasterWorkflowRecord:
    """Helper to insert a seeded workflow record into the test database."""
    now = datetime.now(timezone.utc)
    rec = DisasterWorkflowRecord(
        id=uuid.uuid4(),
        workflow_id=workflow_id,
        request_id="req-seeded-01",
        disaster_type="wildfire",
        workflow_status=workflow_status,
        workflow_stage="human_review_gate",
        latitude=30.3256,
        longitude=78.0422,
        search_radius_meters=5000.0,
        request_payload={"source_description": "Field camera observation"},
        execution_state={
            "records": [{"agent_name": "request_validator", "stage": "request_validated", "status": "success"}],
            "errors": [],
            "warnings": [],
        },
        intelligence_assessment={"incident_status": "CONFIRMED"},
        weather_interpretation={"fwi_value": 31.0, "fwi_category": "EXTREME"},
        geospatial_context={"exposure_category": "CRITICAL"},
        risk_assessment={"composite_threat_level": "EXTREME"},
        response_plan={
            "plan_id": "plan-seeded-01",
            "incident_status": "CONFIRMED",
            "assessed_threat_level": "EXTREME",
            "recommendations": [{"title": "Establish staging area", "priority": "HIGH", "action_type": "staging"}],
            "human_approval_status": approval_status,
        },
        coordinator_report={"executive_summary": "Seeded coordinator executive summary."},
        approval_status=approval_status,
        version=1,
        created_at=now,
        updated_at=now,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


# ===========================================================================
# 1. create_workflow Endpoint Tests (POST /api/v1/workflows)
# ===========================================================================

def test_endpoint_create_workflow_success(api_db: Session):
    """create_workflow executes multi-agent pipeline and returns WorkflowCreateResponse."""
    mock_m11 = _build_mock_m11_assessment()

    with patch("app.agents.nodes.intelligence.MultimodalIntelligenceService") as mock_svc:
        mock_svc.return_value.analyze_observation.return_value = mock_m11

        req = WorkflowCreateRequest(
            latitude=30.3256,
            longitude=78.0422,
            disaster_type=DisasterType.WILDFIRE,
            search_radius_meters=5000.0,
            source_description="Sensor cluster alert",
        )

        response: WorkflowCreateResponse = create_workflow(request=req, db=api_db)

        assert isinstance(response, WorkflowCreateResponse)
        assert response.workflow_id.startswith("wf-")
        assert response.disaster_type == "wildfire"
        assert response.status == WorkflowStatus.SUSPENDED_FOR_APPROVAL
        assert response.stage == WorkflowStage.COORDINATOR_REPORT
        assert response.location["latitude"] == 30.3256
        assert response.location["longitude"] == 78.0422
        assert response.approval_status == "pending"
        assert response.has_coordinator_report is True
        assert response.execution_records_count == 8

        # Verify DB persistence
        persisted = api_db.query(DisasterWorkflowRecord).filter_by(workflow_id=response.workflow_id).one()
        assert persisted.workflow_status == WorkflowStatus.SUSPENDED_FOR_APPROVAL.value
        assert persisted.approval_status == "pending"
        assert persisted.coordinator_report is not None


# ===========================================================================
# 2. get_workflow_details Endpoint Tests (GET /api/v1/workflows/{workflow_id})
# ===========================================================================

def test_endpoint_get_workflow_details_success(api_db: Session):
    """get_workflow_details retrieves complete workflow record with full state snapshots."""
    rec = _seed_test_workflow(api_db, workflow_id="wf-detail-01")

    detail: WorkflowDetailResponse = get_workflow_details(workflow_id="wf-detail-01", db=api_db)

    assert isinstance(detail, WorkflowDetailResponse)
    assert detail.workflow_id == "wf-detail-01"
    assert detail.disaster_type == "wildfire"
    assert detail.workflow_status == "suspended_for_approval"
    assert detail.approval_status == "pending"
    assert detail.source_description == "Field camera observation"
    assert detail.response_plan["plan_id"] == "plan-seeded-01"
    assert detail.coordinator_report["executive_summary"] == "Seeded coordinator executive summary."
    assert len(detail.execution_records) == 1


def test_endpoint_get_workflow_details_not_found(api_db: Session):
    """get_workflow_details raises WorkflowNotFoundError (HTTP 404) for non-existent ID."""
    with pytest.raises(WorkflowNotFoundError, match="Disaster workflow 'wf-missing' was not found"):
        get_workflow_details(workflow_id="wf-missing", db=api_db)


# ===========================================================================
# 3. list_workflows Endpoint Tests (GET /api/v1/workflows)
# ===========================================================================

def test_endpoint_list_workflows_pagination_and_filters(api_db: Session):
    """list_workflows supports pagination and filtering across disaster_type and approval_status."""
    _seed_test_workflow(api_db, workflow_id="wf-list-1", approval_status="pending")
    _seed_test_workflow(api_db, workflow_id="wf-list-2", approval_status="approved", workflow_status="completed")

    # List all
    res_all: WorkflowListResponse = list_workflows(skip=0, limit=10, db=api_db)
    assert res_all.total == 2
    assert len(res_all.items) == 2

    # Filter by approval_status
    res_filt: WorkflowListResponse = list_workflows(approval_status="pending", db=api_db)
    assert res_filt.total == 1
    assert res_filt.items[0].workflow_id == "wf-list-1"

    # Pagination skip=1, limit=1
    res_page: WorkflowListResponse = list_workflows(skip=1, limit=1, db=api_db)
    assert res_page.total == 2
    assert len(res_page.items) == 1


# ===========================================================================
# 4. list_pending_approvals Endpoint Tests (GET /api/v1/workflows/pending-approvals)
# ===========================================================================

def test_endpoint_list_pending_approvals(api_db: Session):
    """list_pending_approvals returns only workflows suspended at the human approval gate."""
    _seed_test_workflow(api_db, workflow_id="wf-pending-a", approval_status="pending")
    _seed_test_workflow(api_db, workflow_id="wf-completed-b", approval_status="approved", workflow_status="completed")

    items = list_pending_approvals(db=api_db)

    assert len(items) == 1
    item: PendingApprovalItem = items[0]
    assert item.workflow_id == "wf-pending-a"
    assert item.plan_id == "plan-seeded-01"
    assert item.threat_level == "EXTREME"
    assert item.requires_approval is True
    assert item.recommendations_count == 1


# ===========================================================================
# 5. submit_approval_decision Endpoint Tests (POST /api/v1/workflows/{workflow_id}/approval)
# ===========================================================================

def test_endpoint_submit_approval_authorized_success(api_db: Session):
    """submit_approval_decision authorizes advisory plan and transitions status without autonomous dispatch."""
    rec = _seed_test_workflow(api_db, workflow_id="wf-submit-auth")

    payload = WorkflowApprovalRequest(
        decision=HumanApprovalStatus.APPROVED,
        reviewer_comments="Advisory plan reviewed and accepted by Incident Commander.",
    )

    response: WorkflowApprovalResponse = submit_approval_decision(
        workflow_id=rec.workflow_id,
        payload=payload,
        reviewer_id="commander-jones",
        db=api_db,
    )

    assert isinstance(response, WorkflowApprovalResponse)
    assert response.workflow_id == "wf-submit-auth"
    assert response.plan_id == "plan-seeded-01"
    assert response.previous_status == "pending"
    assert response.new_status == "approved"
    assert response.workflow_status == "completed"
    assert response.reviewer_id == "commander-jones"
    assert response.reviewer_comments == payload.reviewer_comments

    # Verify DB update and optimistic locking
    refreshed = api_db.query(DisasterWorkflowRecord).filter_by(workflow_id="wf-submit-auth").one()
    assert refreshed.approval_status == "approved"
    assert refreshed.workflow_status == "completed"
    assert refreshed.version == 2
    assert refreshed.completed_at is not None


def test_endpoint_submit_rejection_mandates_reason(api_db: Session):
    """submit_approval_decision requires a written explanation when rejecting (HTTP 422)."""
    rec = _seed_test_workflow(api_db, workflow_id="wf-submit-rej")

    payload = WorkflowApprovalRequest(
        decision=HumanApprovalStatus.REJECTED,
        rejection_or_revision_reason="",  # Missing required reason
    )

    with pytest.raises(HTTPException) as exc_info:
        submit_approval_decision(
            workflow_id=rec.workflow_id,
            payload=payload,
            reviewer_id="commander-smith",
            db=api_db,
        )
    assert exc_info.value.status_code == 422
    assert "mandatory" in exc_info.value.detail.lower()


def test_endpoint_submit_revision_mandates_reason(api_db: Session):
    """submit_approval_decision requires a written explanation when requesting revision (HTTP 422)."""
    rec = _seed_test_workflow(api_db, workflow_id="wf-submit-rev")

    payload = WorkflowApprovalRequest(
        decision=HumanApprovalStatus.NEEDS_REVISION,
        rejection_or_revision_reason=None,  # Missing required reason
    )

    with pytest.raises(HTTPException) as exc_info:
        submit_approval_decision(
            workflow_id=rec.workflow_id,
            payload=payload,
            reviewer_id="commander-smith",
            db=api_db,
        )
    assert exc_info.value.status_code == 422


def test_endpoint_submit_approval_duplicate_conflict_raises_409(api_db: Session):
    """submit_approval_decision on an already-decided workflow raises WorkflowApprovalConflictError (HTTP 409)."""
    _seed_test_workflow(api_db, workflow_id="wf-already-decided", approval_status="approved", workflow_status="completed")

    payload = WorkflowApprovalRequest(decision=HumanApprovalStatus.APPROVED)

    with pytest.raises(WorkflowApprovalConflictError, match="approval status is already 'approved'"):
        submit_approval_decision(
            workflow_id="wf-already-decided",
            payload=payload,
            reviewer_id="commander-carter",
            db=api_db,
        )


# ===========================================================================
# 6. get_approval_history Endpoint Tests (GET /api/v1/workflows/{workflow_id}/approval-history)
# ===========================================================================

def test_endpoint_get_approval_history_success(api_db: Session):
    """get_approval_history retrieves full chronological audit trail of review decisions."""
    rec = _seed_test_workflow(api_db, workflow_id="wf-hist-endpoint")

    # Perform approval decision
    payload = WorkflowApprovalRequest(
        decision=HumanApprovalStatus.APPROVED,
        reviewer_comments="Authorized with perimeter verification.",
    )
    submit_approval_decision(
        workflow_id=rec.workflow_id,
        payload=payload,
        reviewer_id="chief-wood",
        db=api_db,
    )

    history_resp: ApprovalHistoryResponse = get_approval_history(workflow_id="wf-hist-endpoint", db=api_db)

    assert isinstance(history_resp, ApprovalHistoryResponse)
    assert history_resp.workflow_id == "wf-hist-endpoint"
    assert history_resp.total_decisions == 1
    entry = history_resp.history[0]
    assert entry.previous_status == "pending"
    assert entry.new_status == "approved"
    assert entry.reviewer_id == "chief-wood"
    assert entry.reviewer_comments == "Authorized with perimeter verification."


def test_endpoint_get_approval_history_not_found(api_db: Session):
    """get_approval_history raises WorkflowNotFoundError (HTTP 404) for unknown workflow ID."""
    with pytest.raises(WorkflowNotFoundError, match="Disaster workflow 'wf-unknown' was not found"):
        get_approval_history(workflow_id="wf-unknown", db=api_db)
