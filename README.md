# MAIS — Medical Autonomous Intelligence System

Clinical decision-support agent built on **LangGraph** and a **Neo4j knowledge graph**, with **CRAG / Self-RAG** verification and **human-in-the-loop safety tiers**.

> **Status:** personal research / portfolio prototype (built March 2026). **Not clinically validated and not intended for clinical use.** Evaluation numbers are still to be measured (see *Evaluation and known limitations*).

## Why

Plain vector RAG over medical documents returns fragments with no notion of how entities (conditions, drugs, procedures, guidelines) relate, and it happily answers even when retrieval was poor. MAIS addresses both problems:

- documents are turned into a **knowledge graph** so multi-hop questions can follow relationships instead of matching text;
- every answer passes through a **retrieval-quality gate (CRAG)** and a **fact-checking critic (Self-RAG)** that can trigger re-planning;
- any proposed clinical action is classified into a **safety tier** — auto-execute, human approval, or mandatory escalation — and every decision is written to an **immutable audit trail**.

## Architecture

```
                 ┌────────────────────────────── LangGraph agent (14 nodes) ──────────────────────────────┐
 clinician ─────►│ supervisor ─► graph_search ─┐                                                          │
 question        │              hybrid_search ─┼─► quality_checker (CRAG) ──► synthesizer ─► self_critic   │
                 │              web fallback  ─┘        │ retry / re-plan          (Self-RAG)   │           │
                 │                                       ▼                                       ▼          │
                 │                            decision_engine ─► human_approval ─► action_executor          │
                 │                                   │                │                 │                   │
                 │                                   └──► escalation  └──► feedback     └──► audit_logger   │
                 └──────────────────────────────────────────────────────────────────────────────────────────┘
                                   ▲                         ▲                       ▲
                        Neo4j knowledge graph      LanceDB (BGE-M3) + BM25      PostgreSQL audit trail
                        (Leiden communities)       + MS MARCO cross-encoder     Redis approval queue
```

**Ingestion pipeline** (`medical_ais/pipeline/`): chunking → LLM entity extraction → entity resolution → relationship extraction → graph building in Neo4j → **Leiden** community detection → BGE-M3 embedding into LanceDB.

**Retrieval** (`medical_ais/agent/nodes/`): graph traversal, BM25 keyword search and BGE-M3 dense search run in parallel; candidates are fused with **Reciprocal Rank Fusion** and reranked by an **MS MARCO cross-encoder**; a Tavily web search is the fallback when the CRAG grader rejects local results.

**Safety** (`medical_ais/security/`): capability guard, idempotency manager, input sanitiser; approvals are queued in Redis and every state transition is logged to PostgreSQL.

**Adapters** (`medical_ais/adapters/`): LLM providers (Anthropic Claude, Azure OpenAI, OpenAI), EHR/FHIR R4 input, Neo4j, LanceDB, reranker, BM25, PostgreSQL audit store, Redis cache.

**Frontend** (`frontend/`): Next.js app with a clinician chat UI (Server-Sent Events streaming) and an admin area (dashboard, audit log, graph explorer, ingestion, sessions).

## Key features

- 14-node LangGraph graph with conditional routing, CRAG retry loops, Self-RAG fact-check loops and human-in-the-loop interrupts
- Knowledge-graph construction with entity resolution and Leiden community detection
- Hybrid retrieval (graph + BM25 + dense) with RRF fusion and cross-encoder reranking
- Three-tier clinical action framework with idempotency keys and a Redis-backed approval queue
- Immutable PostgreSQL audit trail for every decision and action
- FastAPI backend with SSE streaming; Next.js clinician and admin dashboards
- Five-service Docker Compose deployment (Neo4j, PostgreSQL, Redis, backend, frontend)

## Tech stack

Python, LangGraph, LangSmith, Anthropic Claude / Azure OpenAI, Neo4j (Cypher), LanceDB, BGE-M3 (Sentence Transformers), rank-bm25, MS MARCO cross-encoder, Tavily, FastAPI, Pydantic, Structlog, PostgreSQL, Redis, Next.js, TypeScript, Docker Compose.

## Running locally

Requirements: Docker Desktop, an LLM API key (Anthropic or Azure OpenAI), optionally a Tavily key.

```bash
git clone https://github.com/AliTahaEng/mais-clinical-agent
cd mais-clinical-agent

# 1. Backend configuration — the compose file reads ./medical_ais/.env
#    Create it with the variables defined in medical_ais/config/settings.py
#    (LLM provider + key, Neo4j / PostgreSQL / Redis URLs, Tavily key).
cp medical_ais/.env.example medical_ais/.env   # if the example file exists; otherwise create it by hand

# 2. Start everything (Neo4j, PostgreSQL, Redis, backend, frontend)
docker compose up --build

# 3. Open the UI
#    frontend: http://localhost:3000   backend API: http://localhost:8000/docs
```

Ingest documents from the admin *Ingest* page (or via the pipeline runner in `medical_ais/pipeline/runner.py`), then ask questions in the clinician UI.

### Tests

```bash
cd medical_ais
pip install -r requirements.txt
pytest tests/
```

## Project structure

```
medical_ais/
  adapters/      llm, ehr/fhir, graph_db/neo4j, vector_store/lancedb, reranker, search/bm25, storage
  agent/         graph.py (node wiring), state.py, routers.py, nodes/ (12 node modules), prompts/
  api/           FastAPI routes, SSE streaming
  pipeline/      chunking, entity_extractor, entity_resolver, graph_builder, community_detector, embedder, runner
  security/      capability_guard, idempotency_manager, input_sanitizer
  services/      approval_store and application services
  tests/         pytest suite
frontend/        Next.js (clinician UI + admin area)
docker-compose.yml
```

## Evaluation and known limitations

- **No clinical validation.** The system has not been evaluated by clinicians or against a clinical benchmark; outputs must not be used for patient care.
- **Evaluation numbers pending.** Planned metrics: retrieval recall@k and MRR on a held-out question set, answer faithfulness (LLM-judge calibrated against human labels), CRAG rejection rate, and tier-classifier agreement with human labels.
- **Audit trail is a pattern, not a certification.** The immutable log follows a HIPAA-style audit-trail design; no compliance claim is made.
- Requires paid LLM APIs; there is no offline model option yet.
- The previous public demo URL has been removed; run locally with Docker Compose.

## Roadmap

- [ ] Build a small evaluation harness (question set, recall@k, faithfulness) and publish the numbers here
- [ ] Add screenshots / a short demo video
- [ ] Optional open-weight LLM backend (vLLM) for on-prem deployment
- [ ] Ingest FHIR R4 resources end-to-end (Patient / Observation) with PHI redaction before LLM calls

## Screenshots

_Coming soon — clinician chat with streaming answer and citations; admin graph explorer; audit log._

## License

MIT — see `LICENSE`.
