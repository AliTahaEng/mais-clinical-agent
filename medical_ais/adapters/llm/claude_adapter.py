"""
Claude (Anthropic) LLM adapter.
Wraps the Anthropic SDK behind ILLMProvider.
"""
from __future__ import annotations

import json

import anthropic
import structlog

from medical_ais.core.exceptions import LLMInvalidResponseError, LLMRateLimitError
from medical_ais.interfaces.llm import ILLMProvider, LLMMessage, LLMResponse

logger = structlog.get_logger(__name__)


class ClaudeAdapter(ILLMProvider):
    """ILLMProvider implementation backed by Anthropic Claude."""

    def __init__(self, api_key: str, model: str) -> None:
        self._model = model
        self._client = anthropic.AsyncAnthropic(api_key=api_key)

    @property
    def model_name(self) -> str:
        return self._model

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        system_text, anthropic_messages = self._split_messages(messages)
        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_text or anthropic.NOT_GIVEN,
                messages=anthropic_messages,
            )
        except anthropic.RateLimitError as exc:
            raise LLMRateLimitError(f"Anthropic rate limit: {exc}") from exc
        except anthropic.APIError as exc:
            raise LLMInvalidResponseError(f"Anthropic API error: {exc}") from exc

        content = response.content[0].text if response.content else ""
        return LLMResponse(
            content=content,
            model=self._model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            stop_reason=response.stop_reason or "end_turn",
        )

    async def complete_json(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> dict:
        response = await self.complete(messages, temperature=temperature, max_tokens=max_tokens)
        raw = response.content.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LLMInvalidResponseError(
                f"Claude returned non-JSON: {exc}", raw_response=response.content
            ) from exc

    async def stream(self, messages, max_tokens=1024):
        system_msg = ""
        turns = []
        for m in messages:
            if m["role"] == "system":
                system_msg = m["content"]
            else:
                turns.append(m)
        async with self._client.messages.stream(
            model=self._model,
            max_tokens=max_tokens,
            system=system_msg or anthropic.NOT_GIVEN,
            messages=turns,
        ) as s:
            async for token in s.text_stream:
                yield token

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _split_messages(
        messages: list[LLMMessage],
    ) -> tuple[str, list[dict]]:
        """Separate the system message from human/assistant turns."""
        system_parts: list[str] = []
        turns: list[dict] = []
        for msg in messages:
            if msg.role == "system":
                system_parts.append(msg.content)
            else:
                # LangChain uses "human"; Anthropic expects "user"
                role = "user" if msg.role == "human" else msg.role
                turns.append({"role": role, "content": msg.content})
        return "\n\n".join(system_parts), turns
