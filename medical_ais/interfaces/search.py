"""
Abstract interface for keyword/BM25/Elasticsearch search.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class SearchResult:
    id: str
    text: str
    score: float
    metadata: dict = field(default_factory=dict)


class ISearchEngine(ABC):
    """Contract every keyword-search adapter must satisfy."""

    @abstractmethod
    async def index(self, documents: list[dict]) -> None:
        """
        Index *documents*.
        Each dict must contain at minimum: ``id`` (str) and ``text`` (str).
        """

    @abstractmethod
    async def search(
        self,
        query: str,
        *,
        top_k: int = 10,
        filter_metadata: dict | None = None,
    ) -> list[SearchResult]:
        """Return *top_k* keyword-matched results for *query*."""

    @abstractmethod
    async def delete(self, ids: list[str]) -> None:
        """Remove documents by their IDs."""

    @abstractmethod
    async def health_check(self) -> bool:
        """Return True if the engine is reachable."""
