"""
Admin API routes — protected by admin token.
  GET  /admin/health                  — system health
  GET  /admin/audit                   — audit log entries
  GET  /admin/sessions                — active sessions overview
  GET  /admin/sessions/{sid}          — session graph state
  GET  /admin/stats                   — usage statistics
  GET  /admin/graph/nodes             — knowledge graph node counts
  GET  /admin/settings                — current feature flags
  PATCH /admin/settings               — update feature flags (in-memory only)
  POST /admin/ingest/upload           — start async ingestion, returns job_id
  GET  /admin/ingest/jobs             — list recent pipeline jobs
  GET  /admin/ingest/jobs/{job_id}    — get single job status + per-step logs
"""
from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from pydantic import BaseModel

from medical_ais.api.auth import require_admin
from medical_ais.auth.models import User
from medical_ais.core.container import Container
from medical_ais.pipeline.runner import run_full_pipeline

logger = structlog.get_logger(__name__)

admin_router = APIRouter(prefix="/admin", tags=["admin"])


def get_container(request: Request) -> Container:
    return request.app.state.container


# ── Health ─────────────────────────────────────────────────────────────────────

@admin_router.get("/health")
async def admin_health(
    container: Container = Depends(get_container),
    _: User = Depends(require_admin),
) -> dict[str, Any]:
    services: dict[str, bool] = {}
    if container.graph_db:
        services["graph_db"] = await container.graph_db.health_check()
    if container.vector_store:
        services["vector_store"] = await container.vector_store.health_check()
    if container.ehr_client:
        services["ehr"] = await container.ehr_client.health_check()
    if container.cache:
        services["cache"] = await container.cache.health_check()

    all_healthy = all(services.values()) if services else True
    return {
        "status": "healthy" if all_healthy else "degraded",
        "timestamp": datetime.utcnow().isoformat(),
        "services": services,
    }


# ── Audit log ─────────────────────────────────────────────────────────────────

@admin_router.get("/audit")
async def get_audit_log(
    limit: int = 50,
    session_id: str | None = None,
    container: Container = Depends(get_container),
    _: User = Depends(require_admin),
) -> dict[str, Any]:
    try:
        if container.audit_store:
            audit_records = await container.audit_store.query(
                session_id=session_id,
                limit=limit,
            )
            # Convert AuditRecord dataclass instances to dicts
            records = [
                {
                    "session_id": r.session_id,
                    "event_type": r.event_type,
                    "agent_id": r.agent_id,
                    "timestamp": r.timestamp.isoformat() if hasattr(r.timestamp, "isoformat") else str(r.timestamp),
                    **r.payload,
                }
                for r in audit_records
            ]
        else:
            records = []
        return {"records": records, "total": len(records)}
    except Exception as exc:
        logger.error("admin.audit_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


# ── Sessions ──────────────────────────────────────────────────────────────────

@admin_router.get("/sessions")
async def list_sessions(
    container: Container = Depends(get_container),
    _: User = Depends(require_admin),
) -> dict[str, Any]:
    """List all sessions with pending approvals."""
    try:
        pending = await container.approval_store.list_pending()
        return {"sessions": pending, "total": len(pending)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@admin_router.get("/sessions/{session_id}")
async def get_session_state(
    session_id: str,
    container: Container = Depends(get_container),
    _: User = Depends(require_admin),
) -> dict[str, Any]:
    """Get the LangGraph state for a specific session."""
    try:
        config = {"configurable": {"thread_id": session_id}}
        state = await container.compiled_graph.aget_state(config)
        if state is None:
            raise HTTPException(status_code=404, detail="Session not found")
        # Convert state to serialisable form
        state_dict = dict(state.values) if hasattr(state, "values") else {}
        # Remove non-serialisable objects
        safe_state = {
            k: v for k, v in state_dict.items()
            if isinstance(v, (str, int, float, bool, list, dict, type(None)))
        }
        return {"session_id": session_id, "state": safe_state}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Statistics ────────────────────────────────────────────────────────────────

@admin_router.get("/stats")
async def get_stats(
    container: Container = Depends(get_container),
    _: User = Depends(require_admin),
) -> dict[str, Any]:
    """Usage statistics: audit record counts by event type."""
    try:
        from collections import Counter
        if container.audit_store:
            all_records = await container.audit_store.query(limit=1000)
            event_counts = Counter(r.event_type for r in all_records)
        else:
            event_counts = Counter()

        return {
            "total_queries": event_counts.get("session.completed", 0),
            "total_actions_executed": event_counts.get("action.executed", 0),
            "event_breakdown": dict(event_counts),
            "pending_approvals": len(await container.approval_store.list_pending()),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Graph ─────────────────────────────────────────────────────────────────────

@admin_router.get("/graph/nodes")
async def get_graph_nodes(
    label: str | None = None,
    limit: int = 100,
    container: Container = Depends(get_container),
    _: User = Depends(require_admin),
) -> dict[str, Any]:
    """Get knowledge graph node counts or nodes by label."""
    try:
        if label:
            query = f"MATCH (n:{label}) RETURN n.canonical_name AS name, n.entity_type AS type, n.description AS description LIMIT $limit"
            rows = await container.graph_db.run_query(query, {"limit": limit})
        else:
            query = "MATCH (n) RETURN labels(n)[0] AS label, count(n) AS count"
            rows = await container.graph_db.run_query(query, {})
        return {"nodes": rows, "label_filter": label}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Knowledge base clear ──────────────────────────────────────────────────────

@admin_router.delete("/knowledge-base")
async def clear_knowledge_base(
    container: Container = Depends(get_container),
    _: User = Depends(require_admin),
) -> dict[str, Any]:
    """
    Wipe all ingested knowledge:
      - Neo4j: delete every node and relationship
      - LanceDB: drop the medical_chunks table
      - BM25: clear the in-memory index
    This is irreversible. Re-ingest documents to rebuild.
    """
    results: dict[str, Any] = {}
    errors: list[str] = []

    # 1. Neo4j — delete all nodes and relationships
    try:
        await container.graph_db.run_write("MATCH (n) DETACH DELETE n")
        results["neo4j"] = "cleared"
    except Exception as exc:
        errors.append(f"neo4j: {exc}")
        results["neo4j"] = f"error: {exc}"

    # 2. LanceDB — drop table
    try:
        if hasattr(container.vector_store, "clear"):
            await container.vector_store.clear()
        results["lancedb"] = "cleared"
    except Exception as exc:
        errors.append(f"lancedb: {exc}")
        results["lancedb"] = f"error: {exc}"

    # 3. BM25 — clear in-memory index
    try:
        if hasattr(container.search_engine, "clear"):
            await container.search_engine.clear()
        results["bm25"] = "cleared"
    except Exception as exc:
        errors.append(f"bm25: {exc}")
        results["bm25"] = f"error: {exc}"

    status = "errors" if errors else "ok"
    return {"status": status, "results": results, "errors": errors}


# ── Feature flags ─────────────────────────────────────────────────────────────

class FeatureFlagUpdate(BaseModel):
    enable_action_execution: bool | None = None
    force_human_approval: bool | None = None
    enable_web_search: bool | None = None
    enable_tracing: bool | None = None


@admin_router.get("/settings")
async def get_settings_endpoint(
    container: Container = Depends(get_container),
    _: User = Depends(require_admin),
) -> dict[str, Any]:
    """Get current feature flags and key settings."""
    s = container._settings
    return {
        "llm_provider": s.llm_provider,
        "embedding_provider": s.embedding_provider,
        "ehr_provider": s.ehr_provider,
        "enable_action_execution": s.enable_action_execution,
        "force_human_approval": s.force_human_approval,
        "enable_web_search": s.enable_web_search,
        "enable_tracing": s.enable_tracing,
        "confidence_threshold": s.confidence_threshold,
        "max_iterations": s.max_iterations,
    }


@admin_router.patch("/settings")
async def update_settings(
    body: FeatureFlagUpdate,
    container: Container = Depends(get_container),
    _: User = Depends(require_admin),
) -> dict[str, Any]:
    """Update feature flags in-memory (restart to make permanent)."""
    s = container._settings
    changed: dict[str, Any] = {}
    if body.enable_action_execution is not None:
        s.enable_action_execution = body.enable_action_execution
        changed["enable_action_execution"] = body.enable_action_execution
    if body.force_human_approval is not None:
        s.force_human_approval = body.force_human_approval
        changed["force_human_approval"] = body.force_human_approval
    if body.enable_web_search is not None:
        s.enable_web_search = body.enable_web_search
        changed["enable_web_search"] = body.enable_web_search
    if body.enable_tracing is not None:
        s.enable_tracing = body.enable_tracing
        changed["enable_tracing"] = body.enable_tracing
    logger.info("admin.settings_updated", changes=changed)
    return {"updated": changed, "note": "Changes are in-memory only; restart to revert"}


# ── File upload + async ingest ────────────────────────────────────────────────

@admin_router.post("/ingest/upload")
async def upload_and_ingest(
    request: Request,
    files: list[UploadFile] = File(...),
    container: Container = Depends(get_container),
    _: User = Depends(require_admin),
) -> dict[str, Any]:
    """
    Upload medical documents and start the Graph RAG ingestion pipeline.

    Returns immediately with a job_id.  Poll GET /admin/ingest/jobs/{job_id}
    to track per-step progress and logs.
    """
    store = container.pipeline_job_store

    # Save uploaded files
    job = await store.create_job([])   # placeholder; real names added below
    upload_dir = os.path.join(container._settings.upload_dir, job.job_id)
    os.makedirs(upload_dir, exist_ok=True)

    saved_files: list[str] = []
    for file in files:
        if not file.filename:
            continue
        dest = os.path.join(upload_dir, file.filename)
        content = await file.read()
        with open(dest, "wb") as fh:
            fh.write(content)
        saved_files.append(file.filename)

    if not saved_files:
        raise HTTPException(status_code=400, detail="No valid files uploaded")

    # Update file list on the job
    j = await store.get_job(job.job_id)
    if j:
        j["files"] = saved_files
        await store._persist(job.job_id, j)

    # Launch pipeline as a background task so we can return immediately
    asyncio.create_task(
        _run_pipeline_background(
            job_id=job.job_id,
            upload_dir=upload_dir,
            container=container,
        )
    )

    logger.info("admin.ingest_started", job_id=job.job_id, files=saved_files)
    return {"job_id": job.job_id, "files": saved_files, "status": "queued"}


async def _run_pipeline_background(
    *,
    job_id: str,
    upload_dir: str,
    container: Container,
) -> None:
    """Background coroutine — runs the pipeline and updates the job store."""
    store = container.pipeline_job_store
    await store.start_job(job_id)
    try:
        result = await run_full_pipeline(
            upload_dir,
            llm=container.llm,
            graph_db=container.graph_db,
            vector_store=container.vector_store,
            search_engine=container.search_engine,
            embedding_model=container.embedding_model,
            parent_chunk_size=container._settings.parent_chunk_size,
            child_chunk_size=container._settings.child_chunk_size,
            chunk_overlap=container._settings.chunk_overlap,
            job_store=store,
            job_id=job_id,
        )
        await store.finish_job(
            job_id,
            success=True,
            totals={
                "documents_loaded": result.documents_loaded,
                "parent_chunks": result.parent_chunks,
                "child_chunks": result.child_chunks,
                "entities_written": result.entities_written,
                "relationships_written": result.relationships_written,
                "communities_found": result.communities_found,
                "chunks_embedded": result.chunks_embedded,
                "errors": len(result.errors),
            },
        )
        logger.info("admin.ingest_complete", job_id=job_id)
    except Exception as exc:
        logger.error("admin.ingest_failed", job_id=job_id, error=str(exc))
        await store.finish_job(job_id, success=False, error=str(exc))


# ── Pipeline job status ───────────────────────────────────────────────────────

@admin_router.get("/ingest/jobs")
async def list_ingest_jobs(
    limit: int = 20,
    container: Container = Depends(get_container),
    _: User = Depends(require_admin),
) -> dict[str, Any]:
    """List recent ingestion pipeline jobs (newest first)."""
    jobs = await container.pipeline_job_store.list_jobs(limit=limit)
    # Return a summary (omit per-step logs for list view)
    summaries = [_job_summary(j) for j in jobs]
    return {"jobs": summaries, "total": len(summaries)}


@admin_router.get("/ingest/jobs/{job_id}")
async def get_ingest_job(
    job_id: str,
    container: Container = Depends(get_container),
    _: User = Depends(require_admin),
) -> dict[str, Any]:
    """Get full job details including per-step logs."""
    job = await container.pipeline_job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return job


def _job_summary(job: dict) -> dict[str, Any]:
    """Compact summary without per-step log lists (for the job list view)."""
    steps_summary = [
        {
            "name": s["name"],
            "display_name": s["display_name"],
            "status": s["status"],
            "duration_ms": s.get("duration_ms"),
            "counts": s.get("counts", {}),
        }
        for s in job.get("steps", [])
    ]
    return {
        "job_id": job["job_id"],
        "files": job.get("files", []),
        "status": job["status"],
        "created_at": job.get("created_at"),
        "started_at": job.get("started_at"),
        "finished_at": job.get("finished_at"),
        "error": job.get("error"),
        "totals": job.get("totals", {}),
        "steps": steps_summary,
    }
