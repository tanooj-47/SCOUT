"""
backend/app/environmental/exceptions.py
Domain exceptions for SCOUT Environmental Data Integration Subsystem.
Inherits from SCOUTException for uniform HTTP error envelope handling.
"""

from typing import Any, Dict, Optional
from app.core.exceptions import SCOUTException


class EnvironmentalException(SCOUTException):
    """Base domain exception for environmental subsystem."""
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(code=code, message=message, status_code=status_code, details=details)


class ProviderAPIError(EnvironmentalException):
    """Raised when an external weather provider returns a 4xx/5xx HTTP error or malformed payload."""
    def __init__(self, provider: str, status_code: int, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            code="PROVIDER_API_ERROR",
            message=f"External provider '{provider}' returned error: {message}",
            status_code=status_code if 400 <= status_code < 600 else 502,
            details={"provider": provider, "upstream_status": status_code, **(details or {})},
        )


class ProviderTimeoutError(EnvironmentalException):
    """Raised when an external provider request times out."""
    def __init__(self, provider: str, timeout_seconds: float):
        super().__init__(
            code="PROVIDER_TIMEOUT",
            message=f"Request to environmental provider '{provider}' timed out after {timeout_seconds}s.",
            status_code=504,
            details={"provider": provider, "timeout_seconds": timeout_seconds},
        )


class ProviderRateLimitError(EnvironmentalException):
    """Raised when an external provider throttles requests (HTTP 429)."""
    def __init__(self, provider: str, retry_after: Optional[int] = None):
        super().__init__(
            code="PROVIDER_RATE_LIMIT",
            message=f"Rate limit exceeded for environmental provider '{provider}'.",
            status_code=429,
            details={"provider": provider, "retry_after": retry_after},
        )


class TimeRangeUnavailableError(EnvironmentalException):
    """Raised when a requested temporal window is not supported by the provider."""
    def __init__(self, provider: str, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            code="TIME_RANGE_UNAVAILABLE",
            message=f"Requested time range is unavailable from provider '{provider}': {message}",
            status_code=422,
            details={"provider": provider, **(details or {})},
        )


class NormalizationError(EnvironmentalException):
    """Raised when provider data fails physical plausibility checks or unit normalization."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            code="NORMALIZATION_ERROR",
            message=f"Environmental normalization error: {message}",
            status_code=422,
            details=details,
        )


class FWICalculationError(EnvironmentalException):
    """Raised when Fire Weather Index calculation preconditions are violated."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            code="FWI_CALCULATION_ERROR",
            message=f"FWI calculation failed: {message}",
            status_code=422,
            details=details,
        )


class FWITimeseriesGapError(FWICalculationError):
    """Raised when non-consecutive, duplicate, or out-of-order dates are detected in recursive FWI calculations."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            details=details,
        )
        self.code = "FWI_TIMESERIES_GAP"
