"""
Mock LLM adapter for unit tests.
Returns configurable canned responses without network calls.
"""
from __future__ import annotations

from medical_ais.interfaces.llm import ILLMProvider, LLMMessage, LLMResponse


class MockLLMAdapter(ILLMProvider):
    """
    Deterministic test double for ILLMProvider.

    Usage::

        adapter = MockLLMAdapter(responses=["Hello world", '{"score": 0.9}'])
        # First call returns "Hello world", second returns '{"score": 0.9}'
    """

    def __init__(self, responses: list[str] | None = None) -> None:
        self._responses = list(responses or ['{"result": "mock"}'])
        self._index = 0
        self.calls: list[list[LLMMessage]] = []

    @property
    def model_name(self) -> str:
        return "mock-llm"

    def _next_response(self) -> str:
        if self._index >= len(self._responses):
            return self._responses[-1]
        text = self._responses[self._index]
        self._index += 1
        return text

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        self.calls.append(messages)
        return LLMResponse(
            content=self._next_response(),
            model="mock-llm",
        )

    async def complete_json(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> dict:
        import json
        response = await self.complete(messages, temperature=temperature, max_tokens=max_tokens)
        return json.loads(response.content)

    async def stream(self, messages, max_tokens=1024):
        response = self._next_response()
        for word in response.split(" "):
            yield word + " "
