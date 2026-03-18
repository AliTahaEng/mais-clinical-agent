"""
SSE streaming endpoint — GET /query/stream
Streams step progress and token-by-token LLM output to the client.
"""
from __future__ import annotations

import asyncio
import uuid

import structlog
from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from medical_ais.agent.graph import run_query
from medical_ais.agent.state import MedicalAgentState
from medical_ais.api.auth import get_current_user
from medical_ais.api.sse_utils import astream_graph_events, format_sse, sse_heartbeat
from medical_ais.auth.models import User
from medical_ais.core.container import Container
from medical_ais.core.exceptions import InputValidationError
from medical_ais.security.input_sanitizer import sanitize_query
from fastapi import Depends
from langchain_core.messages import HumanMessage

logger = structlog.get_logger(__name__)

stream_router = APIRouter()


def get_container(request: Request) -> Container:
    return request.app.state.container


@stream_router.get("/query/stream")
async def stream_query(
    request: Request,
    q: str = Query(..., min_length=1, max_length=2000, description="Medical query"),
    patient_id: str | None = Query(None, max_length=64),
    session_id: str | None = Query(None, max_length=128),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """
    Stream a medical query response via Server-Sent Events.

    Events emitted:
      - step: node start/complete progress
      - token: individual LLM output tokens (during synthesis)
      - interrupt: graph paused for human approval
      - done: final answer + metadata
      - error: processing error
    """
    container: Container = get_container(request)

    try:
        sanitized = sanitize_query(q, patient_id, session_id)
    except InputValidationError as exc:
        async def error_gen():
            yield format_sse("error", {"message": str(exc)})
        return StreamingResponse(error_gen(), media_type="text/event-stream")

    sid = sanitized.session_id or str(uuid.uuid4())

    initial_state = MedicalAgentState(
        query=sanitized.query,
        patient_id=sanitized.patient_id,
        session_id=sid,
        messages=[HumanMessage(content=sanitized.query)],
        retrieved_chunks=[],
        graph_context="",
        community_context="",
        current_plan="",
        sub_queries=[],
        iteration=0,
        retrieval_quality=0.0,
        needs_web_search=False,
        draft_answer="",
        fact_check_passed=False,
        fact_check_issues=[],
        final_answer="",
        confidence_score=0.0,
        proposed_actions=[],
        approved_actions=[],
        executed_actions=[],
        requires_human_approval=False,
        human_feedback=None,
        error=None,
        escalated=False,
    )

    config = {"configurable": {"thread_id": sid}, "recursion_limit": 25}

    async def event_generator():
        heartbeat_interval = getattr(container._settings, "sse_heartbeat_interval", 15)
        last_heartbeat = asyncio.get_event_loop().time()

        async for sse_msg in astream_graph_events(
            container.compiled_graph,
            initial_state,
            config,
        ):
            # Check if client disconnected
            if await request.is_disconnected():
                logger.info("sse.client_disconnected", session_id=sid)
                return
            yield sse_msg

            # Send heartbeat if needed
            now = asyncio.get_event_loop().time()
            if now - last_heartbeat > heartbeat_interval:
                yield sse_heartbeat()
                last_heartbeat = now

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Session-ID": sid,
        },
    )
