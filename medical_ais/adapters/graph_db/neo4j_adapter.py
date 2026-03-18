"""
Neo4j graph-database adapter.
Wraps the official neo4j Python driver behind IGraphDB.
"""
from __future__ import annotations

from typing import Any

import structlog
from neo4j import AsyncGraphDatabase, AsyncDriver

from medical_ais.core.exceptions import GraphDBUnavailableError
from medical_ais.interfaces.graph_db import IGraphDB

logger = structlog.get_logger(__name__)


class Neo4jAdapter(IGraphDB):
    """IGraphDB implementation backed by Neo4j."""

    def __init__(self, uri: str, username: str, password: str) -> None:
        self._uri = uri
        self._username = username
        self._password = password
        self._driver: AsyncDriver | None = None

    async def connect(self) -> None:
        self._driver = AsyncGraphDatabase.driver(
            self._uri, auth=(self._username, self._password)
        )
        try:
            await self._driver.verify_connectivity()
        except Exception as exc:
            raise GraphDBUnavailableError(f"Cannot connect to Neo4j: {exc}") from exc
        logger.info("neo4j.connected", uri=self._uri)

    async def close(self) -> None:
        if self._driver:
            await self._driver.close()
            self._driver = None

    async def run_query(
        self, cypher: str, parameters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        self._ensure_connected()
        async with self._driver.session() as session:
            result = await session.run(cypher, parameters or {})
            records = await result.data()
            return records

    async def run_write(
        self, cypher: str, parameters: dict[str, Any] | None = None
    ) -> None:
        self._ensure_connected()
        async with self._driver.session() as session:
            await session.run(cypher, parameters or {})

    async def health_check(self) -> bool:
        try:
            self._ensure_connected()
            await self._driver.verify_connectivity()
            return True
        except Exception:
            return False

    def _ensure_connected(self) -> None:
        if self._driver is None:
            raise GraphDBUnavailableError("Neo4j driver not initialised — call connect() first")
