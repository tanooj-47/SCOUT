"""
backend/app/agents/exceptions.py
Domain exceptions for SCOUT Multi-Agent Disaster Response Workflow (Milestone 12).
"""

from typing import Any, Dict, Optional
from app.core.exceptions import SCOUTException


class AgentWorkflowError(SCOUTException):
    """Base exception for all multi-agent disaster response workflow failures."""

    def __init__(
        self,
        code: str = "AGENT_WORKFLOW_ERROR",
        message: str = "An error occurred during workflow execution",
        status_code: int = 400,
        details: Optional[Dict[str, Any]] = None,
        stage: Optional[str] = None,
        agent: Optional[str] = None,
    ) -> None:
        super().__init__(code=code, message=message, status_code=status_code, details=details or {})
        self.stage = stage
        self.agent = agent


class WorkflowValidationError(AgentWorkflowError):
    """Raised when request payload or initial graph state fails domain validation rules."""

    def __init__(self, message: str, field: Optional[str] = None) -> None:
        details = {"field": field} if field else {}
        super().__init__(
            code="WORKFLOW_VALIDATION_ERROR",
            message=message,
            status_code=400,
            details=details,
            stage="request_validation",
        )
        self.field = field


class WorkflowExecutionError(AgentWorkflowError):
    """Raised when an unrecoverable error occurs during graph node execution."""

    def __init__(
        self,
        message: str,
        stage: Optional[str] = None,
        agent: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            code="WORKFLOW_EXECUTION_ERROR",
            message=message,
            status_code=500,
            details=details,
            stage=stage,
            agent=agent,
        )


class InvalidStateTransitionError(AgentWorkflowError):
    """Raised when an illegal or unsupported workflow lifecycle stage transition is attempted."""

    def __init__(self, current_stage: str, target_stage: str, reason: str = "") -> None:
        msg = f"Cannot transition workflow from '{current_stage}' to '{target_stage}'. {reason}".strip()
        super().__init__(
            code="INVALID_STATE_TRANSITION",
            message=msg,
            status_code=409,
            details={"current_stage": current_stage, "target_stage": target_stage},
            stage=current_stage,
        )
        self.current_stage = current_stage
        self.target_stage = target_stage

