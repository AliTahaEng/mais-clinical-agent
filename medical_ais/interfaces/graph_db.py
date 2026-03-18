"""
Abstract interface for the graph database (Neo4j / Memgraph / mock).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class IGraphDB(ABC):
    """Contract every graph-database adapter must satisfy."""

    @abstractmethod
    async def connect(self) -> None:
        """Open / verify the connection."""

    @abstractmethod
    async def close(self) -> None:
        """Gracefully close the connection."""

    @abstractmethod
    async def run_query(
        self, cypher: str, parameters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Execute *cypher* and return a list of row dicts."""

    @abstractmethod
    async def run_write(
        self, cypher: str, parameters: dict[str, Any] | None = None
    ) -> None:
        """Execute a write query (CREATE / MERGE / SET / DELETE)."""

    @abstractmethod
    async def health_check(self) -> bool:
        """Return True if the database is reachable."""
