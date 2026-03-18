"""
Feedback node — processes human feedback after action approval.
Updates the message history for conversational continuity.
"""
from __future__ import annotations

import structlog
from langchain_core.messages import HumanMessage

from medical_ais.agent.state import MedicalAgentState

logger = structlog.get_logger(__name__)


async def feedback_node(state: MedicalAgentState) -> dict:
    """
    Incorporate human feedback into the conversation history.
    Called after human_approval_node when feedback is provided.
    """
    feedback = state.get("human_feedback")
    if not feedback:
        return {}

    logger.info("feedback.received", feedback_len=len(feedback))

    executed = state.get("executed_actions", [])
    action_summary = (
        f"Executed {len(executed)} action(s)." if executed else "No actions executed."
    )

    return {
        "messages": [
            HumanMessage(content=f"[Human feedback]: {feedback}"),
        ],
        "final_answer": (
            state.get("final_answer", "")
            + f"\n\n---\n*{action_summary} Feedback: {feedback}*"
        ),
    }
