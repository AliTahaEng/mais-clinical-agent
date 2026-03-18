"""
Graph search tools — read-only queries against the Neo4j knowledge graph.
These are used inside agent nodes to retrieve structured knowledge.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog

from medical_ais.interfaces.graph_db import IGraphDB

logger = structlog.get_logger(__name__)

# ── Cypher queries ─────────────────────────────────────────────────────────────

_FIND_ENTITY = """
MATCH (e:Entity)
WHERE toLower(e.canonical_name) = toLower($name)
   OR $name IN [alias IN e.aliases | toLower(alias)]
RETURN e.canonical_name AS name,
       e.entity_type    AS entity_type,
       e.description    AS description,
       e.community_id   AS community_id
LIMIT 1
"""

_TRAVERSE_RELATIONSHIPS = """
MATCH (e:Entity {canonical_name: $name})-[r:RELATIONSHIP*1..$hops]-(related:Entity)
RETURN DISTINCT
  e.canonical_name       AS source,
  related.canonical_name AS target,
  r[-1].type             AS rel_type,
  related.entity_type    AS entity_type,
  related.description    AS description
LIMIT 50
"""

_FIND_CONNECTION = """
MATCH path = shortestPath(
  (a:Entity {canonical_name: $entity_a})-[*..{max_hops}]-(b:Entity {canonical_name: $entity_b})
)
RETURN [n IN nodes(path) | n.canonical_name] AS path_nodes,
       [r IN relationships(path) | type(r)] AS rel_types,
       length(path) AS hops
LIMIT 1
"""

_GET_COMMUNITY_CONTEXT = """
MATCH (e:Entity {community_id: $community_id})
RETURN collect(e.canonical_name)[0..20] AS members,
       e.community_summary AS summary
LIMIT 1
"""

_FULL_TEXT_COMMUNITY = """
MATCH (e:Entity)
WHERE e.community_id IS NOT NULL
  AND (
    toLower(e.canonical_name) CONTAINS toLower($query)
    OR any(alias IN e.aliases WHERE toLower(alias) CONTAINS toLower($query))
  )
WITH e.community_id AS cid, count(e) AS hits
ORDER BY hits DESC
LIMIT 1
MATCH (member:Entity {community_id: cid})
RETURN cid AS community_id,
       collect(member.canonical_name)[0..20] AS members,
       member.community_summary AS summary
LIMIT 1
"""


# ── Tool functions ─────────────────────────────────────────────────────────────

async def find_entity(name: str, db: IGraphDB) -> dict[str, Any] | None:
    """Return entity node details, or None if not found."""
    rows = await db.run_query(_FIND_ENTITY, {"name": name})
    return rows[0] if rows else None


async def traverse_relationships(
    entity_name: str,
    db: IGraphDB,
    max_hops: int = 2,
) -> list[dict[str, Any]]:
    """Return entities reachable from *entity_name* within *max_hops*."""
    return await db.run_query(
        _TRAVERSE_RELATIONSHIPS,
        {"name": entity_name, "hops": max_hops},
    )


async def find_connection(
    entity_a: str,
    entity_b: str,
    db: IGraphDB,
    max_hops: int = 3,
) -> dict[str, Any] | None:
    """Return shortest path between two entities, or None if unreachable."""
    query = _FIND_CONNECTION.replace("{max_hops}", str(max_hops))
    rows = await db.run_query(query, {"entity_a": entity_a, "entity_b": entity_b})
    return rows[0] if rows else None


async def get_community_context(
    query: str,
    db: IGraphDB,
) -> dict[str, Any] | None:
    """Return community context most relevant to *query*."""
    rows = await db.run_query(_FULL_TEXT_COMMUNITY, {"query": query})
    return rows[0] if rows else None


def format_graph_context(
    entity: dict | None,
    relationships: list[dict],
    community: dict | None,
) -> str:
    """Convert raw graph query results into a readable context string."""
    parts: list[str] = []

    if entity:
        parts.append(
            f"ENTITY: {entity['name']} ({entity.get('entity_type', 'Unknown')})\n"
            f"Description: {entity.get('description', 'N/A')}"
        )

    if relationships:
        rel_lines = [
            f"  - {r['source']} --[{r.get('rel_type', '?')}]--> {r['target']}"
            f" ({r.get('entity_type', '')})"
            for r in relationships[:20]
        ]
        parts.append("RELATIONSHIPS:\n" + "\n".join(rel_lines))

    if community:
        members = ", ".join(community.get("members", [])[:10])
        summary = community.get("summary", "")
        parts.append(f"COMMUNITY CONTEXT: {summary}\nRelated entities: {members}")

    return "\n\n".join(parts) if parts else ""
