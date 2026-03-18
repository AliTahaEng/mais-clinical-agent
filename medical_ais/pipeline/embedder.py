"""
Embedding and indexing step.
Steps 9–10 of the data pipeline.

Embeds child chunks → vector store.
Indexes child chunks → BM25 search engine.
Stores parent chunks for retrieval at answer time.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

import structlog

from medical_ais.interfaces.embedding import IEmbeddingModel
from medical_ais.interfaces.search import ISearchEngine
from medical_ais.interfaces.vector_store import IVectorStore, VectorDocument
from medical_ais.pipeline.chunking import TextChunk

logger = structlog.get_logger(__name__)

_BATCH_SIZE = 32  # embed this many chunks at once


@dataclass
class EmbeddingStats:
    chunks_embedded: int = 0
    chunks_indexed: int = 0
    errors: int = 0


async def embed_and_index(
    chunks: list[TextChunk],
    embedding_model: IEmbeddingModel,
    vector_store: IVectorStore,
    search_engine: ISearchEngine,
) -> EmbeddingStats:
    """
    Embed *chunks* and load them into both the vector store and BM25 index.
    Only child chunks are embedded; parent chunks are stored as-is for retrieval.
    """
    child_chunks = [c for c in chunks if c.chunk_type == "child"]
    stats = EmbeddingStats()

    # --- vector store ---------------------------------------------------
    for i in range(0, len(child_chunks), _BATCH_SIZE):
        batch = child_chunks[i : i + _BATCH_SIZE]
        texts = [c.text for c in batch]
        try:
            embeddings = await embedding_model.embed_texts(texts)
        except Exception as exc:
            logger.error("embedder.embed_failed", batch_start=i, error=str(exc))
            stats.errors += len(batch)
            continue

        vector_docs = [
            VectorDocument(
                id=chunk.id,
                text=chunk.text,
                embedding=emb,
                metadata={
                    **chunk.metadata,
                    "parent_id": chunk.parent_id or "",
                    "chunk_type": chunk.chunk_type,
                },
            )
            for chunk, emb in zip(batch, embeddings)
        ]
        try:
            await vector_store.upsert(vector_docs)
            stats.chunks_embedded += len(batch)
        except Exception as exc:
            logger.error("embedder.upsert_failed", error=str(exc))
            stats.errors += len(batch)

    # --- BM25 search index ---------------------------------------------
    index_docs = [
        {
            "id": c.id,
            "text": c.text,
            **c.metadata,
        }
        for c in child_chunks
    ]
    try:
        await search_engine.index(index_docs)
        stats.chunks_indexed = len(index_docs)
    except Exception as exc:
        logger.error("embedder.bm25_index_failed", error=str(exc))

    logger.info(
        "embedder.done",
        embedded=stats.chunks_embedded,
        indexed=stats.chunks_indexed,
        errors=stats.errors,
    )
    return stats
