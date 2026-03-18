"""
LangGraph routing functions — pure functions that return node names or END.
All conditional edges in the graph use functions from this module.
"""
from __future__ import annotations

from langgraph.graph import END

from medical_ais.agent.state import MedicalAgentState


def route_after_quality_check(state: MedicalAgentState) -> str:
    """
    CRAG routing:
    - If web search needed → web_search
    - If quality is poor AND more iterations available → supervisor (retry)
    - Otherwise → synthesizer
    """
    max_iterations = 5  # matches settings default; could be injected

    needs_web = state.get("needs_web_search", False)
    quality = state.get("retrieval_quality", 0.5)
    iteration = state.get("iteration", 0)
    error = state.get("error")

    if error:
        return "audit_logger"

    if needs_web:
        return "web_search"

    # Re-route to supervisor if quality is poor and we haven't exceeded iterations
    if quality < 0.5 and iteration < max_iterations:
        return "supervisor"

    return "synthesizer"


def route_after_self_critic(state: MedicalAgentState) -> str:
    """
    Self-RAG routing:
    - If fact check failed AND iterations available → re-retrieve (supervisor)
    - Otherwise → decision_engine
    """
    max_iterations = 5
    passed = state.get("fact_check_passed", True)
    iteration = state.get("iteration", 0)

    if not passed and iteration < max_iterations:
        return "supervisor"

    return "decision_engine"


def route_after_decision_engine(state: MedicalAgentState) -> str:
    """
    Action routing:
    - TIER_3 present → mandatory_escalation
    - TIER_2 or force_human → human_approval
    - TIER_1 only (or no actions) → action_executor
    - No actions → audit_logger
    """
    escalated = state.get("escalated", False)
    requires_human = state.get("requires_human_approval", False)
    proposed = state.get("proposed_actions", [])

    if not proposed:
        return "audit_logger"

    if escalated:
        return "mandatory_escalation"

    if requires_human:
        return "human_approval"

    return "action_executor"


def route_after_human_approval(state: MedicalAgentState) -> str:
    """After human review: execute approved actions or skip to audit."""
    approved = state.get("approved_actions", [])
    if approved:
        return "action_executor"
    return "audit_logger"


def route_after_action_executor(state: MedicalAgentState) -> str:
    """After execution: check for human feedback, then audit."""
    feedback = state.get("human_feedback")
    if feedback:
        return "feedback"
    return "audit_logger"
