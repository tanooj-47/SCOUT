"""
backend/app/agents/nodes/human_approval.py
Human Review Gate node and decision handling for SCOUT LangGraph Disaster Response Workflow (Milestone 12.4).
Enforces the mandatory human-in-the-loop safety boundary, ensuring no AI-generated response plan
is ever autonomously executed, dispatched, or treated as pre-approved.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
from uuid import uuid4

from app.agents.schemas import (
    AgentExecutionRecord,
    HumanApprovalState,
    HumanApprovalStatus,
    WorkflowError,
    WorkflowStage,
    WorkflowStatus,
)
from app.agents.state import DisasterWorkflowState

logger = logging.getLogger(__name__)


def human_review_gate_node(state: DisasterWorkflowState) -> Dict[str, Any]:
    """
    Human Review Gate Node (Safety Boundary)
    Responsibilities:
    - Inspects state after response planning has produced a candidate response plan.
    - Halts automated workflow progression, ensuring human incident commanders retain sole authority.
    - Initializes HumanApprovalState with strictly PENDING status.
    - Sets workflow status to SUSPENDED_FOR_APPROVAL (or FAILED if unrecoverable errors present).
    - Prevents downstream automated execution until human authorization is explicitly recorded.
    """
    start_time = datetime.now(timezone.utc)
    errors: List[Dict[str, Any]] = list(state.get("errors", []))
    warnings: List[str] = list(state.get("warnings", []))

    plan = state.get("response_plan_output")
    plan_id = plan.get("plan_id", "unassigned") if plan else "unassigned"

    if not plan and not errors:
        err = WorkflowError(
            code="MISSING_RESPONSE_PLAN",
            message="Cannot establish human review gate: response_plan_output is absent from state.",
            stage=WorkflowStage.HUMAN_REVIEW_GATE.value,
            agent="human_review_gate",
            recoverable=False,
        ).model_dump(mode="json")
        errors.append(err)

    has_errors = bool(
        state.get("status") == WorkflowStatus.FAILED.value
        or state.get("errors")
        or (not plan and errors)
    )

    approval = HumanApprovalState(
        approval_id=f"appr-{uuid4().hex[:8]}",
        plan_id=plan_id,
        approval_status=HumanApprovalStatus.PENDING,
        requires_approval=True,
        reviewer_id=None,
        review_timestamp=None,
        reviewer_comments=None,
        rejection_or_revision_reason=None,
        decision_status="pending",
    ).model_dump(mode="json")

    end_time = datetime.now(timezone.utc)
    duration = (end_time - start_time).total_seconds()
    now_iso = end_time.isoformat()

    final_status = (
        WorkflowStatus.FAILED.value
        if has_errors
        else WorkflowStatus.SUSPENDED_FOR_APPROVAL.value
    )
    final_stage = (
        WorkflowStage.TERMINATED_WITH_ERROR.value
        if has_errors
        else WorkflowStage.HUMAN_REVIEW_GATE.value
    )

    rec = AgentExecutionRecord(
        agent_name="human_review_gate",
        stage=WorkflowStage.HUMAN_REVIEW_GATE.value,
        status="failed" if has_errors else "success",
        start_time=start_time,
        end_time=end_time,
        duration_seconds=round(duration, 4),
        details=(
            f"Human review gate reached: Plan='{plan_id}', "
            f"ApprovalStatus=PENDING, SuspendedForApproval={not has_errors}."
        ),
    ).model_dump(mode="json")

    return {
        "status": final_status,
        "stage": final_stage,
        "human_approval": approval,
        "warnings": warnings,
        "errors": errors,
        "execution_records": [rec],
        "updated_at": now_iso,
    }


def apply_human_approval_decision(
    approval_state: Dict[str, Any],
    decision_status: HumanApprovalStatus,
    reviewer_id: str,
    reviewer_comments: Optional[str] = None,
    rejection_or_revision_reason: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Pure helper to evaluate and transition HumanApprovalState upon human reviewer input.
    Validates legal state transitions and requires reasons for rejection or revisions.
    """
    current_status = approval_state.get("approval_status")
    if current_status != HumanApprovalStatus.PENDING.value:
        raise ValueError(
            f"Cannot apply review decision: Human review is in '{current_status}' state, not 'pending'."
        )

    if (
        decision_status in (HumanApprovalStatus.REJECTED, HumanApprovalStatus.NEEDS_REVISION)
        and not rejection_or_revision_reason
    ):
        raise ValueError(
            f"Rejection or revision reason is required when status is '{decision_status.value}'."
        )

    now_iso = datetime.now(timezone.utc).isoformat()
    updated = dict(approval_state)
    updated["approval_status"] = decision_status.value
    updated["decision_status"] = decision_status.value
    updated["reviewer_id"] = reviewer_id
    updated["review_timestamp"] = now_iso
    updated["reviewer_comments"] = reviewer_comments
    updated["rejection_or_revision_reason"] = rejection_or_revision_reason

    if decision_status == HumanApprovalStatus.APPROVED:
        updated["authorized_by"] = reviewer_id
        updated["authorized_at"] = now_iso

    return updated
