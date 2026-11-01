"""
backend/app/agents/nodes/validation.py
Request validation node for the LangGraph multi-agent disaster response workflow.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List

from app.agents.schemas import AgentExecutionRecord, WorkflowError, WorkflowStage, WorkflowStatus
from app.agents.state import DisasterWorkflowState
from app.schemas.incident import DisasterType

logger = logging.getLogger(__name__)

# Currently calibrated and supported disaster categories in M11 model registry
SUPPORTED_DISASTER_TYPES = {DisasterType.WILDFIRE.value}


def validate_request_node(state: DisasterWorkflowState) -> Dict[str, Any]:
    """
    Validates disaster workflow request parameters.
    Checks coordinate bounds, geographic search radius, and supported hazard types.
    Does NOT fabricate agent outputs or allow uncalibrated disaster types to proceed.
    """
    start_time = datetime.now(timezone.utc)
    errors: List[Dict[str, Any]] = []
    warnings: List[str] = []

    # 1. Coordinate Validation
    lat = state.get("latitude")
    lon = state.get("longitude")

    if lat is None:
        errors.append(
            WorkflowError(
                code="MISSING_COORDINATES",
                message="Latitude is required but was not provided.",
                stage=WorkflowStage.REQUEST_VALIDATION.value,
                agent="request_validator",
            ).model_dump(mode="json")
        )
    elif not (-90.0 <= float(lat) <= 90.0):
        errors.append(
            WorkflowError(
                code="INVALID_COORDINATES_LATITUDE",
                message=f"Latitude {lat} is out of bounds. Must be between -90.0 and 90.0 degrees.",
                stage=WorkflowStage.REQUEST_VALIDATION.value,
                agent="request_validator",
            ).model_dump(mode="json")
        )

    if lon is None:
        errors.append(
            WorkflowError(
                code="MISSING_COORDINATES",
                message="Longitude is required but was not provided.",
                stage=WorkflowStage.REQUEST_VALIDATION.value,
                agent="request_validator",
            ).model_dump(mode="json")
        )
    elif not (-180.0 <= float(lon) <= 180.0):
        errors.append(
            WorkflowError(
                code="INVALID_COORDINATES_LONGITUDE",
                message=f"Longitude {lon} is out of bounds. Must be between -180.0 and 180.0 degrees.",
                stage=WorkflowStage.REQUEST_VALIDATION.value,
                agent="request_validator",
            ).model_dump(mode="json")
        )

    # 2. Search Radius Validation
    radius = state.get("search_radius_meters")
    if radius is not None:
        if radius < 100.0 or radius > 100000.0:
            errors.append(
                WorkflowError(
                    code="INVALID_SEARCH_RADIUS",
                    message=f"Search radius {radius}m is invalid. Must be between 100.0m and 100,000.0m.",
                    stage=WorkflowStage.REQUEST_VALIDATION.value,
                    agent="request_validator",
                ).model_dump(mode="json")
            )

    # 3. Disaster Category Support Validation
    disaster_type = state.get("disaster_type")
    if not disaster_type:
        errors.append(
            WorkflowError(
                code="MISSING_DISASTER_TYPE",
                message="Disaster category is required but was not provided.",
                stage=WorkflowStage.REQUEST_VALIDATION.value,
                agent="request_validator",
            ).model_dump(mode="json")
        )
    elif disaster_type not in SUPPORTED_DISASTER_TYPES:
        errors.append(
            WorkflowError(
                code="UNSUPPORTED_DISASTER_TYPE",
                message=(
                    f"Disaster type '{disaster_type}' is not supported by calibrated models in SCOUT. "
                    f"Currently supported operational disaster types: {sorted(list(SUPPORTED_DISASTER_TYPES))}."
                ),
                stage=WorkflowStage.REQUEST_VALIDATION.value,
                agent="request_validator",
            ).model_dump(mode="json")
        )

    end_time = datetime.now(timezone.utc)
    duration = (end_time - start_time).total_seconds()
    now_iso = end_time.isoformat()

    if errors:
        logger.warning(
            "Workflow request validation failed for request %s: %s",
            state.get("request_id"),
            [e["message"] for e in errors],
        )
        rec = AgentExecutionRecord(
            agent_name="request_validator",
            stage=WorkflowStage.REQUEST_VALIDATION.value,
            status="failed",
            start_time=start_time,
            end_time=end_time,
            duration_seconds=round(duration, 4),
            details=f"Validation failed with {len(errors)} error(s).",
        ).model_dump(mode="json")

        return {
            "status": WorkflowStatus.FAILED.value,
            "stage": WorkflowStage.TERMINATED_WITH_ERROR.value,
            "errors": errors,
            "warnings": warnings,
            "execution_records": [rec],
            "updated_at": now_iso,
            "completed_at": now_iso,
        }

    # Request is valid
    logger.info("Workflow request validated successfully for request %s", state.get("request_id"))
    rec = AgentExecutionRecord(
        agent_name="request_validator",
        stage=WorkflowStage.REQUEST_VALIDATION.value,
        status="success",
        start_time=start_time,
        end_time=end_time,
        duration_seconds=round(duration, 4),
        details="Coordinates, search radius, and disaster category successfully verified.",
    ).model_dump(mode="json")

    return {
        "status": WorkflowStatus.RUNNING.value,
        "stage": WorkflowStage.REQUEST_VALIDATED.value,
        "warnings": warnings,
        "execution_records": [rec],
        "updated_at": now_iso,
    }
