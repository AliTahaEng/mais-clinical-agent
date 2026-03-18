"""
Hybrid search tool — combines BM25 keyword + vector semantic search,
fuses results with Reciprocal Rank Fusion, then reranks with cross-encoder.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog

from medical_ais.interfaces.embedding import IEmbeddingModel
from medical_ais.interfaces.reranker import IReranker
from medical_ais.interfaces.search import ISearchEngine
from medical_ais.interfaces.vector_store import IVectorStore

logger = structlog.get_logger(__name__)


@dataclass
class HybridResult:
    id: str
    text: str
    score: float
    source: str    # "vector" | "bm25" | "fused"
    metadata: dict = field(default_factory=dict)


def _reciprocal_rank_fusion(
    vector_results: list,
    bm25_results: list,
    k: int = 60,
) -> list[tuple[str, float]]:
    """
    Fuse two ranked lists using Reciprocal Rank Fusion.
    Returns list of (id, fused_score) sorted descending.
    """
    scores: dict[str, float] = {}

    for rank, result in enumerate(vector_results):
        scores[result.id] = scores.get(result.id, 0.0) + 1.0 / (k + rank + 1)

    for rank, result in enumerate(bm25_results):
        scores[result.id] = scores.get(result.id, 0.0) + 1.0 / (k + rank + 1)

    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


async def hybrid_search(
    query: str,
    *,
    vector_store: IVectorStore,
    search_engine: ISearchEngine,
    embedding_model: IEmbeddingModel,
    reranker: IReranker,
    top_k: int = 10,
    rerank_top_k: int = 5,
) -> list[HybridResult]:
    """
    Execute hybrid search and return reranked results.

    Flow: embed query → vector search + BM25 search → RRF fusion → rerank
    """
    # Parallel vector + BM25 search
    import asyncio
    query_embedding = await embedding_model.embed_query(query)
    vector_task = vector_store.search(query_embedding, top_k=top_k)
    bm25_task = search_engine.search(query, top_k=top_k)
    vector_results, bm25_results = await asyncio.gather(vector_task, bm25_task)

    # Build ID → result lookup for both sources
    all_docs: dict[str, dict] = {}
    for r in vector_results:
        all_docs[r.id] = {"id": r.id, "text": r.text, "metadata": r.metadata}
    for r in bm25_results:
        if r.id not in all_docs:
            all_docs[r.id] = {"id": r.id, "text": r.text, "metadata": r.metadata}

    # Reciprocal Rank Fusion
    fused = _reciprocal_rank_fusion(vector_results, bm25_results)

    # Take top candidates for reranking
    candidates = [
        all_docs[id_] for id_, _ in fused[:top_k * 2] if id_ in all_docs
    ]

    if not candidates:
        return []

    # Rerank with cross-encoder
    ranked = await reranker.rerank(query, candidates, top_k=rerank_top_k)

    return [
        HybridResult(
            id=r.id,
            text=r.text,
            score=r.score,
            source="fused",
            metadata=all_docs.get(r.id, {}).get("metadata", {}),
        )
        for r in ranked
    ]


async def parent_document_lookup(
    child_ids: list[str],
    *,
    vector_store: IVectorStore,
) -> list[HybridResult]:
    """
    Given child chunk IDs, return their parent chunks for richer context.
    Parent IDs are stored in child metadata under 'parent_id'.
    """
    # Fetch children metadata to get parent_ids, then fetch parents
    parent_ids: list[str] = []
    for child_id in child_ids:
        # Parent ID is encoded in the child ID by convention: {parent_id}_c_{hash}
        parts = child_id.rsplit("_c_", 1)
        if len(parts) == 2:
            parent_ids.append(parts[0])

    if not parent_ids:
        return []

    # Search by ID — approximate: use a dummy embedding and filter by ID
    # In practice, we'd use a direct ID lookup in LanceDB
    # For now return empty list — parent retrieval is handled by index metadata
    return []
