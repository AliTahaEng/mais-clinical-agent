"""
FastAPI route handlers.
Thin layer: validate → call graph → return response.
"""
from __future__ import annotations

import uuid
from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status

from medical_ais.agent.graph import run_query
from medical_ais.api.auth import get_current_user
from medical_ais.api.schemas import (
    ApprovalRequest,
    ApprovalResponse,
    HealthResponse,
    IngestRequest,
    IngestResponse,
    QueryRequest,
    QueryResponse,
)
from medical_ais.auth.models import User
from medical_ais.core.container import Container
from medical_ais.core.exceptions import (
    CircuitBreakerOpenError,
    InputValidationError,
    ServiceUnavailableError,
)
from medical_ais.pipeline.runner import run_full_pipeline
from medical_ais.security.input_sanitizer import sanitize_query

logger = structlog.get_logger(__name__)

router = APIRouter()


def get_container(request: Request) -> Container:
    return request.app.state.container


# ── Query endpoint ────────────────────────────────────────────────────────────

@router.post("/query", response_model=QueryResponse)
async def query_endpoint(
    body: QueryRequest,
    container: Container = Depends(get_container),
    current_user: User = Depends(get_current_user),
) -> QueryResponse:
    """Submit a medical query for processing."""
    try:
        sanitized = sanitize_query(body.query, body.patient_id, body.session_id)
    except InputValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    session_id = sanitized.session_id or str(uuid.uuid4())

    try:
        final_state = await run_query(
            container.compiled_graph,
            sanitized.query,
            patient_id=sanitized.patient_id,
            session_id=session_id,
            user_id=current_user.id,
        )
    except CircuitBreakerOpenError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except ServiceUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except Exception as exc:
        logger.error("query.failed", session_id=session_id, error=str(exc))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Query processing failed")

    # Determine status
    if final_state.get("escalated"):
        api_status = "escalated"
    elif final_state.get("requires_human_approval"):
        api_status = "awaiting_approval"
    elif final_state.get("error"):
        api_status = "error"
    else:
        api_status = "complete"

    return QueryResponse(
        session_id=session_id,
        answer=final_state.get("final_answer", ""),
        confidence_score=final_state.get("confidence_score", 0.0),
        fact_check_passed=final_state.get("fact_check_passed", True),
        retrieval_quality=final_state.get("retrieval_quality", 0.0),
        chunks_used=len(final_state.get("retrieved_chunks", [])),
        actions_proposed=len(final_state.get("proposed_actions", [])),
        actions_executed=len(final_state.get("executed_actions", [])),
        requires_human_approval=final_state.get("requires_human_approval", False),
        status=api_status,
    )


# ── Approval endpoint ─────────────────────────────────────────────────────────

@router.post("/approve", response_model=ApprovalResponse)
async def approve_endpoint(
    body: ApprovalRequest,
    container: Container = Depends(get_container),
) -> ApprovalResponse:
    """Resume a paused graph with human approval decision."""
    config = {"configurable": {"thread_id": body.session_id}}
    human_response = {
        "approved_indices": body.approved_indices,
        "feedback": body.feedback,
    }

    try:
        final_state = await container.compiled_graph.ainvoke(
            human_response,
            config=config,
        )
    except Exception as exc:
        logger.error("approve.failed", session_id=body.session_id, error=str(exc))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

    return ApprovalResponse(
        session_id=body.session_id,
        approved_count=len(body.approved_indices),
        executed_count=len(final_state.get("executed_actions", [])),
        status="complete",
    )


# ── Ingest endpoint ───────────────────────────────────────────────────────────

@router.post("/ingest", response_model=IngestResponse)
async def ingest_endpoint(
    body: IngestRequest,
    container: Container = Depends(get_container),
) -> IngestResponse:
    """Trigger the document ingestion pipeline."""
    docs_dir = body.documents_dir or container._settings.documents_dir

    try:
        result = await run_full_pipeline(
            docs_dir,
            llm=container.llm,
            graph_db=container.graph_db,
            vector_store=container.vector_store,
            search_engine=container.search_engine,
            embedding_model=container.embedding_model,
            parent_chunk_size=container._settings.parent_chunk_size,
            child_chunk_size=container._settings.child_chunk_size,
            chunk_overlap=container._settings.chunk_overlap,
        )
    except Exception as exc:
        logger.error("ingest.failed", error=str(exc))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

    return IngestResponse(
        status="complete",
        documents_loaded=result.documents_loaded,
        entities_written=result.entities_written,
        relationships_written=result.relationships_written,
        communities_found=result.communities_found,
        chunks_embedded=result.chunks_embedded,
        errors=result.errors,
    )


# ── Health endpoint ───────────────────────────────────────────────────────────

@router.get("/health", response_model=HealthResponse)
async def health_endpoint(
    container: Container = Depends(get_container),
) -> HealthResponse:
    """Check health of all external services."""
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
    overall = "healthy" if all_healthy else "degraded"

    return HealthResponse(
        status=overall,
        timestamp=datetime.utcnow(),
        services=services,
    )
