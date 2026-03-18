"""Unit tests for the supervisor node."""
from __future__ import annotations

import json

import pytest

from medical_ais.adapters.llm.mock_llm_adapter import MockLLMAdapter
from medical_ais.agent.nodes.supervisor import supervisor_node
from medical_ais.core.exceptions import MaxIterationsExceededError


@pytest.mark.asyncio
async def test_supervisor_produces_plan():
    response = json.dumps({
        "plan": "search drug interactions",
        "sub_queries": ["Metformin interactions", "Warfarin drug interactions"],
        "requires_graph_search": True,
        "requires_hybrid_search": True,
        "requires_web_search": False,
        "requires_patient_context": False,
        "reasoning": "Need drug interaction data",
    })
    llm = MockLLMAdapter(responses=[response])

    state = {
        "query": "What drug interactions exist for Metformin?",
        "patient_id": None,
        "session_id": "test-123",
        "iteration": 0,
        "retrieval_quality": -1.0,
    }

    result = await supervisor_node(state, llm=llm, max_iterations=5)
    assert result["current_plan"] == "search drug interactions"
    assert len(result["sub_queries"]) == 2
    assert result["iteration"] == 1


@pytest.mark.asyncio
async def test_supervisor_raises_on_max_iterations():
    llm = MockLLMAdapter()
    state = {
        "query": "test",
        "patient_id": None,
        "session_id": "test",
        "iteration": 5,
        "retrieval_quality": 0.0,
    }

    with pytest.raises(MaxIterationsExceededError):
        await supervisor_node(state, llm=llm, max_iterations=5)


@pytest.mark.asyncio
async def test_supervisor_handles_llm_failure():
    """Supervisor falls back gracefully on LLM error."""
    from medical_ais.core.exceptions import LLMInvalidResponseError
    from unittest.mock import AsyncMock

    from medical_ais.interfaces.llm import ILLMProvider

    class FailingLLM(ILLMProvider):
        @property
        def model_name(self):
            return "fail"
        async def complete(self, messages, **kw):
            raise LLMInvalidResponseError("LLM failed")
        async def complete_json(self, messages, **kw):
            raise LLMInvalidResponseError("LLM failed")

    state = {
        "query": "test query",
        "patient_id": None,
        "session_id": "test",
        "iteration": 0,
        "retrieval_quality": 0.0,
    }
    result = await supervisor_node(state, llm=FailingLLM(), max_iterations=5)
    assert "error" in result
    assert result["iteration"] == 1
