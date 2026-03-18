"""
Hybrid search node — BM25 + vector + rerank.
"""
from __future__ import annotations

import structlog

from medical_ais.agent.state import MedicalAgentState, RetrievedChunk
from medical_ais.interfaces.embedding import IEmbeddingModel
from medical_ais.interfaces.reranker import IReranker
from medical_ais.interfaces.search import ISearchEngine
from medical_ais.interfaces.vector_store import IVectorStore
from medical_ais.tools.search_tools import hybrid_search

logger = structlog.get_logger(__name__)


async def hybrid_search_node(
    state: MedicalAgentState,
    *,
    vector_store: IVectorStore,
    search_engine: ISearchEngine,
    embedding_model: IEmbeddingModel,
    reranker: IReranker,
    top_k: int = 10,
) -> dict:
    """Run hybrid search for all sub-queries and merge results."""
    sub_queries = state.get("sub_queries", [state["query"]])
    new_chunks: list[RetrievedChunk] = []
    seen_ids: set[str] = {c["id"] for c in state.get("retrieved_chunks", [])}

    for query in sub_queries[:5]:
        results = await hybrid_search(
            query,
            vector_store=vector_store,
            search_engine=search_engine,
            embedding_model=embedding_model,
            reranker=reranker,
            top_k=top_k,
            rerank_top_k=5,
        )
        for r in results:
            if r.id not in seen_ids:
                seen_ids.add(r.id)
                new_chunks.append(
                    RetrievedChunk(
                        id=r.id,
                        text=r.text,
                        score=r.score,
                        source="hybrid",
                        metadata=r.metadata,
                    )
                )

    logger.info("hybrid_search.results", new_chunks=len(new_chunks))
    # Return only new_chunks — the operator.add reducer in state accumulates them.
    return {"retrieved_chunks": new_chunks}


async def web_search_node(
    state: MedicalAgentState,
    *,
    tavily_api_key: str,
) -> dict:
    """
    Web search fallback — called by CRAG when local retrieval is insufficient.
    Uses Tavily for medical literature search.
    """
    if not tavily_api_key:
        logger.warning("web_search.no_api_key")
        return {}

    try:
        from tavily import AsyncTavilyClient
        client = AsyncTavilyClient(api_key=tavily_api_key)
        response = await client.search(
            query=state["query"],
            search_depth="advanced",
            max_results=5,
            include_domains=["pubmed.ncbi.nlm.nih.gov", "medscape.com", "uptodate.com"],
        )
        results = response.get("results", [])
    except Exception as exc:
        logger.error("web_search.failed", error=str(exc))
        return {}

    new_chunks = [
        RetrievedChunk(
            id=f"web_{i}_{r.get('url', '')[:20]}",
            text=r.get("content", ""),
            score=r.get("score", 0.5),
            source="web",
            metadata={"url": r.get("url", ""), "title": r.get("title", "")},
        )
        for i, r in enumerate(results)
        if r.get("content")
    ]

    # Return only new_chunks — the operator.add reducer in state accumulates them.
    return {"retrieved_chunks": new_chunks, "needs_web_search": False}
