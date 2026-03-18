"""
Mandatory escalation node for TIER_3 (critical/irreversible) actions.
These are never executed automatically — always routed to a senior clinician.
"""
from __future__ import annotations

import structlog
from langgraph.types import interrupt

from medical_ais.agent.state import MedicalAgentState
from medical_ais.interfaces.action_tool import ActionTier

logger = structlog.get_logger(__name__)


async def mandatory_escalation_node(state: MedicalAgentState) -> dict:
    """
    Escalate TIER_3 actions for mandatory senior clinician review.
    Uses interrupt() — never auto-executes these actions.
    """
    tier3_actions = [
        a for a in state.get("proposed_actions", [])
        if a["tier"] == ActionTier.TIER_3
    ]

    if not tier3_actions:
        return {"escalated": False}

    action_summary = "\n".join(
        f"- {a['tool_name']}: {a['rationale']}"
        for a in tier3_actions
    )

    logger.warning(
        "escalation.tier3_required",
        count=len(tier3_actions),
        session_id=state.get("session_id"),
    )

    # Always interrupt for TIER_3 — no auto-execution
    interrupt({
        "type": "mandatory_escalation",
        "urgency": "immediate",
        "message": (
            "CRITICAL: The following actions require MANDATORY senior clinician review. "
            "These actions cannot be executed automatically.\n\n" + action_summary
        ),
        "tier3_actions": [dict(a) for a in tier3_actions],
        "patient_id": state.get("patient_id"),
        "session_id": state.get("session_id"),
        "final_answer": state.get("final_answer", ""),
    })

    return {"escalated": True}
