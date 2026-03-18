"""
Adapter factory — reads Settings and returns the right concrete adapter.
Nothing outside this file should import concrete adapter classes.
All other code depends only on interfaces.
"""
from __future__ import annotations

import structlog

from medical_ais.config.settings import Settings
from medical_ais.core.exceptions import ConfigurationError
from medical_ais.interfaces.audit import IAuditStore
from medical_ais.interfaces.cache import ICacheStore
from medical_ais.interfaces.ehr import IEHRClient
from medical_ais.interfaces.embedding import IEmbeddingModel
from medical_ais.interfaces.graph_db import IGraphDB
from medical_ais.interfaces.llm import ILLMProvider
from medical_ais.interfaces.reranker import IReranker
from medical_ais.interfaces.search import ISearchEngine
from medical_ais.interfaces.vector_store import IVectorStore

logger = structlog.get_logger(__name__)


class AdapterFactory:
    """
    Creates adapter instances from application settings.
    Each factory method returns the matching interface — callers are
    unaware of which concrete class was instantiated.
    """

    def __init__(self, settings: Settings) -> None:
        self._s = settings

    # ── LLM ───────────────────────────────────────────────────────────────────

    def make_llm(self) -> ILLMProvider:
        """Primary reasoning / synthesis LLM."""
        if self._s.llm_provider == "claude":
            if not self._s.anthropic_api_key:
                raise ConfigurationError("ANTHROPIC_API_KEY is required for llm_provider=claude")
            from medical_ais.adapters.llm.claude_adapter import ClaudeAdapter
            return ClaudeAdapter(
                api_key=self._s.anthropic_api_key,
                model=self._s.claude_model,
            )
        if self._s.llm_provider == "gpt4o":
            if not self._s.openai_api_key:
                raise ConfigurationError("OPENAI_API_KEY is required for llm_provider=gpt4o")
            from medical_ais.adapters.llm.gpt4o_adapter import GPT4oAdapter
            return GPT4oAdapter(
                api_key=self._s.openai_api_key,
                model=self._s.openai_model,
            )
        if self._s.llm_provider == "azure":
            if not self._s.azure_openai_api_key:
                raise ConfigurationError("AZURE_OPENAI_API_KEY is required for llm_provider=azure")
            if not self._s.azure_openai_endpoint:
                raise ConfigurationError("AZURE_OPENAI_ENDPOINT is required for llm_provider=azure")
            from medical_ais.adapters.llm.azure_openai_adapter import AzureOpenAIAdapter
            return AzureOpenAIAdapter(
                api_key=self._s.azure_openai_api_key,
                endpoint=self._s.azure_openai_endpoint,
                deployment=self._s.azure_openai_deployment,
                api_version=self._s.azure_openai_api_version,
            )
        if self._s.llm_provider == "mock":
            from medical_ais.adapters.llm.mock_llm_adapter import MockLLMAdapter
            return MockLLMAdapter()
        raise ConfigurationError(f"Unknown llm_provider: '{self._s.llm_provider}'")

    def make_classifier_llm(self) -> ILLMProvider:
        """Cheap classifier LLM (Haiku for Claude, same model for GPT)."""
        if self._s.llm_provider == "claude":
            if not self._s.anthropic_api_key:
                raise ConfigurationError("ANTHROPIC_API_KEY is required")
            from medical_ais.adapters.llm.claude_adapter import ClaudeAdapter
            return ClaudeAdapter(
                api_key=self._s.anthropic_api_key,
                model=self._s.claude_classifier_model,
            )
        # Fall back to primary LLM for non-Claude providers
        return self.make_llm()

    # ── Graph DB ──────────────────────────────────────────────────────────────

    def make_graph_db(self) -> IGraphDB:
        from medical_ais.adapters.graph_db.neo4j_adapter import Neo4jAdapter
        return Neo4jAdapter(
            uri=self._s.neo4j_uri,
            username=self._s.neo4j_username,
            password=self._s.neo4j_password,
        )

    # ── Vector Store ──────────────────────────────────────────────────────────

    def make_vector_store(self) -> IVectorStore:
        if self._s.vector_store_provider == "lancedb":
            from medical_ais.adapters.vector_store.lancedb_adapter import LanceDBAdapter
            return LanceDBAdapter(path=self._s.lancedb_path)
        if self._s.vector_store_provider == "mock":
            from medical_ais.adapters.vector_store.mock_vector_store import MockVectorStore
            return MockVectorStore()
        raise ConfigurationError(f"Unknown vector_store_provider: '{self._s.vector_store_provider}'")

    # ── Search ────────────────────────────────────────────────────────────────

    def make_search_engine(self) -> ISearchEngine:
        from medical_ais.adapters.search.bm25_adapter import BM25Adapter
        return BM25Adapter()

    # ── Embedding ─────────────────────────────────────────────────────────────

    def make_embedding_model(self) -> IEmbeddingModel:
        if self._s.embedding_provider == "bgem3":
            from medical_ais.adapters.embedding.bgem3_adapter import BGEM3Adapter
            return BGEM3Adapter(model_name=self._s.embedding_model)
        if self._s.embedding_provider == "openai":
            # Use OpenAI embeddings via LangChain (imported lazily)
            from medical_ais.adapters.embedding.bgem3_adapter import BGEM3Adapter
            logger.warning("openai_embedding.fallback_to_bgem3")
            return BGEM3Adapter()
        if self._s.embedding_provider == "mock":
            from medical_ais.adapters.embedding.mock_embedding import MockEmbeddingModel
            return MockEmbeddingModel()
        raise ConfigurationError(f"Unknown embedding_provider: '{self._s.embedding_provider}'")

    # ── Reranker ──────────────────────────────────────────────────────────────

    def make_reranker(self) -> IReranker:
        from medical_ais.adapters.reranker.cross_encoder_adapter import CrossEncoderAdapter
        return CrossEncoderAdapter(model_name=self._s.reranker_model)

    # ── EHR ───────────────────────────────────────────────────────────────────

    def make_ehr_client(self) -> IEHRClient:
        if self._s.ehr_provider == "mock":
            from medical_ais.adapters.ehr.mock_ehr import MockEHRAdapter
            return MockEHRAdapter()
        if self._s.ehr_provider == "fhir":
            from medical_ais.adapters.ehr.fhir_adapter import FHIRAdapter
            return FHIRAdapter(
                server_url=self._s.fhir_server_url,
                api_key=self._s.fhir_api_key,
                client_id=self._s.fhir_client_id,
            )
        raise ConfigurationError(f"Unknown ehr_provider: '{self._s.ehr_provider}'")

    # ── Storage ───────────────────────────────────────────────────────────────

    def make_audit_store(self) -> IAuditStore:
        if self._s.postgres_url and "postgresql" in self._s.postgres_url:
            from medical_ais.adapters.storage.postgres_audit_store import PostgresAuditStore
            return PostgresAuditStore(connection_url=self._s.postgres_url)
        from medical_ais.adapters.storage.in_memory_audit_store import InMemoryAuditStore
        return InMemoryAuditStore()

    def make_cache(self) -> ICacheStore:
        if self._s.redis_url:
            from medical_ais.adapters.storage.redis_cache import RedisCacheAdapter
            return RedisCacheAdapter(url=self._s.redis_url)
        from medical_ais.adapters.storage.in_memory_cache import InMemoryCacheAdapter
        return InMemoryCacheAdapter()
