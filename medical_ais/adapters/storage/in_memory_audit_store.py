"""In-memory audit store for tests — no Postgres required."""
from __future__ import annotations

from medical_ais.interfaces.audit import AuditRecord, IAuditStore


class InMemoryAuditStore(IAuditStore):
    def __init__(self) -> None:
        self._records: list[AuditRecord] = []

    async def record(self, entry: AuditRecord) -> None:
        # Idempotency: skip if key already stored
        if entry.idempotency_key:
            if any(r.idempotency_key == entry.idempotency_key for r in self._records):
                return
        self._records.append(entry)

    async def query(
        self,
        session_id: str | None = None,
        event_type: str | None = None,
        limit: int = 100,
    ) -> list[AuditRecord]:
        results = self._records
        if session_id:
            results = [r for r in results if r.session_id == session_id]
        if event_type:
            results = [r for r in results if r.event_type == event_type]
        return list(reversed(results))[:limit]
