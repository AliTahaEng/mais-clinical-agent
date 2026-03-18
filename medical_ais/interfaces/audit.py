"""
Abstract interface for the audit trail store.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class AuditRecord:
    event_type: str                      # e.g. "action.executed", "alert.written"
    agent_id: str
    session_id: str
    user_id: str = ""                    # Authenticated user (empty for legacy/anonymous)
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    idempotency_key: str = ""


class IAuditStore(ABC):
    """Contract every audit-store adapter must satisfy."""

    @abstractmethod
    async def record(self, entry: AuditRecord) -> None:
        """Persist *entry* to the audit trail (append-only, never deletes)."""

    @abstractmethod
    async def query(
        self,
        session_id: str | None = None,
        event_type: str | None = None,
        limit: int = 100,
    ) -> list[AuditRecord]:
        """Return recent audit records matching the given filters."""
