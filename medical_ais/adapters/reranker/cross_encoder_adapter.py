"""
Cross-encoder reranker adapter.
Uses the sentence-transformers CrossEncoder model (ms-marco family).
"""
from __future__ import annotations

import asyncio
from typing import Any

import structlog

from medical_ais.interfaces.reranker import IReranker, RankedResult

logger = structlog.get_logger(__name__)


class CrossEncoderAdapter(IReranker):
    """IReranker backed by sentence-transformers CrossEncoder."""

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2") -> None:
        self._model_name = model_name
        self._model: Any = None

    def _load(self) -> None:
        if self._model is None:
            from sentence_transformers import CrossEncoder
            self._model = CrossEncoder(self._model_name)
            logger.info("reranker.loaded", model=self._model_name)

    async def rerank(
        self,
        query: str,
        candidates: list[dict],
        *,
        top_k: int = 5,
    ) -> list[RankedResult]:
        if not candidates:
            return []

        pairs = [(query, c["text"]) for c in candidates]

        def _score() -> list[float]:
            self._load()
            return self._model.predict(pairs).tolist()

        scores = await asyncio.to_thread(_score)

        ranked = sorted(
            zip(candidates, scores),
            key=lambda x: x[1],
            reverse=True,
        )

        return [
            RankedResult(id=c["id"], text=c["text"], score=float(s))
            for c, s in ranked[:top_k]
        ]
