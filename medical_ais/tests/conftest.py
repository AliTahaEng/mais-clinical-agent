"""Shared pytest fixtures."""
from __future__ import annotations

import pytest
import pytest_asyncio

from medical_ais.adapters.ehr.mock_ehr import MockEHRAdapter
from medical_ais.adapters.embedding.mock_embedding import MockEmbeddingModel
from medical_ais.adapters.graph_db.mock_graph_db import MockGraphDB
from medical_ais.adapters.llm.mock_llm_adapter import MockLLMAdapter
from medical_ais.adapters.search.bm25_adapter import BM25Adapter
from medical_ais.adapters.storage.in_memory_audit_store import InMemoryAuditStore
from medical_ais.adapters.storage.in_memory_cache import InMemoryCacheAdapter
from medical_ais.adapters.vector_store.mock_vector_store import MockVectorStore
from medical_ais.security.capability_guard import CapabilityGuard
from medical_ais.security.idempotency_manager import IdempotencyManager
from medical_ais.tools.action_tools import SendNotificationTool, WriteEHRAlertTool
from medical_ais.tools.tool_registry import ToolRegistry


@pytest.fixture
def mock_llm():
    return MockLLMAdapter()


@pytest.fixture
def mock_graph_db():
    return MockGraphDB()


@pytest.fixture
def mock_vector_store():
    return MockVectorStore()


@pytest.fixture
def mock_search_engine():
    return BM25Adapter()


@pytest.fixture
def mock_embedding():
    return MockEmbeddingModel()


@pytest.fixture
def mock_ehr():
    return MockEHRAdapter()


@pytest.fixture
def mock_audit_store():
    return InMemoryAuditStore()


@pytest.fixture
def mock_cache():
    return InMemoryCacheAdapter()


@pytest.fixture
def capability_guard():
    return CapabilityGuard()


@pytest.fixture
def idempotency_manager(mock_cache):
    return IdempotencyManager(mock_cache)


@pytest.fixture
def tool_registry(capability_guard, mock_ehr):
    registry = ToolRegistry(capability_guard, timeout_seconds=10.0)
    registry.register(WriteEHRAlertTool(mock_ehr))
    registry.register(SendNotificationTool())
    return registry
