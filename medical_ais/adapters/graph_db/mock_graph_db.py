"""
In-memory mock graph database for unit tests.
Stores data as plain Python dicts — no external process required.
"""
from __future__ import annotations

from typing import Any

from medical_ais.interfaces.graph_db import IGraphDB


class MockGraphDB(IGraphDB):
    """
    Test double for IGraphDB.
    Queries and writes are recorded; callers can inspect self.queries
    and configure self.query_results for controlled responses.
    """

    def __init__(self) -> None:
        self.queries: list[tuple[str, dict]] = []
        self.writes: list[tuple[str, dict]] = []
        # Pre-programme results: query_text → list of row dicts
        self.query_results: dict[str, list[dict[str, Any]]] = {}
        self._connected = False

    async def connect(self) -> None:
        self._connected = True

    async def close(self) -> None:
        self._connected = False

    async def run_query(
        self, cypher: str, parameters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        params = parameters or {}
        self.queries.append((cypher, params))
        # Return pre-programmed result or empty list
        return self.query_results.get(cypher, [])

    async def run_write(
        self, cypher: str, parameters: dict[str, Any] | None = None
    ) -> None:
        self.writes.append((cypher, parameters or {}))

    async def health_check(self) -> bool:
        return self._connected
