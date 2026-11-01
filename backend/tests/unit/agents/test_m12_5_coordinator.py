"""
backend/tests/unit/agents/test_m12_5_coordinator.py
Comprehensive unit test suite for Milestone 12.5: Coordinator Agent & Workflow Persistence.
Verifies coordinator report synthesis, cross-agent summary, partial failure handling,
lifecycle status determination, persistent database operations, optimistic locking,
and approval audit trail generation.
"""

from datetime import datetime, timezone
import json
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch
import uuid
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.agents.graph import compile_workflow_graph, create_disaster_workflow_graph
from app.agents.nodes.coordinator import coordinator_agent_node
from app.agents.schemas import (
    ActionRecommendation,
    AgentExecutionRecord,
    CoordinatorReportOutput,
    DisasterResponseWorkflowRequest,
    DisasterType,
    GeospatialAgentOutput,
    HumanApprovalState,
    HumanApprovalStatus,
    IntelligenceAgentOutput,
    RecommendationPriority,
    ResponsePlanningAgentOutput,
    RiskAssessmentAgentOutput,
    RiskAssessmentStatus,
    WeatherAgentOutput,
    WorkflowError,
    WorkflowExecutionResult,
    WorkflowStage,
    WorkflowStatus,
)
from app.agents.services.workflow_service import DisasterWorkflowService
from app.agents.state import (
    DisasterWorkflowState,
    deserialize_workflow_state,
    initialize_workflow_state,
    serialize_workflow_state,
)
from app.core.auth import get_authenticated_reviewer
from app.core.exceptions import (
    AuthenticationServiceUnavailableError,
    ForbiddenReviewerError,
    UnauthorizedReviewerError,
    WorkflowApprovalConflictError,
    WorkflowExecutionFailedError,
    WorkflowNotFoundError,
)
from app.models.base import Base
from app.models.workflow import DisasterWorkflowRecord, WorkflowApprovalHistory


from tests.unit.agents.test_m12_4_response_planning import _build_mock_m11_assessment

# ===========================================================================
# Helper Fixtures & Builders
# ===========================================================================

@pytest.fixture(scope="function")
def memory_db() -> Session:
    """Provides an isolated in-memory SQLite database session with workflow tables."""
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


def _build_test_state(
    status: str = WorkflowStatus.SUSPENDED_FOR_APPROVAL.value,
    stage: str = WorkflowStage.HUMAN_REVIEW_GATE.value,
    with_intel: bool = True,
    with_weather: bool = True,
    with_geo: bool = True,
    with_risk: bool = True,
    with_plan: bool = True,
    with_approval: bool = True,
    errors: Optional[List[Dict[str, Any]]] = None,
) -> DisasterWorkflowState:
    """Builds a test DisasterWorkflowState with controlled agent output presence."""
    now_iso = datetime.now(timezone.utc).isoformat()
    state: DisasterWorkflowState = {
        "workflow_id": f"wf-{uuid.uuid4().hex[:8]}",
        "request_id": f"req-{uuid.uuid4().hex[:8]}",
        "disaster_type": "wildfire",
        "latitude": 30.3256,
        "longitude": 78.0422,
        "search_radius_meters": 5000.0,
        "image_path": "tests/fixtures/fire.jpg",
        "source_description": "Ground camera observation",
        "metadata": {"source": "unit_test"},
        "status": status,
        "stage": stage,
        "m11_assessment": None,
        "intelligence_output": None,
        "weather_output": None,
        "geospatial_output": None,
        "risk_assessment_output": None,
        "response_plan_output": None,
        "human_approval": None,
        "coordinator_report": None,
        "execution_records": [
            {
                "agent_name": "request_validator",
                "stage": "request_validated",
                "status": "success",
                "start_time": now_iso,
                "end_time": now_iso,
                "duration_seconds": 0.001,
                "details": "Validated",
            }
        ],
        "errors": list(errors or []),
        "warnings": [],
        "provenance": {"origin": "disaster_workflow_request", "created_at": now_iso},
        "created_at": now_iso,
        "updated_at": now_iso,
        "completed_at": None,
    }

    if with_intel:
        state["intelligence_output"] = {
            "incident_status": "CONFIRMED",
            "threat_level": "CRITICAL",
            "confidence": 0.88,
            "severity": "CRITICAL",
            "recommendations": ["Initiate visual perimeter check"],
            "uncertainty_notes": ["Satellite pass pending"],
            "primary_evidence_sources": ["visual_rgb", "fwi_engine"],
            "generated_at": now_iso,
        }

    if with_weather:
        state["weather_output"] = {
            "temperature_c": 34.5,
            "relative_humidity_pct": 18.0,
            "wind_speed_kmh": 28.5,
            "wind_direction_deg": 135.0,
            "precipitation_mm": 0.0,
            "fwi_value": 32.4,
            "fwi_category": "EXTREME",
            "weather_source": "open_meteo_live",
            "generated_at": now_iso,
        }

    if with_geo:
        state["geospatial_output"] = {
            "critical_infrastructure_count": 2,
            "residential_settlement_count": 1,
            "total_features_found": 3,
            "exposure_category": "CRITICAL",
            "features_summary": [{"name": "Substation", "category": "critical_infrastructure"}],
            "generated_at": now_iso,
        }

    if with_risk:
        state["risk_assessment_output"] = {
            "assessment_id": f"risk-{uuid.uuid4().hex[:8]}",
            "incident_status": "CONFIRMED",
            "incident_severity": "CRITICAL",
            "composite_threat_level": "EXTREME",
            "assessment_status": "complete",
            "key_risk_drivers": ["Extreme FWI (32.4)", "High winds (28.5 km/h)", "Critical infrastructure within 1km"],
            "conflicting_evidence": [],
            "missing_evidence": ["Live thermal infrared telemetry"],
            "threat_breakdown": {"weather": "extreme", "exposure": "critical"},
            "recommendations": ["Stage defensive line at substation"],
            "source_agent_provenance": {"intelligence": True, "weather": True, "geospatial": True},
            "generated_at": now_iso,
        }

    if with_plan:
        state["response_plan_output"] = {
            "plan_id": f"plan-{uuid.uuid4().hex[:8]}",
            "disaster_type": "wildfire",
            "incident_status": "CONFIRMED",
            "assessed_threat_level": "EXTREME",
            "overall_plan_status": "complete",
            "recommendations": [
                {
                    "recommendation_id": "rec-1",
                    "title": "Establish Incident Command Staging Area",
                    "description": "Deploy incident command post 3km upwind.",
                    "priority": "HIGH",
                    "action_type": "incident_command",
                    "target_sector": "North-West flank",
                    "safety_precautions": ["Ensure escape route"],
                    "information_gaps": [],
                }
            ],
            "relevant_geographic_context": {"infrastructure_count": 2},
            "suggested_resource_categories": ["wildland_fire_engine", "water_tender"],
            "safety_precautions": ["Maintain continuous LCES protocol"],
            "missing_information": [],
            "operational_limitations": ["Night operations restricted"],
            "human_approval_status": "pending",
            "source_agent_provenance": {"risk_assessment": True},
            "priority_level": "HIGH",
            "life_safety_notes": ["Warn civilian settlements downwind"],
            "responder_information_gaps": ["Spot weather forecast pending"],
            "evacuation_alert_guidance": "Recommended evacuation warning zone within 2km.",
            "generated_at": now_iso,
        }

    if with_approval:
        plan_id = state["response_plan_output"]["plan_id"] if state.get("response_plan_output") else "plan-test"
        state["human_approval"] = {
            "approval_id": f"appr-{uuid.uuid4().hex[:8]}",
            "plan_id": plan_id,
            "approval_status": HumanApprovalStatus.PENDING.value,
            "requires_approval": True,
            "reviewer_id": None,
            "review_timestamp": None,
            "reviewer_comments": None,
            "rejection_or_revision_reason": None,
            "decision_status": "pending",
        }

    return state


# ===========================================================================
# 1. Coordinator Node Core Tests
# ===========================================================================

def test_coordinator_synthesizes_complete_report():
    """Coordinator Agent successfully aggregates all agent artifacts into a comprehensive report."""
    state = _build_test_state()

    result = coordinator_agent_node(state)

    assert result["status"] == WorkflowStatus.SUSPENDED_FOR_APPROVAL.value
    assert result["stage"] == WorkflowStage.COORDINATOR_REPORT.value
    assert "coordinator_report" in result
    report = result["coordinator_report"]

    assert report["incident_status"] == "CONFIRMED"
    assert report["composite_threat_level"] == "EXTREME"
    assert "FWI" in report["weather_summary"]
    assert "Exposure Category" in report["exposure_summary"]
    assert len(report["recommendations_summary"]) == 1
    assert "Establish Incident Command" in report["recommendations_summary"][0]
    assert len(report["human_decisions_required"]) >= 1
    assert any("PENDING" in d for d in report["human_decisions_required"])
    assert len(report["unresolved_uncertainties"]) >= 1
    assert "audit_trail" in report
    assert report["audit_trail"]["workflow_id"] == state["workflow_id"]

    # Verify execution record
    assert len(result["execution_records"]) == 1
    rec = result["execution_records"][0]
    assert rec["agent_name"] == "coordinator_agent"
    assert rec["status"] == "success"
    assert rec["duration_seconds"] >= 0.0


def test_coordinator_handles_missing_weather_and_geospatial():
    """Coordinator synthesizes report gracefully when perception data is partially missing without fabricating values."""
    state = _build_test_state(with_weather=False, with_geo=False)

    result = coordinator_agent_node(state)

    assert result["status"] == WorkflowStatus.SUSPENDED_FOR_APPROVAL.value
    report = result["coordinator_report"]
    assert report["weather_summary"] == "Weather observations unavailable."
    assert report["exposure_summary"] == "Geospatial exposure data unavailable."
    assert report["incident_status"] == "CONFIRMED"


def test_coordinator_handles_fatal_errors_in_state():
    """When fatal errors exist in state, coordinator marks status FAILED and stage TERMINATED_WITH_ERROR."""
    err = WorkflowError(
        code="INSUFFICIENT_INPUTS",
        message="Fatal model failure",
        stage=WorkflowStage.INTELLIGENCE_ASSESSMENT.value,
        agent="intelligence_agent",
        recoverable=False,
    ).model_dump(mode="json")
    state = _build_test_state(status=WorkflowStatus.FAILED.value, errors=[err])

    result = coordinator_agent_node(state)

    assert result["status"] == WorkflowStatus.FAILED.value
    assert result["stage"] == WorkflowStage.TERMINATED_WITH_ERROR.value
    assert len(result["execution_records"]) == 1
    assert result["execution_records"][0]["status"] == "failed"


def test_coordinator_marks_completed_when_approval_not_required():
    """When human approval is not required or already approved, coordinator marks workflow COMPLETED."""
    state = _build_test_state()
    state["human_approval"]["approval_status"] = HumanApprovalStatus.APPROVED.value
    state["human_approval"]["requires_approval"] = False

    result = coordinator_agent_node(state)

    assert result["status"] == WorkflowStatus.COMPLETED.value
    assert result["stage"] == WorkflowStage.COMPLETED.value
    assert result["completed_at"] is not None


# ===========================================================================
# 2. End-to-End LangGraph with Coordinator
# ===========================================================================

def test_full_graph_executes_through_coordinator():
    """Full 8-agent LangGraph workflow executes end-to-end through coordinator agent."""
    mock_m11 = _build_mock_m11_assessment()

    with patch("app.agents.nodes.intelligence.MultimodalIntelligenceService") as mock_svc_cls:
        instance = mock_svc_cls.return_value
        instance.analyze_observation.return_value = mock_m11

        service = DisasterWorkflowService(include_coordinator=True)
        req = DisasterResponseWorkflowRequest(
            latitude=30.3256,
            longitude=78.0422,
            disaster_type=DisasterType.WILDFIRE,
            search_radius_meters=5000.0,
        )

        result: WorkflowExecutionResult = service.run_workflow(req, workflow_id="wf-test-8-nodes")

        # Must halt at coordinator with suspended status (pending human approval)
        assert result.status == WorkflowStatus.SUSPENDED_FOR_APPROVAL
        assert result.stage == WorkflowStage.COORDINATOR_REPORT
        assert result.coordinator_report is not None
        assert "SCOUT Coordinator Report" in result.coordinator_report.executive_summary

        # 8 execution records in sequence
        assert len(result.execution_records) == 8
        agent_names = [r.agent_name for r in result.execution_records]
        assert agent_names == [
            "request_validator",
            "intelligence_agent",
            "weather_agent",
            "geospatial_agent",
            "risk_assessment_agent",
            "response_planning_agent",
            "human_review_gate",
            "coordinator_agent",
        ]


# ===========================================================================
# 3. Persistent Database Operations Tests
# ===========================================================================

def test_workflow_database_persistence_lifecycle(memory_db: Session):
    """Workflow creation, execution snapshot, and retrieval succeed in database."""
    service = DisasterWorkflowService(include_coordinator=False)

    req = DisasterResponseWorkflowRequest(
        latitude=30.3256,
        longitude=78.0422,
        disaster_type=DisasterType.WILDFIRE,
        source_description="Sensor cluster alert",
    )

    mock_m11 = _build_mock_m11_assessment()
    with patch("app.agents.nodes.intelligence.MultimodalIntelligenceService") as mock_svc_cls:
        mock_svc_cls.return_value.analyze_observation.return_value = mock_m11
        record = service.create_and_run_workflow(request=req, db=memory_db, workflow_id="wf-db-persist-01")

        assert record.workflow_id == "wf-db-persist-01"
        assert record.disaster_type == "wildfire"
        assert record.latitude == 30.3256
        assert record.longitude == 78.0422
        assert record.approval_status == "pending"
        assert record.version == 1

        # Retrieve by ID
        fetched = service.get_workflow_by_id("wf-db-persist-01", memory_db)
        assert fetched.id == record.id
        assert fetched.request_id == req.request_id
        assert fetched.request_payload["source_description"] == "Sensor cluster alert"


def test_get_workflow_by_id_not_found(memory_db: Session):
    """Querying non-existent workflow raises WorkflowNotFoundError (HTTP 404)."""
    service = DisasterWorkflowService()
    with pytest.raises(WorkflowNotFoundError, match="Disaster workflow 'wf-nonexistent' was not found"):
        service.get_workflow_by_id("wf-nonexistent", memory_db)


def test_list_workflows_with_pagination_and_filters(memory_db: Session):
    """Filtering by disaster_type and approval_status with limit/skip works correctly."""
    service = DisasterWorkflowService()

    # Create 3 records
    for i in range(3):
        rec = DisasterWorkflowRecord(
            id=uuid.uuid4(),
            workflow_id=f"wf-filter-{i}",
            request_id=f"req-{i}",
            disaster_type="wildfire" if i < 2 else "flood",
            workflow_status=WorkflowStatus.SUSPENDED_FOR_APPROVAL.value,
            workflow_stage=WorkflowStage.HUMAN_REVIEW_GATE.value,
            latitude=30.0 + i,
            longitude=78.0 + i,
            search_radius_meters=5000.0,
            request_payload={},
            execution_state={},
            approval_status="pending" if i == 0 else "approved",
            version=1,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        memory_db.add(rec)
    memory_db.commit()

    # Total unfiltered
    total, items = service.list_workflows(memory_db, skip=0, limit=10)
    assert total == 3
    assert len(items) == 3

    # Filter disaster_type=wildfire
    total_wf, items_wf = service.list_workflows(memory_db, disaster_type="wildfire")
    assert total_wf == 2
    assert len(items_wf) == 2

    # Filter approval_status=pending
    total_p, items_p = service.list_workflows(memory_db, approval_status="pending")
    assert total_p == 1
    assert items_p[0].workflow_id == "wf-filter-0"

    # Pagination skip=1, limit=1
    total_pg, items_pg = service.list_workflows(memory_db, skip=1, limit=1)
    assert total_pg == 3
    assert len(items_pg) == 1


def test_list_pending_approvals_query(memory_db: Session):
    """Pending approvals query returns only suspended workflows with pending approval."""
    service = DisasterWorkflowService()

    # Pending suspended workflow
    rec1 = DisasterWorkflowRecord(
        id=uuid.uuid4(),
        workflow_id="wf-pending-1",
        request_id="req-p1",
        disaster_type="wildfire",
        workflow_status=WorkflowStatus.SUSPENDED_FOR_APPROVAL.value,
        workflow_stage=WorkflowStage.HUMAN_REVIEW_GATE.value,
        latitude=30.0,
        longitude=78.0,
        request_payload={},
        execution_state={},
        response_plan={"plan_id": "plan-p1", "recommendations": [{"title": "Action 1"}]},
        approval_status=HumanApprovalStatus.PENDING.value,
        version=1,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    # Completed workflow
    rec2 = DisasterWorkflowRecord(
        id=uuid.uuid4(),
        workflow_id="wf-completed-2",
        request_id="req-p2",
        disaster_type="wildfire",
        workflow_status=WorkflowStatus.COMPLETED.value,
        workflow_stage=WorkflowStage.COMPLETED.value,
        latitude=30.0,
        longitude=78.0,
        request_payload={},
        execution_state={},
        approval_status=HumanApprovalStatus.APPROVED.value,
        version=2,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    memory_db.add_all([rec1, rec2])
    memory_db.commit()

    pending = service.list_pending_approvals(memory_db)
    assert len(pending) == 1
    assert pending[0].workflow_id == "wf-pending-1"


# ===========================================================================
# 4. Human Approval Lifecycle & Concurrency Tests
# ===========================================================================

def test_authorized_approval_updates_status_and_audit_history(memory_db: Session):
    """Applying authorized approval transitions workflow to COMPLETED and inserts audit history."""
    service = DisasterWorkflowService()

    rec = DisasterWorkflowRecord(
        id=uuid.uuid4(),
        workflow_id="wf-appr-test",
        request_id="req-appr",
        disaster_type="wildfire",
        workflow_status=WorkflowStatus.SUSPENDED_FOR_APPROVAL.value,
        workflow_stage=WorkflowStage.HUMAN_REVIEW_GATE.value,
        latitude=30.0,
        longitude=78.0,
        request_payload={},
        execution_state={},
        response_plan={"plan_id": "plan-appr", "human_approval_status": "pending"},
        approval_status=HumanApprovalStatus.PENDING.value,
        version=1,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    memory_db.add(rec)
    memory_db.commit()

    updated_rec, history = service.apply_persistent_approval(
        workflow_id="wf-appr-test",
        decision=HumanApprovalStatus.APPROVED,
        reviewer_id="commander-77",
        reviewer_comments="Plan approved for execution.",
        db=memory_db,
    )

    assert updated_rec.approval_status == HumanApprovalStatus.APPROVED.value
    assert updated_rec.workflow_status == WorkflowStatus.COMPLETED.value
    assert updated_rec.version == 2
    assert updated_rec.response_plan["human_approval_status"] == "approved"
    assert updated_rec.completed_at is not None

    # Audit history verification
    assert history.workflow_id == "wf-appr-test"
    assert history.plan_id == "plan-appr"
    assert history.previous_status == "pending"
    assert history.new_status == "approved"
    assert history.reviewer_id == "commander-77"
    assert history.reviewer_comments == "Plan approved for execution."

    # History query verification
    hist_entries = service.get_approval_history("wf-appr-test", memory_db)
    assert len(hist_entries) == 1
    assert hist_entries[0].id == history.id


def test_rejection_mandates_written_reason(memory_db: Session):
    """Rejection without a written justification raises ValueError."""
    service = DisasterWorkflowService()
    rec = DisasterWorkflowRecord(
        id=uuid.uuid4(),
        workflow_id="wf-reject-test",
        request_id="req-rej",
        disaster_type="wildfire",
        workflow_status=WorkflowStatus.SUSPENDED_FOR_APPROVAL.value,
        workflow_stage=WorkflowStage.HUMAN_REVIEW_GATE.value,
        latitude=30.0,
        longitude=78.0,
        request_payload={},
        execution_state={},
        approval_status=HumanApprovalStatus.PENDING.value,
        version=1,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    memory_db.add(rec)
    memory_db.commit()

    with pytest.raises(ValueError, match="Rejection or revision reason is mandatory"):
        service.apply_persistent_approval(
            workflow_id="wf-reject-test",
            decision=HumanApprovalStatus.REJECTED,
            reviewer_id="commander-88",
            rejection_or_revision_reason="",
            db=memory_db,
        )


def test_conflicting_approval_decision_rejected(memory_db: Session):
    """Attempting approval on a workflow whose approval is already resolved raises 409 Conflict."""
    service = DisasterWorkflowService()
    rec = DisasterWorkflowRecord(
        id=uuid.uuid4(),
        workflow_id="wf-conflict-test",
        request_id="req-conf",
        disaster_type="wildfire",
        workflow_status=WorkflowStatus.COMPLETED.value,
        workflow_stage=WorkflowStage.COMPLETED.value,
        latitude=30.0,
        longitude=78.0,
        request_payload={},
        execution_state={},
        approval_status=HumanApprovalStatus.APPROVED.value,
        version=2,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    memory_db.add(rec)
    memory_db.commit()

    with pytest.raises(WorkflowApprovalConflictError, match="approval status is already 'approved'"):
        service.apply_persistent_approval(
            workflow_id="wf-conflict-test",
            decision=HumanApprovalStatus.REJECTED,
            reviewer_id="commander-99",
            rejection_or_revision_reason="Too late to reject",
            db=memory_db,
        )


# ===========================================================================
# 5. Security & Authentication Guardrail Tests
# ===========================================================================

def test_auth_missing_header_raises_401():
    """Missing reviewer credentials header raises UnauthorizedReviewerError (HTTP 401)."""
    mock_request = MagicMock()
    with pytest.raises(UnauthorizedReviewerError, match="Authentication credentials required"):
        get_authenticated_reviewer(request=mock_request, authorization=None, x_reviewer_token=None)


def test_auth_invalid_token_raises_403():
    """Supplying an invalid or expired token raises ForbiddenReviewerError (HTTP 403)."""
    mock_request = MagicMock()
    with pytest.raises(ForbiddenReviewerError, match="invalid, expired, or has insufficient clearance"):
        get_authenticated_reviewer(
            request=mock_request,
            authorization="Bearer invalid-token",
            x_reviewer_token=None,
        )


def test_auth_valid_token_resolves_reviewer_id():
    """Valid Bearer or X-Reviewer-Token successfully resolves reviewer identity string."""
    mock_request = MagicMock()

    rev1 = get_authenticated_reviewer(
        request=mock_request,
        authorization="Bearer test-token-chief-fire-officer",
        x_reviewer_token=None,
    )
    assert rev1 == "chief-fire-officer"

    rev2 = get_authenticated_reviewer(
        request=mock_request,
        authorization=None,
        x_reviewer_token="commander-42",
    )
    assert rev2 == "commander-42"


def test_auth_production_fail_closed_without_idp(monkeypatch):
    """In production environment without IdP, reviewer authentication fails closed with HTTP 503."""
    mock_request = MagicMock()
    from app.core import config

    monkeypatch.setattr(config.settings, "APP_ENV", "production")

    with pytest.raises(AuthenticationServiceUnavailableError, match="Authentication provider not configured"):
        get_authenticated_reviewer(
            request=mock_request,
            authorization="Bearer chief-01",
            x_reviewer_token=None,
        )
