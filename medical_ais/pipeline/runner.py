"""
Pipeline runner — orchestrates all 8 steps end-to-end.
Entry point: run_full_pipeline(directory, container, ...)

Pass job_store + job_id to get per-step progress tracking in the admin UI.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import structlog

from medical_ais.pipeline.chunking import chunk_document
from medical_ais.pipeline.community_detector import run_community_detection, summarise_communities
from medical_ais.pipeline.embedder import embed_and_index
from medical_ais.pipeline.entity_extractor import extract_from_chunk
from medical_ais.pipeline.entity_resolver import resolve_entities, resolve_relationships
from medical_ais.pipeline.graph_builder import write_entities, write_relationships
from medical_ais.pipeline.ingestion import load_directory

if TYPE_CHECKING:
    from medical_ais.services.pipeline_job_store import PipelineJobStore

logger = structlog.get_logger(__name__)

_EXTRACTION_CONCURRENCY = 5   # parallel LLM calls for entity extraction


@dataclass
class PipelineResult:
    documents_loaded: int = 0
    parent_chunks: int = 0
    child_chunks: int = 0
    entities_written: int = 0
    relationships_written: int = 0
    communities_found: int = 0
    chunks_embedded: int = 0
    errors: list[str] = field(default_factory=list)


async def run_full_pipeline(
    documents_dir: str,
    *,
    llm,
    graph_db,
    vector_store,
    search_engine,
    embedding_model,
    parent_chunk_size: int = 1200,
    child_chunk_size: int = 200,
    chunk_overlap: int = 50,
    # Optional job tracking — pass both or neither
    job_store: "PipelineJobStore | None" = None,
    job_id: str | None = None,
) -> PipelineResult:
    """
    Execute the complete 8-step ingestion pipeline.

    Parameters are injected — no global state, fully testable.
    When job_store + job_id are provided every step updates the job store
    so the admin UI can show real-time progress.
    """
    result = PipelineResult()

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _start(step: str) -> None:
        logger.info(f"pipeline.{step}")
        if job_store and job_id:
            await job_store.start_step(job_id, step)

    async def _done(step: str, counts: dict, skipped: bool = False) -> None:
        if job_store and job_id:
            await job_store.complete_step(job_id, step, counts=counts, skipped=skipped)

    async def _log(step: str, level: str, msg: str, data: dict | None = None) -> None:
        if job_store and job_id:
            await job_store.add_log(job_id, step, level, msg, data)

    async def _fail(step: str, error: str) -> None:
        if job_store and job_id:
            await job_store.fail_step(job_id, step, error)

    async def _skip_remaining(from_idx: int) -> None:
        """Mark all steps from from_idx onwards as skipped."""
        from medical_ais.services.pipeline_job_store import PIPELINE_STEPS
        if job_store and job_id:
            for name, _ in PIPELINE_STEPS[from_idx:]:
                await job_store.complete_step(job_id, name, skipped=True)

    # ── STEP 1: Ingestion ─────────────────────────────────────────────────────
    await _start("step1_ingestion")
    try:
        documents = await load_directory(documents_dir)
        result.documents_loaded = len(documents)
        await _log("step1_ingestion", "info",
                   f"Discovered {len(documents)} document(s) in {documents_dir}")
        await _done("step1_ingestion", {"documents": len(documents)})
    except Exception as exc:
        await _fail("step1_ingestion", str(exc))
        await _skip_remaining(1)
        result.errors.append(str(exc))
        return result

    if not documents:
        logger.warning("pipeline.no_documents", directory=documents_dir)
        await _log("step1_ingestion", "warning",
                   "No documents found — skipping remaining steps")
        await _skip_remaining(1)
        return result

    # ── STEP 2: Chunking ──────────────────────────────────────────────────────
    await _start("step2_chunking")
    all_parents, all_children = [], []
    for doc in documents:
        parents, children = chunk_document(
            doc,
            parent_chunk_size=parent_chunk_size,
            child_chunk_size=child_chunk_size,
            chunk_overlap=chunk_overlap,
        )
        all_parents.extend(parents)
        all_children.extend(children)

    result.parent_chunks = len(all_parents)
    result.child_chunks  = len(all_children)
    await _log("step2_chunking", "info",
               f"Created {len(all_parents)} parent chunks and {len(all_children)} child chunks",
               {"parent_chunks": len(all_parents), "child_chunks": len(all_children)})
    await _done("step2_chunking", {
        "parent_chunks": len(all_parents),
        "child_chunks": len(all_children),
    })

    # ── STEP 3–4: Entity + relationship extraction ────────────────────────────
    await _start("step3_4_extraction")
    await _log("step3_4_extraction", "info",
               f"Extracting entities from {len(all_children)} child chunks "
               f"(concurrency={_EXTRACTION_CONCURRENCY})")

    semaphore = asyncio.Semaphore(_EXTRACTION_CONCURRENCY)

    async def _extract_safe(chunk):
        async with semaphore:
            return await extract_from_chunk(chunk.text, chunk.id, llm)

    extraction_results = await asyncio.gather(
        *[_extract_safe(c) for c in all_children],
        return_exceptions=True,
    )

    all_entities, all_relationships = [], []
    extraction_errors = 0
    for er in extraction_results:
        if isinstance(er, Exception):
            result.errors.append(str(er))
            extraction_errors += 1
        else:
            all_entities.extend(er.entities)
            all_relationships.extend(er.relationships)

    await _log("step3_4_extraction", "info",
               f"Extracted {len(all_entities)} entities, {len(all_relationships)} relationships "
               f"({extraction_errors} chunk errors)",
               {"entities": len(all_entities), "relationships": len(all_relationships),
                "errors": extraction_errors})
    await _done("step3_4_extraction", {
        "entities_raw": len(all_entities),
        "relationships_raw": len(all_relationships),
        "errors": extraction_errors,
    })

    # ── STEP 5: Entity resolution ─────────────────────────────────────────────
    await _start("step5_resolution")
    resolved_entities, name_map = resolve_entities(all_entities)
    resolved_relationships = resolve_relationships(all_relationships, name_map)
    duplicates_removed = len(all_entities) - len(resolved_entities)

    await _log("step5_resolution", "info",
               f"Resolved {len(all_entities)} → {len(resolved_entities)} unique entities "
               f"({duplicates_removed} duplicates merged)")
    await _done("step5_resolution", {
        "unique_entities": len(resolved_entities),
        "duplicates_merged": duplicates_removed,
        "relationships_normalised": len(resolved_relationships),
    })

    # ── STEP 6: Graph storage ─────────────────────────────────────────────────
    await _start("step6_graph_storage")
    await _log("step6_graph_storage", "info",
               f"Writing {len(resolved_entities)} entities to Neo4j...")
    try:
        result.entities_written = await write_entities(graph_db, resolved_entities)
        await _log("step6_graph_storage", "info",
                   f"Wrote {result.entities_written} entities")
        await _log("step6_graph_storage", "info",
                   f"Writing {len(resolved_relationships)} relationships to Neo4j...")
        result.relationships_written = await write_relationships(graph_db, resolved_relationships)
        await _log("step6_graph_storage", "info",
                   f"Wrote {result.relationships_written} relationships")
        await _done("step6_graph_storage", {
            "entities_written": result.entities_written,
            "relationships_written": result.relationships_written,
        })
    except Exception as exc:
        await _fail("step6_graph_storage", str(exc))
        result.errors.append(str(exc))

    # ── STEP 7: Community detection ───────────────────────────────────────────
    await _start("step7_community_detection")
    await _log("step7_community_detection", "info",
               "Running Leiden community detection via Neo4j GDS...")
    try:
        result.communities_found = await run_community_detection(graph_db)
        await _log("step7_community_detection", "info",
                   f"Found {result.communities_found} communities")
        await _done("step7_community_detection", {"communities": result.communities_found})
    except Exception as exc:
        await _log("step7_community_detection", "warning",
                   f"Community detection unavailable: {exc}")
        await _done("step7_community_detection", {"communities": 0})

    # ── STEP 8: Community summarisation ──────────────────────────────────────
    if result.communities_found > 0:
        await _start("step8_community_summarisation")
        await _log("step8_community_summarisation", "info",
                   f"Summarising {result.communities_found} communities with LLM...")
        try:
            await summarise_communities(graph_db, llm)
            await _log("step8_community_summarisation", "info",
                       "Community summaries written to graph")
            await _done("step8_community_summarisation",
                        {"communities_summarised": result.communities_found})
        except Exception as exc:
            await _log("step8_community_summarisation", "warning", str(exc))
            await _done("step8_community_summarisation", {"communities_summarised": 0})
    else:
        await _start("step8_community_summarisation")
        await _log("step8_community_summarisation", "info",
                   "No communities found — skipping summarisation")
        await _done("step8_community_summarisation", {}, skipped=True)

    # ── STEP 9–10: Embedding + indexing ───────────────────────────────────────
    all_chunks = all_parents + all_children
    await _start("step9_10_embedding_indexing")
    await _log("step9_10_embedding_indexing", "info",
               f"Embedding {len(all_children)} child chunks (batch=32) and building BM25 index "
               f"over {len(all_chunks)} total chunks...")
    try:
        embed_stats = await embed_and_index(
            all_chunks, embedding_model, vector_store, search_engine
        )
        result.chunks_embedded = embed_stats.chunks_embedded
        await _log("step9_10_embedding_indexing", "info",
                   f"Embedded {result.chunks_embedded} chunks, BM25 index built")
        await _done("step9_10_embedding_indexing", {
            "chunks_embedded": result.chunks_embedded,
            "bm25_indexed": len(all_chunks),
        })
    except Exception as exc:
        await _fail("step9_10_embedding_indexing", str(exc))
        result.errors.append(str(exc))

    logger.info(
        "pipeline.complete",
        docs=result.documents_loaded,
        entities=result.entities_written,
        relationships=result.relationships_written,
        communities=result.communities_found,
        embedded=result.chunks_embedded,
    )
    return result
