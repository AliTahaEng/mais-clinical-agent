"""
Pipeline Job Store — tracks real-time progress of ingestion pipeline runs.

Each job has 8 steps. As the pipeline runs it calls:
    store.start_step(job_id, step_name)
    store.add_log(job_id, step_name, level, message, data)
    store.complete_step(job_id, step_name, counts)
    store.fail_step(job_id, step_name, error)
    store.finish_job(job_id, success, totals, error)

Backed by Redis (24-hour TTL). Falls back to an in-memory dict.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# ── Step registry — defines order and display names ──────────────────────────

PIPELINE_STEPS: list[tuple[str, str]] = [
    ("step1_ingestion",               "Document Ingestion"),
    ("step2_chunking",                "Parent-Child Chunking"),
    ("step3_4_extraction",            "Entity & Relationship Extraction"),
    ("step5_resolution",              "Entity Resolution"),
    ("step6_graph_storage",           "Graph Storage (Neo4j)"),
    ("step7_community_detection",     "Community Detection"),
    ("step8_community_summarisation", "Community Summarisation"),
    ("step9_10_embedding_indexing",   "Embedding + BM25 Indexing"),
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Data models ───────────────────────────────────────────────────────────────

@dataclass
class PipelineStepResult:
    name: str
    display_name: str
    status: str = "pending"          # pending | running | completed | failed | skipped
    started_at: str | None = None
    finished_at: str | None = None
    duration_ms: int | None = None
    counts: dict[str, Any] = field(default_factory=dict)
    logs: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class PipelineJob:
    job_id: str
    files: list[str]
    status: str                      # queued | running | completed | failed
    steps: list[dict[str, Any]]      # serialised PipelineStepResult dicts
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None
    totals: dict[str, Any] = field(default_factory=dict)


# ── Store ─────────────────────────────────────────────────────────────────────

class PipelineJobStore:
    """Persists pipeline job progress in Redis with in-memory fallback."""

    _JOB_TTL   = 86_400          # 24 h
    _INDEX_KEY = "pipeline_jobs:index"

    def __init__(self, cache: Any) -> None:
        self._cache = cache
        self._mem: dict[str, dict] = {}   # fallback when Redis unavailable

    # ── Public API ────────────────────────────────────────────────────────────

    async def create_job(self, files: list[str]) -> PipelineJob:
        job_id = str(uuid.uuid4())
        steps = [
            asdict(PipelineStepResult(name=n, display_name=d))
            for n, d in PIPELINE_STEPS
        ]
        job = PipelineJob(
            job_id=job_id,
            files=files,
            status="queued",
            steps=steps,
            created_at=_now(),
        )
        await self._persist(job.job_id, asdict(job))
        return job

    async def start_job(self, job_id: str) -> None:
        j = await self._load(job_id)
        if j:
            j["status"] = "running"
            j["started_at"] = _now()
            await self._persist(job_id, j)

    async def start_step(self, job_id: str, step_name: str) -> None:
        j = await self._load(job_id)
        if not j:
            return
        for s in j["steps"]:
            if s["name"] == step_name:
                s["status"] = "running"
                s["started_at"] = _now()
                break
        await self._persist(job_id, j)

    async def complete_step(
        self,
        job_id: str,
        step_name: str,
        counts: dict[str, Any] | None = None,
        skipped: bool = False,
    ) -> None:
        j = await self._load(job_id)
        if not j:
            return
        for s in j["steps"]:
            if s["name"] == step_name:
                s["status"] = "skipped" if skipped else "completed"
                s["finished_at"] = _now()
                if s["started_at"]:
                    s["duration_ms"] = _ms(s["started_at"], s["finished_at"])
                if counts:
                    s["counts"] = counts
                break
        await self._persist(job_id, j)

    async def fail_step(self, job_id: str, step_name: str, error: str) -> None:
        j = await self._load(job_id)
        if not j:
            return
        for s in j["steps"]:
            if s["name"] == step_name:
                s["status"] = "failed"
                s["finished_at"] = _now()
                if s["started_at"]:
                    s["duration_ms"] = _ms(s["started_at"], s["finished_at"])
                s["logs"].append(_log_entry("error", error))
                break
        await self._persist(job_id, j)

    async def add_log(
        self,
        job_id: str,
        step_name: str,
        level: str,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        j = await self._load(job_id)
        if not j:
            return
        entry = _log_entry(level, message, data)
        for s in j["steps"]:
            if s["name"] == step_name:
                s["logs"].append(entry)
                break
        await self._persist(job_id, j)

    async def finish_job(
        self,
        job_id: str,
        success: bool,
        totals: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        j = await self._load(job_id)
        if not j:
            return
        j["status"] = "completed" if success else "failed"
        j["finished_at"] = _now()
        if totals:
            j["totals"] = totals
        if error:
            j["error"] = error
        await self._persist(job_id, j)

    async def get_job(self, job_id: str) -> dict | None:
        return await self._load(job_id)

    async def list_jobs(self, limit: int = 20) -> list[dict]:
        """Return recent jobs newest-first."""
        try:
            client = getattr(self._cache, "_client", None)
            if client:
                ids = await client.lrange(self._INDEX_KEY, 0, limit - 1)
                jobs: list[dict] = []
                for raw_id in ids:
                    jid = raw_id if isinstance(raw_id, str) else raw_id.decode()
                    j = await self._load(jid)
                    if j:
                        jobs.append(j)
                return jobs
        except Exception:
            pass
        # in-memory fallback
        all_jobs = sorted(
            self._mem.values(),
            key=lambda j: j.get("created_at", ""),
            reverse=True,
        )
        return all_jobs[:limit]

    # ── Private helpers ───────────────────────────────────────────────────────

    async def _persist(self, job_id: str, data: dict) -> None:
        try:
            client = getattr(self._cache, "_client", None)
            if client:
                await client.setex(
                    f"pipeline_job:{job_id}",
                    self._JOB_TTL,
                    json.dumps(data, default=str),
                )
                # keep a sorted index (LPUSH = newest first, capped at 100)
                await client.lrem(self._INDEX_KEY, 0, job_id)
                await client.lpush(self._INDEX_KEY, job_id)
                await client.ltrim(self._INDEX_KEY, 0, 99)
                return
        except Exception as exc:
            logger.warning("pipeline_job_store.redis_write_failed", error=str(exc))
        self._mem[job_id] = data

    async def _load(self, job_id: str) -> dict | None:
        try:
            client = getattr(self._cache, "_client", None)
            if client:
                raw = await client.get(f"pipeline_job:{job_id}")
                return json.loads(raw) if raw else None
        except Exception:
            pass
        return self._mem.get(job_id)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _log_entry(
    level: str,
    message: str,
    data: dict | None = None,
) -> dict[str, Any]:
    return {"timestamp": _now(), "level": level, "message": message, "data": data or {}}


def _ms(start_iso: str, end_iso: str) -> int:
    start = datetime.fromisoformat(start_iso)
    end   = datetime.fromisoformat(end_iso)
    return int((end - start).total_seconds() * 1000)
