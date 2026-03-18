"""
Azure OpenAI LLM adapter.
Wraps the openai SDK's AzureOpenAI client behind ILLMProvider.

Required env vars:
    AZURE_OPENAI_ENDPOINT       e.g. https://optimusrcm.openai.azure.com/
    AZURE_OPENAI_DEPLOYMENT     e.g. gpt-4.1
    AZURE_OPENAI_API_KEY        your Azure key
    AZURE_OPENAI_API_VERSION    e.g. 2024-12-01-preview
"""
from __future__ import annotations

import json

import structlog
from openai import AsyncAzureOpenAI, RateLimitError, APIError

from medical_ais.core.exceptions import LLMInvalidResponseError, LLMRateLimitError
from medical_ais.interfaces.llm import ILLMProvider, LLMMessage, LLMResponse

logger = structlog.get_logger(__name__)


class AzureOpenAIAdapter(ILLMProvider):
    """ILLMProvider implementation backed by Azure OpenAI."""

    def __init__(
        self,
        api_key: str,
        endpoint: str,
        deployment: str,
        api_version: str,
    ) -> None:
        self._deployment = deployment
        self._client = AsyncAzureOpenAI(
            api_key=api_key,
            azure_endpoint=endpoint,
            api_version=api_version,
        )

    @property
    def model_name(self) -> str:
        return f"azure/{self._deployment}"

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
                model=self._deployment,   # Azure uses deployment name as model
                messages=openai_messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except RateLimitError as exc:
            raise LLMRateLimitError(f"Azure OpenAI rate limit: {exc}") from exc
        except APIError as exc:
            raise LLMInvalidResponseError(f"Azure OpenAI API error: {exc}") from exc

        choice = response.choices[0]
        return LLMResponse(
            content=choice.message.content or "",
            model=self.model_name,
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
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LLMInvalidResponseError(
                f"Azure OpenAI returned non-JSON: {exc}", raw_response=response.content
            ) from exc

    async def stream(self, messages, max_tokens=1024):
        resp = await self._client.chat.completions.create(
            model=self._deployment,
            messages=messages,
            max_tokens=max_tokens,
            stream=True,
        )
        async for chunk in resp:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
