"""
backend/app/agents/services/workflow_service.py
Service runner orchestrating LangGraph multi-agent disaster response execution.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4
import uuid

from langgraph.graph.state import CompiledStateGraph
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.graph import compile_workflow_graph
from app.agents.schemas import (
    AgentExecutionRecord,
    CoordinatorReportOutput,
    DisasterResponseWorkflowRequest,
    GeospatialAgentOutput,
    HumanApprovalState,
    HumanApprovalStatus,
    IntelligenceAgentOutput,
    ResponsePlanningAgentOutput,
    RiskAssessmentAgentOutput,
    WeatherAgentOutput,
    WorkflowError,
    WorkflowExecutionResult,
    WorkflowStage,
    WorkflowStatus,
)
from app.agents.state import DisasterWorkflowState, initialize_workflow_state
from app.core.exceptions import (
    WorkflowApprovalConflictError,
    WorkflowExecutionFailedError,
    WorkflowNotFoundError,
)
from app.models.workflow import DisasterWorkflowRecord, WorkflowApprovalHistory

logger = logging.getLogger(__name__)


class DisasterWorkflowService:
    """
    Main orchestration service for launching, monitoring, and executing LangGraph disaster workflows.
    Decoupled from HTTP controllers for clean testability.
    """

    def __init__(
        self,
        compiled_graph: Optional[CompiledStateGraph] = None,
        include_agents: bool = True,
        include_risk_agent: bool = True,
        include_planning_agent: bool = True,
        include_coordinator: bool = True,
    ) -> None:
        self.graph = compiled_graph or compile_workflow_graph(
            include_agents=include_agents,
            include_risk_agent=include_risk_agent,
            include_planning_agent=include_planning_agent,
            include_coordinator=include_coordinator,
        )

    def run_workflow(
        self,
        request: DisasterResponseWorkflowRequest,
        workflow_id: Optional[str] = None,
    ) -> WorkflowExecutionResult:
        """
        Executes end-to-end multi-agent disaster workflow starting from an initialized request.
        """
        logger.info(
            "Initiating disaster workflow execution for request %s (hazard=%s)",
            request.request_id,
            request.disaster_type.value,
        )

        initial_state: DisasterWorkflowState = initialize_workflow_state(
            request=request,
            workflow_id=workflow_id,
        )

        # Invoke LangGraph StateGraph
        final_state: DisasterWorkflowState = self.graph.invoke(initial_state)

        # Transform final dictionary state to typed domain result
        execution_records = [
            AgentExecutionRecord(**rec) for rec in final_state.get("execution_records", [])
        ]
        errors = [WorkflowError(**err) for err in final_state.get("errors", [])]
        warnings = list(final_state.get("warnings", []))

        created_dt = (
            datetime.fromisoformat(final_state["created_at"])
            if isinstance(final_state["created_at"], str)
            else final_state["created_at"]
        )
        updated_dt = (
            datetime.fromisoformat(final_state["updated_at"])
            if isinstance(final_state["updated_at"], str)
            else final_state["updated_at"]
        )
        completed_dt = (
            datetime.fromisoformat(final_state["completed_at"])
            if final_state.get("completed_at") and isinstance(final_state["completed_at"], str)
            else final_state.get("completed_at")
        )

        # Map agent output contracts if present
        intelligence_out = (
            IntelligenceAgentOutput(**final_state["intelligence_output"])
            if final_state.get("intelligence_output")
            else None
        )
        weather_out = (
            WeatherAgentOutput(**final_state["weather_output"])
            if final_state.get("weather_output")
            else None
        )
        geospatial_out = (
            GeospatialAgentOutput(**final_state["geospatial_output"])
            if final_state.get("geospatial_output")
            else None
        )
        risk_out = (
            RiskAssessmentAgentOutput(**final_state["risk_assessment_output"])
            if final_state.get("risk_assessment_output")
            else None
        )
        plan_out = (
            ResponsePlanningAgentOutput(**final_state["response_plan_output"])
            if final_state.get("response_plan_output")
            else None
        )
        approval_out = (
            HumanApprovalState(**final_state["human_approval"])
            if final_state.get("human_approval")
            else None
        )
        coord_out = (
            CoordinatorReportOutput(**final_state["coordinator_report"])
            if final_state.get("coordinator_report")
            else None
        )

        return WorkflowExecutionResult(
            workflow_id=final_state["workflow_id"],
            request_id=final_state["request_id"],
            status=WorkflowStatus(final_state["status"]),
            stage=WorkflowStage(final_state["stage"]),
            disaster_type=final_state["disaster_type"],
            location={
                "latitude": final_state["latitude"],
                "longitude": final_state["longitude"],
            },
            search_radius_meters=final_state["search_radius_meters"],
            execution_records=execution_records,
            errors=errors,
            warnings=warnings,
            intelligence_output=intelligence_out,
            weather_output=weather_out,
            geospatial_output=geospatial_out,
            risk_assessment_output=risk_out,
            response_plan_output=plan_out,
            human_approval=approval_out,
            coordinator_report=coord_out,
            created_at=created_dt,
            updated_at=updated_dt,
            completed_at=completed_dt,
        )

    def apply_human_approval(
        self,
        workflow_result: WorkflowExecutionResult,
        decision_status: HumanApprovalStatus,
        reviewer_id: str,
        reviewer_comments: Optional[str] = None,
        rejection_or_revision_reason: Optional[str] = None,
    ) -> WorkflowExecutionResult:
        """
        Applies a human review gate decision to an existing WorkflowExecutionResult suspended at the gate.
        Enforces verification that review is pending, and mandates a reason when rejecting or requesting revisions.
        """
        if not workflow_result.human_approval:
            raise ValueError("WorkflowExecutionResult does not contain a HumanApprovalState.")

        if workflow_result.human_approval.approval_status != HumanApprovalStatus.PENDING:
            raise ValueError(
                f"Cannot apply review: approval status is '{workflow_result.human_approval.approval_status.value}', not 'pending'."
            )

        if decision_status in (HumanApprovalStatus.REJECTED, HumanApprovalStatus.NEEDS_REVISION):
            if not rejection_or_revision_reason:
                raise ValueError(
                    f"Rejection or revision reason is required when status is '{decision_status.value}'."
                )

        now_dt = datetime.now(timezone.utc)
        now_iso = now_dt.isoformat()

        # Update human approval object
        updated_approval = workflow_result.human_approval.model_copy(
            update={
                "approval_status": decision_status,
                "decision_status": decision_status.value,
                "reviewer_id": reviewer_id,
                "review_timestamp": now_iso,
                "reviewer_comments": reviewer_comments,
                "rejection_or_revision_reason": rejection_or_revision_reason,
                "authorized_by": reviewer_id if decision_status == HumanApprovalStatus.APPROVED else None,
                "authorized_at": now_dt if decision_status == HumanApprovalStatus.APPROVED else None,
            }
        )

        # Update plan output if present
        updated_plan = None
        if workflow_result.response_plan_output:
            updated_plan = workflow_result.response_plan_output.model_copy(
                update={"human_approval_status": decision_status.value}
            )

        # If approved, update status to COMPLETED (suspended -> completed)
        new_status = workflow_result.status
        if decision_status == HumanApprovalStatus.APPROVED:
            new_status = WorkflowStatus.COMPLETED

        return workflow_result.model_copy(
            update={
                "status": new_status,
                "human_approval": updated_approval,
                "response_plan_output": updated_plan,
                "updated_at": now_dt,
            }
        )

    # ---------------------------------------------------------------------------
    # Persistent Database Operations (Milestone 12.5)
    # ---------------------------------------------------------------------------

    def create_and_run_workflow(
        self,
        request: DisasterResponseWorkflowRequest,
        db: Session,
        workflow_id: Optional[str] = None,
    ) -> DisasterWorkflowRecord:
        """
        Atomically executes the multi-agent disaster response workflow and persists
        the resulting state snapshot and agent artifacts to the database.
        """
        wf_id = workflow_id or f"wf-{uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)

        # 1. Initialize persistent record in RUNNING status
        record = DisasterWorkflowRecord(
            id=uuid.uuid4(),
            workflow_id=wf_id,
            request_id=request.request_id,
            disaster_type=request.disaster_type.value,
            workflow_status=WorkflowStatus.RUNNING.value,
            workflow_stage=WorkflowStage.REQUEST_VALIDATION.value,
            latitude=request.latitude,
            longitude=request.longitude,
            search_radius_meters=request.search_radius_meters,
            request_payload=request.model_dump(mode="json"),
            execution_state={"status": "running", "initialized_at": now.isoformat()},
            approval_status=HumanApprovalStatus.PENDING.value,
            version=1,
            created_at=now,
            updated_at=now,
        )
        db.add(record)
        db.commit()
        db.refresh(record)

        # 2. Execute LangGraph workflow
        try:
            result = self.run_workflow(request=request, workflow_id=wf_id)
        except Exception as exc:
            logger.exception("LangGraph workflow %s failed unhandled during execution: %s", wf_id, exc)
            record.workflow_status = WorkflowStatus.FAILED.value
            record.workflow_stage = WorkflowStage.TERMINATED_WITH_ERROR.value
            record.updated_at = datetime.now(timezone.utc)
            record.execution_state = {"error": str(exc), "stage": "graph_execution_failure"}
            db.commit()
            db.refresh(record)
            raise WorkflowExecutionFailedError(
                workflow_id=wf_id,
                message=f"Disaster workflow execution failed: {exc}",
                details={"stage": record.workflow_stage},
            ) from exc

        # 3. Snapshot agent artifacts into database record
        intel_dump = result.intelligence_output.model_dump(mode="json") if result.intelligence_output else None
        weather_dump = result.weather_output.model_dump(mode="json") if result.weather_output else None
        geo_dump = result.geospatial_output.model_dump(mode="json") if result.geospatial_output else None
        risk_dump = result.risk_assessment_output.model_dump(mode="json") if result.risk_assessment_output else None
        plan_dump = result.response_plan_output.model_dump(mode="json") if result.response_plan_output else None
        coord_dump = result.coordinator_report.model_dump(mode="json") if result.coordinator_report else None
        approval_val = (
            result.human_approval.approval_status.value
            if result.human_approval
            else HumanApprovalStatus.PENDING.value
        )

        completed_dt = (
            datetime.now(timezone.utc)
            if result.status == WorkflowStatus.COMPLETED
            else None
        )

        record.workflow_status = result.status.value
        record.workflow_stage = result.stage.value
        record.intelligence_assessment = intel_dump
        record.weather_interpretation = weather_dump
        record.geospatial_context = geo_dump
        record.risk_assessment = risk_dump
        record.response_plan = plan_dump
        record.coordinator_report = coord_dump
        record.approval_status = approval_val
        record.execution_state = {
            "records": [r.model_dump(mode="json") for r in result.execution_records],
            "errors": [e.model_dump(mode="json") for e in result.errors],
            "warnings": result.warnings,
        }
        record.updated_at = datetime.now(timezone.utc)
        record.completed_at = completed_dt

        db.commit()
        db.refresh(record)
        return record

    def get_workflow_by_id(self, workflow_id: str, db: Session) -> DisasterWorkflowRecord:
        """
        Retrieves a persistent disaster workflow record by unique workflow_id.
        Raises WorkflowNotFoundError if the workflow does not exist.
        """
        stmt = select(DisasterWorkflowRecord).where(DisasterWorkflowRecord.workflow_id == workflow_id)
        record = db.execute(stmt).scalar_one_or_none()
        if not record:
            raise WorkflowNotFoundError(workflow_id)
        return record

    def list_workflows(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 50,
        disaster_type: Optional[str] = None,
        workflow_status: Optional[str] = None,
        approval_status: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Tuple[int, List[DisasterWorkflowRecord]]:
        """
        Retrieves a paginated list of workflow records with optional filtering.
        """
        query = select(DisasterWorkflowRecord)

        if disaster_type:
            query = query.where(DisasterWorkflowRecord.disaster_type == disaster_type)
        if workflow_status:
            query = query.where(DisasterWorkflowRecord.workflow_status == workflow_status)
        if approval_status:
            query = query.where(DisasterWorkflowRecord.approval_status == approval_status)
        if start_date:
            query = query.where(DisasterWorkflowRecord.created_at >= start_date)
        if end_date:
            query = query.where(DisasterWorkflowRecord.created_at <= end_date)

        # Count total matching
        count_stmt = select(func.count()).select_from(query.subquery())
        total = db.execute(count_stmt).scalar() or 0

        # Fetch page items
        page_stmt = (
            query.order_by(DisasterWorkflowRecord.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        items = list(db.execute(page_stmt).scalars().all())
        return total, items

    def list_pending_approvals(self, db: Session) -> List[DisasterWorkflowRecord]:
        """
        Retrieves all workflows requiring human review at the human approval gate.
        """
        stmt = (
            select(DisasterWorkflowRecord)
            .where(
                DisasterWorkflowRecord.approval_status == HumanApprovalStatus.PENDING.value,
                DisasterWorkflowRecord.workflow_status == WorkflowStatus.SUSPENDED_FOR_APPROVAL.value,
            )
            .order_by(DisasterWorkflowRecord.created_at.asc())
        )
        return list(db.execute(stmt).scalars().all())

    def apply_persistent_approval(
        self,
        workflow_id: str,
        decision: HumanApprovalStatus,
        reviewer_id: str,
        db: Session,
        reviewer_comments: Optional[str] = None,
        rejection_or_revision_reason: Optional[str] = None,
    ) -> Tuple[DisasterWorkflowRecord, WorkflowApprovalHistory]:
        """
        Applies an authorized human approval decision to a suspended workflow.
        Guarantees:
        - Optimistic locking / state checking: rejects conflicting or duplicate reviews (HTTP 409).
        - Mandatory justification for rejections and revisions (ValueError).
        - Immutable audit logging in WorkflowApprovalHistory.
        - Advisory safety boundary: does NOT trigger autonomous dispatch.
        """
        record = self.get_workflow_by_id(workflow_id, db)

        if record.approval_status != HumanApprovalStatus.PENDING.value:
            raise WorkflowApprovalConflictError(
                workflow_id=workflow_id,
                current_status=record.approval_status,
                message=(
                    f"Cannot apply approval decision: workflow '{workflow_id}' approval status "
                    f"is already '{record.approval_status}'."
                ),
            )

        if decision in (HumanApprovalStatus.REJECTED, HumanApprovalStatus.NEEDS_REVISION):
            if not rejection_or_revision_reason or not rejection_or_revision_reason.strip():
                raise ValueError(
                    f"Rejection or revision reason is mandatory when decision is '{decision.value}'."
                )

        now = datetime.now(timezone.utc)
        prev_status = record.approval_status
        plan_id = "unassigned"
        if record.response_plan and isinstance(record.response_plan, dict):
            plan_id = record.response_plan.get("plan_id", "unassigned")

        # 1. Update response plan payload
        if record.response_plan and isinstance(record.response_plan, dict):
            updated_plan = dict(record.response_plan)
            updated_plan["human_approval_status"] = decision.value
            record.response_plan = updated_plan

        # 2. Update record status and version
        record.approval_status = decision.value
        record.version += 1
        record.updated_at = now

        if decision == HumanApprovalStatus.APPROVED:
            record.workflow_status = WorkflowStatus.COMPLETED.value
            record.completed_at = now
        elif decision == HumanApprovalStatus.REJECTED:
            # Remains suspended or marked as rejected/reviewed
            record.workflow_status = "rejected"
        elif decision == HumanApprovalStatus.NEEDS_REVISION:
            record.workflow_status = "revision_requested"

        # 3. Create immutable audit history entry
        history_entry = WorkflowApprovalHistory(
            id=uuid.uuid4(),
            workflow_id=workflow_id,
            plan_id=plan_id,
            previous_status=prev_status,
            new_status=decision.value,
            reviewer_id=reviewer_id,
            reviewer_comments=reviewer_comments,
            rejection_or_revision_reason=rejection_or_revision_reason,
            decision_type=decision.value,
            created_at=now,
        )
        db.add(history_entry)
        db.commit()
        db.refresh(record)
        db.refresh(history_entry)

        return record, history_entry

    def get_approval_history(
        self,
        workflow_id: str,
        db: Session,
    ) -> List[WorkflowApprovalHistory]:
        """
        Retrieves the complete audit trail of review decisions for a workflow.
        """
        # Ensure workflow exists
        self.get_workflow_by_id(workflow_id, db)

        stmt = (
            select(WorkflowApprovalHistory)
            .where(WorkflowApprovalHistory.workflow_id == workflow_id)
            .order_by(WorkflowApprovalHistory.created_at.asc())
        )
        return list(db.execute(stmt).scalars().all())
