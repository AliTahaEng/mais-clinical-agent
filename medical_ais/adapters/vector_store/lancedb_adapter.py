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
        try:
            table_names = await asyncio.to_thread(self._db.table_names)
            if _TABLE_NAME not in table_names:
                # Table not yet created — ingestion hasn't run step 9-10 yet
                return None
            if self._table is None:
                self._table = await asyncio.to_thread(self._db.open_table, _TABLE_NAME)
            return self._table
        except Exception as exc:
            # lancedb ≥ 0.10 raises when table is missing or files are inaccessible
            logger.warning("lancedb.table_not_accessible", error=str(exc))
            self._table = None
            return None

    # ── IVectorStore ──────────────────────────────────────────────────────────

    async def upsert(self, documents: list[VectorDocument]) -> None:
        if not documents:
            return
        await self._ensure_connected()
        import pyarrow as pa

        dim = len(documents[0].embedding)

        # Collect all metadata keys to build a consistent schema
        meta_keys: list[str] = []
        for doc in documents:
            for k in doc.metadata:
                key = f"meta_{k}"
                if key not in meta_keys:
                    meta_keys.append(key)

        # Build PyArrow schema — float32 fixed-size list is required by lancedb ≥ 0.10
        schema_fields = [
            pa.field("id", pa.utf8()),
            pa.field("text", pa.utf8()),
            pa.field("vector", pa.list_(pa.float32(), dim)),
        ] + [pa.field(k, pa.utf8()) for k in meta_keys]
        schema = pa.schema(schema_fields)

        # Build rows with float32 vectors
        rows = []
        for doc in documents:
            row: dict = {
                "id": doc.id,
                "text": doc.text,
                "vector": [float(x) for x in doc.embedding],
            }
            for k in meta_keys:
                orig_key = k[len("meta_"):]
                row[k] = str(doc.metadata.get(orig_key, ""))
            rows.append(row)

        # Build a typed PyArrow table so lancedb gets the correct vector dtype
        vectors_flat = []
        for row in rows:
            vectors_flat.extend(row["vector"])
        vector_array = pa.FixedSizeListArray.from_arrays(
            pa.array(vectors_flat, type=pa.float32()), dim
        )
        arrays = [
            pa.array([r["id"] for r in rows], type=pa.utf8()),
            pa.array([r["text"] for r in rows], type=pa.utf8()),
            vector_array,
        ] + [pa.array([r[k] for r in rows], type=pa.utf8()) for k in meta_keys]
        table = pa.table(dict(zip(schema.names, arrays)))

        try:
            table_names = await asyncio.to_thread(self._db.table_names)
            if _TABLE_NAME not in table_names:
                self._table = await asyncio.to_thread(
                    self._db.create_table, _TABLE_NAME, data=table
                )
            else:
                if self._table is None:
                    self._table = await asyncio.to_thread(self._db.open_table, _TABLE_NAME)
                await asyncio.to_thread(self._table.add, table)
        except Exception as exc:
            logger.error("lancedb.upsert_failed", error=str(exc))
            self._table = None
            raise  # re-raise so embedder.py can count the error

    async def search(
        self,
        query_embedding: list[float],
        *,
        top_k: int = 10,
        filter_metadata: dict | None = None,
    ) -> list[VectorSearchResult]:
        tbl = await self._get_table()
        if tbl is None:
            logger.info("lancedb.search_skipped", reason="table not yet created — run document ingestion first")
            return []

        try:
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
        except Exception as exc:
            logger.warning("lancedb.search_failed", error=str(exc))
            self._table = None  # force reconnect on next call
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
