"""
backend/app/agents/state.py
Typed state definition, state initialization, and lifecycle validators for LangGraph disaster workflow.
"""

from datetime import datetime, timezone
import json
import operator
from typing import Annotated, Any, Dict, List, Optional, TypedDict
from uuid import uuid4

from app.agents.exceptions import InvalidStateTransitionError
from app.agents.schemas import DisasterResponseWorkflowRequest, WorkflowStage, WorkflowStatus


class DisasterWorkflowState(TypedDict, total=False):
    """
    Comprehensive typed state passed through the LangGraph multi-agent disaster response workflow.
    Designed for full serialization, graph checkpointing, and auditable evidence provenance.
    """

    # Identifiers
    workflow_id: str
    request_id: str

    # Core Request & Location Parameters
    disaster_type: str
    latitude: float
    longitude: float
    search_radius_meters: float

    # Input References & Context
    image_path: Optional[str]
    source_description: str
    metadata: Dict[str, Any]

    # Workflow Lifecycle State
    status: str  # WorkflowStatus value
    stage: str   # WorkflowStage value

    # Existing Milestone Integration Reference (Populated in M12.2)
    m11_assessment: Optional[Dict[str, Any]]

    # Agent Output Slots (Contractually Typed, None until implemented)
    intelligence_output: Optional[Dict[str, Any]]      # Planned M12.2
    weather_output: Optional[Dict[str, Any]]           # Planned M12.3
    geospatial_output: Optional[Dict[str, Any]]        # Planned M12.3
    risk_assessment_output: Optional[Dict[str, Any]]   # Planned M12.4
    response_plan_output: Optional[Dict[str, Any]]     # Planned M12.4
    human_approval: Optional[Dict[str, Any]]           # Planned M12.5
    coordinator_report: Optional[Dict[str, Any]]       # Planned M12.5

    # Traceable Accumulators (LangGraph Reducer: operator.add)
    execution_records: Annotated[List[Dict[str, Any]], operator.add]
    errors: Annotated[List[Dict[str, Any]], operator.add]
    warnings: Annotated[List[str], operator.add]

    # Provenance and Timestamps
    provenance: Dict[str, Any]
    created_at: str  # ISO 8601 UTC string
    updated_at: str  # ISO 8601 UTC string
    completed_at: Optional[str]  # ISO 8601 UTC string


# Permitted lifecycle stage transitions
VALID_STAGE_TRANSITIONS: Dict[str, List[str]] = {
    WorkflowStage.INITIALIZED.value: [
        WorkflowStage.REQUEST_VALIDATION.value,
        WorkflowStage.TERMINATED_WITH_ERROR.value,
    ],
    WorkflowStage.REQUEST_VALIDATION.value: [
        WorkflowStage.REQUEST_VALIDATED.value,
        WorkflowStage.TERMINATED_WITH_ERROR.value,
    ],
    WorkflowStage.REQUEST_VALIDATED.value: [
        WorkflowStage.INTELLIGENCE_ASSESSMENT.value,
        WorkflowStage.COMPLETED.value,
        WorkflowStage.TERMINATED_WITH_ERROR.value,
    ],
    WorkflowStage.INTELLIGENCE_ASSESSMENT.value: [
        WorkflowStage.CONTEXT_INTERPRETATION.value,
        WorkflowStage.TERMINATED_WITH_ERROR.value,
    ],
    WorkflowStage.CONTEXT_INTERPRETATION.value: [
        WorkflowStage.RISK_ASSESSMENT.value,
        WorkflowStage.COMPLETED.value,  # Allowed for M12.2 completion boundary
        WorkflowStage.TERMINATED_WITH_ERROR.value,
    ],
    WorkflowStage.RISK_ASSESSMENT.value: [
        WorkflowStage.RESPONSE_PLANNING.value,
        WorkflowStage.COMPLETED.value,  # Allowed for M12.3 completion boundary
        WorkflowStage.TERMINATED_WITH_ERROR.value,
    ],
    WorkflowStage.RESPONSE_PLANNING.value: [
        WorkflowStage.HUMAN_REVIEW_GATE.value,
        WorkflowStage.COORDINATOR_REPORT.value,
        WorkflowStage.TERMINATED_WITH_ERROR.value,
    ],
    WorkflowStage.HUMAN_REVIEW_GATE.value: [
        WorkflowStage.COORDINATOR_REPORT.value,
        WorkflowStage.COMPLETED.value,
        WorkflowStage.TERMINATED_WITH_ERROR.value,
    ],
    WorkflowStage.COORDINATOR_REPORT.value: [
        WorkflowStage.COMPLETED.value,
        WorkflowStage.TERMINATED_WITH_ERROR.value,
    ],
    WorkflowStage.COMPLETED.value: [
        WorkflowStage.RESPONSE_PLANNING.value,
    ],
    WorkflowStage.TERMINATED_WITH_ERROR.value: [],
}


def validate_state_transition(current_stage: str, target_stage: str) -> None:
    """
    Validates whether transitioning from current_stage to target_stage is legally permissible.
    Raises InvalidStateTransitionError if the transition violates the workflow graph topology.
    """
    allowed_targets = VALID_STAGE_TRANSITIONS.get(current_stage)
    if allowed_targets is None:
        raise InvalidStateTransitionError(
            current_stage=current_stage,
            target_stage=target_stage,
            reason=f"Unknown origin stage '{current_stage}'.",
        )
    if target_stage not in allowed_targets:
        raise InvalidStateTransitionError(
            current_stage=current_stage,
            target_stage=target_stage,
            reason=f"Stage '{target_stage}' is not in allowed target set {allowed_targets}.",
        )


def initialize_workflow_state(
    request: DisasterResponseWorkflowRequest,
    workflow_id: Optional[str] = None,
) -> DisasterWorkflowState:
    """
    Initializes a clean, fully-typed workflow state from a verified request object.
    Ensures zero fake outputs and valid ISO timestamps.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    wf_id = workflow_id or f"wf-{uuid4().hex[:12]}"

    return {
        "workflow_id": wf_id,
        "request_id": request.request_id,
        "disaster_type": request.disaster_type.value,
        "latitude": request.latitude,
        "longitude": request.longitude,
        "search_radius_meters": request.search_radius_meters,
        "image_path": request.image_path,
        "source_description": request.source_description,
        "metadata": dict(request.metadata),
        "status": WorkflowStatus.INITIALIZED.value,
        "stage": WorkflowStage.INITIALIZED.value,
        "m11_assessment": None,
        "intelligence_output": None,
        "weather_output": None,
        "geospatial_output": None,
        "risk_assessment_output": None,
        "response_plan_output": None,
        "human_approval": None,
        "coordinator_report": None,
        "execution_records": [],
        "errors": [],
        "warnings": [],
        "provenance": {
            "origin": "disaster_workflow_request",
            "source_description": request.source_description,
            "created_at": now_iso,
        },
        "created_at": now_iso,
        "updated_at": now_iso,
        "completed_at": None,
    }


def serialize_workflow_state(state: DisasterWorkflowState) -> str:
    """
    Serializes workflow state to a JSON string.
    Ensures that state contains only JSON-serializable primitives (no open sessions, handles, etc.).
    """
    return json.dumps(state, default=str)


def deserialize_workflow_state(json_str: str) -> DisasterWorkflowState:
    """
    Deserializes a JSON string back into a DisasterWorkflowState dictionary.
    """
    data = json.loads(json_str)
    return DisasterWorkflowState(**data)
