"""
Human approval node — uses LangGraph interrupt() to pause execution
and wait for a clinician to approve or reject proposed actions.
"""
from __future__ import annotations

import structlog
from langgraph.types import interrupt

from medical_ais.agent.state import MedicalAgentState, ProposedAction

logger = structlog.get_logger(__name__)


async def human_approval_node(state: MedicalAgentState, *, approval_store=None) -> dict:
    """
    Interrupt the graph and present proposed actions for human review.

    When the graph is resumed, the human's response populates state.human_feedback.
    Approved actions move to state.approved_actions.
    Rejected actions are dropped.
    """
    proposed = state.get("proposed_actions", [])
    if not proposed:
        return {"approved_actions": [], "human_feedback": None}

    # Build a human-readable summary for the approval UI
    action_summary = "\n".join(
        f"[{i+1}] TIER {a['tier']} — {a['tool_name']}: {a['rationale']}"
        for i, a in enumerate(proposed)
    )

    # Write to approval store BEFORE interrupt so the UI can show it immediately
    if approval_store is not None:
        try:
            await approval_store.save(
                session_id=state.get("session_id", ""),
                proposed_actions=[dict(a) for a in proposed],
                message=(
                    "The following clinical actions require your review and approval:\n\n"
                    + action_summary
                ),
            )
        except Exception as exc:
            logger.warning("human_approval.store_save_failed", error=str(exc))

    # LangGraph interrupt: pauses execution here and returns control to the caller.
    # The caller (API layer) must resume the graph with human feedback.
    human_response = interrupt({
        "type": "human_approval_required",
        "message": (
            "The following clinical actions require your review and approval:\n\n"
            + action_summary
        ),
        "proposed_actions": [dict(a) for a in proposed],
        "session_id": state.get("session_id"),
    })

    # After resume: human_response is the feedback dict returned by the caller
    approved_indices: list[int] = []
    feedback = ""

    if isinstance(human_response, dict):
        approved_indices = human_response.get("approved_indices", list(range(len(proposed))))
        feedback = human_response.get("feedback", "Approved")
    elif human_response is True:
        # Shorthand: approve all
        approved_indices = list(range(len(proposed)))
        feedback = "All approved"

    approved_actions = [proposed[i] for i in approved_indices if i < len(proposed)]

    logger.info(
        "human_approval.done",
        proposed=len(proposed),
        approved=len(approved_actions),
        session_id=state.get("session_id"),
    )

    return {
        "approved_actions": approved_actions,
        "human_feedback": feedback,
        "requires_human_approval": False,
    }
