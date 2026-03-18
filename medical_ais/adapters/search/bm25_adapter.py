"""
BM25 keyword-search adapter (local, no server needed).
Uses the rank-bm25 library for scoring.
"""
from __future__ import annotations

import asyncio
import re
from typing import Any

import structlog

from medical_ais.interfaces.search import ISearchEngine, SearchResult

logger = structlog.get_logger(__name__)


def _tokenize(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


class BM25Adapter(ISearchEngine):
    """ISearchEngine backed by rank-bm25 (in-process, no Elasticsearch)."""

    def __init__(self) -> None:
        self._ids: list[str] = []
        self._texts: list[str] = []
        self._metadata: list[dict] = []
        self._bm25: Any = None

    async def index(self, documents: list[dict]) -> None:
        for doc in documents:
            self._ids.append(doc["id"])
            self._texts.append(doc["text"])
            self._metadata.append({k: v for k, v in doc.items() if k not in ("id", "text")})
        await asyncio.to_thread(self._rebuild_index)

    def _rebuild_index(self) -> None:
        from rank_bm25 import BM25Okapi
        corpus = [_tokenize(t) for t in self._texts]
        self._bm25 = BM25Okapi(corpus) if corpus else None

    async def search(
        self,
        query: str,
        *,
        top_k: int = 10,
        filter_metadata: dict | None = None,
    ) -> list[SearchResult]:
        if self._bm25 is None or not self._ids:
            return []

        tokens = _tokenize(query)
        scores = await asyncio.to_thread(self._bm25.get_scores, tokens)

        # Pair with metadata and filter
        indexed = [
            (i, float(scores[i]))
            for i in range(len(self._ids))
            if scores[i] > 0
        ]

        if filter_metadata:
            indexed = [
                (i, s) for i, s in indexed
                if all(self._metadata[i].get(k) == v for k, v in filter_metadata.items())
            ]

        indexed.sort(key=lambda x: x[1], reverse=True)

        return [
            SearchResult(
                id=self._ids[i],
                text=self._texts[i],
                score=score,
                metadata=self._metadata[i],
            )
            for i, score in indexed[:top_k]
        ]

    async def clear(self) -> None:
        """Wipe the entire BM25 index."""
        self._ids = []
        self._texts = []
        self._metadata = []
        self._bm25 = None
        logger.info("bm25.index_cleared")

    async def delete(self, ids: list[str]) -> None:
        ids_set = set(ids)
        keep = [i for i, id_ in enumerate(self._ids) if id_ not in ids_set]
        self._ids = [self._ids[i] for i in keep]
        self._texts = [self._texts[i] for i in keep]
        self._metadata = [self._metadata[i] for i in keep]
        await asyncio.to_thread(self._rebuild_index)

    async def health_check(self) -> bool:
        return True
