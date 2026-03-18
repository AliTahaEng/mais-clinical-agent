# 03 — Project Structure

## Full Folder and File Layout

```
medical_ais/
│
├── main.py                          # Entry point — boots DI container and starts app
├── .env                             # Environment variables (never commit)
├── .env.example                     # Template with all required variables
├── requirements.txt                 # Python dependencies
├── docker-compose.yml               # Neo4j + PostgreSQL + Redis + Elasticsearch
├── Makefile                         # Common commands: test, lint, ingest, run
│
├── config/
│   ├── __init__.py
│   ├── settings.py                  # Pydantic Settings — loads from .env
│   └── defaults.py                  # Default values for all config keys
│
├── core/
│   ├── __init__.py
│   ├── container.py                 # DI container — registers all dependencies
│   ├── application.py               # App bootstrap — starts all services in order
│   ├── message_bus.py               # Central EventBus for all inter-component events
│   ├── circuit_breaker.py           # CircuitBreaker class (wraps all external calls)
│   └── exceptions.py                # All custom exceptions
│
├── interfaces/
│   ├── __init__.py
│   ├── i_llm_provider.py            # Abstract: generate_response(), stream_response()
│   ├── i_graph_db.py                # Abstract: query(), traverse(), get_entity()
│   ├── i_vector_store.py            # Abstract: similarity_search(), upsert(), delete()
│   ├── i_search_engine.py           # Abstract: keyword_search(), index_document()
│   ├── i_embedding_model.py         # Abstract: embed_text(), embed_batch()
│   ├── i_reranker.py                # Abstract: rerank(query, documents)
│   ├── i_ehr_client.py              # Abstract: get_patient(), write_alert(), create_task()
│   ├── i_audit_store.py             # Abstract: record(), query_by_session()
│   ├── i_cache_store.py             # Abstract: get(), set(), delete()
│   └── i_action_tool.py             # Abstract: execute(payload) → ActionResult
│
├── adapters/
│   ├── __init__.py
│   ├── llm/
│   │   ├── claude_adapter.py        # Implements ILLMProvider using Anthropic SDK
│   │   ├── gpt4o_adapter.py         # Implements ILLMProvider using OpenAI SDK
│   │   └── gemini_adapter.py        # Implements ILLMProvider using Google SDK
│   ├── graph/
│   │   ├── neo4j_adapter.py         # Implements IGraphDB using neo4j driver
│   │   ├── memgraph_adapter.py      # Implements IGraphDB using pymgclient
│   │   └── mock_graph_adapter.py    # Implements IGraphDB with in-memory dict (testing)
│   ├── vector/
│   │   ├── lancedb_adapter.py       # Implements IVectorStore using lancedb
│   │   ├── pinecone_adapter.py      # Implements IVectorStore using pinecone-client
│   │   └── mock_vector_adapter.py   # In-memory implementation (testing)
│   ├── search/
│   │   ├── elasticsearch_adapter.py # Implements ISearchEngine using elasticsearch-py
│   │   └── bm25_adapter.py          # Implements ISearchEngine using rank_bm25
│   ├── embedding/
│   │   ├── bgem3_adapter.py         # Implements IEmbeddingModel using FlagEmbedding
│   │   └── openai_embed_adapter.py  # Implements IEmbeddingModel using OpenAI embeddings
│   ├── reranker/
│   │   └── cross_encoder_adapter.py # Implements IReranker using sentence-transformers
│   ├── ehr/
│   │   ├── fhir_adapter.py          # Implements IEHRClient using FHIR R4 API
│   │   └── mock_ehr_adapter.py      # Implements IEHRClient with mock data (testing)
│   ├── storage/
│   │   ├── postgres_audit_adapter.py # Implements IAuditStore using asyncpg
│   │   └── redis_cache_adapter.py    # Implements ICacheStore using aioredis
│   └── factories/
│       ├── llm_factory.py            # Creates correct ILLMProvider from config
│       ├── graph_factory.py          # Creates correct IGraphDB from config
│       └── vector_factory.py         # Creates correct IVectorStore from config
│
├── pipeline/
│   ├── __init__.py
│   ├── ingestion/
│   │   ├── document_loader.py       # Loads PDF, DOCX, HTML, TXT files
│   │   ├── text_chunker.py          # Parent + child chunk strategy
│   │   └── metadata_extractor.py   # Extract source, date, document type
│   ├── extraction/
│   │   ├── entity_extractor.py      # LLM-based entity extraction
│   │   ├── relationship_extractor.py # LLM-based relationship extraction
│   │   └── extraction_prompts.py    # All extraction prompt templates
│   ├── resolution/
│   │   ├── entity_resolver.py       # Deduplication and alias merging
│   │   └── resolution_rules.py      # Domain rules for entity matching
│   ├── graph_builder/
│   │   ├── graph_writer.py          # Writes entities + relationships to Neo4j
│   │   └── schema_migrator.py       # Applies graph schema migrations
│   ├── community/
│   │   ├── community_detector.py    # Leiden algorithm wrapper
│   │   └── community_summarizer.py  # LLM generates community summaries
│   ├── embedding/
│   │   └── embedding_writer.py      # Embeds entities, chunks, reports to vector store
│   └── pipeline_runner.py           # Orchestrates all pipeline steps in order
│
├── agents/
│   ├── __init__.py
│   ├── state.py                     # MedicalAgentState TypedDict — single source of truth
│   ├── graph.py                     # LangGraph StateGraph definition — all nodes + edges
│   ├── nodes/
│   │   ├── supervisor_node.py       # Query classification + reasoning plan
│   │   ├── local_graph_search_node.py  # Entity traversal in Neo4j
│   │   ├── global_graph_search_node.py # Community report retrieval
│   │   ├── hybrid_search_node.py    # BM25 + vector + reranking
│   │   ├── web_search_node.py       # Tavily web search
│   │   ├── parent_document_node.py  # Fetch parent chunks
│   │   ├── synthesizer_node.py      # Merge context + draft answer
│   │   ├── quality_checker_node.py  # CRAG — evaluate retrieval quality
│   │   ├── self_critic_node.py      # Self-RAG — verify answer grounding
│   │   ├── decision_engine_node.py  # Extract action + risk level
│   │   ├── human_approval_node.py   # LangGraph interrupt for doctor input
│   │   ├── action_executor_node.py  # Execute approved actions via tools
│   │   ├── mandatory_escalation_node.py # TIER 3 escalation
│   │   ├── audit_logger_node.py     # Immutable audit entry
│   │   └── feedback_node.py         # Track outcomes + update graph
│   ├── routers/
│   │   ├── search_router.py         # Routes supervisor → search agents
│   │   ├── quality_router.py        # Routes CRAG result
│   │   ├── critic_router.py         # Routes Self-RAG result
│   │   └── risk_router.py           # Routes by risk level to action tier
│   └── prompts/
│       ├── supervisor_prompt.py
│       ├── synthesizer_prompt.py
│       ├── quality_checker_prompt.py
│       ├── self_critic_prompt.py
│       └── decision_engine_prompt.py
│
├── tools/
│   ├── __init__.py
│   ├── graph_tools/
│   │   ├── find_entity_tool.py      # Search graph by entity name
│   │   ├── traverse_relationships_tool.py  # Multi-hop traversal
│   │   ├── find_connection_tool.py  # Shortest path between two entities
│   │   └── get_community_tool.py    # Retrieve community at level
│   ├── search_tools/
│   │   ├── hybrid_search_tool.py    # BM25 + vector fusion
│   │   ├── vector_search_tool.py    # Pure vector similarity
│   │   └── web_search_tool.py       # Tavily API wrapper
│   ├── action_tools/
│   │   ├── write_ehr_alert_tool.py  # Write alert to EHR patient record
│   │   ├── send_notification_tool.py # Send to doctor / nurse
│   │   ├── create_clinical_task_tool.py # Create task in EHR
│   │   ├── schedule_test_tool.py    # Request lab or imaging test
│   │   └── notify_pharmacy_tool.py  # Alert pharmacist
│   └── tool_registry.py             # Registers all tools + capability manifest
│
├── security/
│   ├── __init__.py
│   ├── capability_guard.py          # Enforces agent capability manifests
│   ├── input_sanitizer.py           # Validates + sanitizes all inputs
│   └── idempotency_manager.py       # Checks + records idempotency keys
│
├── api/
│   ├── __init__.py
│   ├── app.py                       # FastAPI app definition
│   ├── routes/
│   │   ├── query_routes.py          # POST /query, GET /query/{id}
│   │   ├── patient_routes.py        # GET /patient/{id}/history
│   │   ├── webhook_routes.py        # POST /events/prescription etc.
│   │   ├── audit_routes.py          # GET /audit/{session_id}
│   │   └── admin_routes.py          # POST /admin/pipeline/run
│   ├── schemas/
│   │   ├── query_schema.py          # Pydantic models for query requests
│   │   ├── event_schema.py          # Pydantic models for EHR events
│   │   ├── action_schema.py         # Pydantic models for action requests
│   │   └── audit_schema.py          # Pydantic models for audit responses
│   └── middleware/
│       ├── auth_middleware.py        # API key validation
│       ├── rate_limit_middleware.py  # Rate limiting per client
│       └── logging_middleware.py    # Request/response logging
│
├── migrations/
│   ├── graph/
│   │   ├── 001_initial_schema.cypher
│   │   ├── 002_add_community_nodes.cypher
│   │   └── 003_add_claim_nodes.cypher
│   └── postgres/
│       ├── 001_create_audit_table.sql
│       ├── 002_create_action_log_table.sql
│       └── 003_create_feedback_table.sql
│
└── tests/
    ├── unit/
    │   ├── test_entity_extractor.py
    │   ├── test_entity_resolver.py
    │   ├── test_supervisor_node.py
    │   ├── test_quality_checker_node.py
    │   ├── test_self_critic_node.py
    │   ├── test_decision_engine_node.py
    │   ├── test_capability_guard.py
    │   └── test_idempotency_manager.py
    ├── integration/
    │   ├── test_pipeline_e2e.py
    │   ├── test_graph_search_flow.py
    │   ├── test_crag_loop.py
    │   ├── test_selfrag_loop.py
    │   └── test_action_tier_routing.py
    ├── fixtures/
    │   ├── sample_medical_docs/
    │   ├── mock_patient_profiles.py
    │   └── mock_graph_data.py
    └── conftest.py                  # Shared fixtures and mock container
```

---

## Key Design Rules for This Structure

### One Responsibility Per File
Each file has exactly one class or one group of tightly related functions. No file mixes concerns.

### Interfaces Own Nothing
Files in `interfaces/` contain only abstract base classes. Zero business logic. Zero dependencies on external libraries.

### Adapters Are Thin
Files in `adapters/` only translate between external API shapes and interface contracts. No business logic inside adapters.

### Nodes Are Pure Functions
Files in `agents/nodes/` take state → return partial state update. No side effects except through tools.

### Tools Are Sandboxed
Files in `tools/` implement `IActionTool`. Each has an explicit timeout. Each is registered in `tool_registry.py` with a capability manifest.

### Config Is Never Hardcoded
Every value that could change (model names, thresholds, URLs, timeouts) lives in `config/settings.py` loaded from `.env`.
