"""
PostgreSQL audit store adapter.
Persists AuditRecord rows via asyncpg — append-only, never deletes.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import structlog

from medical_ais.interfaces.audit import AuditRecord, IAuditStore

logger = structlog.get_logger(__name__)


class PostgresAuditStore(IAuditStore):
    """IAuditStore implementation backed by PostgreSQL."""

    def __init__(self, connection_url: str) -> None:
        self._url = connection_url
        self._pool: Any = None

    async def connect(self) -> None:
        import asyncpg
        # asyncpg uses plain postgresql:// — strip SQLAlchemy's +asyncpg driver qualifier
        url = self._url.replace("postgresql+asyncpg://", "postgresql://").replace(
            "postgres+asyncpg://", "postgres://"
        )
        self._pool = await asyncpg.create_pool(url, min_size=1, max_size=5)
        await self._ensure_schema()
        logger.info("audit_store.connected")

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()

    async def _ensure_schema(self) -> None:
        """Create audit_log table if it doesn't exist yet."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_log (
                    id              BIGSERIAL PRIMARY KEY,
                    event_type      TEXT        NOT NULL,
                    agent_id        TEXT        NOT NULL DEFAULT '',
                    session_id      TEXT        NOT NULL DEFAULT '',
                    payload         JSONB       NOT NULL DEFAULT '{}',
                    timestamp       TIMESTAMPTZ NOT NULL DEFAULT now(),
                    idempotency_key TEXT        NOT NULL DEFAULT '',
                    UNIQUE (idempotency_key)
                )
                """
            )
            # ON CONFLICT requires non-deferrable arbiter constraints.
            # If the table was created with the old DEFERRABLE constraint, migrate it.
            await conn.execute(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM pg_constraint
                        WHERE conrelid = 'audit_log'::regclass
                          AND conname = 'audit_log_idempotency_key_key'
                          AND condeferrable = true
                    ) THEN
                        ALTER TABLE audit_log
                            DROP CONSTRAINT audit_log_idempotency_key_key;
                        ALTER TABLE audit_log
                            ADD CONSTRAINT audit_log_idempotency_key_key
                            UNIQUE (idempotency_key);
                    END IF;
                END $$;
                """
            )

    # ── IAuditStore ───────────────────────────────────────────────────────────

    async def record(self, entry: AuditRecord) -> None:
        self._ensure_connected()
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO audit_log
                    (event_type, agent_id, session_id, user_id, payload, timestamp, idempotency_key)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (idempotency_key) DO NOTHING
                """,
                entry.event_type,
                entry.agent_id,
                entry.session_id,
                getattr(entry, "user_id", "") or "",
                json.dumps(entry.payload),
                entry.timestamp,
                entry.idempotency_key or "",
            )

    async def query(
        self,
        session_id: str | None = None,
        event_type: str | None = None,
        limit: int = 100,
    ) -> list[AuditRecord]:
        self._ensure_connected()
        conditions: list[str] = []
        params: list[Any] = []
        idx = 1

        if session_id:
            conditions.append(f"session_id = ${idx}")
            params.append(session_id)
            idx += 1
        if event_type:
            conditions.append(f"event_type = ${idx}")
            params.append(event_type)
            idx += 1

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        params.append(limit)

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT event_type, agent_id, session_id, payload, timestamp, idempotency_key
                FROM audit_log {where}
                ORDER BY timestamp DESC
                LIMIT ${idx}
                """,
                *params,
            )

        return [
            AuditRecord(
                event_type=row["event_type"],
                agent_id=row["agent_id"],
                session_id=row["session_id"],
                payload=json.loads(row["payload"]),
                timestamp=row["timestamp"],
                idempotency_key=row["idempotency_key"],
            )
            for row in rows
        ]

    def _ensure_connected(self) -> None:
        if self._pool is None:
            raise RuntimeError("PostgresAuditStore not connected — call connect() first")
