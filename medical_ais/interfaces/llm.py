"""
Abstract interface for LLM providers.
Adapters (Claude, GPT-4o, mock) implement this — nothing imports a concrete class.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator


@dataclass
class LLMMessage:
    role: str          # "system" | "human" | "assistant"
    content: str


@dataclass
class LLMResponse:
    content: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    stop_reason: str = "end_turn"


class ILLMProvider(ABC):
    """Contract every LLM adapter must satisfy."""

    @abstractmethod
    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Send *messages* and return a completion."""

    @abstractmethod
    async def complete_json(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> dict:
        """Return parsed JSON from the LLM (raises LLMInvalidResponseError on failure)."""

    @abstractmethod
    async def stream(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 1024,
    ) -> AsyncIterator[str]:
        """Yield text tokens as they arrive from the LLM."""
        # Subclasses must implement this as an async generator
        raise NotImplementedError
        yield  # pragma: no cover  — makes this an async generator function

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Human-readable model identifier, e.g. 'claude-3-5-sonnet-20241022'."""
