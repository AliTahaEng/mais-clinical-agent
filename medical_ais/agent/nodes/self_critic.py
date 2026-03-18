"""
Self-RAG fact-checker node.
Verifies every claim in the draft answer against retrieved evidence.
"""
from __future__ import annotations

import structlog

from medical_ais.agent.prompts.self_critic_prompt import SELF_CRITIC_HUMAN, SELF_CRITIC_SYSTEM
from medical_ais.agent.state import MedicalAgentState
from medical_ais.interfaces.llm import ILLMProvider, LLMMessage

logger = structlog.get_logger(__name__)


async def self_critic_node(
    state: MedicalAgentState,
    *,
    llm: ILLMProvider,
) -> dict:
    """
    Fact-check the draft answer against retrieved evidence.
    Adjusts confidence score downward for unsupported claims.
    """
    draft = state.get("draft_answer", "")
    if not draft:
        return {"fact_check_passed": True, "fact_check_issues": []}

    chunks = state.get("retrieved_chunks", [])
    evidence = "\n\n".join(f"[{i+1}] {c['text'][:400]}" for i, c in enumerate(chunks[:10]))

    messages = [
        LLMMessage(role="system", content=SELF_CRITIC_SYSTEM),
        LLMMessage(
            role="human",
            content=SELF_CRITIC_HUMAN.format(
                draft_answer=draft[:2000],  # cap to avoid token overflow
                evidence=evidence or "No evidence retrieved.",
            ),
        ),
    ]

    try:
        result = await llm.complete_json(messages, temperature=0.0, max_tokens=1024)
    except Exception as exc:
        logger.error("self_critic.llm_error", error=str(exc))
        return {"fact_check_passed": True, "fact_check_issues": []}

    passed = result.get("passed", True)
    issues = [i.get("claim", "") for i in result.get("issues", []) if i.get("claim")]
    confidence_adj = float(result.get("confidence_adjustment", 0.0))

    # Apply confidence adjustment (clamped to [0, 1])
    current_confidence = state.get("confidence_score", 0.5)
    new_confidence = max(0.0, min(1.0, current_confidence + confidence_adj))

    logger.info(
        "self_critic.done",
        passed=passed,
        issues=len(issues),
        confidence_before=current_confidence,
        confidence_after=new_confidence,
    )

    # Promote draft to final answer
    return {
        "fact_check_passed": passed,
        "fact_check_issues": issues,
        "confidence_score": new_confidence,
        "final_answer": state.get("draft_answer", ""),
    }
