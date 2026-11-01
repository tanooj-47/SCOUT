"""
backend/app/environmental/providers/base.py
Abstract base class and execution harness for external environmental data providers.
"""

from abc import ABC, abstractmethod
from datetime import date
import logging
import random
import time
from typing import Any, Callable, Dict, Optional
import httpx

from app.core.config import settings
from app.environmental.exceptions import (
    ProviderAPIError,
    ProviderRateLimitError,
    ProviderTimeoutError,
)

logger = logging.getLogger(__name__)


class BaseWeatherProvider(ABC):
    """
    Abstract interface for external meteorological and environmental data providers.
    Every provider client must implement current, historical, forecast, and health capabilities.
    """

    def __init__(
        self,
        name: str,
        timeout_seconds: Optional[float] = None,
        max_retries: Optional[int] = None,
        backoff_factor: Optional[float] = None,
        transport: Optional[httpx.BaseTransport] = None,
        sleep_func: Optional[Callable[[float], None]] = None,
    ):
        self.name = name
        self.timeout_seconds = timeout_seconds or settings.ENVIRONMENTAL_REQUEST_TIMEOUT_SECONDS
        self.max_retries = max_retries if max_retries is not None else settings.ENVIRONMENTAL_MAX_RETRIES
        self.backoff_factor = backoff_factor if backoff_factor is not None else settings.ENVIRONMENTAL_BACKOFF_FACTOR
        self.transport = transport
        self.sleep_func = sleep_func or time.sleep

    def _create_client(self) -> httpx.Client:
        """Instantiates an HTTPX synchronous client with configured timeout and transport."""
        return httpx.Client(
            timeout=self.timeout_seconds,
            transport=self.transport,
            follow_redirects=True,
        )

    def execute_request_with_retry(
        self,
        method: str,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Executes an HTTP request with bounded exponential backoff and jitter for transient failures.
        Retries on timeouts, connection errors, HTTP 429, and HTTP 5xx responses.
        Does NOT retry non-transient 4xx client errors.
        """
        attempt = 0
        last_exception: Optional[Exception] = None

        with self._create_client() as client:
            while attempt <= self.max_retries:
                try:
                    logger.debug(
                        "[%s] HTTP %s %s (attempt %d/%d) params=%s",
                        self.name,
                        method,
                        url,
                        attempt + 1,
                        self.max_retries + 1,
                        params,
                    )
                    response = client.request(method=method, url=url, params=params, headers=headers)

                    # Handle HTTP 429 Rate Limiting
                    if response.status_code == 429:
                        retry_after = response.headers.get("Retry-After")
                        wait_sec = float(retry_after) if retry_after and retry_after.isdigit() else (
                            self.backoff_factor * (2 ** attempt) + random.uniform(0.05, 0.2)
                        )
                        if attempt < self.max_retries:
                            logger.warning("[%s] HTTP 429 Throttled. Backing off for %.2fs", self.name, wait_sec)
                            self.sleep_func(wait_sec)
                            attempt += 1
                            continue
                        raise ProviderRateLimitError(provider=self.name, retry_after=int(wait_sec))

                    # Handle 5xx Upstream Server Errors
                    if 500 <= response.status_code < 600:
                        if attempt < self.max_retries:
                            wait_sec = self.backoff_factor * (2 ** attempt) + random.uniform(0.05, 0.2)
                            logger.warning(
                                "[%s] HTTP %d transient error. Retrying in %.2fs...",
                                self.name,
                                response.status_code,
                                wait_sec,
                            )
                            self.sleep_func(wait_sec)
                            attempt += 1
                            continue
                        raise ProviderAPIError(
                            provider=self.name,
                            status_code=response.status_code,
                            message=f"Upstream server error: {response.text[:200]}",
                        )

                    # Handle 4xx Client Errors (do not retry)
                    if 400 <= response.status_code < 500:
                        raise ProviderAPIError(
                            provider=self.name,
                            status_code=response.status_code,
                            message=f"Client request rejected: {response.text[:200]}",
                        )

                    # Parse JSON payload
                    try:
                        return response.json()
                    except Exception as json_err:
                        raise ProviderAPIError(
                            provider=self.name,
                            status_code=response.status_code,
                            message=f"Malformed JSON in response: {str(json_err)}",
                        ) from json_err

                except httpx.TimeoutException as exc:
                    last_exception = exc
                    if attempt < self.max_retries:
                        wait_sec = self.backoff_factor * (2 ** attempt) + random.uniform(0.05, 0.2)
                        logger.warning("[%s] Request timed out. Retrying in %.2fs...", self.name, wait_sec)
                        self.sleep_func(wait_sec)
                        attempt += 1
                        continue
                    raise ProviderTimeoutError(provider=self.name, timeout_seconds=self.timeout_seconds) from exc

                except httpx.NetworkError as exc:
                    last_exception = exc
                    if attempt < self.max_retries:
                        wait_sec = self.backoff_factor * (2 ** attempt) + random.uniform(0.05, 0.2)
                        logger.warning("[%s] Network connection error (%s). Retrying in %.2fs...", self.name, exc, wait_sec)
                        self.sleep_func(wait_sec)
                        attempt += 1
                        continue
                    raise ProviderAPIError(
                        provider=self.name,
                        status_code=502,
                        message=f"Network connection failed after {self.max_retries + 1} attempts: {exc}",
                    ) from exc

        # Fallback if loop finishes unexpectedly
        raise ProviderAPIError(
            provider=self.name,
            status_code=502,
            message=f"Failed to communicate with provider: {last_exception}",
        )

    @abstractmethod
    def get_current_conditions(self, latitude: float, longitude: float) -> Dict[str, Any]:
        """Retrieves real-time or nowcast model atmospheric conditions for a point."""
        pass

    @abstractmethod
    def get_historical_weather(
        self,
        latitude: float,
        longitude: float,
        start_date: date,
        end_date: date,
    ) -> Dict[str, Any]:
        """Retrieves retrospective gridded observations or reanalysis over a time range."""
        pass

    @abstractmethod
    def get_weather_forecast(
        self,
        latitude: float,
        longitude: float,
        forecast_days: int = 7,
    ) -> Dict[str, Any]:
        """Retrieves forward numerical weather predictions for a point."""
        pass

    @abstractmethod
    def check_health(self) -> Dict[str, Any]:
        """Executes a lightweight diagnostic probe to verify provider configuration and reachability."""
        pass
