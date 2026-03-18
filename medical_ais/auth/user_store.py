"""
PostgreSQL-backed user store.
Handles users + refresh_tokens tables.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import asyncpg
import structlog

from medical_ais.auth.models import User
from medical_ais.auth.token_utils import hash_password

logger = structlog.get_logger(__name__)


class UserStore:
    def __init__(self, connection_url: str) -> None:
        # Strip SQLAlchemy driver qualifier — asyncpg uses plain postgresql://
        self._url = (
            connection_url
            .replace("postgresql+asyncpg://", "postgresql://")
            .replace("postgres+asyncpg://", "postgres://")
        )
        self._pool: Any = None

    async def connect(self) -> None:
        self._pool = await asyncpg.create_pool(self._url, min_size=1, max_size=5)
        await self._ensure_schema()
        logger.info("user_store.connected")

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()

    # ── Schema ────────────────────────────────────────────────────────────────

    async def _ensure_schema(self) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id               TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
                    email            TEXT UNIQUE NOT NULL,
                    username         TEXT UNIQUE NOT NULL,
                    hashed_password  TEXT NOT NULL,
                    role             TEXT NOT NULL DEFAULT 'user',
                    is_active        BOOLEAN NOT NULL DEFAULT true,
                    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS refresh_tokens (
                    id          TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
                    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    token_hash  TEXT NOT NULL,
                    expires_at  TIMESTAMPTZ NOT NULL,
                    revoked     BOOLEAN NOT NULL DEFAULT false,
                    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            # Migrate audit_log to add user_id column if missing
            await conn.execute(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'audit_log' AND column_name = 'user_id'
                    ) THEN
                        ALTER TABLE audit_log ADD COLUMN user_id TEXT NOT NULL DEFAULT '';
                    END IF;
                END $$;
                """
            )

    # ── User CRUD ─────────────────────────────────────────────────────────────

    async def create_user(
        self,
        email: str,
        username: str,
        plain_password: str,
        role: str = "user",
    ) -> User:
        hashed = hash_password(plain_password)
        user_id = str(uuid.uuid4())
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO users (id, email, username, hashed_password, role)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id, email, username, hashed_password, role, is_active, created_at
                """,
                user_id, email.lower().strip(), username.strip(), hashed, role,
            )
        return _row_to_user(row)

    async def get_by_email(self, email: str) -> User | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM users WHERE email = $1 AND is_active = true",
                email.lower().strip(),
            )
        return _row_to_user(row) if row else None

    async def get_by_id(self, user_id: str) -> User | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM users WHERE id = $1 AND is_active = true",
                user_id,
            )
        return _row_to_user(row) if row else None

    async def exists_any_admin(self) -> bool:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT 1 FROM users WHERE role = 'admin' LIMIT 1"
            )
        return row is not None

    # ── Refresh token management ───────────────────────────────────────────────

    async def save_refresh_token(
        self,
        user_id: str,
        token_hash: str,
        expires_days: int = 7,
    ) -> None:
        expires_at = datetime.now(timezone.utc) + timedelta(days=expires_days)
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO refresh_tokens (id, user_id, token_hash, expires_at)
                VALUES (gen_random_uuid()::text, $1, $2, $3)
                """,
                user_id, token_hash, expires_at,
            )

    async def validate_and_revoke_refresh_token(
        self, token_hash: str
    ) -> str | None:
        """
        Find a valid (non-revoked, non-expired) refresh token by hash,
        revoke it (rotation), and return the owner's user_id.
        Returns None if the token is not found / already revoked / expired.
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE refresh_tokens
                SET revoked = true
                WHERE token_hash = $1
                  AND revoked = false
                  AND expires_at > now()
                RETURNING user_id
                """,
                token_hash,
            )
        return row["user_id"] if row else None

    async def revoke_all_user_tokens(self, user_id: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE refresh_tokens SET revoked = true WHERE user_id = $1",
                user_id,
            )


def _row_to_user(row: Any) -> User:
    return User(
        id=row["id"],
        email=row["email"],
        username=row["username"],
        hashed_password=row["hashed_password"],
        role=row["role"],
        is_active=row["is_active"],
        created_at=row["created_at"],
    )
