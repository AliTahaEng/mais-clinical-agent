"""
Supervisor node — orchestrates the retrieval plan.
LangGraph node: reads state, calls LLM, returns state patch.
"""
from __future__ import annotations

import structlog
from langchain_core.messages import AIMessage

from medical_ais.agent.prompts.supervisor_prompt import SUPERVISOR_HUMAN, SUPERVISOR_SYSTEM
from medical_ais.agent.state import MedicalAgentState
from medical_ais.core.exceptions import MaxIterationsExceededError
from medical_ais.interfaces.llm import ILLMProvider, LLMMessage

logger = structlog.get_logger(__name__)


async def supervisor_node(
    state: MedicalAgentState,
    *,
    llm: ILLMProvider,
    max_iterations: int = 5,
) -> dict:
    """
    Analyse the query and produce a structured retrieval plan.
    Returns state patches only — does not mutate state directly.
    """
    iteration = state.get("iteration", 0)
    if iteration >= max_iterations:
        raise MaxIterationsExceededError(max_iterations)

    messages = [
        LLMMessage(role="system", content=SUPERVISOR_SYSTEM),
        LLMMessage(
            role="human",
            content=SUPERVISOR_HUMAN.format(
                query=state["query"],
                patient_id=state.get("patient_id") or "None",
                iteration=iteration,
                retrieval_quality=state.get("retrieval_quality", -1.0),
            ),
        ),
    ]

    try:
        result = await llm.complete_json(messages, temperature=0.0)
    except Exception as exc:
        logger.error("supervisor.llm_error", error=str(exc))
        return {
            "error": f"Supervisor LLM error: {exc}",
            "current_plan": "fallback: hybrid search only",
            "sub_queries": [state["query"]],
            "iteration": iteration + 1,
        }

    plan = result.get("plan", "hybrid search")
    sub_queries = result.get("sub_queries", [state["query"]])
    if not sub_queries:
        sub_queries = [state["query"]]

    logger.info(
        "supervisor.planned",
        session_id=state.get("session_id"),
        plan=plan,
        sub_queries=len(sub_queries),
        iteration=iteration,
    )

    return {
        "current_plan": plan,
        "sub_queries": sub_queries,
        "iteration": iteration + 1,
        "needs_web_search": result.get("requires_web_search", False),
        "messages": [AIMessage(content=f"Plan: {plan}")],
    }
