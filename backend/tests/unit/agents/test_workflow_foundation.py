"""
backend/tests/unit/agents/test_workflow_foundation.py
Comprehensive unit tests for SCOUT M12.1 Multi-Agent Architecture & LangGraph Foundation.

Covers the 12 required test scenarios:
1. Valid workflow request.
2. Invalid coordinates.
3. Unsupported disaster type.
4. Missing required request fields.
5. Valid initial workflow state.
6. Invalid state transitions where applicable.
7. Successful graph compilation.
8. Successful execution of the implemented validation workflow.
9. Invalid input rejected safely.
10. No fake agent outputs generated.
11. Errors represented explicitly.
12. State serialization compatibility.
"""

from datetime import datetime, timezone
import json
import pytest
from pydantic import ValidationError

from app.agents import (
    DisasterResponseWorkflowRequest,
    DisasterWorkflowService,
    DisasterWorkflowState,
    InvalidStateTransitionError,
    WorkflowError,
    WorkflowExecutionResult,
    WorkflowStage,
    WorkflowStatus,
    compile_workflow_graph,
    create_disaster_workflow_graph,
    deserialize_workflow_state,
    initialize_workflow_state,
    serialize_workflow_state,
    validate_state_transition,
)
from app.agents.nodes.validation import validate_request_node
from app.schemas.incident import DisasterType


# ---------------------------------------------------------------------------
# Test 1: Valid Workflow Request Creation
# ---------------------------------------------------------------------------

def test_valid_workflow_request_creation():
    """1. Valid request creates a complete DisasterResponseWorkflowRequest instance with defaults."""
    req = DisasterResponseWorkflowRequest(
        latitude=30.3256,
        longitude=78.0422,
        disaster_type=DisasterType.WILDFIRE,
        search_radius_meters=5000.0,
        source_description="forest_watch_camera",
        metadata={"division": "Dehradun", "sensor_id": "FW-04"},
    )
    assert req.latitude == 30.3256
    assert req.longitude == 78.0422
    assert req.disaster_type == DisasterType.WILDFIRE
    assert req.search_radius_meters == 5000.0
    assert req.request_id.startswith("req-")
    assert req.source_description == "forest_watch_camera"
    assert req.metadata["division"] == "Dehradun"


# ---------------------------------------------------------------------------
# Test 2: Invalid Coordinates Rejection
# ---------------------------------------------------------------------------

def test_invalid_coordinates_rejection():
    """2. Invalid coordinates (latitude > 90 or longitude > 180) are rejected by schema and node."""
    # Test Pydantic schema rejection for latitude > 90
    with pytest.raises(ValidationError) as exc_info:
        DisasterResponseWorkflowRequest(
            latitude=95.0,
            longitude=78.0422,
        )
    assert "latitude" in str(exc_info.value).lower()

    # Test Pydantic schema rejection for longitude < -180
    with pytest.raises(ValidationError) as exc_info:
        DisasterResponseWorkflowRequest(
            latitude=30.0,
            longitude=-185.0,
        )
    assert "longitude" in str(exc_info.value).lower()

    # Test node validation catches out-of-bounds state directly
    raw_state: DisasterWorkflowState = {
        "workflow_id": "wf-invalid-coords",
        "request_id": "req-invalid",
        "disaster_type": "wildfire",
        "latitude": 99.9,
        "longitude": 78.0,
        "search_radius_meters": 5000.0,
        "image_path": None,
        "source_description": "test",
        "metadata": {},
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
        "provenance": {},
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": None,
    }
    result = validate_request_node(raw_state)
    assert result["status"] == WorkflowStatus.FAILED.value
    assert result["stage"] == WorkflowStage.TERMINATED_WITH_ERROR.value
    assert any(e["code"] == "INVALID_COORDINATES_LATITUDE" for e in result["errors"])


# ---------------------------------------------------------------------------
# Test 3: Unsupported Disaster Type Rejection
# ---------------------------------------------------------------------------

def test_unsupported_disaster_type_rejection():
    """3. Unsupported disaster types (e.g., FLOOD, EARTHQUAKE) are explicitly rejected."""
    # Request with FLOOD
    req = DisasterResponseWorkflowRequest(
        latitude=30.3256,
        longitude=78.0422,
        disaster_type=DisasterType.FLOOD,
    )
    state = initialize_workflow_state(req)
    assert state["disaster_type"] == "flood"

    result = validate_request_node(state)
    assert result["status"] == WorkflowStatus.FAILED.value
    assert result["stage"] == WorkflowStage.TERMINATED_WITH_ERROR.value
    assert any(e["code"] == "UNSUPPORTED_DISASTER_TYPE" for e in result["errors"])
    assert "not supported" in result["errors"][0]["message"].lower()


# ---------------------------------------------------------------------------
# Test 4: Missing Required Request Fields
# ---------------------------------------------------------------------------

def test_missing_required_request_fields():
    """4. Missing required latitude or longitude raises ValidationError on request instantiation."""
    # Missing latitude
    with pytest.raises(ValidationError):
        DisasterResponseWorkflowRequest.model_validate({
            "longitude": 78.0422,
            "disaster_type": "wildfire",
        })

    # Missing longitude
    with pytest.raises(ValidationError):
        DisasterResponseWorkflowRequest.model_validate({
            "latitude": 30.3256,
            "disaster_type": "wildfire",
        })


# ---------------------------------------------------------------------------
# Test 5: Valid Initial Workflow State
# ---------------------------------------------------------------------------

def test_valid_initial_workflow_state():
    """5. Initialized workflow state contains all required fields, valid ISO timestamps, and zero fake outputs."""
    req = DisasterResponseWorkflowRequest(
        latitude=30.3256,
        longitude=78.0422,
        disaster_type=DisasterType.WILDFIRE,
        search_radius_meters=3000.0,
        image_path="data/raw/field_cam_01.jpg",
    )
    state = initialize_workflow_state(req, workflow_id="wf-test-init-001")

    assert state["workflow_id"] == "wf-test-init-001"
    assert state["request_id"] == req.request_id
    assert state["disaster_type"] == "wildfire"
    assert state["latitude"] == 30.3256
    assert state["longitude"] == 78.0422
    assert state["search_radius_meters"] == 3000.0
    assert state["image_path"] == "data/raw/field_cam_01.jpg"
    assert state["status"] == WorkflowStatus.INITIALIZED.value
    assert state["stage"] == WorkflowStage.INITIALIZED.value
    assert state["execution_records"] == []
    assert state["errors"] == []
    assert state["warnings"] == []
    assert state["m11_assessment"] is None
    assert state["intelligence_output"] is None
    assert state["weather_output"] is None
    assert state["geospatial_output"] is None
    assert state["risk_assessment_output"] is None
    assert state["response_plan_output"] is None
    assert state["human_approval"] is None
    assert state["coordinator_report"] is None
    assert state["completed_at"] is None
    assert isinstance(state["created_at"], str)
    assert isinstance(state["updated_at"], str)


# ---------------------------------------------------------------------------
# Test 6: Invalid State Transitions Enforcement
# ---------------------------------------------------------------------------

def test_invalid_state_transitions():
    """6. Attempting illegal or out-of-order stage transitions raises InvalidStateTransitionError."""
    # Legal transitions succeed
    validate_state_transition(WorkflowStage.INITIALIZED.value, WorkflowStage.REQUEST_VALIDATION.value)
    validate_state_transition(WorkflowStage.REQUEST_VALIDATION.value, WorkflowStage.REQUEST_VALIDATED.value)
    validate_state_transition(WorkflowStage.REQUEST_VALIDATED.value, WorkflowStage.INTELLIGENCE_ASSESSMENT.value)
    validate_state_transition(WorkflowStage.REQUEST_VALIDATED.value, WorkflowStage.COMPLETED.value)

    # Illegal transition: INITIALIZED directly to COMPLETED
    with pytest.raises(InvalidStateTransitionError) as exc_info:
        validate_state_transition(WorkflowStage.INITIALIZED.value, WorkflowStage.COMPLETED.value)
    assert "Cannot transition workflow" in str(exc_info.value)
    assert exc_info.value.current_stage == WorkflowStage.INITIALIZED.value

    # Illegal transition: REQUEST_VALIDATION directly to RISK_ASSESSMENT
    with pytest.raises(InvalidStateTransitionError):
        validate_state_transition(WorkflowStage.REQUEST_VALIDATION.value, WorkflowStage.RISK_ASSESSMENT.value)

    # Illegal transition: COMPLETED to RUNNING (completed state has no outbound edges)
    with pytest.raises(InvalidStateTransitionError):
        validate_state_transition(WorkflowStage.COMPLETED.value, WorkflowStage.REQUEST_VALIDATION.value)


# ---------------------------------------------------------------------------
# Test 7: Successful Graph Compilation
# ---------------------------------------------------------------------------

def test_successful_graph_compilation():
    """7. LangGraph StateGraph compiles cleanly into a runnable CompiledStateGraph."""
    graph_builder = create_disaster_workflow_graph()
    assert graph_builder is not None

    compiled_graph = compile_workflow_graph()
    assert compiled_graph is not None
    # Verify node presence in compiled graph
    assert "validate_request" in compiled_graph.nodes


# ---------------------------------------------------------------------------
# Test 8: Successful Execution of Implemented Validation Workflow
# ---------------------------------------------------------------------------

def test_successful_execution_of_validation_workflow():
    """8. Running workflow service with valid input executes validation node and halts safely."""
    service = DisasterWorkflowService(compile_workflow_graph(include_agents=False))
    req = DisasterResponseWorkflowRequest(
        latitude=30.3256,
        longitude=78.0422,
        disaster_type=DisasterType.WILDFIRE,
        search_radius_meters=4000.0,
    )

    result: WorkflowExecutionResult = service.run_workflow(req, workflow_id="wf-exec-success")

    assert result.workflow_id == "wf-exec-success"
    assert result.request_id == req.request_id
    assert result.status == WorkflowStatus.RUNNING
    assert result.stage == WorkflowStage.REQUEST_VALIDATED
    assert result.disaster_type == "wildfire"
    assert result.location["latitude"] == 30.3256
    assert result.location["longitude"] == 78.0422
    assert result.search_radius_meters == 4000.0
    assert len(result.errors) == 0

    # Verify execution record audit trail
    assert len(result.execution_records) == 1
    rec = result.execution_records[0]
    assert rec.agent_name == "request_validator"
    assert rec.stage == WorkflowStage.REQUEST_VALIDATION.value
    assert rec.status == "success"
    assert rec.duration_seconds is not None
    assert rec.duration_seconds >= 0.0


# ---------------------------------------------------------------------------
# Test 9: Invalid Input Rejected Safely in Graph Execution
# ---------------------------------------------------------------------------

def test_invalid_input_rejected_safely():
    """9. Workflow service with invalid input terminates safely with FAILED status and error record."""
    service = DisasterWorkflowService()
    # Create request with unsupported disaster type FLOOD
    req = DisasterResponseWorkflowRequest(
        latitude=30.3256,
        longitude=78.0422,
        disaster_type=DisasterType.FLOOD,
    )

    result: WorkflowExecutionResult = service.run_workflow(req, workflow_id="wf-exec-fail")

    assert result.workflow_id == "wf-exec-fail"
    assert result.status == WorkflowStatus.FAILED
    assert result.stage == WorkflowStage.TERMINATED_WITH_ERROR
    assert len(result.errors) >= 1
    assert result.errors[0].code == "UNSUPPORTED_DISASTER_TYPE"
    assert result.completed_at is not None

    # Verify execution record captures failure
    assert len(result.execution_records) == 1
    rec = result.execution_records[0]
    assert rec.agent_name == "request_validator"
    assert rec.status == "failed"


# ---------------------------------------------------------------------------
# Test 10: No Fake Agent Outputs Generated
# ---------------------------------------------------------------------------

def test_no_fake_agent_outputs_generated():
    """10. Unimplemented agents (Agents 1-6) must NOT generate fake or placeholder outputs."""
    service = DisasterWorkflowService(compile_workflow_graph(include_agents=False))
    req = DisasterResponseWorkflowRequest(
        latitude=30.3256,
        longitude=78.0422,
        disaster_type=DisasterType.WILDFIRE,
    )
    initial_state = initialize_workflow_state(req)
    final_state = service.graph.invoke(initial_state)

    # Assert all future agent output slots remain strictly None
    assert final_state["m11_assessment"] is None
    assert final_state["intelligence_output"] is None
    assert final_state["weather_output"] is None
    assert final_state["geospatial_output"] is None
    assert final_state["risk_assessment_output"] is None
    assert final_state["response_plan_output"] is None
    assert final_state["human_approval"] is None
    assert final_state["coordinator_report"] is None


# ---------------------------------------------------------------------------
# Test 11: Errors Represented Explicitly
# ---------------------------------------------------------------------------

def test_errors_represented_explicitly():
    """11. Validation errors are structured with code, message, stage, timestamp, and agent attributes."""
    raw_state: DisasterWorkflowState = {
        "workflow_id": "wf-err-explicit",
        "request_id": "req-err-01",
        "disaster_type": "wildfire",
        "latitude": 30.0,
        "longitude": 78.0,
        "search_radius_meters": 50.0,  # Invalid: below 100m minimum
        "image_path": None,
        "source_description": "test",
        "metadata": {},
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
        "provenance": {},
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": None,
    }
    update = validate_request_node(raw_state)
    errors = update["errors"]
    assert len(errors) == 1

    err = errors[0]
    assert err["code"] == "INVALID_SEARCH_RADIUS"
    assert "100.0m" in err["message"]
    assert err["stage"] == WorkflowStage.REQUEST_VALIDATION.value
    assert err["agent"] == "request_validator"
    assert "timestamp" in err
    assert err["recoverable"] is False


# ---------------------------------------------------------------------------
# Test 12: State Serialization Compatibility
# ---------------------------------------------------------------------------

def test_state_serialization_compatibility():
    """12. DisasterWorkflowState can be serialized to JSON and round-tripped without loss."""
    req = DisasterResponseWorkflowRequest(
        latitude=30.3256,
        longitude=78.0422,
        disaster_type=DisasterType.WILDFIRE,
        search_radius_meters=5000.0,
        metadata={"region": "Uttarakhand", "station": "UK-44"},
    )
    state = initialize_workflow_state(req, workflow_id="wf-serial-001")

    # Roundtrip serialization
    json_str = serialize_workflow_state(state)
    assert isinstance(json_str, str)
    assert "wf-serial-001" in json_str

    deserialized = deserialize_workflow_state(json_str)
    assert deserialized["workflow_id"] == "wf-serial-001"
    assert deserialized["latitude"] == 30.3256
    assert deserialized["longitude"] == 78.0422
    assert deserialized["status"] == WorkflowStatus.INITIALIZED.value
    assert deserialized["metadata"]["region"] == "Uttarakhand"
    assert deserialized["errors"] == []

    # Verify standard json.loads parses cleanly
    parsed = json.loads(json_str)
    assert parsed["disaster_type"] == "wildfire"
    assert parsed["m11_assessment"] is None
