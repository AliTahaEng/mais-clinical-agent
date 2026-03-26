"""
Audit logger node — records every agent action in the append-only audit trail.
Stores a rich execution trace so the admin can see exactly what happened at each step.
"""
from __future__ import annotations

from datetime import datetime

import structlog

from medical_ais.agent.state import MedicalAgentState
from medical_ais.interfaces.audit import AuditRecord, IAuditStore

logger = structlog.get_logger(__name__)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _build_retrieval_breakdown(chunks: list) -> dict:
    """Count retrieved chunks by source type."""
    breakdown: dict[str, int] = {}
    for c in chunks:
        src = c.get("source", "unknown")
        breakdown[src] = breakdown.get(src, 0) + 1
    return breakdown


def _build_sources_preview(chunks: list, limit: int = 15) -> list:
    """Build a list of source previews stored in the audit record."""
    previews = []
    for i, c in enumerate(chunks[:limit]):
        meta = c.get("metadata") or {}
        previews.append({
            "index": i + 1,
            "source_type": c.get("source", "unknown"),
            "score": round(float(c.get("score", 0.0)), 3),
            "text_preview": (c.get("text") or "")[:400],
            "filename": meta.get("filename") or meta.get("doc_id") or meta.get("entity"),
            "url": meta.get("url"),
        })
    return previews


def _build_execution_trace(state: MedicalAgentState) -> list:
    """
    Build a step-by-step execution trace from the final state.
    Since the audit logger runs last, the full state is available.
    Each step describes which node ran and what it produced.
    """
    chunks = state.get("retrieved_chunks", [])
    breakdown = _build_retrieval_breakdown(chunks)
    graph_local_n  = breakdown.get("graph_local", 0)
    graph_global_n = breakdown.get("graph_global", 0)
    hybrid_n       = breakdown.get("hybrid", 0)
    web_n          = breakdown.get("web", 0)

    steps = []

    # 1. Supervisor — query planning
    sub_queries = state.get("sub_queries", [])
    steps.append({
        "node": "supervisor",
        "label": "Query Planning",
        "icon": "🧭",
        "status": "done",
        "detail": state.get("current_plan") or "No plan recorded.",
        "sub_queries": sub_queries,
        "iterations": state.get("iteration", 0),
    })

    # 2. Local graph search — entity lookup in Neo4j
    steps.append({
        "node": "local_graph_search",
        "label": "Knowledge Graph — Entity Search",
        "icon": "🧠",
        "status": "done" if graph_local_n > 0 else "empty",
        "detail": (
            f"{graph_local_n} entity context(s) retrieved from Neo4j."
            if graph_local_n
            else "No matching entities found in the knowledge graph."
        ),
        "chunks": graph_local_n,
    })

    # 3. Global graph search — community context
    steps.append({
        "node": "global_graph_search",
        "label": "Knowledge Graph — Community Search",
        "icon": "🕸️",
        "status": "done" if graph_global_n > 0 else "empty",
        "detail": (
            f"{graph_global_n} community context(s) retrieved from Neo4j."
            if graph_global_n
            else "No matching medical community found."
        ),
        "chunks": graph_global_n,
    })

    # 4. Hybrid search — vector + BM25 over documents
    steps.append({
        "node": "hybrid_search",
        "label": "Document Search (Vector + BM25 + Reranking)",
        "icon": "📄",
        "status": "done" if hybrid_n > 0 else "empty",
        "detail": (
            f"{hybrid_n} document chunk(s) retrieved via semantic + keyword fusion."
            if hybrid_n
            else "No document chunks retrieved (documents may not be ingested yet)."
        ),
        "chunks": hybrid_n,
    })

    # 5. Quality checker — CRAG score
    quality = state.get("retrieval_quality", 0.0)
    web_triggered = web_n > 0
    steps.append({
        "node": "quality_checker",
        "label": "Retrieval Quality Check (CRAG)",
        "icon": "🔍",
        "status": "done",
        "detail": (
            f"Quality score: {quality:.0%}. "
            + ("Web search triggered as fallback." if web_triggered
               else "Quality sufficient — no web fallback needed.")
        ),
        "score": quality,
        "web_triggered": web_triggered,
    })

    # 6. Web search — only if triggered
    if web_triggered:
        steps.append({
            "node": "web_search",
            "label": "Web Search Fallback",
            "icon": "🌐",
            "status": "done",
            "detail": f"{web_n} result(s) retrieved from medical web sources (PubMed, Medscape, UpToDate).",
            "chunks": web_n,
        })

    # 7. Answer synthesis
    answer = state.get("final_answer", "")
    steps.append({
        "node": "synthesizer",
        "label": "Answer Synthesis",
        "icon": "✍️",
        "status": "done",
        "detail": (
            f"Answer generated ({len(answer)} chars) from {len(chunks)} context chunks "
            f"(graph: {graph_local_n + graph_global_n}, docs: {hybrid_n}, web: {web_n})."
        ),
        "total_chunks": len(chunks),
        "answer_length": len(answer),
    })

    # 8. Fact check — Self-RAG
    fact_passed = state.get("fact_check_passed", True)
    issues = state.get("fact_check_issues", [])
    steps.append({
        "node": "self_critic",
        "label": "Fact Check (Self-RAG)",
        "icon": "✅" if fact_passed else "⚠️",
        "status": "passed" if fact_passed else "failed",
        "detail": (
            "All claims verified against retrieved sources."
            if fact_passed
            else f"{len(issues)} issue(s) found: {'; '.join(issues[:3])}"
        ),
        "passed": fact_passed,
        "issues": issues,
    })

    # 9. Decision engine
    proposed  = state.get("proposed_actions", [])
    executed  = state.get("executed_actions", [])
    escalated = state.get("escalated", False)
    requires_approval = state.get("requires_human_approval", False)
    steps.append({
        "node": "decision_engine",
        "label": "Clinical Decision Engine",
        "icon": "⚕️",
        "status": "done",
        "detail": (
            "Escalated to senior clinical review."
            if escalated
            else f"{len(proposed)} action(s) proposed, {len(executed)} executed."
            if proposed
            else "No clinical actions required for this query."
        ),
        "actions_proposed": len(proposed),
        "actions_executed": len(executed),
        "escalated": escalated,
        "requires_approval": requires_approval,
    })

    return steps


# ── Main node ──────────────────────────────────────────────────────────────────

async def audit_logger_node(
    state: MedicalAgentState,
    *,
    audit_store: IAuditStore,
) -> dict:
    """
    Write a comprehensive audit record for this session's execution.
    Called at the end of every run — whether or not actions were taken.
    """
    executed = state.get("executed_actions", [])
    chunks   = state.get("retrieved_chunks", [])

    record = AuditRecord(
        event_type="session.completed",
        agent_id="mais_system",
        session_id=state.get("session_id", ""),
        user_id=state.get("user_id") or "",
        payload={
            # ── Core ──────────────────────────────────────────────────────────
            "query":      state.get("query", ""),
            "patient_id": state.get("patient_id"),
            "user_id":    state.get("user_id"),

            # ── Answer ────────────────────────────────────────────────────────
            "final_answer":    state.get("final_answer", ""),
            "confidence_score": state.get("confidence_score", 0.0),

            # ── Planning ──────────────────────────────────────────────────────
            "current_plan": state.get("current_plan", ""),
            "sub_queries":  state.get("sub_queries", []),
            "iterations":   state.get("iteration", 0),

            # ── Retrieval ─────────────────────────────────────────────────────
            "retrieval_quality":    state.get("retrieval_quality", 0.0),
            "chunks_retrieved":     len(chunks),
            "retrieval_breakdown":  _build_retrieval_breakdown(chunks),
            "sources_preview":      _build_sources_preview(chunks),
            "graph_context_used":   bool(state.get("graph_context")),
            "community_context_used": bool(state.get("community_context")),
            "web_search_used":      any(c.get("source") == "web" for c in chunks),

            # ── Quality & Fact Check ──────────────────────────────────────────
            "fact_check_passed": state.get("fact_check_passed", True),
            "fact_check_issues": state.get("fact_check_issues", []),

            # ── Actions ───────────────────────────────────────────────────────
            "actions_proposed":       len(state.get("proposed_actions", [])),
            "actions_executed":       len(executed),
            "escalated":              state.get("escalated", False),
            "requires_human_approval": state.get("requires_human_approval", False),

            # ── Full execution trace ──────────────────────────────────────────
            "execution_trace": _build_execution_trace(state),
        },
        timestamp=datetime.utcnow(),
        idempotency_key=f"session:{state.get('session_id', '')}:completed",
    )

    try:
        await audit_store.record(record)
        logger.info("audit_logger.recorded", session_id=record.session_id)
    except Exception as exc:
        logger.error("audit_logger.failed", error=str(exc))

    # Log each executed action separately
    for action in executed:
        action_record = AuditRecord(
            event_type="action.executed",
            agent_id="action_agent",
            session_id=state.get("session_id", ""),
            payload=action,
            timestamp=datetime.utcnow(),
            idempotency_key=f"action:{state.get('session_id', '')}:{action.get('tool', '')}",
        )
        try:
            await audit_store.record(action_record)
        except Exception:
            pass  # Best-effort for individual action records

    return {}  # Audit node doesn't modify state
