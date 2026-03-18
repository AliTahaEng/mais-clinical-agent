"""
BGE-M3 embedding adapter (local, HuggingFace model).
Runs in a thread pool so as not to block the event loop.
"""
from __future__ import annotations

import asyncio
from typing import Any

import structlog

from medical_ais.interfaces.embedding import IEmbeddingModel

logger = structlog.get_logger(__name__)


class BGEM3Adapter(IEmbeddingModel):
    """IEmbeddingModel backed by BAAI/bge-m3 via sentence-transformers."""

    def __init__(self, model_name: str = "BAAI/bge-m3") -> None:
        self._model_name = model_name
        self._model: Any = None

    def _load_model(self) -> None:
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self._model_name)
            logger.info("embedding.loaded", model=self._model_name)

    @property
    def dimension(self) -> int:
        return 1024  # BGE-M3 produces 1024-dim vectors

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        def _encode() -> list[list[float]]:
            self._load_model()
            embeddings = self._model.encode(texts, normalize_embeddings=True)
            return [emb.tolist() for emb in embeddings]

        return await asyncio.to_thread(_encode)

    async def embed_query(self, text: str) -> list[float]:
        results = await self.embed_texts([text])
        return results[0]
