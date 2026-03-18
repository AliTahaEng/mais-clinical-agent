"""
Action executor node — executes approved TIER_1 and TIER_2 actions.
"""
from __future__ import annotations

import structlog

from medical_ais.agent.state import MedicalAgentState, ProposedAction
from medical_ais.interfaces.action_tool import ActionTier
from medical_ais.security.idempotency_manager import IdempotencyManager
from medical_ais.tools.tool_registry import ToolRegistry

logger = structlog.get_logger(__name__)


async def action_executor_node(
    state: MedicalAgentState,
    *,
    tool_registry: ToolRegistry,
    idempotency_manager: IdempotencyManager,
) -> dict:
    """
    Execute approved TIER_1 and TIER_2 actions with idempotency protection.
    TIER_3 actions must be handled by the escalation node.
    """
    # TIER_1: auto-execute from proposed_actions
    # TIER_2: execute from approved_actions (post human review)
    tier1_actions = [
        a for a in state.get("proposed_actions", [])
        if a["tier"] == ActionTier.TIER_1
    ]
    tier2_actions = state.get("approved_actions", [])

    actions_to_execute = tier1_actions + [
        a for a in tier2_actions if a["tier"] != ActionTier.TIER_3
    ]

    executed: list[dict] = list(state.get("executed_actions", []))

    for action in actions_to_execute:
        key = action["idempotency_key"]

        # Idempotency check
        if await idempotency_manager.is_duplicate(key):
            cached = await idempotency_manager.get_cached_result(key)
            logger.info("action_executor.duplicate_skipped", tool=action["tool_name"], key=key[:16])
            executed.append({"tool": action["tool_name"], "result": cached, "skipped": True})
            continue

        try:
            result = await tool_registry.execute(
                action["tool_name"],
                action["parameters"],
                agent_id="action_agent",
            )
            await idempotency_manager.mark_executed(key, result.output)
            executed.append({
                "tool": action["tool_name"],
                "success": result.success,
                "output": result.output,
                "tier": action["tier"],
            })
        except Exception as exc:
            logger.error("action_executor.failed", tool=action["tool_name"], error=str(exc))
            executed.append({
                "tool": action["tool_name"],
                "success": False,
                "error": str(exc),
                "tier": action["tier"],
            })

    logger.info("action_executor.done", executed=len(executed))
    return {"executed_actions": executed}
