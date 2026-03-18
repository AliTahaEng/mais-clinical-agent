"""
Redis cache adapter.
Uses aioredis (redis-py async) behind ICacheStore.
"""
from __future__ import annotations

import json
from typing import Any

import structlog

from medical_ais.interfaces.cache import ICacheStore

logger = structlog.get_logger(__name__)


class RedisCacheAdapter(ICacheStore):
    """ICacheStore backed by Redis."""

    def __init__(self, url: str) -> None:
        self._url = url
        self._client: Any = None

    async def connect(self) -> None:
        import redis.asyncio as aioredis
        self._client = await aioredis.from_url(self._url, decode_responses=True)
        logger.info("redis.connected", url=self._url)

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()

    # ── ICacheStore ───────────────────────────────────────────────────────────

    async def get(self, key: str) -> Any | None:
        self._ensure_connected()
        raw = await self._client.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw

    async def set(self, key: str, value: Any, *, ttl_seconds: int = 300) -> None:
        self._ensure_connected()
        serialised = json.dumps(value) if not isinstance(value, str) else value
        await self._client.setex(key, ttl_seconds, serialised)

    async def delete(self, key: str) -> None:
        self._ensure_connected()
        await self._client.delete(key)

    async def exists(self, key: str) -> bool:
        self._ensure_connected()
        return bool(await self._client.exists(key))

    async def health_check(self) -> bool:
        try:
            self._ensure_connected()
            await self._client.ping()
            return True
        except Exception:
            return False

    async def scan_keys(self, pattern: str) -> list[str]:
        self._ensure_connected()
        return [key async for key in self._client.scan_iter(pattern)]

    def _ensure_connected(self) -> None:
        if self._client is None:
            raise RuntimeError("RedisCacheAdapter not connected — call connect() first")
