"""
Community detection and summarisation.
Steps 7–8 of the data pipeline.

Uses Neo4j GDS Leiden algorithm to find communities, then LLM to summarise each.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import structlog

from medical_ais.interfaces.graph_db import IGraphDB
from medical_ais.interfaces.llm import ILLMProvider, LLMMessage

logger = structlog.get_logger(__name__)

_LEIDEN_PROJECT = """
CALL gds.graph.project(
  'medical_graph',
  'Entity',
  {
    RELATIONSHIP: {
      type: 'RELATIONSHIP',
      orientation: 'UNDIRECTED'
    }
  }
)
"""

_LEIDEN_WRITE = """
CALL gds.leiden.write(
  'medical_graph',
  { writeProperty: 'community_id', maxLevels: 10 }
)
YIELD communityCount, modularity
"""

_FETCH_COMMUNITIES = """
MATCH (e:Entity)
WHERE e.community_id IS NOT NULL
WITH e.community_id AS community_id, collect(e) AS members
RETURN community_id,
       [m IN members | {name: m.canonical_name, type: m.entity_type}] AS members,
       size(members) AS size
ORDER BY size DESC
LIMIT 100
"""

_SUMMARISE_SYSTEM = """\
You are a medical knowledge curator. Summarise this community of related medical
entities into a 2–3 sentence description that captures the main theme and key
relationships between the entities.
Output ONLY valid JSON: {"summary": "..."}
"""


@dataclass
class Community:
    community_id: int
    member_names: list[str] = field(default_factory=list)
    summary: str = ""
    size: int = 0


async def run_community_detection(db: IGraphDB) -> int:
    """
    Run Leiden community detection via Neo4j GDS.
    Returns number of communities found, or 0 if GDS is unavailable.
    """
    try:
        # Drop existing projection if it exists
        try:
            await db.run_write("CALL gds.graph.drop('medical_graph', false) YIELD graphName")
        except Exception:
            pass

        await db.run_write(_LEIDEN_PROJECT)
        rows = await db.run_query(_LEIDEN_WRITE)
        count = rows[0]["communityCount"] if rows else 0
        logger.info("community.detected", count=count)
        return count
    except Exception as exc:
        logger.warning("community.gds_unavailable", error=str(exc))
        return 0


async def summarise_communities(
    db: IGraphDB,
    llm: ILLMProvider,
    min_size: int = 3,
) -> list[Community]:
    """Fetch communities from graph and generate LLM summaries for each."""
    rows = await db.run_query(_FETCH_COMMUNITIES)
    communities: list[Community] = []

    for row in rows:
        size = row.get("size", 0)
        if size < min_size:
            continue

        members = row.get("members", [])
        member_text = "\n".join(
            f"- {m['name']} ({m['type']})" for m in members[:20]  # cap at 20
        )

        messages = [
            LLMMessage(role="system", content=_SUMMARISE_SYSTEM),
            LLMMessage(role="human", content=f"ENTITIES:\n{member_text}"),
        ]
        try:
            result = await llm.complete_json(messages, temperature=0.0, max_tokens=256)
            summary = result.get("summary", "")
        except Exception as exc:
            logger.error("community.summarise_failed", error=str(exc))
            summary = f"Community of {size} medical entities"

        community = Community(
            community_id=int(row["community_id"]),
            member_names=[m["name"] for m in members],
            summary=summary,
            size=size,
        )
        communities.append(community)

        # Persist summary back to graph
        try:
            await db.run_write(
                """
                MATCH (e:Entity {community_id: $cid})
                SET e.community_summary = $summary
                """,
                {"cid": community.community_id, "summary": summary},
            )
        except Exception as exc:
            logger.warning("community.persist_summary_failed", error=str(exc))

    logger.info("community.summarised", count=len(communities))
    return communities
