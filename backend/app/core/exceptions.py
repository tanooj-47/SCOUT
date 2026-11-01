import logging
from typing import Any, Dict, Optional
from uuid import UUID
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class SCOUTException(Exception):
    """Base domain exception for SCOUT application."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


class IncidentNotFoundError(SCOUTException):
    """Raised when an incident is not found by ID."""

    def __init__(self, incident_id: UUID):
        super().__init__(
            code="INCIDENT_NOT_FOUND",
            message=f"Incident with ID '{incident_id}' was not found.",
            status_code=404,
            details={"incident_id": str(incident_id)},
        )


class InvalidStatusTransitionError(SCOUTException):
    """Raised when an invalid lifecycle status transition is requested."""

    def __init__(self, current_status: str, target_status: str):
        super().__init__(
            code="INVALID_STATUS_TRANSITION",
            message=f"Cannot transition incident status from '{current_status}' to '{target_status}'.",
            status_code=409,
            details={"current_status": current_status, "target_status": target_status},
        )


class ArchivedIncidentModificationError(SCOUTException):
    """Raised when an update is attempted on an archived (immutable) incident."""

    def __init__(self, incident_id: UUID):
        super().__init__(
            code="INCIDENT_ARCHIVED",
            message=f"Incident '{incident_id}' is archived and cannot be modified.",
            status_code=409,
            details={"incident_id": str(incident_id)},
        )


class DatabaseConflictError(SCOUTException):
    """Raised when a database constraint or state conflict occurs."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            code="INTEGRITY_VIOLATION",
            message=message,
            status_code=409,
            details=details or {},
        )


class InternalServiceError(SCOUTException):
    """Raised for unexpected service-level failures."""

    def __init__(self, message: str = "An internal error occurred."):
        super().__init__(
            code="INTERNAL_SERVER_ERROR",
            message=message,
            status_code=500,
            details={},
        )


class MediaNotFoundError(SCOUTException):
    """Raised when a media record is not found by ID."""

    def __init__(self, media_id: UUID):
        super().__init__(
            code="MEDIA_NOT_FOUND",
            message=f"Media record with ID '{media_id}' was not found.",
            status_code=404,
            details={"media_id": str(media_id)},
        )


class UnsupportedMediaFormatError(SCOUTException):
    """Raised when an uploaded file is not an approved raster image format."""

    def __init__(self, message: str = "Unsupported media format. Only JPEG, PNG, and WebP raster images are accepted."):
        super().__init__(
            code="UNSUPPORTED_MEDIA_FORMAT",
            message=message,
            status_code=415,
            details={"supported_formats": ["jpeg", "png", "webp"]},
        )


class MediaSizeLimitExceededError(SCOUTException):
    """Raised when an uploaded file exceeds the configured maximum size limit."""

    def __init__(self, max_bytes: int, received_bytes: Optional[int] = None):
        super().__init__(
            code="PAYLOAD_TOO_LARGE",
            message=f"Uploaded file exceeds the maximum permitted size limit of {max_bytes} bytes.",
            status_code=413,
            details={"max_bytes": max_bytes, "received_bytes": received_bytes},
        )


class EmptyFileError(SCOUTException):
    """Raised when an uploaded file is empty (0 bytes)."""

    def __init__(self, message: str = "Uploaded file is empty (0 bytes)."):
        super().__init__(
            code="EMPTY_FILE",
            message=message,
            status_code=400,
            details={},
        )


class InvalidCoordinatesError(SCOUTException):
    """Raised when geographic coordinates are invalid or partially supplied."""

    def __init__(self, message: str = "Invalid coordinates. Both latitude and longitude must be provided together."):
        super().__init__(
            code="INVALID_COORDINATES",
            message=message,
            status_code=400,
            details={},
        )


class InvalidSourceTypeError(SCOUTException):
    """Raised when the acquisition source type is malformed, empty, or invalid."""

    def __init__(self, message: str = "Invalid source type."):
        super().__init__(
            code="INVALID_SOURCE_TYPE",
            message=message,
            status_code=400,
            details={},
        )


class WorkflowNotFoundError(SCOUTException):
    """Raised when a disaster workflow record is not found by ID."""

    def __init__(self, workflow_id: str):
        super().__init__(
            code="WORKFLOW_NOT_FOUND",
            message=f"Disaster workflow '{workflow_id}' was not found.",
            status_code=404,
            details={"workflow_id": workflow_id},
        )


class WorkflowExecutionFailedError(SCOUTException):
    """Raised when a disaster workflow fails unrecoverably during agent execution."""

    def __init__(self, workflow_id: str, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            code="WORKFLOW_EXECUTION_FAILED",
            message=message,
            status_code=422,
            details={"workflow_id": workflow_id, **(details or {})},
        )


class WorkflowApprovalConflictError(SCOUTException):
    """Raised when an approval decision is submitted for a workflow that is not in pending status."""

    def __init__(self, workflow_id: str, current_status: str, message: Optional[str] = None):
        msg = message or f"Cannot record approval decision: workflow '{workflow_id}' approval status is already '{current_status}'."
        super().__init__(
            code="APPROVAL_CONFLICT",
            message=msg,
            status_code=409,
            details={"workflow_id": workflow_id, "current_status": current_status},
        )


class UnauthorizedReviewerError(SCOUTException):
    """Raised when a request attempts to submit human approval without valid authentication credentials."""

    def __init__(self, message: str = "Missing or malformed reviewer authentication credentials."):
        super().__init__(
            code="UNAUTHORIZED_REVIEWER",
            message=message,
            status_code=401,
            details={},
        )


class ForbiddenReviewerError(SCOUTException):
    """Raised when a reviewer token is invalid, expired, or possesses insufficient permissions."""

    def __init__(self, message: str = "Reviewer token is invalid or lacks required incident commander permissions."):
        super().__init__(
            code="FORBIDDEN_REVIEWER",
            message=message,
            status_code=403,
            details={},
        )


class AuthenticationServiceUnavailableError(SCOUTException):
    """Raised when human approval is attempted in production without an authoritative Identity Provider configured."""

    def __init__(
        self,
        message: str = (
            "Authentication provider not configured for production approval operations. "
            "Approval endpoints are disabled in production until an authoritative Identity Provider (IdP) is integrated."
        ),
    ):
        super().__init__(
            code="AUTH_SERVICE_UNAVAILABLE",
            message=message,
            status_code=503,
            details={"environment": "production"},
        )


class StorageError(SCOUTException):
    """Raised when an error occurs during filesystem storage operations."""

    def __init__(self, message: str = "A storage operation failed."):
        super().__init__(
            code="STORAGE_ERROR",
            message=message,
            status_code=500,
            details={},
        )


class MediaPersistenceUncertainError(SCOUTException):
    """Raised when media record persistence outcome cannot be confirmed after a commit failure (HTTP 503)."""

    def __init__(
        self,
        media_id: UUID,
        message: str = "Media upload persistence could not be verified. Evidence preserved for operator reconciliation.",
    ):
        super().__init__(
            code="SERVICE_UNAVAILABLE",
            message=message,
            status_code=503,
            details={"media_id": str(media_id)},
        )


async def scout_exception_handler(request: Request, exc: SCOUTException) -> JSONResponse:
    """Handles all SCOUT custom domain exceptions with standard error envelope."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            }
        },
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handles FastAPI/Pydantic request validation errors with standard error envelope."""
    # Convert error tuples to clean serializable dict
    formatted_errors = []
    for err in exc.errors():
        loc = [str(x) for x in err.get("loc", [])]
        formatted_errors.append({
            "field": ".".join(loc[1:]) if len(loc) > 1 else (loc[0] if loc else ""),
            "message": err.get("msg", ""),
            "type": err.get("type", ""),
        })

    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed.",
                "details": {"errors": formatted_errors},
            }
        },
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Handles standard Starlette/FastAPI HTTPExceptions (e.g. 404 for unknown routes)."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": "NOT_FOUND" if exc.status_code == 404 else "HTTP_ERROR",
                "message": str(exc.detail),
                "details": {},
            }
        },
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Safely catches unhandled exceptions, logs trace, and prevents leaking database internals."""
    logger.exception("Unhandled server exception on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected server error occurred.",
                "details": {},
            }
        },
    )
