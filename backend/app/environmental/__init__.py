"""
backend/app/environmental/__init__.py
SCOUT Environmental Data Integration Subsystem.
"""

from app.environmental.exceptions import (
    EnvironmentalException,
    ProviderAPIError,
    ProviderTimeoutError,
    ProviderRateLimitError,
    TimeRangeUnavailableError,
    NormalizationError,
    FWICalculationError,
    FWITimeseriesGapError,
)

__all__ = [
    "EnvironmentalException",
    "ProviderAPIError",
    "ProviderTimeoutError",
    "ProviderRateLimitError",
    "TimeRangeUnavailableError",
    "NormalizationError",
    "FWICalculationError",
    "FWITimeseriesGapError",
]
