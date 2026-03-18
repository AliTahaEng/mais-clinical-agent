"""
Configuration management using Pydantic Settings.
All values loaded from environment variables / .env file.
No hardcoded values anywhere in the system.
"""
from __future__ import annotations

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── LLM ──────────────────────────────────────────────────────
    llm_provider: str = Field(default="claude", description="LLM provider: claude | gpt4o | azure")
    anthropic_api_key: str = Field(default="", description="Anthropic API key")
    claude_model: str = Field(
        default="claude-3-5-sonnet-20241022",
        description="Claude model for reasoning/synthesis",
    )
    claude_classifier_model: str = Field(
        default="claude-haiku-4-5-20251001",
        description="Claude model for classification (cheaper)",
    )
    openai_api_key: str = Field(default="", description="OpenAI API key")
    openai_model: str = Field(default="gpt-4o", description="OpenAI model for extraction")

    # ── Azure OpenAI ──────────────────────────────────────────────
    azure_openai_endpoint: str = Field(default="", description="Azure OpenAI endpoint URL")
    azure_openai_deployment: str = Field(default="gpt-4.1", description="Azure deployment name")
    azure_openai_api_key: str = Field(default="", description="Azure OpenAI API key")
    azure_openai_api_version: str = Field(
        default="2024-12-01-preview", description="Azure OpenAI API version"
    )
    azure_openai_resource_name: str = Field(default="", description="Azure OpenAI resource name")

    # ── Graph Database ────────────────────────────────────────────
    neo4j_uri: str = Field(default="bolt://localhost:7687", description="Neo4j Bolt URI")
    neo4j_username: str = Field(default="neo4j", description="Neo4j username")
    neo4j_password: str = Field(default="", description="Neo4j password")

    # ── Vector Store ──────────────────────────────────────────────
    vector_store_provider: str = Field(default="lancedb", description="lancedb | pinecone")
    lancedb_path: str = Field(default="./data/lancedb", description="LanceDB storage path")
    pinecone_api_key: str = Field(default="", description="Pinecone API key")
    pinecone_index_name: str = Field(default="medical-ais", description="Pinecone index name")
    pinecone_environment: str = Field(default="us-east-1", description="Pinecone region")

    # ── Search ────────────────────────────────────────────────────
    search_provider: str = Field(default="bm25_local", description="bm25_local | elasticsearch")
    elasticsearch_url: str = Field(
        default="http://localhost:9200", description="Elasticsearch URL"
    )
    elasticsearch_index: str = Field(
        default="medical_chunks", description="Elasticsearch index name"
    )

    # ── Storage ───────────────────────────────────────────────────
    postgres_url: str = Field(
        default="postgresql+asyncpg://mais_user:password@localhost:5432/mais_db",
        description="PostgreSQL async connection string",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", description="Redis URL")

    # ── EHR Integration ───────────────────────────────────────────
    ehr_provider: str = Field(default="mock", description="mock | fhir")
    fhir_server_url: str = Field(default="", description="FHIR R4 server URL")
    fhir_api_key: str = Field(default="", description="FHIR bearer token")
    fhir_client_id: str = Field(default="", description="FHIR client ID")

    # ── Web Search ────────────────────────────────────────────────
    tavily_api_key: str = Field(default="", description="Tavily API key")

    # ── Observability ─────────────────────────────────────────────
    langsmith_api_key: str = Field(default="", description="LangSmith API key")
    langsmith_project: str = Field(default="medical-ais", description="LangSmith project name")
    langchain_tracing_v2: bool = Field(default=False, description="Enable LangSmith tracing")

    # ── Safety Thresholds ─────────────────────────────────────────
    confidence_threshold: float = Field(
        default=0.80,
        ge=0.0,
        le=1.0,
        description="Minimum confidence for autonomous action",
    )
    max_iterations: int = Field(
        default=5, ge=1, le=20, description="Max agent reasoning loop iterations"
    )
    max_hops: int = Field(
        default=3, ge=1, le=5, description="Max knowledge graph traversal hops"
    )
    top_k_retrieval: int = Field(
        default=10, ge=1, le=50, description="Documents to retrieve per search"
    )
    tool_timeout_seconds: float = Field(
        default=30.0, ge=1.0, le=300.0, description="Tool execution timeout in seconds"
    )

    # ── API Security ──────────────────────────────────────────────
    api_secret_key: str = Field(default="change-me-in-production-32-chars!!", description="API secret key")
    jwt_secret: str = Field(default="change-me-jwt-secret-32-chars!!!", description="JWT secret")
    jwt_access_token_expire_minutes: int = Field(default=15, description="Access token lifetime in minutes")
    jwt_refresh_token_expire_days: int = Field(default=7, description="Refresh token lifetime in days")
    allowed_origins: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:8080"],
        description="Allowed CORS origins",
    )
    admin_token: str = Field(default="", description="Legacy Bearer token for admin API (deprecated)")
    # ── Admin seeding ──────────────────────────────────────────────
    admin_email: str = Field(default="admin@mais.local", description="Default admin email")
    admin_password: str = Field(default="Admin1234!", description="Default admin password — change in production")
    upload_dir: str = Field(default="./data/uploads", description="Directory for uploaded files")
    sse_heartbeat_interval: int = Field(default=15, ge=5, le=60, description="SSE heartbeat interval in seconds")

    # ── Feature Flags ─────────────────────────────────────────────
    enable_action_execution: bool = Field(
        default=False, description="Enable autonomous action execution"
    )
    force_human_approval: bool = Field(
        default=False, description="Force human approval for ALL actions"
    )
    enable_web_search: bool = Field(default=True, description="Enable web search fallback")
    enable_tracing: bool = Field(default=True, description="Enable LangSmith tracing")

    # ── Pipeline ──────────────────────────────────────────────────
    documents_dir: str = Field(default="./data/documents", description="Documents directory")
    parent_chunk_size: int = Field(default=1200, ge=200, le=4000, description="Parent chunk token size")
    child_chunk_size: int = Field(default=200, ge=50, le=500, description="Child chunk token size")
    chunk_overlap: int = Field(default=50, ge=0, le=200, description="Chunk overlap in tokens")

    # ── Embedding ─────────────────────────────────────────────────
    embedding_provider: str = Field(default="bgem3", description="bgem3 | openai")
    embedding_model: str = Field(default="BAAI/bge-m3", description="Embedding model name")
    openai_embedding_model: str = Field(
        default="text-embedding-3-large", description="OpenAI embedding model"
    )

    # ── Reranker ─────────────────────────────────────────────────
    reranker_model: str = Field(
        default="cross-encoder/ms-marco-MiniLM-L-6-v2",
        description="Cross-encoder reranker model",
    )

    # ── Logging ───────────────────────────────────────────────────
    log_level: str = Field(default="INFO", description="Log level: DEBUG | INFO | WARNING | ERROR")
    log_format: str = Field(default="json", description="Log format: json | text")

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_origins(cls, v: str | list) -> list[str]:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in valid:
            raise ValueError(f"log_level must be one of {valid}")
        return upper


_settings_instance: Settings | None = None


def get_settings() -> Settings:
    """Return singleton Settings instance."""
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings()
    return _settings_instance
