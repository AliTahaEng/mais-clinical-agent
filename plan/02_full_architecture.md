# 02 — Full System Architecture

## Three-Layer Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         LAYER 1: DATA LAYER                             │
│                    (Runs once at setup + periodic updates)               │
│                                                                         │
│  Raw Documents → Chunking → Entity Extraction → Graph → Communities    │
│                                        ↓              ↓                 │
│                                    Neo4j DB      Vector Store           │
└─────────────────────────────────────────────────────────────────────────┘
                                        ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                       LAYER 2: INTELLIGENCE LAYER                       │
│                    (Runs on every query or trigger event)               │
│                                                                         │
│  Trigger → LangGraph Orchestration → Graph RAG + Agentic RAG            │
│                                   → CRAG + Self-RAG                     │
│                                   → Final Answer + Confidence           │
└─────────────────────────────────────────────────────────────────────────┘
                                        ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                        LAYER 3: ACTION LAYER                            │
│                    (Runs when actionable finding exists)                │
│                                                                         │
│  Decision Engine → Risk Classification → Tiered Execution               │
│                                       → Audit Trail                     │
│                                       → EHR Integration                 │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Complete Component Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              ENTRY POINTS                                       │
│                                                                                 │
│   REST API          EHR Webhook         Scheduled           CLI                 │
│   /query            /events/prescription  /pipeline/run      --ingest           │
│   /patient/{id}     /events/lab                                                 │
│   /audit            /events/vitals                                               │
└────────────────────────────────────┬────────────────────────────────────────────┘
                                     ↓
┌────────────────────────────────────────────────────────────────────────────────┐
│                           MESSAGE BUS (EventBus)                               │
│              All components communicate through typed events                   │
│     query.received | trigger.prescription | trigger.lab | action.approved      │
└────────────────────────────────────┬───────────────────────────────────────────┘
                                     ↓
┌────────────────────────────────────────────────────────────────────────────────┐
│                        LANGGRAPH ORCHESTRATION ENGINE                          │
│                                                                                │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │                         SUPERVISOR NODE                                  │  │
│  │  - Classifies query/trigger type                                         │  │
│  │  - Builds reasoning plan                                                 │  │
│  │  - Routes to appropriate search agents                                   │  │
│  │  - Manages iteration count (max 5)                                       │  │
│  └──────────────────┬─────────────────────────────────────────────────────┘  │
│                     │ (parallel execution via Send API)                       │
│         ┌───────────┼───────────────┬───────────────┐                        │
│         ↓           ↓               ↓               ↓                        │
│  ┌────────────┐ ┌──────────┐ ┌───────────┐ ┌──────────────┐                  │
│  │LOCAL GRAPH │ │GLOBAL    │ │HYBRID     │ │ WEB SEARCH   │                  │
│  │SEARCH NODE │ │GRAPH     │ │SEARCH     │ │ NODE         │                  │
│  │            │ │SEARCH    │ │NODE       │ │              │                  │
│  │Traverses   │ │NODE      │ │BM25 +     │ │Tavily API    │                  │
│  │Neo4j for   │ │          │ │Vector +   │ │for real-time │                  │
│  │entities    │ │Community │ │Reranking  │ │data          │                  │
│  │and rels    │ │reports   │ │           │ │              │                  │
│  └─────┬──────┘ └────┬─────┘ └─────┬─────┘ └──────┬───────┘                  │
│        │             │             │              │                           │
│        └─────────────┴─────────────┴──────────────┘                           │
│                              ↓                                                │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │                    PARENT DOCUMENT NODE                                  │  │
│  │  Matched child chunks → fetch full parent chunks for rich context        │  │
│  └──────────────────────────────────┬───────────────────────────────────────┘  │
│                                     ↓                                         │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │                      SYNTHESIZER NODE                                    │  │
│  │  Merges all retrieved context → generates draft answer with citations    │  │
│  └──────────────────────────────────┬───────────────────────────────────────┘  │
│                                     ↓                                         │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │                    QUALITY CHECKER NODE (CRAG)                           │  │
│  │  good → continue | bad → loop back to supervisor | ambiguous → retry     │  │
│  └──────────────────────────────────┬───────────────────────────────────────┘  │
│                                     ↓ (good only)                             │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │                     SELF-CRITIC NODE (Self-RAG)                          │  │
│  │  supported → continue | hallucinated → regenerate | incomplete → retry   │  │
│  └──────────────────────────────────┬───────────────────────────────────────┘  │
│                                     ↓ (supported only)                        │
└────────────────────────────────────────────────────────────────────────────────┘
                                     ↓
┌────────────────────────────────────────────────────────────────────────────────┐
│                           ACTION LAYER                                         │
│                                                                                │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │                      DECISION ENGINE NODE                                │  │
│  │  Is there an actionable finding? → What action? → What risk level?       │  │
│  │  confidence < 0.80 → force human review regardless of risk level         │  │
│  └──────────────────┬────────────────────────────────────────────────────┘  │
│                     │                                                         │
│         ┌───────────┼───────────────────┐                                    │
│         ↓           ↓                   ↓                                    │
│  ┌────────────┐ ┌──────────────┐ ┌─────────────────┐                         │
│  │TIER 1      │ │TIER 2        │ │TIER 3            │                         │
│  │LOW RISK    │ │MEDIUM RISK   │ │HIGH / CRITICAL   │                         │
│  │            │ │              │ │                  │                         │
│  │Auto execute│ │LangGraph     │ │Alert + escalate  │                         │
│  │No approval │ │interrupt()   │ │NEVER auto-act    │                         │
│  │needed      │ │Wait for      │ │Human must        │                         │
│  │            │ │doctor input  │ │intervene         │                         │
│  └─────┬──────┘ └──────┬───────┘ └──────┬───────────┘                         │
│        │               │ (approved)      │                                    │
│        └───────────────┴─────────────────┘                                    │
│                              ↓                                                │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │                     ACTION EXECUTOR NODE                                 │  │
│  │  Calls real tools: write_ehr | send_alert | create_task | notify_pharma  │  │
│  └──────────────────────────────────┬───────────────────────────────────────┘  │
│                                     ↓                                         │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │                       AUDIT LOGGER NODE                                  │  │
│  │  Immutable log: trigger + retrieval + reasoning + decision + action      │  │
│  └──────────────────────────────────┬───────────────────────────────────────┘  │
│                                     ↓                                         │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │                       FEEDBACK NODE                                      │  │
│  │  Track outcomes → update knowledge graph → improve routing thresholds    │  │
│  └──────────────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────────────┘
```

---

## Data Storage Architecture

```
┌───────────────────────────────────────────────────────────────┐
│                     DATA STORES                               │
│                                                               │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────────┐  │
│  │   Neo4j        │  │   LanceDB /   │  │   PostgreSQL      │  │
│  │ (Knowledge     │  │   Pinecone    │  │   (Audit +        │  │
│  │  Graph)        │  │  (Vector      │  │   Checkpoints +   │  │
│  │                │  │   Store)      │  │   Patient State)  │  │
│  │ Entities       │  │               │  │                   │  │
│  │ Relationships  │  │ Entity        │  │ AuditEntry        │  │
│  │ Communities    │  │ embeddings    │  │ SessionState      │  │
│  │                │  │ Chunk         │  │ ActionLog         │  │
│  │                │  │ embeddings    │  │ FeedbackRecord    │  │
│  │                │  │ Community     │  │                   │  │
│  │                │  │ embeddings    │  │                   │  │
│  └───────────────┘  └───────────────┘  └───────────────────┘  │
│                                                               │
│  ┌───────────────┐  ┌───────────────┐                         │
│  │ Elasticsearch │  │    Redis      │                         │
│  │ (BM25 keyword │  │  (Cache +     │                         │
│  │  search)      │  │   Rate limit) │                         │
│  └───────────────┘  └───────────────┘                         │
└───────────────────────────────────────────────────────────────┘
```

---

## Interface / Adapter Layer

```
┌────────────────────────────────────────────────────────────────────────┐
│                     INTERFACE CONTRACTS (ABCs)                         │
│                                                                        │
│  ILLMProvider    IGraphDB      IVectorStore   IEHRClient               │
│  ISearchEngine   IAuditStore   IMessageBus    IEmbeddingModel          │
│  IReranker       IActionTool   ICacheStore    ICircuitBreaker          │
└────────────────────────────────────────────────────────────────────────┘
                              ↕ (implements)
┌────────────────────────────────────────────────────────────────────────┐
│                       ADAPTER IMPLEMENTATIONS                          │
│                                                                        │
│  ClaudeAdapter      Neo4jAdapter       LanceDBAdapter                  │
│  GPT4oAdapter       MemgraphAdapter    PineconeAdapter                 │
│  GeminiAdapter      FalkorDBAdapter    ElasticsearchAdapter            │
│                     EHRFHIRAdapter     RedisAdapter                    │
│                     MockEHRAdapter     PostgreSQLAdapter               │
└────────────────────────────────────────────────────────────────────────┘
```

---

## Security Boundary

```
┌─────────────────────────────────────────────────────────────┐
│                    TRUST BOUNDARY                           │
│                                                             │
│  External Input (doctor query, EHR event)                   │
│         ↓ [Schema Validation + Sanitization]                │
│  Internal Processing (agents, tools)                        │
│         ↓ [Capability Guard checks permissions]             │
│  External Output (EHR write, alert send)                    │
│         ↓ [Idempotency check + audit log]                   │
│  Action Executed                                            │
└─────────────────────────────────────────────────────────────┘
```

---

## Graceful Degradation Chain

```
Primary:     Graph RAG (Neo4j) + Hybrid Search
                      ↓ (if Neo4j unavailable)
Fallback 1:  Vector Search Only (LanceDB)
                      ↓ (if vector store unavailable)
Fallback 2:  Web Search Only (Tavily)
                      ↓ (if all retrieval fails)
Fallback 3:  LLM baseline answer with explicit uncertainty warning
                      ↓ (if LLM fails)
Fallback 4:  Escalate to human with "system unavailable" message
```

Each fallback is automatically engaged when the previous level fails.
Never crashes. Always returns a response or escalates appropriately.
