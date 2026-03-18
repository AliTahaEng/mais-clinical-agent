"""
Graph builder — writes resolved entities and relationships to Neo4j.
Step 6 of the data pipeline.
"""
from __future__ import annotations

import structlog

from medical_ais.interfaces.graph_db import IGraphDB
from medical_ais.pipeline.entity_resolver import ResolvedEntity, ResolvedRelationship

logger = structlog.get_logger(__name__)

# Cypher: MERGE so re-running the pipeline is idempotent
_UPSERT_ENTITY = """
MERGE (e:Entity {canonical_name: $name})
SET e.entity_type = $entity_type,
    e.description = $description,
    e.aliases = $aliases,
    e.source_chunks = $source_chunks
WITH e
CALL apoc.create.addLabels(e, [$entity_type]) YIELD node
RETURN node
"""

_UPSERT_RELATIONSHIP = """
MATCH (s:Entity {canonical_name: $source})
MATCH (t:Entity {canonical_name: $target})
MERGE (s)-[r:RELATIONSHIP {type: $rel_type}]->(t)
SET r.confidence = $confidence,
    r.evidence = $evidence,
    r.source_chunks = $source_chunks
"""

# Simplified fallback (no APOC) — used when APOC plugin is unavailable
_UPSERT_ENTITY_NO_APOC = """
MERGE (e:Entity {canonical_name: $name})
SET e.entity_type = $entity_type,
    e.description = $description,
    e.aliases = $aliases,
    e.source_chunks = $source_chunks
"""


async def write_entities(db: IGraphDB, entities: list[ResolvedEntity]) -> int:
    """Write all entities to the graph. Returns count written."""
    written = 0
    for entity in entities:
        params = {
            "name": entity.canonical_name,
            "entity_type": entity.entity_type,
            "description": entity.description,
            "aliases": entity.aliases,
            "source_chunks": entity.source_chunks,
        }
        try:
            await db.run_write(_UPSERT_ENTITY, params)
        except Exception:
            # APOC unavailable — fall back to simpler query
            try:
                await db.run_write(_UPSERT_ENTITY_NO_APOC, params)
            except Exception as exc:
                logger.error("graph_builder.entity_write_failed", name=entity.canonical_name, error=str(exc))
                continue
        written += 1

    logger.info("graph_builder.entities_written", count=written)
    return written


async def write_relationships(db: IGraphDB, relationships: list[ResolvedRelationship]) -> int:
    """Write all relationships to the graph. Returns count written."""
    written = 0
    for rel in relationships:
        try:
            await db.run_write(
                _UPSERT_RELATIONSHIP,
                {
                    "source": rel.source_canonical,
                    "target": rel.target_canonical,
                    "rel_type": rel.rel_type,
                    "confidence": rel.confidence,
                    "evidence": rel.evidence,
                    "source_chunks": rel.source_chunks,
                },
            )
            written += 1
        except Exception as exc:
            logger.error(
                "graph_builder.rel_write_failed",
                source=rel.source_canonical,
                target=rel.target_canonical,
                error=str(exc),
            )

    logger.info("graph_builder.relationships_written", count=written)
    return written
