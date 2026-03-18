"""
Approval management API routes.
  GET  /approvals          — list all pending approvals
  GET  /approvals/{sid}    — get a specific approval request
  POST /approvals/{sid}/decide — submit approval/rejection decision
"""
from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from langgraph.types import Command

from medical_ais.api.schemas import ApprovalDecisionRequest, ApprovalDecisionResponse, ApprovalListResponse, ApprovalDetailResponse
from medical_ais.core.container import Container

logger = structlog.get_logger(__name__)

approvals_router = APIRouter(prefix="/approvals", tags=["approvals"])


def get_container(request: Request) -> Container:
    return request.app.state.container


@approvals_router.get("", response_model=ApprovalListResponse)
async def list_approvals(
    container: Container = Depends(get_container),
) -> ApprovalListResponse:
    """List all pending approval requests."""
    items = await container.approval_store.list_pending()
    return ApprovalListResponse(items=items, total=len(items))


@approvals_router.get("/{session_id}", response_model=ApprovalDetailResponse)
async def get_approval(
    session_id: str,
    container: Container = Depends(get_container),
) -> ApprovalDetailResponse:
    """Get a specific approval request."""
    item = await container.approval_store.get(session_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval request not found")
    return ApprovalDetailResponse(**item)


@approvals_router.post("/{session_id}/decide", response_model=ApprovalDecisionResponse)
async def decide_approval(
    session_id: str,
    body: ApprovalDecisionRequest,
    container: Container = Depends(get_container),
) -> ApprovalDecisionResponse:
    """Submit approval or rejection decision, then resume the paused LangGraph."""
    # Mark as decided in the store
    await container.approval_store.mark_decided(
        session_id=session_id,
        approved_indices=body.approved_indices,
        feedback=body.feedback,
    )

    # Resume the paused LangGraph with the human decision
    config = {"configurable": {"thread_id": session_id}}
    human_response = {
        "approved_indices": body.approved_indices,
        "feedback": body.feedback,
    }

    try:
        final_state = await container.compiled_graph.ainvoke(
            Command(resume=human_response),
            config=config,
        )
    except Exception as exc:
        logger.error("approval.resume_failed", session_id=session_id, error=str(exc))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

    # Clean up approval store after successful resume
    await container.approval_store.delete(session_id)

    return ApprovalDecisionResponse(
        session_id=session_id,
        approved_count=len(body.approved_indices),
        executed_count=len(final_state.get("executed_actions", [])),
        status="complete",
    )
