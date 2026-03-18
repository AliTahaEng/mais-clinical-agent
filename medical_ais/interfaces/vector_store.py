"""
Abstract interface for the vector store (LanceDB / Pinecone / mock).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class VectorDocument:
    id: str
    text: str
    embedding: list[float]
    metadata: dict = field(default_factory=dict)


@dataclass
class VectorSearchResult:
    id: str
    text: str
    score: float
    metadata: dict = field(default_factory=dict)


class IVectorStore(ABC):
    """Contract every vector store adapter must satisfy."""

    @abstractmethod
    async def upsert(self, documents: list[VectorDocument]) -> None:
        """Insert or update *documents* in the store."""

    @abstractmethod
    async def search(
        self,
        query_embedding: list[float],
        *,
        top_k: int = 10,
        filter_metadata: dict | None = None,
    ) -> list[VectorSearchResult]:
        """Return *top_k* nearest neighbours for *query_embedding*."""

    @abstractmethod
    async def delete(self, ids: list[str]) -> None:
        """Remove documents by their IDs."""

    @abstractmethod
    async def health_check(self) -> bool:
        """Return True if the store is reachable."""
