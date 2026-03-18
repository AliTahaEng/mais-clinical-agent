"""Unit tests for the circuit breaker."""
from __future__ import annotations

import asyncio

import pytest

from medical_ais.core.circuit_breaker import CircuitBreaker, CircuitState
from medical_ais.core.exceptions import CircuitBreakerOpenError, ServiceUnavailableError


@pytest.mark.asyncio
async def test_closed_state_success():
    cb = CircuitBreaker(name="test", failure_threshold=3, retry_attempts=1)

    async def always_ok():
        return "ok"

    result = await cb.execute(always_ok)
    assert result == "ok"
    assert cb.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_opens_after_threshold():
    cb = CircuitBreaker(name="test", failure_threshold=2, retry_attempts=1)

    async def always_fail():
        raise RuntimeError("boom")

    with pytest.raises(ServiceUnavailableError):
        await cb.execute(always_fail)
    with pytest.raises(ServiceUnavailableError):
        await cb.execute(always_fail)

    assert cb.state == CircuitState.OPEN


@pytest.mark.asyncio
async def test_open_raises_circuit_breaker_error():
    cb = CircuitBreaker(
        name="test", failure_threshold=1, retry_attempts=1, reset_timeout=9999
    )

    async def fail():
        raise RuntimeError("x")

    with pytest.raises(ServiceUnavailableError):
        await cb.execute(fail)

    with pytest.raises(CircuitBreakerOpenError):
        await cb.execute(fail)


@pytest.mark.asyncio
async def test_reset_on_success():
    cb = CircuitBreaker(name="test", failure_threshold=1, retry_attempts=1)

    async def fail():
        raise RuntimeError("x")

    async def succeed():
        return "ok"

    with pytest.raises(ServiceUnavailableError):
        await cb.execute(fail)

    # Force half-open by backdating last_failure_time
    cb._last_failure_time = 0  # epoch → timeout already elapsed
    cb._state = CircuitState.HALF_OPEN

    result = await cb.execute(succeed)
    assert result == "ok"
    assert cb.state == CircuitState.CLOSED
