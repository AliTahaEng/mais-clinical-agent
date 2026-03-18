"""
Approval store — persists pending human-approval requests using ICacheStore.

Keys: approval:{session_id}
TTL: 24 hours (configurable)
Value: JSON-serialisable dict with approval request details
"""
from __future__ import annotations

import structlog
from typing import Any

from medical_ais.interfaces.cache import ICacheStore

logger = structlog.get_logger(__name__)

_DEFAULT_TTL = 86_400  # 24 hours


class ApprovalStore:
    """
    Wraps ICacheStore with approval-specific helpers.
    Writes approval requests BEFORE LangGraph interrupt() is called.
    """

    KEY_PREFIX = "approval:"

    def __init__(self, cache: ICacheStore, ttl_seconds: int = _DEFAULT_TTL) -> None:
        self._cache = cache
        self._ttl = ttl_seconds

    def _key(self, session_id: str) -> str:
        return f"{self.KEY_PREFIX}{session_id}"

    async def save(
        self,
        session_id: str,
        proposed_actions: list[dict[str, Any]],
        message: str = "",
    ) -> None:
        """Persist an approval request so the UI can show it."""
        payload: dict[str, Any] = {
            "session_id": session_id,
            "message": message,
            "proposed_actions": proposed_actions,
            "status": "pending",
        }
        await self._cache.set(self._key(session_id), payload, ttl_seconds=self._ttl)
        logger.info("approval_store.saved", session_id=session_id, actions=len(proposed_actions))

    async def get(self, session_id: str) -> dict[str, Any] | None:
        """Return approval request for *session_id*, or None if expired/missing."""
        return await self._cache.get(self._key(session_id))

    async def list_pending(self) -> list[dict[str, Any]]:
        """Return all pending approval requests."""
        keys = await self._cache.scan_keys(f"{self.KEY_PREFIX}*")
        results: list[dict[str, Any]] = []
        for key in keys:
            value = await self._cache.get(key)
            if value is not None:
                results.append(value)
        return results

    async def delete(self, session_id: str) -> None:
        """Remove an approval request (after decision is made)."""
        await self._cache.delete(self._key(session_id))
        logger.info("approval_store.deleted", session_id=session_id)

    async def mark_decided(
        self,
        session_id: str,
        approved_indices: list[int],
        feedback: str,
    ) -> None:
        """Update the approval status to 'decided' for audit trail."""
        existing = await self.get(session_id)
        if existing:
            existing["status"] = "decided"
            existing["approved_indices"] = approved_indices
            existing["feedback"] = feedback
            # Keep for short window after decision (5 min) so UI can show result
            await self._cache.set(self._key(session_id), existing, ttl_seconds=300)
