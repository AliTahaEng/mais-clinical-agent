"""Mock vector store for tests — stores everything in memory."""
from __future__ import annotations

import math

from medical_ais.interfaces.vector_store import IVectorStore, VectorDocument, VectorSearchResult


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x ** 2 for x in a)) or 1e-9
    mag_b = math.sqrt(sum(x ** 2 for x in b)) or 1e-9
    return dot / (mag_a * mag_b)


class MockVectorStore(IVectorStore):
    def __init__(self) -> None:
        self._store: dict[str, VectorDocument] = {}

    async def upsert(self, documents: list[VectorDocument]) -> None:
        for doc in documents:
            self._store[doc.id] = doc

    async def search(
        self,
        query_embedding: list[float],
        *,
        top_k: int = 10,
        filter_metadata: dict | None = None,
    ) -> list[VectorSearchResult]:
        scored = [
            VectorSearchResult(id=doc.id, text=doc.text, score=_cosine(query_embedding, doc.embedding))
            for doc in self._store.values()
        ]
        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:top_k]

    async def delete(self, ids: list[str]) -> None:
        for id_ in ids:
            self._store.pop(id_, None)

    async def health_check(self) -> bool:
        return True
