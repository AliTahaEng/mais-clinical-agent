# 04 — Technology Stack

## Every Technology Choice with Justification

---

## Orchestration

| Technology | Role | Why This |
|---|---|---|
| **LangGraph** | Agent workflow engine | Native support for cyclic graphs, state machine, checkpointing, interrupt/resume, streaming. The only framework that natively supports all required patterns: loops, parallelism, human-in-the-loop |
| **LangChain** | Tool abstractions + LLM wrappers | Provides standardized tool interfaces, prompt templates, and document loaders. LangGraph is built on top of it — natural combination |

---

## Language Models

| Technology | Role | Why This |
|---|---|---|
| **Claude 3.5 Sonnet** (primary) | Complex reasoning, synthesis, self-critique | Best balance of reasoning quality, long context (200K tokens), and cost. Excellent at following structured output instructions |
| **GPT-4o** | Entity/relationship extraction | Strong structured JSON output. Used in batch processing at index time |
| **Claude Haiku / GPT-4o-mini** | Classification, routing, quick decisions | 10x cheaper, fast enough for simple classification tasks |
| **Adapter pattern** | All LLMs behind ILLMProvider | Swap any LLM by changing one config line |

---

## Embeddings

| Technology | Role | Why This |
|---|---|---|
| **BGE-M3** | Primary embedding model | Top MTEB scores, supports multiple retrieval modes (dense + sparse + multi-vector), multilingual, open source |
| **text-embedding-3-large** (fallback) | OpenAI embeddings | Available as managed service, good performance, easy to use |

---

## Knowledge Graph

| Technology | Role | Why This |
|---|---|---|
| **Neo4j** | Primary graph database | Most mature graph DB, excellent Python driver, Cypher query language, built-in community detection via Graph Data Science library, APOC procedures |
| **Memgraph** (alternative) | Graph database | Faster for real-time queries, compatible Cypher syntax, good for high-throughput scenarios |
| **Neo4j Graph Data Science** | Leiden community detection | Official Neo4j library for graph algorithms. Leiden implementation built-in |

---

## Vector Storage

| Technology | Role | Why This |
|---|---|---|
| **LanceDB** | Primary vector store | File-based (no external service needed), fast, supports hybrid search, open source, good LangChain integration |
| **Pinecone** (production scale) | Managed vector store | When LanceDB doesn't scale enough. Fully managed, high availability |

---

## Search

| Technology | Role | Why This |
|---|---|---|
| **Elasticsearch** | BM25 keyword search | Industry standard for full-text search. Mature Python client. Handles medical terminology exact matching well |
| **rank_bm25** (lightweight) | BM25 without Elasticsearch | For development/testing. No infrastructure needed |
| **Reciprocal Rank Fusion** | Combine BM25 + vector results | Simple, effective, no training required. Outperforms learned fusion in most benchmarks |

---

## Reranking

| Technology | Role | Why This |
|---|---|---|
| **cross-encoder/ms-marco-MiniLM-L-6-v2** | Post-retrieval reranking | Fast cross-encoder, good accuracy, runs locally. Cuts top-20 retrieval failure rate by 67% |
| **sentence-transformers** | Reranker library | Standard library for cross-encoders in Python |

---

## Database (Structured Data)

| Technology | Role | Why This |
|---|---|---|
| **PostgreSQL** | Audit trail + checkpoints + feedback | ACID compliant, excellent for append-only audit logs. LangGraph checkpoint persistence support |
| **Redis** | Cache + rate limiting + idempotency keys | Sub-millisecond reads. Perfect for caching LLM responses and checking idempotency keys |

---

## Web / Real-Time Search

| Technology | Role | Why This |
|---|---|---|
| **Tavily API** | Web search for real-time medical data | Designed for AI agents. Returns clean, structured results. Medical literature search built-in |

---

## API Framework

| Technology | Role | Why This |
|---|---|---|
| **FastAPI** | REST API server | Async-native, Pydantic integration for schema validation, auto-generates OpenAPI docs, excellent performance |
| **Pydantic v2** | Schema validation | All inputs/outputs validated. Type safety across all API boundaries |
| **Uvicorn** | ASGI server | Production-grade async server for FastAPI |

---

## EHR Integration

| Technology | Role | Why This |
|---|---|---|
| **FHIR R4 API** | EHR integration standard | International standard for health data exchange. Supported by Epic, Cerner, OpenMRS. Write once, works with any compliant EHR |
| **fhirclient** | Python FHIR library | Official FHIR Python client. Handles resource types, validation, authentication |

---

## Infrastructure

| Technology | Role | Why This |
|---|---|---|
| **Docker + Docker Compose** | Local development environment | One command to start Neo4j + PostgreSQL + Redis + Elasticsearch. Consistent environment |
| **python-dotenv** | Environment variable loading | Load .env file. Standard approach |
| **dependency-injector** | DI container | Mature Python DI library. Supports singleton, factory, and provider patterns. Wiring decorators for auto-injection |

---

## Observability

| Technology | Role | Why This |
|---|---|---|
| **LangSmith** | LangGraph tracing | Official LangChain tracing. Every node execution, state transition, and tool call is recorded automatically |
| **structlog** | Structured logging | JSON logs with context fields. Easy to ship to log aggregation systems |
| **Prometheus + Grafana** | Metrics | Track latency, error rates, token usage, action execution rates |

---

## Testing

| Technology | Role | Why This |
|---|---|---|
| **pytest** | Test runner | Standard Python testing. Excellent async support via pytest-asyncio |
| **pytest-asyncio** | Async test support | Required for async agent nodes |
| **pytest-mock** | Mocking | Clean mocking syntax. Mock any IInterface with one line |
| **factory_boy** | Test data factories | Generate realistic test data programmatically |

---

## Complete Dependency List (requirements.txt)

```
# Core LangGraph
langgraph>=0.2.0
langchain>=0.3.0
langchain-anthropic>=0.2.0
langchain-openai>=0.2.0
langchain-community>=0.3.0

# LLM Providers
anthropic>=0.30.0
openai>=1.40.0

# Graph Database
neo4j>=5.20.0

# Vector Store
lancedb>=0.10.0
pinecone-client>=4.0.0

# Search
elasticsearch>=8.13.0
rank-bm25>=0.2.2

# Embeddings & Reranking
FlagEmbedding>=1.2.0
sentence-transformers>=3.0.0

# API
fastapi>=0.111.0
uvicorn[standard]>=0.30.0
pydantic>=2.7.0
pydantic-settings>=2.3.0

# Database
asyncpg>=0.29.0
redis>=5.0.0
aioredis>=2.0.0

# DI Container
dependency-injector>=4.41.0

# EHR
fhirclient>=4.0.0

# Web Search
tavily-python>=0.3.0

# Infrastructure
python-dotenv>=1.0.0

# Observability
langsmith>=0.1.80
structlog>=24.1.0

# Pipeline
pypdf>=4.0.0
python-docx>=1.1.0
beautifulsoup4>=4.12.0

# Testing
pytest>=8.0.0
pytest-asyncio>=0.23.0
pytest-mock>=3.14.0
factory-boy>=3.3.0

# Utilities
tenacity>=8.3.0        # Retry with backoff
httpx>=0.27.0          # Async HTTP client
python-jose>=3.3.0     # JWT for API auth
```
