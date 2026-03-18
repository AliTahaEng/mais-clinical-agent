"""Unit tests for the CRAG quality checker node."""
from __future__ import annotations

import json

import pytest

from medical_ais.adapters.llm.mock_llm_adapter import MockLLMAdapter
from medical_ais.agent.nodes.quality_checker import quality_checker_node


@pytest.mark.asyncio
async def test_good_retrieval_no_web_search():
    response = json.dumps({
        "relevance_score": 0.92,
        "is_sufficient": True,
        "missing_information": [],
        "needs_web_search": False,
        "reasoning": "Highly relevant documents found",
    })
    llm = MockLLMAdapter(responses=[response])

    state = {
        "query": "Metformin side effects",
        "retrieved_chunks": [
            {"id": "c1", "text": "Metformin commonly causes GI side effects.", "score": 0.9, "source": "hybrid", "metadata": {}}
        ],
    }

    result = await quality_checker_node(state, llm=llm)
    assert result["retrieval_quality"] == pytest.approx(0.92)
    assert result["needs_web_search"] is False


@pytest.mark.asyncio
async def test_poor_retrieval_triggers_web_search():
    response = json.dumps({
        "relevance_score": 0.3,
        "is_sufficient": False,
        "missing_information": ["recent clinical trials"],
        "needs_web_search": True,
        "reasoning": "Insufficient relevant documents",
    })
    llm = MockLLMAdapter(responses=[response])

    state = {
        "query": "Latest COVID-19 treatment guidelines",
        "retrieved_chunks": [
            {"id": "c1", "text": "Unrelated text.", "score": 0.1, "source": "hybrid", "metadata": {}}
        ],
    }

    result = await quality_checker_node(state, llm=llm)
    assert result["retrieval_quality"] < 0.5
    assert result["needs_web_search"] is True


@pytest.mark.asyncio
async def test_empty_chunks_triggers_web_search():
    llm = MockLLMAdapter()

    state = {
        "query": "test",
        "retrieved_chunks": [],
    }

    result = await quality_checker_node(state, llm=llm)
    assert result["retrieval_quality"] == 0.0
    assert result["needs_web_search"] is True
