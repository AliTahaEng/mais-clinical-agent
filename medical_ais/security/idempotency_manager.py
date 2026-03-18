"""
Idempotency manager for action execution.
Prevents duplicate EHR writes if the same action is retried.
Uses the cache store to track executed idempotency keys.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

import structlog

from medical_ais.interfaces.cache import ICacheStore

logger = structlog.get_logger(__name__)

_TTL_SECONDS = 86_400  # 24 hours — enough to cover any reasonable retry window


def make_idempotency_key(tool_name: str, parameters: dict[str, Any]) -> str:
    """Derive a deterministic key from (tool_name, parameters)."""
    canonical = json.dumps({"tool": tool_name, "params": parameters}, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


class IdempotencyManager:
    """
    Wraps action execution with a key-based deduplication layer.

    Usage::

        if await manager.is_duplicate(key):
            return cached_result
        result = await execute_action(...)
        await manager.mark_executed(key, result)
    """

    def __init__(self, cache: ICacheStore) -> None:
        self._cache = cache

    async def is_duplicate(self, key: str) -> bool:
        """Return True if this key has already been executed."""
        return await self._cache.exists(f"idempotency:{key}")

    async def get_cached_result(self, key: str) -> Any | None:
        """Return the stored result for *key*, or None if not found."""
        return await self._cache.get(f"idempotency:{key}")

    async def mark_executed(self, key: str, result: Any) -> None:
        """Store *result* for *key* so duplicates can be detected."""
        await self._cache.set(f"idempotency:{key}", result, ttl_seconds=_TTL_SECONDS)
        logger.debug("idempotency.marked", key=key[:16] + "...")
