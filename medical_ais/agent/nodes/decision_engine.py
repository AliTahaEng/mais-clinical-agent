"""
Decision engine node — determines which actions to take and routes by tier.
"""
from __future__ import annotations

import structlog

from medical_ais.agent.prompts.decision_engine_prompt import (
    DECISION_ENGINE_HUMAN,
    DECISION_ENGINE_SYSTEM,
)
from medical_ais.agent.state import MedicalAgentState, ProposedAction
from medical_ais.interfaces.llm import ILLMProvider, LLMMessage
from medical_ais.tools.tool_registry import ToolRegistry

logger = structlog.get_logger(__name__)


async def decision_engine_node(
    state: MedicalAgentState,
    *,
    llm: ILLMProvider,
    tool_registry: ToolRegistry,
    confidence_threshold: float = 0.80,
    enable_action_execution: bool = False,
) -> dict:
    """
    Review the final answer and decide whether actions should be taken.

    If confidence < threshold OR action_execution is disabled → no actions.
    Otherwise: classify actions by tier and route appropriately.
    """
    confidence = state.get("confidence_score", 0.0)
    final_answer = state.get("final_answer", "")

    if not enable_action_execution or not final_answer:
        logger.info("decision_engine.actions_disabled")
        return {
            "proposed_actions": [],
            "requires_human_approval": False,
            "escalated": False,
        }

    if confidence < confidence_threshold:
        logger.info(
            "decision_engine.confidence_too_low",
            confidence=confidence,
            threshold=confidence_threshold,
        )
        return {
            "proposed_actions": [],
            "requires_human_approval": False,
            "escalated": False,
        }

    available_tools = tool_registry.list_tools()
    messages = [
        LLMMessage(
            role="system",
            content=DECISION_ENGINE_SYSTEM.format(
                available_tools=str(available_tools)
            ),
        ),
        LLMMessage(
            role="human",
            content=DECISION_ENGINE_HUMAN.format(
                final_answer=final_answer[:2000],
                patient_id=state.get("patient_id") or "None",
                confidence_score=confidence,
            ),
        ),
    ]

    try:
        result = await llm.complete_json(messages, temperature=0.0)
    except Exception as exc:
        logger.error("decision_engine.llm_error", error=str(exc))
        return {"proposed_actions": [], "requires_human_approval": False, "escalated": False}

    if not result.get("should_act", False):
        return {"proposed_actions": [], "requires_human_approval": False, "escalated": False}

    proposed_actions: list[ProposedAction] = []
    has_tier2 = False
    has_tier3 = False

    for action_data in result.get("proposed_actions", []):
        import hashlib, json
        ikey = hashlib.sha256(
            json.dumps(
                {"tool": action_data.get("tool_name"), "params": action_data.get("parameters", {})},
                sort_keys=True
            ).encode()
        ).hexdigest()

        tier = int(action_data.get("tier", 1))
        proposed_actions.append(
            ProposedAction(
                tool_name=action_data.get("tool_name", ""),
                parameters=action_data.get("parameters", {}),
                tier=tier,
                rationale=action_data.get("rationale", ""),
                idempotency_key=ikey,
            )
        )
        if tier == 2:
            has_tier2 = True
        if tier == 3:
            has_tier3 = True

    # Any TIER_3 action → mandatory escalation
    escalated = has_tier3
    # Any TIER_2 action (or TIER_3) → requires human approval
    requires_human = has_tier2 or has_tier3

    logger.info(
        "decision_engine.done",
        actions=len(proposed_actions),
        tier2=has_tier2,
        tier3=has_tier3,
    )

    return {
        "proposed_actions": proposed_actions,
        "requires_human_approval": requires_human,
        "escalated": escalated,
    }
