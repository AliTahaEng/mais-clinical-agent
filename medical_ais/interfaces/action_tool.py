"""
Abstract interface for action tools (EHR writes, notifications, scheduling).
Every action tool must declare its tier so the decision engine can route it.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any


class ActionTier(IntEnum):
    """
    TIER_1 — low-risk, automatic execution allowed.
    TIER_2 — medium-risk, requires human approval via interrupt.
    TIER_3 — critical/irreversible, mandatory human review.
    """
    TIER_1 = 1
    TIER_2 = 2
    TIER_3 = 3


@dataclass
class ActionResult:
    success: bool
    tool_name: str
    output: Any = None
    error: str = ""
    idempotency_key: str = ""


class IActionTool(ABC):
    """Contract every action tool must satisfy."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique tool identifier, e.g. 'write_ehr_alert'."""

    @property
    @abstractmethod
    def description(self) -> str:
        """One-line description used in LLM prompts."""

    @property
    @abstractmethod
    def tier(self) -> ActionTier:
        """Risk tier that determines approval routing."""

    @property
    @abstractmethod
    def required_capabilities(self) -> list[str]:
        """Capability names an agent must hold to invoke this tool."""

    @abstractmethod
    async def execute(self, parameters: dict[str, Any]) -> ActionResult:
        """
        Execute the action with *parameters*.
        Must be idempotent — calling twice with the same inputs = same outcome.
        """

    def to_schema(self) -> dict:
        """Return a JSON-schema description of this tool's parameters."""
        return {
            "name": self.name,
            "description": self.description,
            "tier": self.tier.value,
            "required_capabilities": self.required_capabilities,
        }
