"""Unit tests for hybrid search (BM25 + vector + rerank)."""
from __future__ import annotations

import pytest

from medical_ais.adapters.embedding.mock_embedding import MockEmbeddingModel
from medical_ais.adapters.search.bm25_adapter import BM25Adapter
from medical_ais.adapters.vector_store.mock_vector_store import MockVectorStore
from medical_ais.interfaces.reranker import IReranker, RankedResult
from medical_ais.interfaces.vector_store import VectorDocument
from medical_ais.tools.search_tools import hybrid_search


class PassthroughReranker(IReranker):
    """Reranker that returns candidates in their original order."""

    async def rerank(self, query: str, candidates: list[dict], *, top_k: int = 5) -> list[RankedResult]:
        return [
            RankedResult(id=c["id"], text=c["text"], score=1.0 / (i + 1))
            for i, c in enumerate(candidates[:top_k])
        ]


@pytest.mark.asyncio
async def test_hybrid_search_returns_results():
    embedding = MockEmbeddingModel()
    vector_store = MockVectorStore()
    search_engine = BM25Adapter()
    reranker = PassthroughReranker()

    # Index some documents
    docs = [
        {"id": f"doc{i}", "text": f"Metformin is used to treat diabetes condition {i}"}
        for i in range(5)
    ]
    await search_engine.index(docs)

    embeddings = await embedding.embed_texts([d["text"] for d in docs])
    vector_docs = [
        VectorDocument(id=d["id"], text=d["text"], embedding=e)
        for d, e in zip(docs, embeddings)
    ]
    await vector_store.upsert(vector_docs)

    results = await hybrid_search(
        "Metformin diabetes",
        vector_store=vector_store,
        search_engine=search_engine,
        embedding_model=embedding,
        reranker=reranker,
        top_k=5,
        rerank_top_k=3,
    )

    assert len(results) > 0
    assert all(r.text for r in results)


@pytest.mark.asyncio
async def test_hybrid_search_empty_index():
    embedding = MockEmbeddingModel()
    vector_store = MockVectorStore()
    search_engine = BM25Adapter()
    reranker = PassthroughReranker()

    results = await hybrid_search(
        "Metformin",
        vector_store=vector_store,
        search_engine=search_engine,
        embedding_model=embedding,
        reranker=reranker,
    )

    assert results == []
