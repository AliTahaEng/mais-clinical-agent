"""
Capability-based security guard.
Every agent declares a manifest of allowed capabilities.
The guard enforces that no agent can invoke a tool it hasn't declared.
"""
from __future__ import annotations

import structlog

from medical_ais.core.exceptions import UnauthorizedAgentAction, UnknownAgentError

logger = structlog.get_logger(__name__)

# Registry: agent_id → set of allowed capability strings
_REGISTRY: dict[str, set[str]] = {
    "supervisor": {
        "route_query",
        "read_graph",
        "hybrid_search",
        "synthesize",
        "quality_check",
    },
    "graph_agent": {
        "read_graph",
        "traverse_relationships",
        "find_entity",
    },
    "search_agent": {
        "hybrid_search",
        "web_search",
        "parent_document_retrieval",
    },
    "synthesizer": {
        "synthesize",
        "self_critic",
    },
    "action_agent": {
        "write_ehr_alert",
        "send_notification",
        "create_clinical_task",
        "schedule_test",
    },
}


class CapabilityGuard:
    """
    Checks agent capabilities before a tool is executed.
    Raise UnauthorizedAgentAction if the agent lacks the required capability.
    """

    def __init__(self, registry: dict[str, set[str]] | None = None) -> None:
        self._registry = registry if registry is not None else dict(_REGISTRY)

    def register_agent(self, agent_id: str, capabilities: list[str]) -> None:
        """Register a new agent with its allowed capabilities."""
        self._registry[agent_id] = set(capabilities)
        logger.info("capability_guard.registered", agent_id=agent_id, capabilities=capabilities)

    def check(self, agent_id: str, capability: str) -> None:
        """
        Verify that *agent_id* holds *capability*.
        Raises UnknownAgentError or UnauthorizedAgentAction on failure.
        """
        if agent_id not in self._registry:
            raise UnknownAgentError(agent_id)
        if capability not in self._registry[agent_id]:
            logger.warning(
                "capability_guard.denied",
                agent_id=agent_id,
                capability=capability,
                allowed=list(self._registry[agent_id]),
            )
            raise UnauthorizedAgentAction(agent_id, capability)
        logger.debug("capability_guard.allowed", agent_id=agent_id, capability=capability)

    def get_capabilities(self, agent_id: str) -> set[str]:
        if agent_id not in self._registry:
            raise UnknownAgentError(agent_id)
        return frozenset(self._registry[agent_id])
