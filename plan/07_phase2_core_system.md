# 07 — Phase 2: Core Intelligence System

## Purpose
Build the LangGraph agent system that queries the knowledge graph, reasons across retrieved context, self-corrects, and produces verified answers with citations and confidence scores.

---

## The Six Components of Phase 2

```
1. Supervisor Node       → plan the retrieval strategy
2. Search Agents         → retrieve from graph, vector, BM25, web (parallel)
3. Parent Document Node  → fetch full context
4. Synthesizer Node      → merge all context, draft answer
5. Quality Checker (CRAG) → verify retrieval quality, loop if bad
6. Self-Critic (Self-RAG) → verify answer is grounded, loop if hallucinated
```

---

## The LangGraph State (Single Source of Truth)

**File**: `agents/state.py`

```python
from typing_extensions import TypedDict, Annotated
from typing import Literal
import operator

class MedicalAgentState(TypedDict):
    # Protocol
    protocol_version: str                   # "v1"

    # Input
    query: str                              # original question or trigger description
    trigger_type: str                       # "manual" | "prescription" | "lab" | "vital"
    patient_context: dict                   # age, conditions, medications, allergies

    # Session
    session_id: str                         # LangGraph thread ID for checkpointing
    iteration_count: int                    # loop guard — max 5

    # Planning (set by supervisor)
    query_type: Literal[
        "entity", "relationship", "corpus", "simple", "realtime"
    ]
    reasoning_plan: list[str]               # step-by-step plan
    search_strategy: list[str]              # which agents to call

    # Retrieval (set by search agents)
    graph_entities: list[dict]              # from local graph search
    graph_relationships: list[dict]         # from relationship traversal
    community_reports: list[dict]           # from global graph search
    vector_chunks: list[dict]               # from hybrid search
    web_results: list[dict]                 # from web search
    parent_chunks: list[dict]               # fetched full-context chunks

    # Quality Control
    retrieval_quality: Literal["good", "ambiguous", "bad"] | None
    retrieval_quality_reason: str           # why quality was rated this way

    # Answer
    answer_draft: str                       # synthesizer draft
    answer_supported: bool | None           # self-RAG verdict
    hallucinated_claims: list[str]          # claims self-RAG flagged
    missing_info: list[str]                 # what self-RAG says is missing

    # Final Output
    final_answer: str
    confidence_score: float                 # 0.0 - 1.0
    sources: list[str]                      # citations
    reasoning_trace: list[dict]             # every step for explainability

    # Action (set in Phase 3)
    actionable_finding: bool
    action_type: str
    action_payload: dict
    risk_level: str
    action_approved: bool
    action_executed: bool
    approved_by: str
    human_override_reason: str

    # Audit
    audit_recorded: bool
    messages: Annotated[list, operator.add]  # conversation history
```

---

## Node 1: Supervisor Node

**File**: `agents/nodes/supervisor_node.py`

**Responsibility**: Classify query → build plan → decide search strategy.

```python
class SupervisorNode:
    def __init__(self, llm: ILLMProvider, config: Settings):
        self._llm = llm
        self._config = config

    async def __call__(self, state: MedicalAgentState) -> dict:
        # Guard: prevent infinite loops
        if state.get("iteration_count", 0) >= self._config.max_iterations:
            return {
                "final_answer": "Maximum reasoning iterations reached. Please rephrase your query.",
                "confidence_score": 0.0,
                "iteration_count": state.get("iteration_count", 0)
            }

        response = await self._llm.generate_response(
            system=SUPERVISOR_PROMPT,
            user=f"Query: {state['query']}\nPatient context: {state['patient_context']}\n"
                 f"Previous iteration note: {state.get('retrieval_quality_reason', 'First attempt')}"
        )

        parsed = SupervisorOutput.model_validate_json(response)

        return {
            "query_type": parsed.query_type,
            "reasoning_plan": parsed.reasoning_plan,
            "search_strategy": parsed.search_strategy,
            "iteration_count": state.get("iteration_count", 0) + 1,
            "reasoning_trace": state.get("reasoning_trace", []) + [{
                "step": "supervisor",
                "iteration": state.get("iteration_count", 0) + 1,
                "plan": parsed.reasoning_plan
            }]
        }
```

**Supervisor Prompt** (`agents/prompts/supervisor_prompt.py`):
```python
SUPERVISOR_PROMPT = """
You are a medical query planning expert for an AI clinical decision support system.

Given a medical query and patient context, you must:

1. Classify query_type as ONE of:
   - "entity"       : asks about a specific drug, disease, or medical entity
   - "relationship" : asks how entities connect (interaction, causation, mechanism)
   - "corpus"       : asks for synthesis across medical literature
   - "simple"       : simple factual question, likely no retrieval needed
   - "realtime"     : needs current/recent data (latest guidelines, recent trials)

2. Build a step-by-step reasoning_plan (2-5 steps)

3. Select search_strategy — list of agents to call:
   - "local_graph"  : for entity and relationship queries
   - "global_graph" : for corpus-wide synthesis
   - "hybrid"       : always include for semantic + keyword coverage
   - "web"          : only for realtime queries or when previous retrieval was bad

Output valid JSON:
{
  "query_type": "...",
  "reasoning_plan": ["step 1", "step 2", ...],
  "search_strategy": ["local_graph", "hybrid"]
}
"""
```

---

## Node 2: Local Graph Search Node

**File**: `agents/nodes/local_graph_search_node.py`

**Responsibility**: Find entities in Neo4j and traverse their relationships.

```python
class LocalGraphSearchNode:
    def __init__(self, graph_db: IGraphDB, embedding_model: IEmbeddingModel,
                 vector_store: IVectorStore, config: Settings):
        self._graph_db = graph_db
        self._embedding_model = embedding_model
        self._vector_store = vector_store
        self._config = config

    async def __call__(self, state: MedicalAgentState) -> dict:
        query = state["query"]
        query_type = state["query_type"]

        # Step 1: Find candidate entities via vector similarity
        query_embedding = await self._embedding_model.embed_text(query)
        candidate_entities = await self._vector_store.similarity_search(
            embedding=query_embedding,
            filter={"type": "entity"},
            top_k=5
        )

        all_entities = []
        all_relationships = []

        for entity in candidate_entities:
            # Step 2: Get entity details from graph
            entity_data = await self._graph_db.get_entity(entity["name"])
            if entity_data:
                all_entities.append(entity_data)

            # Step 3: Traverse relationships (depth depends on query type)
            hops = 2 if query_type == "relationship" else 1
            rels = await self._graph_db.traverse(entity["name"], hops=hops)
            all_relationships.extend(rels)

            # Step 4: For relationship queries, find path between entity pairs
            if query_type == "relationship" and len(candidate_entities) >= 2:
                path = await self._graph_db.find_shortest_path(
                    candidate_entities[0]["name"],
                    candidate_entities[1]["name"]
                )
                if path:
                    all_relationships.extend(path)

        return {
            "graph_entities": all_entities,
            "graph_relationships": all_relationships,
            "reasoning_trace": state.get("reasoning_trace", []) + [{
                "step": "local_graph_search",
                "entities_found": len(all_entities),
                "relationships_found": len(all_relationships)
            }]
        }
```

---

## Node 3: Global Graph Search Node

**File**: `agents/nodes/global_graph_search_node.py`

**Responsibility**: Retrieve community reports for corpus-wide synthesis.

```python
async def __call__(self, state: MedicalAgentState) -> dict:
    query = state["query"]

    # Search community report embeddings
    query_embedding = await self._embedding_model.embed_text(query)
    community_hits = await self._vector_store.similarity_search(
        embedding=query_embedding,
        filter={"type": "community_report"},
        top_k=5
    )

    # Fetch full community reports
    reports = []
    for hit in community_hits:
        report = await self._community_store.get(hit["community_id"])
        if report:
            reports.append({
                "community_id": hit["community_id"],
                "level": hit["level"],
                "summary": report["summary"],
                "relevance_score": hit["score"]
            })

    return {"community_reports": reports}
```

---

## Node 4: Hybrid Search Node

**File**: `agents/nodes/hybrid_search_node.py`

**Responsibility**: BM25 keyword + vector semantic search + reranking.

```python
async def __call__(self, state: MedicalAgentState) -> dict:
    query = state["query"]

    # Run BM25 and vector search in parallel
    bm25_results, vector_results = await asyncio.gather(
        self._search_engine.keyword_search(query, top_k=20),
        self._vector_store.similarity_search(
            embedding=await self._embedding_model.embed_text(query),
            filter={"type": "chunk"},
            top_k=20
        )
    )

    # Reciprocal Rank Fusion
    fused = self._reciprocal_rank_fusion(bm25_results, vector_results, top_k=20)

    # Rerank with cross-encoder
    reranked = await self._reranker.rerank(query, fused, top_k=10)

    return {"vector_chunks": reranked}

def _reciprocal_rank_fusion(self, list1, list2, top_k=20, k=60) -> list:
    scores = {}
    for rank, doc in enumerate(list1):
        scores[doc["id"]] = scores.get(doc["id"], 0) + 1 / (k + rank + 1)
    for rank, doc in enumerate(list2):
        scores[doc["id"]] = scores.get(doc["id"], 0) + 1 / (k + rank + 1)
    sorted_ids = sorted(scores, key=scores.get, reverse=True)[:top_k]
    # Return merged documents in fused rank order
    all_docs = {d["id"]: d for d in list1 + list2}
    return [all_docs[doc_id] for doc_id in sorted_ids if doc_id in all_docs]
```

---

## Node 5: Parent Document Node

**File**: `agents/nodes/parent_document_node.py`

**Responsibility**: Fetch full parent chunks for matched child chunks.

```python
async def __call__(self, state: MedicalAgentState) -> dict:
    child_chunks = state.get("vector_chunks", [])
    parent_chunks = []
    seen_parent_ids = set()

    for chunk in child_chunks:
        parent_id = chunk.get("parent_chunk_id")
        if parent_id and parent_id not in seen_parent_ids:
            parent = await self._vector_store.get_by_id(parent_id)
            if parent:
                parent_chunks.append(parent)
                seen_parent_ids.add(parent_id)

    return {"parent_chunks": parent_chunks}
```

---

## Node 6: Synthesizer Node

**File**: `agents/nodes/synthesizer_node.py`

**Responsibility**: Merge all retrieved context and draft an answer.

```python
SYNTHESIZER_PROMPT = """
You are a medical clinical decision support AI.

Based on the retrieved medical evidence below, answer the query.

REQUIREMENTS:
1. Every factual claim MUST be supported by the retrieved evidence
2. Include inline citations [Source: document_id]
3. If evidence is insufficient, say so explicitly — do NOT speculate
4. Structure: Finding → Evidence → Clinical Implication
5. End with a confidence level: HIGH | MEDIUM | LOW and why

Query: {query}
Patient Context: {patient_context}

Retrieved Evidence:
{context}
"""

async def __call__(self, state: MedicalAgentState) -> dict:
    context = self._format_all_context(state)
    response = await self._llm.generate_response(
        system=SYNTHESIZER_PROMPT.format(
            query=state["query"],
            patient_context=state["patient_context"],
            context=context
        )
    )
    return {"answer_draft": response}
```

---

## Node 7: Quality Checker Node (CRAG)

**File**: `agents/nodes/quality_checker_node.py`

**Responsibility**: Evaluate if retrieved context is good enough. If not, signal the router to loop back.

```python
QUALITY_CHECKER_PROMPT = """
You are a medical retrieval quality evaluator.

Given a medical query and the retrieved evidence, assess retrieval quality:

- "good"      : Evidence directly and comprehensively addresses the query
- "ambiguous" : Evidence is partially relevant but may be insufficient
- "bad"       : Evidence is irrelevant, empty, or clearly wrong for this query

Output JSON: {"quality": "good|ambiguous|bad", "reason": "explanation", "missing": "what is missing"}
"""

async def __call__(self, state: MedicalAgentState) -> dict:
    context_summary = self._summarize_retrieved_context(state)

    response = await self._llm.generate_response(
        system=QUALITY_CHECKER_PROMPT,
        user=f"Query: {state['query']}\n\nRetrieved Context Summary:\n{context_summary}"
    )

    result = QualityCheckResult.model_validate_json(response)

    return {
        "retrieval_quality": result.quality,
        "retrieval_quality_reason": result.reason,
    }
```

---

## Node 8: Self-Critic Node (Self-RAG)

**File**: `agents/nodes/self_critic_node.py`

**Responsibility**: Verify every claim in the draft answer is grounded in retrieved evidence.

```python
SELF_CRITIC_PROMPT = """
You are a medical factuality checker.

Given a query, retrieved evidence, and a draft answer:

Check EVERY factual claim in the answer:
1. Is it directly supported by the retrieved evidence?
2. Is it consistent with the patient context?
3. Are there any claims made without evidence?

Verdict:
- "supported"    : all claims traceable to retrieved evidence
- "hallucinated" : one or more claims NOT supported by evidence
- "incomplete"   : supported but misses critical information present in evidence

Output JSON:
{
  "verdict": "supported|hallucinated|incomplete",
  "hallucinated_claims": ["claim 1 that has no evidence"],
  "missing_info": ["important info in evidence not included in answer"],
  "confidence": 0.0-1.0
}
"""

async def __call__(self, state: MedicalAgentState) -> dict:
    context = self._format_all_context(state)
    response = await self._llm.generate_response(
        system=SELF_CRITIC_PROMPT,
        user=f"""
Query: {state['query']}
Patient Context: {state['patient_context']}

Retrieved Evidence:
{context}

Draft Answer:
{state['answer_draft']}
        """
    )

    result = SelfCriticResult.model_validate_json(response)

    if result.verdict == "supported":
        return {
            "answer_supported": True,
            "final_answer": state["answer_draft"],
            "confidence_score": result.confidence,
            "sources": self._extract_citations(state["answer_draft"])
        }
    else:
        return {
            "answer_supported": False,
            "hallucinated_claims": result.hallucinated_claims,
            "missing_info": result.missing_info,
        }
```

---

## Routing Logic

**File**: `agents/routers/`

```python
# quality_router.py
def route_quality(state: MedicalAgentState) -> str:
    quality = state.get("retrieval_quality")
    iterations = state.get("iteration_count", 0)

    if iterations >= 5:
        return "synthesizer"       # force forward after max iterations
    if quality == "good":
        return "synthesizer"
    elif quality == "ambiguous":
        return "hybrid_search"     # try better retrieval
    else:  # "bad"
        return "supervisor"        # re-plan with web search added

# critic_router.py
def route_critic(state: MedicalAgentState) -> str:
    if state.get("answer_supported"):
        return "decision_engine"   # proceed to action layer

    iterations = state.get("iteration_count", 0)
    if iterations >= 5:
        return "decision_engine"   # force forward with low confidence

    if state.get("missing_info"):
        return "supervisor"        # need more information
    else:
        return "synthesizer"       # regenerate with same context
```

---

## Phase 2 Verification Checklist

Before moving to Phase 3, verify:
- [ ] Supervisor correctly classifies entity vs relationship vs corpus queries
- [ ] Local graph search returns connected entities with correct hop depth
- [ ] Hybrid search fusion returns better results than either BM25 or vector alone
- [ ] Parent document fetch returns correct parent for each child chunk
- [ ] Synthesizer produces answers with inline citations
- [ ] CRAG correctly rates bad retrieval and triggers loop back
- [ ] Self-RAG correctly identifies hallucinated claims in test cases
- [ ] Loop guard prevents infinite iteration (test with unanswerable query)
- [ ] Full flow handles: drug interaction query → multi-hop → synthesized answer with sources
