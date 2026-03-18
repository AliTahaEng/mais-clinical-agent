"""Mock embedding model for tests — returns deterministic random-ish vectors."""
from __future__ import annotations

import hashlib

from medical_ais.interfaces.embedding import IEmbeddingModel

_DIM = 128


def _text_to_vector(text: str, dim: int) -> list[float]:
    """Deterministic fake embedding derived from the text's SHA-256 hash."""
    digest = hashlib.sha256(text.encode()).digest()
    # Extend digest to fill dim floats
    extended = (digest * ((dim // 32) + 1))[:dim]
    vec = [(b / 255.0) * 2 - 1 for b in extended]
    mag = sum(x ** 2 for x in vec) ** 0.5 or 1.0
    return [x / mag for x in vec]


class MockEmbeddingModel(IEmbeddingModel):
    @property
    def dimension(self) -> int:
        return _DIM

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [_text_to_vector(t, _DIM) for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        return _text_to_vector(text, _DIM)
