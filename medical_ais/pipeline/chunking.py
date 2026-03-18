"""
Parent-child chunking strategy.
Step 2 of the data pipeline.

Parent chunks (large): stored in vector store for full-context retrieval.
Child chunks (small): indexed for precise semantic matching.
Search hits child → return parent for richer context.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field

import structlog

from medical_ais.pipeline.ingestion import RawDocument

logger = structlog.get_logger(__name__)


@dataclass
class TextChunk:
    """A piece of a document, either parent or child."""
    id: str
    text: str
    doc_id: str
    chunk_type: str        # "parent" | "child"
    parent_id: str | None  # child chunks reference their parent
    start_char: int
    end_char: int
    metadata: dict = field(default_factory=dict)


def _split_by_sentences(text: str, max_chars: int) -> list[str]:
    """Split text into chunks of roughly *max_chars*, breaking on sentence boundaries."""
    # Split on sentence-ending punctuation
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks: list[str] = []
    current = ""

    for sentence in sentences:
        if len(current) + len(sentence) + 1 > max_chars and current:
            chunks.append(current.strip())
            current = sentence
        else:
            current = (current + " " + sentence).strip() if current else sentence

    if current:
        chunks.append(current.strip())

    return [c for c in chunks if c.strip()]


def chunk_document(
    doc: RawDocument,
    parent_chunk_size: int = 1200,
    child_chunk_size: int = 200,
    chunk_overlap: int = 50,
) -> tuple[list[TextChunk], list[TextChunk]]:
    """
    Split *doc* into (parent_chunks, child_chunks).

    Returns
    -------
    parents : list[TextChunk]  — large context chunks
    children : list[TextChunk] — small search-target chunks
    """
    text = doc.text
    parents: list[TextChunk] = []
    children: list[TextChunk] = []

    # --- build parent chunks -------------------------------------------------
    raw_parents = _split_by_sentences(text, parent_chunk_size)
    cursor = 0

    for raw in raw_parents:
        start = text.find(raw, cursor)
        if start == -1:
            start = cursor
        end = start + len(raw)
        cursor = max(0, end - chunk_overlap)

        parent = TextChunk(
            id=f"{doc.id}_p_{uuid.uuid4().hex[:8]}",
            text=raw,
            doc_id=doc.id,
            chunk_type="parent",
            parent_id=None,
            start_char=start,
            end_char=end,
            metadata={**doc.metadata, "doc_id": doc.id},
        )
        parents.append(parent)

        # --- build child chunks from this parent ----------------------------
        raw_children = _split_by_sentences(raw, child_chunk_size)
        child_cursor = 0
        for c_raw in raw_children:
            c_start = raw.find(c_raw, child_cursor)
            c_start_abs = start + (c_start if c_start != -1 else child_cursor)
            child_cursor = max(0, (c_start if c_start != -1 else child_cursor) + len(c_raw) - chunk_overlap)

            child = TextChunk(
                id=f"{parent.id}_c_{uuid.uuid4().hex[:8]}",
                text=c_raw,
                doc_id=doc.id,
                chunk_type="child",
                parent_id=parent.id,
                start_char=c_start_abs,
                end_char=c_start_abs + len(c_raw),
                metadata={**doc.metadata, "doc_id": doc.id, "parent_id": parent.id},
            )
            children.append(child)

    logger.info(
        "chunking.done",
        doc_id=doc.id,
        parents=len(parents),
        children=len(children),
    )
    return parents, children
