"""
OpenAI GPT-4o LLM adapter.
Wraps the OpenAI SDK behind ILLMProvider.
"""
from __future__ import annotations

import json

import structlog
from openai import AsyncOpenAI, RateLimitError, APIError

from medical_ais.core.exceptions import LLMInvalidResponseError, LLMRateLimitError
from medical_ais.interfaces.llm import ILLMProvider, LLMMessage, LLMResponse

logger = structlog.get_logger(__name__)


class GPT4oAdapter(ILLMProvider):
    """ILLMProvider implementation backed by OpenAI GPT-4o."""

    def __init__(self, api_key: str, model: str = "gpt-4o") -> None:
        self._model = model
        self._client = AsyncOpenAI(api_key=api_key)

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
        openai_messages = [
            {"role": "user" if m.role == "human" else m.role, "content": m.content}
            for m in messages
        ]
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=openai_messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except RateLimitError as exc:
            raise LLMRateLimitError(f"OpenAI rate limit: {exc}") from exc
        except APIError as exc:
            raise LLMInvalidResponseError(f"OpenAI API error: {exc}") from exc

        choice = response.choices[0]
        return LLMResponse(
            content=choice.message.content or "",
            model=self._model,
            input_tokens=response.usage.prompt_tokens if response.usage else 0,
            output_tokens=response.usage.completion_tokens if response.usage else 0,
            stop_reason=choice.finish_reason or "stop",
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
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LLMInvalidResponseError(
                f"GPT-4o returned non-JSON: {exc}", raw_response=response.content
            ) from exc

    async def stream(self, messages, max_tokens=1024):
        resp = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            max_tokens=max_tokens,
            stream=True,
        )
        async for chunk in resp:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
