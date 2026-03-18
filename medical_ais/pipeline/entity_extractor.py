"""
Entity and relationship extraction from text chunks.
Step 3–4 of the data pipeline.
Uses the LLM to identify medical entities and their relationships.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import structlog

from medical_ais.interfaces.llm import ILLMProvider, LLMMessage

logger = structlog.get_logger(__name__)

_EXTRACTION_SYSTEM = """\
You are a medical knowledge graph builder. Extract named entities and relationships
from the provided medical text.

ENTITY TYPES: Drug, Disease, Symptom, Enzyme, Gene, Lab_Value, Condition,
              Clinical_Trial, Guideline, Procedure, Anatomy

RELATIONSHIP TYPES: TREATS, INTERACTS_WITH, METABOLIZED_BY, CAUSES, INDICATED_FOR,
                    CONTRAINDICATED_WITH, ASSOCIATED_WITH, PART_OF, MEASURED_BY,
                    REFERENCED_IN, DIAGNOSED_BY

OUTPUT ONLY valid JSON:
{
  "entities": [
    {"name": "...", "type": "Drug|Disease|...", "aliases": ["..."], "description": "..."}
  ],
  "relationships": [
    {"source": "entity name", "target": "entity name", "type": "RELATIONSHIP_TYPE",
     "confidence": 0.0–1.0, "evidence": "exact quote supporting this relationship"}
  ]
}

Only extract entities and relationships explicitly supported by the text.
Do not invent or infer beyond what is stated.
"""


@dataclass
class ExtractedEntity:
    name: str
    entity_type: str
    aliases: list[str] = field(default_factory=list)
    description: str = ""
    source_chunk_id: str = ""


@dataclass
class ExtractedRelationship:
    source: str
    target: str
    rel_type: str
    confidence: float = 1.0
    evidence: str = ""
    source_chunk_id: str = ""


@dataclass
class ExtractionResult:
    entities: list[ExtractedEntity]
    relationships: list[ExtractedRelationship]
    chunk_id: str


async def extract_from_chunk(
    chunk_text: str,
    chunk_id: str,
    llm: ILLMProvider,
) -> ExtractionResult:
    """Extract entities and relationships from a single text chunk."""
    messages = [
        LLMMessage(role="system", content=_EXTRACTION_SYSTEM),
        LLMMessage(role="human", content=f"TEXT:\n{chunk_text}"),
    ]

    try:
        data = await llm.complete_json(messages, temperature=0.0)
    except Exception as exc:
        logger.error("extraction.failed", chunk_id=chunk_id, error=str(exc))
        return ExtractionResult(entities=[], relationships=[], chunk_id=chunk_id)

    entities = [
        ExtractedEntity(
            name=e.get("name", ""),
            entity_type=e.get("type", "Unknown"),
            aliases=e.get("aliases", []),
            description=e.get("description", ""),
            source_chunk_id=chunk_id,
        )
        for e in data.get("entities", [])
        if e.get("name")
    ]

    relationships = [
        ExtractedRelationship(
            source=r.get("source", ""),
            target=r.get("target", ""),
            rel_type=r.get("type", "ASSOCIATED_WITH"),
            confidence=float(r.get("confidence", 1.0)),
            evidence=r.get("evidence", ""),
            source_chunk_id=chunk_id,
        )
        for r in data.get("relationships", [])
        if r.get("source") and r.get("target")
    ]

    logger.info(
        "extraction.complete",
        chunk_id=chunk_id,
        entities=len(entities),
        relationships=len(relationships),
    )
    return ExtractionResult(entities=entities, relationships=relationships, chunk_id=chunk_id)
