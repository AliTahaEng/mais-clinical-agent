"""
Entity resolution — deduplicates extracted entities across chunks.
Step 5 of the data pipeline.

Merges "Metformin", "METFORMIN", "metformin hydrochloride" → one canonical node.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

import structlog

from medical_ais.pipeline.entity_extractor import ExtractedEntity, ExtractedRelationship

logger = structlog.get_logger(__name__)


def _normalise(name: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    name = name.lower().strip()
    name = re.sub(r"[^a-z0-9 ]", " ", name)
    return re.sub(r"\s+", " ", name).strip()


@dataclass
class ResolvedEntity:
    canonical_name: str
    entity_type: str
    aliases: list[str] = field(default_factory=list)
    description: str = ""
    source_chunks: list[str] = field(default_factory=list)


@dataclass
class ResolvedRelationship:
    source_canonical: str
    target_canonical: str
    rel_type: str
    confidence: float
    evidence: str
    source_chunks: list[str] = field(default_factory=list)


def resolve_entities(
    entities: list[ExtractedEntity],
) -> tuple[list[ResolvedEntity], dict[str, str]]:
    """
    Merge duplicate entities.

    Returns
    -------
    resolved : list[ResolvedEntity]
    name_map : dict mapping raw name → canonical name
    """
    # Group by normalised name
    groups: dict[str, list[ExtractedEntity]] = defaultdict(list)
    for e in entities:
        key = _normalise(e.name)
        groups[key].append(e)
        for alias in e.aliases:
            groups[_normalise(alias)].append(e)

    resolved: list[ResolvedEntity] = []
    name_map: dict[str, str] = {}  # raw_name → canonical_name

    for norm_key, group in groups.items():
        # Pick the longest original name as canonical
        canonical = max((e.name for e in group), key=len)
        all_aliases = list({e.name for e in group} - {canonical})
        all_chunks = list({e.source_chunk_id for e in group})
        best_desc = next((e.description for e in group if e.description), "")
        entity_type = group[0].entity_type

        re_obj = ResolvedEntity(
            canonical_name=canonical,
            entity_type=entity_type,
            aliases=all_aliases,
            description=best_desc,
            source_chunks=all_chunks,
        )
        resolved.append(re_obj)

        for e in group:
            name_map[e.name] = canonical
            for alias in e.aliases:
                name_map[alias] = canonical

    # Deduplicate resolved list (same canonical may appear from multiple aliases)
    seen: dict[str, ResolvedEntity] = {}
    for r in resolved:
        if r.canonical_name not in seen:
            seen[r.canonical_name] = r
    resolved = list(seen.values())

    logger.info("resolution.done", raw=len(entities), resolved=len(resolved))
    return resolved, name_map


def resolve_relationships(
    relationships: list[ExtractedRelationship],
    name_map: dict[str, str],
) -> list[ResolvedRelationship]:
    """Map raw entity names in relationships to canonical names."""
    resolved: list[ResolvedRelationship] = []
    for rel in relationships:
        source_canon = name_map.get(rel.source, rel.source)
        target_canon = name_map.get(rel.target, rel.target)

        resolved.append(
            ResolvedRelationship(
                source_canonical=source_canon,
                target_canonical=target_canon,
                rel_type=rel.rel_type,
                confidence=rel.confidence,
                evidence=rel.evidence,
                source_chunks=[rel.source_chunk_id],
            )
        )
    return resolved
