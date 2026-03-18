"""Unit tests for the idempotency manager."""
from __future__ import annotations

import pytest

from medical_ais.adapters.storage.in_memory_cache import InMemoryCacheAdapter
from medical_ais.security.idempotency_manager import IdempotencyManager, make_idempotency_key


def test_make_idempotency_key_deterministic():
    k1 = make_idempotency_key("write_ehr_alert", {"patient_id": "P001", "message": "test"})
    k2 = make_idempotency_key("write_ehr_alert", {"patient_id": "P001", "message": "test"})
    assert k1 == k2


def test_make_idempotency_key_different_inputs():
    k1 = make_idempotency_key("write_ehr_alert", {"patient_id": "P001"})
    k2 = make_idempotency_key("write_ehr_alert", {"patient_id": "P002"})
    assert k1 != k2


@pytest.mark.asyncio
async def test_not_duplicate_initially():
    manager = IdempotencyManager(InMemoryCacheAdapter())
    key = make_idempotency_key("tool", {"p": 1})
    assert not await manager.is_duplicate(key)


@pytest.mark.asyncio
async def test_duplicate_after_mark():
    manager = IdempotencyManager(InMemoryCacheAdapter())
    key = make_idempotency_key("tool", {"p": 1})
    await manager.mark_executed(key, {"result": "done"})
    assert await manager.is_duplicate(key)


@pytest.mark.asyncio
async def test_cached_result_returned():
    manager = IdempotencyManager(InMemoryCacheAdapter())
    key = make_idempotency_key("tool", {"x": 42})
    await manager.mark_executed(key, {"output": "value"})
    result = await manager.get_cached_result(key)
    assert result == {"output": "value"}
