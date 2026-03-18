"""
Abstract interface for embedding models (BGE-M3, OpenAI, mock).
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class IEmbeddingModel(ABC):
    """Contract every embedding adapter must satisfy."""

    @abstractmethod
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per text (same order)."""

    @abstractmethod
    async def embed_query(self, text: str) -> list[float]:
        """Return the embedding for a single query string."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Dimensionality of the embedding vectors produced."""
