"""
Circuit Breaker pattern implementation.
Wraps all external service calls (LLM, Neo4j, EHR, Redis).
States: CLOSED (normal) → OPEN (failing) → HALF_OPEN (testing recovery)
"""
from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from enum import Enum
from typing import Any, TypeVar

import structlog

from medical_ais.core.exceptions import CircuitBreakerOpenError, ServiceUnavailableError

logger = structlog.get_logger(__name__)

T = TypeVar("T")


class CircuitState(str, Enum):
    CLOSED = "CLOSED"       # Normal operation
    OPEN = "OPEN"           # Failing — reject all calls
    HALF_OPEN = "HALF_OPEN" # Testing — allow one probe call


class CircuitBreaker:
    """
    Thread-safe async circuit breaker.
    Wraps external calls with automatic retry + failure detection.
    """

    def __init__(
        self,
        name: str = "default",
        failure_threshold: int = 5,
        reset_timeout: float = 60.0,
        retry_attempts: int = 3,
        retry_delay: float = 1.0,
        retry_backoff: float = 2.0,
    ) -> None:
        self.name = name
        self._failure_threshold = failure_threshold
        self._reset_timeout = reset_timeout
        self._retry_attempts = retry_attempts
        self._retry_delay = retry_delay
        self._retry_backoff = retry_backoff

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float | None = None
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        return self._state

    async def execute(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """
        Execute fn with retry and circuit breaker protection.
        Raises CircuitBreakerOpenError if circuit is OPEN.
        """
        async with self._lock:
            if self._state == CircuitState.OPEN:
                # Check if enough time has passed to try half-open
                if (
                    self._last_failure_time
                    and time.monotonic() - self._last_failure_time >= self._reset_timeout
                ):
                    self._state = CircuitState.HALF_OPEN
                    logger.info("circuit_breaker.half_open", name=self.name)
                else:
                    raise CircuitBreakerOpenError(
                        f"Circuit breaker '{self.name}' is OPEN — service unavailable"
                    )

        # Execute with retry
        last_error: Exception | None = None
        delay = self._retry_delay

        for attempt in range(1, self._retry_attempts + 1):
            try:
                result = await fn(*args, **kwargs)
                await self._on_success()
                return result
            except CircuitBreakerOpenError:
                raise
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "circuit_breaker.retry",
                    name=self.name,
                    attempt=attempt,
                    max_attempts=self._retry_attempts,
                    error=str(exc),
                )
                if attempt < self._retry_attempts:
                    await asyncio.sleep(delay)
                    delay *= self._retry_backoff

        await self._on_failure()
        raise ServiceUnavailableError(
            f"Service '{self.name}' failed after {self._retry_attempts} attempts",
            details={"last_error": str(last_error)},
        ) from last_error

    async def _on_success(self) -> None:
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                logger.info("circuit_breaker.closed", name=self.name)
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._last_failure_time = None

    async def _on_failure(self) -> None:
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()

            if self._failure_count >= self._failure_threshold:
                self._state = CircuitState.OPEN
                logger.error(
                    "circuit_breaker.opened",
                    name=self.name,
                    failures=self._failure_count,
                )
            else:
                logger.warning(
                    "circuit_breaker.failure",
                    name=self.name,
                    failures=self._failure_count,
                    threshold=self._failure_threshold,
                )
