"""
LanceDB vector store adapter.
Stores embeddings locally as Arrow/Lance files — no server needed.

Tested with lancedb 0.30.x + PyArrow 23.x + NumPy 2.x.
Key requirement: vector field must be numpy float32 array, not a Python list[float].
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
                import lancedb
                Path(self._path).mkdir(parents=True, exist_ok=True)
                self._db = await asyncio.to_thread(lancedb.connect, self._path)
            except Exception as exc:
                raise VectorStoreUnavailableError(f"LanceDB connect failed: {exc}") from exc

    async def _get_table(self) -> Any:
        """Return the open table, or None if not yet created."""
        await self._ensure_connected()
        # Use cached table handle first
        if self._table is not None:
            return self._table
        try:
            table_names = await asyncio.to_thread(self._db.table_names)
            if _TABLE_NAME not in table_names:
                return None
            self._table = await asyncio.to_thread(self._db.open_table, _TABLE_NAME)
            return self._table
        except Exception as exc:
            logger.warning("lancedb.table_not_accessible", error=str(exc))
            self._table = None
            return None

    # ── IVectorStore ──────────────────────────────────────────────────────────

    async def upsert(self, documents: list[VectorDocument]) -> None:
        """
        Write documents to LanceDB.

        Vectors MUST be numpy float32 arrays for lancedb 0.30.x to infer
        the correct fixed_size_list<float32> schema. Python list[float]
        produces float64 variable-length lists which lancedb rejects.
        """
        if not documents:
            return
        await self._ensure_connected()

        import numpy as np

        # Build rows — vector as numpy float32 (critical for lancedb schema inference)
        rows = [
            {
                "id": doc.id,
                "text": doc.text,
                "vector": np.array(doc.embedding, dtype=np.float32),
                **{f"meta_{k}": str(v) for k, v in doc.metadata.items()},
            }
            for doc in documents
        ]

        def _write() -> Any:
            table_names = self._db.table_names()
            if _TABLE_NAME not in table_names:
                return self._db.create_table(_TABLE_NAME, data=rows)
            else:
                tbl = self._db.open_table(_TABLE_NAME)
                tbl.add(rows)
                return tbl

        try:
            self._table = await asyncio.to_thread(_write)
        except Exception as exc:
            logger.error("lancedb.upsert_failed", error=str(exc))
            self._table = None
            raise  # re-raise so embedder.py records the error

    async def search(
        self,
        query_embedding: list[float],
        *,
        top_k: int = 10,
        filter_metadata: dict | None = None,
    ) -> list[VectorSearchResult]:
        tbl = await self._get_table()
        if tbl is None:
            logger.info("lancedb.search_skipped",
                        reason="table not yet created — run document ingestion first")
            return []

        try:
            import numpy as np
            query_vec = np.array(query_embedding, dtype=np.float32)

            def _search() -> list[dict]:
                return tbl.search(query_vec).limit(top_k).to_list()

            rows = await asyncio.to_thread(_search)
            return [
                VectorSearchResult(
                    id=row["id"],
                    text=row["text"],
                    score=float(row.get("_distance", 0.0)),
                )
                for row in rows
            ]
        except Exception as exc:
            logger.warning("lancedb.search_failed", error=str(exc))
            self._table = None
            return []

    async def clear(self) -> None:
        """Drop the medical_chunks table entirely."""
        await self._ensure_connected()
        try:
            table_names = await asyncio.to_thread(self._db.table_names)
            if _TABLE_NAME in table_names:
                await asyncio.to_thread(self._db.drop_table, _TABLE_NAME)
                logger.info("lancedb.table_dropped", table=_TABLE_NAME)
            self._table = None
        except Exception as exc:
            logger.error("lancedb.clear_failed", error=str(exc))
            raise

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
