"""In-memory cache for tests — no Redis required."""
from __future__ import annotations

import time
from typing import Any

from medical_ais.interfaces.cache import ICacheStore


class InMemoryCacheAdapter(ICacheStore):
    def __init__(self) -> None:
        # key → (value, expiry_timestamp or None)
        self._store: dict[str, tuple[Any, float | None]] = {}

    async def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expiry = entry
        if expiry is not None and time.monotonic() > expiry:
            del self._store[key]
            return None
        return value

    async def set(self, key: str, value: Any, *, ttl_seconds: int = 300) -> None:
        expiry = time.monotonic() + ttl_seconds if ttl_seconds > 0 else None
        self._store[key] = (value, expiry)

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)

    async def exists(self, key: str) -> bool:
        return (await self.get(key)) is not None

    async def health_check(self) -> bool:
        return True

    async def scan_keys(self, pattern: str) -> list[str]:
        import fnmatch
        import time as _time
        # Expire stale keys first
        now = _time.monotonic()
        self._store = {k: v for k, v in self._store.items() if v[1] is None or v[1] > now}
        return [k for k in self._store if fnmatch.fnmatch(k, pattern)]
