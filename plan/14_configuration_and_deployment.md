# 14 — Configuration and Deployment

## Environment Variables (.env)

**File**: `.env.example` — copy this to `.env` and fill in real values

```bash
# ── LLM ──────────────────────────────────────────────────────
LLM_PROVIDER=claude                  # claude | gpt4o | gemini
ANTHROPIC_API_KEY=sk-ant-...
CLAUDE_MODEL=claude-3-5-sonnet-20241022
CLAUDE_CLASSIFIER_MODEL=claude-haiku-4-5-20251001

OPENAI_API_KEY=sk-...                # Optional if using GPT-4o
OPENAI_MODEL=gpt-4o

# ── Graph Database ────────────────────────────────────────────
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your_secure_password

# ── Vector Store ──────────────────────────────────────────────
VECTOR_STORE_PROVIDER=lancedb        # lancedb | pinecone
LANCEDB_PATH=./data/lancedb
PINECONE_API_KEY=...                 # Only if using Pinecone
PINECONE_INDEX_NAME=medical-ais

# ── Elasticsearch (BM25) ─────────────────────────────────────
ELASTICSEARCH_URL=http://localhost:9200
ELASTICSEARCH_INDEX=medical_chunks

# ── PostgreSQL (Audit + Checkpoints) ─────────────────────────
POSTGRES_URL=postgresql://mais_user:password@localhost:5432/mais_db

# ── Redis (Cache + Idempotency) ───────────────────────────────
REDIS_URL=redis://localhost:6379

# ── EHR Integration ───────────────────────────────────────────
EHR_PROVIDER=mock                    # mock | fhir
FHIR_SERVER_URL=https://your-ehr.hospital.com/fhir/r4
FHIR_API_KEY=...

# ── Web Search ────────────────────────────────────────────────
TAVILY_API_KEY=tvly-...

# ── Observability ─────────────────────────────────────────────
LANGSMITH_API_KEY=ls__...
LANGSMITH_PROJECT=medical-ais
LANGSMITH_TRACING_V2=true

# ── System Thresholds ─────────────────────────────────────────
CONFIDENCE_THRESHOLD=0.80            # Min confidence for auto-action
MAX_ITERATIONS=5                     # Max agent loop iterations
MAX_HOPS=3                           # Max graph traversal hops
TOP_K_RETRIEVAL=10                   # Documents to retrieve

# ── API Security ──────────────────────────────────────────────
API_KEY=your_api_key_for_clients
JWT_SECRET=your_jwt_secret
ALLOWED_ORIGINS=http://localhost:3000,https://hospital.internal

# ── Feature Flags ─────────────────────────────────────────────
ENABLE_WEB_SEARCH=true
ENABLE_ACTION_EXECUTION=true         # Set false in dev/testing
ENABLE_HUMAN_APPROVAL=true           # Set false for automated testing
```

---

## Settings Class

**File**: `config/settings.py`

```python
from pydantic_settings import BaseSettings
from pydantic import Field

class Settings(BaseSettings):
    # LLM
    llm_provider: str = "claude"
    anthropic_api_key: str = ""
    claude_model: str = "claude-3-5-sonnet-20241022"
    claude_classifier_model: str = "claude-haiku-4-5-20251001"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"

    # Graph DB
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_username: str = "neo4j"
    neo4j_password: str

    # Vector Store
    vector_store_provider: str = "lancedb"
    lancedb_path: str = "./data/lancedb"
    pinecone_api_key: str = ""
    pinecone_index_name: str = "medical-ais"

    # Search
    elasticsearch_url: str = "http://localhost:9200"
    elasticsearch_index: str = "medical_chunks"

    # Storage
    postgres_url: str
    redis_url: str = "redis://localhost:6379"

    # EHR
    ehr_provider: str = "mock"
    fhir_server_url: str = ""
    fhir_api_key: str = ""

    # Web Search
    tavily_api_key: str = ""

    # Observability
    langsmith_api_key: str = ""
    langsmith_project: str = "medical-ais"
    langsmith_tracing_v2: bool = True

    # Thresholds
    confidence_threshold: float = Field(default=0.80, ge=0.0, le=1.0)
    max_iterations: int = Field(default=5, ge=1, le=20)
    max_hops: int = Field(default=3, ge=1, le=5)
    top_k_retrieval: int = Field(default=10, ge=1, le=50)

    # Security
    api_key: str
    jwt_secret: str
    allowed_origins: list[str] = ["http://localhost:3000"]

    # Feature Flags
    enable_web_search: bool = True
    enable_action_execution: bool = True
    enable_human_approval: bool = True

    class Config:
        env_file = ".env"
        case_sensitive = False
```

---

## Docker Compose

**File**: `docker-compose.yml`

```yaml
version: '3.9'

services:

  neo4j:
    image: neo4j:5.20-enterprise
    ports:
      - "7474:7474"   # Browser
      - "7687:7687"   # Bolt
    environment:
      NEO4J_AUTH: neo4j/your_secure_password
      NEO4J_PLUGINS: '["graph-data-science", "apoc"]'
      NEO4J_dbms_memory_heap_initial__size: 512m
      NEO4J_dbms_memory_heap_max__size: 2G
    volumes:
      - neo4j_data:/data
      - neo4j_logs:/logs
    healthcheck:
      test: ["CMD", "wget", "-O", "/dev/null", "http://localhost:7474"]
      interval: 30s
      timeout: 10s
      retries: 5

  postgres:
    image: postgres:16
    ports:
      - "5432:5432"
    environment:
      POSTGRES_DB: mais_db
      POSTGRES_USER: mais_user
      POSTGRES_PASSWORD: your_secure_password
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./migrations/postgres:/docker-entrypoint-initdb.d
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U mais_user -d mais_db"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  elasticsearch:
    image: elasticsearch:8.13.0
    ports:
      - "9200:9200"
    environment:
      discovery.type: single-node
      ES_JAVA_OPTS: "-Xms512m -Xmx512m"
      xpack.security.enabled: "false"
    volumes:
      - elasticsearch_data:/usr/share/elasticsearch/data
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost:9200/_cluster/health"]
      interval: 30s
      timeout: 10s
      retries: 5

volumes:
  neo4j_data:
  neo4j_logs:
  postgres_data:
  redis_data:
  elasticsearch_data:
```

---

## Makefile

**File**: `Makefile`

```makefile
.PHONY: setup start stop ingest test test-unit test-integration lint

# Infrastructure
setup:
    docker-compose up -d
    sleep 10
    make migrate

start:
    docker-compose up -d
    python main.py

stop:
    docker-compose down

# Database
migrate:
    python -m pipeline.graph_builder.schema_migrator
    psql $(POSTGRES_URL) -f migrations/postgres/001_create_audit_table.sql
    psql $(POSTGRES_URL) -f migrations/postgres/002_create_action_log_table.sql

# Pipeline
ingest:
    python -m pipeline.pipeline_runner --source $(SOURCE)

ingest-update:
    python -m pipeline.pipeline_runner --source $(SOURCE) --incremental

pipeline-status:
    python -m pipeline.pipeline_runner --status

# Testing
test:
    pytest tests/ -v --tb=short

test-unit:
    pytest tests/unit/ -v --tb=short

test-integration:
    pytest tests/integration/ -v --tb=short -m integration

test-coverage:
    pytest tests/ --cov=. --cov-report=html --cov-fail-under=80
    open htmlcov/index.html

# Code quality
lint:
    ruff check .
    mypy . --ignore-missing-imports

format:
    ruff format .
```

---

## Application Bootstrap

**File**: `core/application.py`

```python
class Application:
    def __init__(self, container: Container):
        self._container = container
        self._services = []

    async def start(self) -> None:
        """Start all services in correct order"""
        required_services = [
            ("graph_db",       "Graph Database"),
            ("vector_store",   "Vector Store"),
            ("search_engine",  "Elasticsearch"),
            ("audit_store",    "Audit Database"),
            ("cache_store",    "Redis Cache"),
        ]

        optional_services = [
            ("ehr_client",    "EHR Client"),
        ]

        # Required services — failure stops startup
        for service_attr, service_name in required_services:
            service = getattr(self._container, service_attr)()
            await self._start_service(service, service_name, required=True)

        # Optional services — failure logs warning, startup continues
        for service_attr, service_name in optional_services:
            service = getattr(self._container, service_attr)()
            await self._start_service(service, service_name, required=False)

        logger.info("Medical AI System started successfully")

    async def _start_service(self, service, name: str, required: bool) -> None:
        try:
            if hasattr(service, "connect"):
                await service.connect()
            logger.info(f"Service started: {name}")
        except Exception as e:
            if required:
                logger.error(f"Critical service failed: {name} — {e}")
                raise
            else:
                logger.warning(f"Optional service unavailable: {name} — {e}")
```

**File**: `main.py`

```python
import asyncio
from core.container import Container
from core.application import Application
from api.app import create_api_app
import uvicorn

async def main():
    container = Container()
    container.config.from_dotenv(".env")

    app_service = Application(container)
    await app_service.start()

    api_app = create_api_app(container)

    config = uvicorn.Config(
        api_app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == "__main__":
    asyncio.run(main())
```

---

## Deployment Checklist

Before going to production:

- [ ] All secrets in `.env` not in code
- [ ] `.env` in `.gitignore`
- [ ] Docker health checks all passing
- [ ] Graph schema migrations applied
- [ ] PostgreSQL migrations applied
- [ ] Pipeline run and knowledge graph populated
- [ ] Unit tests passing (100%)
- [ ] Integration tests passing (100%)
- [ ] LangSmith tracing connected
- [ ] `ENABLE_ACTION_EXECUTION=true` confirmed
- [ ] `EHR_PROVIDER` set to real value (not mock)
- [ ] `CONFIDENCE_THRESHOLD` reviewed and set
- [ ] Circuit breaker thresholds reviewed
- [ ] Idempotency Redis TTL confirmed
- [ ] API rate limits configured
- [ ] Audit database retention policy set
- [ ] Rollback plan prepared (docker-compose down, restore DB snapshot)
