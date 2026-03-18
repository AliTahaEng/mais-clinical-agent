"""
Abstract interface for cross-encoder rerankers.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class RankedResult:
    id: str
    text: str
    score: float


class IReranker(ABC):
    """Contract every reranker adapter must satisfy."""

    @abstractmethod
    async def rerank(
        self,
        query: str,
        candidates: list[dict],
        *,
        top_k: int = 5,
    ) -> list[RankedResult]:
        """
        Score *candidates* against *query* and return top-k sorted by score desc.
        Each candidate dict must contain ``id`` and ``text``.
        """
