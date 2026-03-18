"""
Graph search nodes — local entity search and global community search.
"""
from __future__ import annotations

import structlog

from medical_ais.agent.state import MedicalAgentState, RetrievedChunk
from medical_ais.interfaces.graph_db import IGraphDB
from medical_ais.tools.graph_tools import (
    find_entity,
    format_graph_context,
    get_community_context,
    traverse_relationships,
)

logger = structlog.get_logger(__name__)


async def local_graph_search_node(
    state: MedicalAgentState,
    *,
    graph_db: IGraphDB,
    max_hops: int = 2,
) -> dict:
    """
    Local graph search: find specific entities + traverse their relationships.
    Runs in parallel with other search nodes (via LangGraph Send API).
    """
    sub_queries = state.get("sub_queries", [state["query"]])
    new_chunks: list[RetrievedChunk] = []
    graph_context_parts: list[str] = []

    for query in sub_queries[:3]:  # cap to avoid runaway graph traversal
        # Extract likely entity name from query (first noun phrase approximation)
        entity_name = _extract_entity_name(query)
        if not entity_name:
            continue

        entity = await find_entity(entity_name, graph_db)
        if not entity:
            logger.debug("local_graph.entity_not_found", name=entity_name)
            continue

        relationships = await traverse_relationships(entity_name, graph_db, max_hops=max_hops)
        context_str = format_graph_context(entity, relationships, None)

        if context_str:
            graph_context_parts.append(context_str)
            new_chunks.append(
                RetrievedChunk(
                    id=f"graph_local_{entity_name}",
                    text=context_str,
                    score=0.9,
                    source="graph_local",
                    metadata={"entity": entity_name, "relationships": len(relationships)},
                )
            )

    # Return only new_chunks — the operator.add reducer in state accumulates them.
    return {
        "retrieved_chunks": new_chunks,
        "graph_context": "\n\n".join(graph_context_parts),
    }


async def global_graph_search_node(
    state: MedicalAgentState,
    *,
    graph_db: IGraphDB,
) -> dict:
    """
    Global graph search: retrieve community-level context.
    Captures thematic knowledge that local entity search misses.
    """
    query = state["query"]
    community = await get_community_context(query, graph_db)

    if not community:
        return {"community_context": ""}

    context_str = format_graph_context(None, [], community)

    # Return only the new chunk — the operator.add reducer in state accumulates it.
    return {
        "retrieved_chunks": [
            RetrievedChunk(
                id=f"graph_community_{community.get('community_id', 0)}",
                text=context_str,
                score=0.75,
                source="graph_global",
                metadata={"community_id": community.get("community_id")},
            )
        ],
        "community_context": context_str,
    }


def _extract_entity_name(query: str) -> str:
    """
    Very lightweight entity name extraction.
    In production, replace with an NER model or LLM call.
    Returns the first 1–3 significant words as a candidate entity name.
    """
    # Remove question words and common stopwords
    stopwords = {"what", "is", "are", "how", "does", "do", "can", "the", "a", "an",
                 "of", "for", "in", "and", "or", "with", "to", "from", "about"}
    words = [w for w in query.lower().split() if w not in stopwords]
    # Return first 1-3 words capitalised
    candidate = " ".join(w.capitalize() for w in words[:3])
    return candidate
