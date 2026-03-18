"""
Tool registry — single place to look up action tools by name.
Provides timeout enforcement and capability checking at execution time.
"""
from __future__ import annotations

import asyncio

import structlog

from medical_ais.core.exceptions import ToolNotFoundError, ToolTimeoutError
from medical_ais.interfaces.action_tool import ActionResult, IActionTool
from medical_ais.security.capability_guard import CapabilityGuard

logger = structlog.get_logger(__name__)


class ToolRegistry:
    """Stores and dispatches action tools with timeout + capability enforcement."""

    def __init__(
        self,
        capability_guard: CapabilityGuard,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._tools: dict[str, IActionTool] = {}
        self._guard = capability_guard
        self._timeout = timeout_seconds

    def register(self, tool: IActionTool) -> None:
        self._tools[tool.name] = tool
        logger.info("tool_registry.registered", name=tool.name, tier=tool.tier.value)

    def get(self, tool_name: str) -> IActionTool:
        if tool_name not in self._tools:
            raise ToolNotFoundError(tool_name)
        return self._tools[tool_name]

    def list_tools(self) -> list[dict]:
        return [t.to_schema() for t in self._tools.values()]

    async def execute(
        self,
        tool_name: str,
        parameters: dict,
        *,
        agent_id: str = "action_agent",
    ) -> ActionResult:
        """
        Look up the tool, check capability, then execute with timeout.
        Raises ToolNotFoundError, UnauthorizedAgentAction, ToolTimeoutError.
        """
        tool = self.get(tool_name)

        # Capability check: agent must hold every required capability
        for cap in tool.required_capabilities:
            self._guard.check(agent_id, cap)

        try:
            result = await asyncio.wait_for(
                tool.execute(parameters),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError:
            raise ToolTimeoutError(tool_name, self._timeout)

        logger.info(
            "tool_registry.executed",
            tool=tool_name,
            success=result.success,
            agent=agent_id,
        )
        return result
