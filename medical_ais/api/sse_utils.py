"""
SSE (Server-Sent Events) utilities.
Formats events as spec-compliant SSE messages and wraps LangGraph astream_events.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator

import structlog

logger = structlog.get_logger(__name__)

# ── SSE formatting ─────────────────────────────────────────────────────────────

def format_sse(event: str, data: Any) -> str:
    """
    Format a single SSE message.

    event: event name (e.g. "step", "token", "interrupt", "done", "error")
    data: JSON-serialisable payload
    """
    payload = json.dumps(data, default=str)
    return f"event: {event}\ndata: {payload}\n\n"


def sse_heartbeat() -> str:
    """SSE comment (keepalive ping, no-op on client side)."""
    return ": heartbeat\n\n"


# ── LangGraph event → SSE mapping ─────────────────────────────────────────────

# Map LangGraph node names to human-readable step labels
_NODE_LABELS: dict[str, str] = {
    "supervisor": "Planning query decomposition",
    "local_graph_search": "Searching knowledge graph (local)",
    "global_graph_search": "Searching knowledge graph (global)",
    "hybrid_search": "Searching medical literature",
    "web_search": "Searching the web for latest information",
    "quality_checker": "Evaluating retrieval quality",
    "synthesizer": "Synthesizing answer",
    "self_critic": "Fact-checking answer",
    "decision_engine": "Evaluating recommended actions",
    "human_approval": "Waiting for clinician approval",
    "mandatory_escalation": "Escalating to senior clinician",
    "action_executor": "Executing approved actions",
    "audit_logger": "Recording audit log",
    "feedback": "Recording feedback",
}


async def astream_graph_events(
    compiled_graph,
    initial_state: dict,
    config: dict,
    token_queue: asyncio.Queue | None = None,
) -> AsyncIterator[str]:
    """
    Drive a compiled LangGraph graph with astream_events and yield SSE strings.

    Emits:
      event: step  — when a node starts (on_chain_start)
      event: token — individual LLM output token (via token_queue or on_chat_model_stream)
      event: interrupt — graph paused for human approval
      event: done  — graph completed (final answer + metadata)
      event: error — processing error
    """
    final_state: dict = {}
    interrupted = False

    try:
        async for lg_event in compiled_graph.astream_events(
            initial_state, config=config, version="v2"
        ):
            kind = lg_event.get("event", "")
            name = lg_event.get("name", "")

            # ── Node started ──────────────────────────────────────────────────
            if kind == "on_chain_start" and name in _NODE_LABELS:
                yield format_sse("step", {
                    "node": name,
                    "label": _NODE_LABELS[name],
                    "status": "running",
                })

            # ── Node completed — capture final state ─────────────────────────
            elif kind == "on_chain_end" and name in _NODE_LABELS:
                output = lg_event.get("data", {}).get("output", {})
                if isinstance(output, dict):
                    final_state.update(output)

                yield format_sse("step", {
                    "node": name,
                    "label": _NODE_LABELS[name],
                    "status": "done",
                })

                # Detect interrupt after human_approval node fires on_chain_end
                if name == "human_approval" and output.get("requires_human_approval"):
                    interrupted = True

            # ── LLM token streaming ───────────────────────────────────────────
            elif kind == "on_chat_model_stream":
                chunk = lg_event.get("data", {}).get("chunk")
                if chunk:
                    token = ""
                    # LangChain AIMessageChunk
                    if hasattr(chunk, "content") and isinstance(chunk.content, str):
                        token = chunk.content
                    elif isinstance(chunk, str):
                        token = chunk
                    if token:
                        yield format_sse("token", {"token": token})

            # ── Drain token_queue if provided (synthesizer puts tokens here) ──
            if token_queue is not None:
                while not token_queue.empty():
                    token = token_queue.get_nowait()
                    if token is None:
                        break
                    yield format_sse("token", {"token": token})

    except Exception as exc:
        logger.error("sse.graph_stream_error", error=str(exc))
        yield format_sse("error", {"message": str(exc)})
        return

    # ── Interrupted: emit interrupt event ────────────────────────────────────
    if interrupted or final_state.get("requires_human_approval"):
        proposed = final_state.get("proposed_actions", [])
        yield format_sse("interrupt", {
            "session_id": final_state.get("session_id", ""),
            "message": "Clinician approval required for proposed actions",
            "proposed_actions": [dict(a) for a in proposed],
        })
        return

    # ── Completed: emit done event ────────────────────────────────────────────
    chunks = final_state.get("retrieved_chunks", [])

    # Build source list — one entry per chunk sent to the synthesizer (max 15)
    sources = []
    for i, c in enumerate(chunks[:15]):
        meta = c.get("metadata") or {}
        sources.append({
            "index": i + 1,
            "source_type": c.get("source", "unknown"),
            "score": round(float(c.get("score", 0.0)), 3),
            "text_preview": (c.get("text") or "")[:300],
            "url": meta.get("url"),
            "filename": meta.get("filename") or meta.get("doc_id"),
        })

    yield format_sse("done", {
        "session_id": final_state.get("session_id", ""),
        "answer": final_state.get("final_answer", ""),
        "confidence_score": final_state.get("confidence_score", 0.0),
        "fact_check_passed": final_state.get("fact_check_passed", True),
        "retrieval_quality": final_state.get("retrieval_quality", 0.0),
        "chunks_used": len(chunks),
        "actions_proposed": len(final_state.get("proposed_actions", [])),
        "actions_executed": len(final_state.get("executed_actions", [])),
        "requires_human_approval": final_state.get("requires_human_approval", False),
        "escalated": final_state.get("escalated", False),
        "sources": sources,
        "web_search_used": any(c.get("source") == "web" for c in chunks),
    })
