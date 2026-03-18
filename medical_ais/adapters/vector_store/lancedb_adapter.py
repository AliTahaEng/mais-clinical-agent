"""
LanceDB vector store adapter.
Stores embeddings locally as Arrow/Lance files — no server needed.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import structlog

from medical_ais.core.exceptions import VectorStoreUnavailableError
from medical_ais.interfaces.vector_store import IVectorStore, VectorDocument, VectorSearchResult

logger = structlog.get_logger(__name__)

_TABLE_NAME = "medical_chunks"


class LanceDBAdapter(IVectorStore):
    """IVectorStore backed by LanceDB (local file storage)."""

    def __init__(self, path: str) -> None:
        self._path = path
        self._db: Any = None
        self._table: Any = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def _ensure_connected(self) -> None:
        if self._db is None:
            try:
                import lancedb  # imported lazily to keep tests light
                self._db = await asyncio.to_thread(lancedb.connect, self._path)
                Path(self._path).mkdir(parents=True, exist_ok=True)
            except Exception as exc:
                raise VectorStoreUnavailableError(f"LanceDB connect failed: {exc}") from exc

    async def _get_table(self) -> Any:
        await self._ensure_connected()
        import lancedb
        table_names = await asyncio.to_thread(self._db.table_names)
        if _TABLE_NAME not in table_names:
            # Table created on first upsert
            return None
        if self._table is None:
            self._table = await asyncio.to_thread(self._db.open_table, _TABLE_NAME)
        return self._table

    # ── IVectorStore ──────────────────────────────────────────────────────────

    async def upsert(self, documents: list[VectorDocument]) -> None:
        await self._ensure_connected()
        import lancedb
        import pyarrow as pa

        rows = [
            {
                "id": doc.id,
                "text": doc.text,
                "vector": doc.embedding,
                **{f"meta_{k}": str(v) for k, v in doc.metadata.items()},
            }
            for doc in documents
        ]

        table_names = await asyncio.to_thread(self._db.table_names)
        if _TABLE_NAME not in table_names:
            self._table = await asyncio.to_thread(
                self._db.create_table, _TABLE_NAME, data=rows
            )
        else:
            tbl = await asyncio.to_thread(self._db.open_table, _TABLE_NAME)
            await asyncio.to_thread(tbl.add, rows)
            self._table = tbl

    async def search(
        self,
        query_embedding: list[float],
        *,
        top_k: int = 10,
        filter_metadata: dict | None = None,
    ) -> list[VectorSearchResult]:
        tbl = await self._get_table()
        if tbl is None:
            return []

        def _search() -> list[dict]:
            query = tbl.search(query_embedding).limit(top_k)
            return query.to_list()

        rows = await asyncio.to_thread(_search)
        return [
            VectorSearchResult(
                id=row["id"],
                text=row["text"],
                score=float(row.get("_distance", 0.0)),
            )
            for row in rows
        ]

    async def delete(self, ids: list[str]) -> None:
        tbl = await self._get_table()
        if tbl is None:
            return
        ids_str = ", ".join(f"'{i}'" for i in ids)
        await asyncio.to_thread(tbl.delete, f"id IN ({ids_str})")

    async def health_check(self) -> bool:
        try:
            await self._ensure_connected()
            return True
        except Exception:
            return False
