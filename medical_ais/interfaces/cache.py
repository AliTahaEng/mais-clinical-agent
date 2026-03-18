"""
Abstract interface for the cache store (Redis / in-memory mock).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ICacheStore(ABC):
    """Contract every cache adapter must satisfy."""

    @abstractmethod
    async def get(self, key: str) -> Any | None:
        """Return cached value for *key*, or None if missing/expired."""

    @abstractmethod
    async def set(self, key: str, value: Any, *, ttl_seconds: int = 300) -> None:
        """Store *value* under *key* with optional TTL."""

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Remove *key* from the cache."""

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Return True if *key* exists and has not expired."""

    @abstractmethod
    async def health_check(self) -> bool:
        """Return True if the cache is reachable."""

    @abstractmethod
    async def scan_keys(self, pattern: str) -> list[str]:
        """Return all keys matching *pattern* (glob-style, e.g. 'approval:*')."""
