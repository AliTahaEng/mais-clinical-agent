"""
CRAG (Corrective RAG) quality checker node.
Assesses retrieval quality and decides whether to re-retrieve or fall back to web.
"""
from __future__ import annotations

import structlog

from medical_ais.agent.prompts.quality_check_prompt import (
    QUALITY_CHECK_HUMAN,
    QUALITY_CHECK_SYSTEM,
)
from medical_ais.agent.state import MedicalAgentState
from medical_ais.interfaces.llm import ILLMProvider, LLMMessage

logger = structlog.get_logger(__name__)

_MIN_QUALITY_THRESHOLD = 0.5


async def quality_checker_node(
    state: MedicalAgentState,
    *,
    llm: ILLMProvider,
) -> dict:
    """
    Evaluate retrieval quality.
    Returns: retrieval_quality score + needs_web_search flag.
    """
    chunks = state.get("retrieved_chunks", [])
    if not chunks:
        logger.warning("quality_checker.no_chunks")
        return {
            "retrieval_quality": 0.0,
            "needs_web_search": True,
        }

    retrieved_text = "\n\n".join(
        f"[{i+1}] {c['text'][:300]}" for i, c in enumerate(chunks[:10])
    )

    messages = [
        LLMMessage(role="system", content=QUALITY_CHECK_SYSTEM),
        LLMMessage(
            role="human",
            content=QUALITY_CHECK_HUMAN.format(
                query=state["query"],
                retrieved_docs=retrieved_text,
            ),
        ),
    ]

    try:
        result = await llm.complete_json(messages, temperature=0.0, max_tokens=512)
    except Exception as exc:
        logger.error("quality_checker.llm_error", error=str(exc))
        return {"retrieval_quality": 0.5, "needs_web_search": False}

    score = float(result.get("relevance_score", 0.5))
    needs_web = result.get("needs_web_search", score < _MIN_QUALITY_THRESHOLD)

    logger.info(
        "quality_checker.done",
        score=score,
        needs_web=needs_web,
        session_id=state.get("session_id"),
    )

    return {
        "retrieval_quality": score,
        "needs_web_search": needs_web,
    }
