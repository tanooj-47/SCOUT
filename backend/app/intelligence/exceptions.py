"""
backend/app/intelligence/exceptions.py
Domain exceptions for SCOUT Multimodal Disaster Intelligence (Milestone 11).
"""

from typing import Optional


class IntelligenceException(Exception):
    """Base exception for all multimodal intelligence operations."""

    def __init__(self, message: str, details: Optional[dict] = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class UnsupportedDisasterTypeError(IntelligenceException):
    """Raised when an assessment or model is requested for an unsupported or uncalibrated hazard."""

    def __init__(self, disaster_type: str, supported: list[str]) -> None:
        msg = f"Disaster type '{disaster_type}' is not supported. Supported types: {supported}"
        super().__init__(msg, details={"disaster_type": disaster_type, "supported": supported})


class ProviderUnavailableError(IntelligenceException):
    """Raised when an external or downstream provider cannot fulfill an evidence request."""

    def __init__(self, provider_name: str, reason: str) -> None:
        msg = f"Intelligence provider '{provider_name}' unavailable: {reason}"
        super().__init__(msg, details={"provider": provider_name, "reason": reason})


class StaleDataError(IntelligenceException):
    """Raised when evidence freshness exceeds operational thresholds and no fresh data is available."""

    def __init__(self, stream_name: str, age_hours: float, threshold_hours: float) -> None:
        msg = f"Evidence '{stream_name}' is stale ({age_hours:.1f}h old; threshold {threshold_hours:.1f}h)"
        super().__init__(
            msg,
            details={"stream": stream_name, "age_hours": age_hours, "threshold_hours": threshold_hours},
        )


class InsufficientDataError(IntelligenceException):
    """Raised when missing evidence precludes computing a defensible assessment."""

    def __init__(self, missing_streams: list[str], reason: str) -> None:
        msg = f"Insufficient data for intelligence assessment. Missing: {missing_streams}. {reason}"
        super().__init__(msg, details={"missing_streams": missing_streams, "reason": reason})


class InvalidEvidenceError(IntelligenceException):
    """Raised when evidence fails structural, semantic, or boundary validation."""

    def __init__(self, evidence_id: str, reason: str) -> None:
        msg = f"Evidence '{evidence_id}' is invalid: {reason}"
        super().__init__(msg, details={"evidence_id": evidence_id, "reason": reason})


class VisionInferenceError(IntelligenceException):
    """Raised when computer vision inference encounters an unrecoverable runtime failure."""

    def __init__(self, reason: str) -> None:
        msg = f"Computer vision inference failed: {reason}"
        super().__init__(msg, details={"reason": reason})
