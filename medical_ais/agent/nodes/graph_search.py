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
    seen_entities: set[str] = set()

    for query in sub_queries[:3]:  # cap to avoid runaway graph traversal
        candidates = _extract_entity_names(query)

        for entity_name in candidates:
            if entity_name in seen_entities:
                continue

            entity = await find_entity(entity_name, graph_db)
            if not entity:
                logger.debug("local_graph.entity_not_found", name=entity_name)
                continue

            canonical = entity["name"]
            if canonical in seen_entities:
                continue
            seen_entities.add(canonical)

            relationships = await traverse_relationships(canonical, graph_db, max_hops=max_hops)
            context_str = format_graph_context(entity, relationships, None)

            if context_str:
                graph_context_parts.append(context_str)
                new_chunks.append(
                    RetrievedChunk(
                        id=f"graph_local_{canonical}",
                        text=context_str,
                        score=0.9,
                        source="graph_local",
                        metadata={"entity": canonical, "relationships": len(relationships)},
                    )
                )
            break  # found one entity for this sub-query, move to next

    logger.info(
        "local_graph_search.done",
        chunks=len(new_chunks),
        entities=list(seen_entities),
        session_id=state.get("session_id"),
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
    Searches by individual significant words from the query, not the full sentence.
    """
    # Try the original query first, then fall back to sub_queries
    search_texts = [state["query"]] + state.get("sub_queries", [])

    community = None
    for text in search_texts[:4]:
        community = await get_community_context(text, graph_db)
        if community:
            break

    if not community:
        logger.info(
            "global_graph_search.no_community",
            query=state["query"][:80],
            session_id=state.get("session_id"),
        )
        return {"community_context": ""}

    context_str = format_graph_context(None, [], community)
    logger.info(
        "global_graph_search.done",
        community_id=community.get("community_id"),
        members=len(community.get("members", [])),
        session_id=state.get("session_id"),
    )

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


_GRAPH_STOPWORDS = {
    "what", "is", "are", "how", "does", "do", "can", "the", "a", "an",
    "of", "for", "in", "and", "or", "with", "to", "from", "about",
    "tell", "me", "you", "why", "when", "which", "who", "where",
    "not", "no", "if", "then", "give", "show", "please", "hi", "hello",
    "explain", "describe", "define", "list", "between", "difference",
    "important", "early", "late", "common", "main", "major", "key",
    "used", "called", "known", "related", "associated", "found",
    "causes", "caused", "treatment", "treated", "diagnosis", "diagnosed",
}


def _extract_entity_names(query: str) -> list[str]:
    """
    Extract multiple candidate entity names from a query.
    Returns individual significant words AND short multi-word combinations,
    prioritising longer phrases first (more specific before general).
    """
    clean = query.strip("?.,!").lower()
    words = [w.strip("?.,!") for w in clean.split()
             if w.strip("?.,!") not in _GRAPH_STOPWORDS and len(w.strip("?.,!")) > 2]

    candidates: list[str] = []

    # Multi-word phrases (most specific first)
    if len(words) >= 3:
        candidates.append(" ".join(w.capitalize() for w in words[:3]))
    if len(words) >= 2:
        candidates.append(" ".join(w.capitalize() for w in words[:2]))
    # Individual words
    for w in words[:6]:
        c = w.capitalize()
        if c not in candidates:
            candidates.append(c)

    return candidates
