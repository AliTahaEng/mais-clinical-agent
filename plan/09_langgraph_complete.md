# 09 — LangGraph: Complete Graph Definition

## Full Graph — All Nodes, All Edges, All Routes

**File**: `agents/graph.py`

```python
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from agents.state import MedicalAgentState
from agents.nodes import (
    supervisor_node, local_graph_search_node, global_graph_search_node,
    hybrid_search_node, web_search_node, parent_document_node,
    synthesizer_node, quality_checker_node, self_critic_node,
    decision_engine_node, human_approval_node, action_executor_node,
    mandatory_escalation_node, audit_logger_node, feedback_node
)
from agents.routers import (
    route_search, route_quality, route_critic, route_risk
)


def build_medical_agent_graph(container) -> CompiledStateGraph:
    """
    Builds and compiles the complete LangGraph for the Medical AI System.
    All nodes and edges defined here — single source of truth for the flow.
    """

    # ── Build Graph ────────────────────────────────────────────────────────
    graph = StateGraph(MedicalAgentState)

    # ── Register All Nodes ─────────────────────────────────────────────────

    # Phase 2 — Intelligence Layer
    graph.add_node("supervisor",            container.supervisor_node())
    graph.add_node("local_graph_search",    container.local_graph_search_node())
    graph.add_node("global_graph_search",   container.global_graph_search_node())
    graph.add_node("hybrid_search",         container.hybrid_search_node())
    graph.add_node("web_search",            container.web_search_node())
    graph.add_node("parent_document",       container.parent_document_node())
    graph.add_node("synthesizer",           container.synthesizer_node())
    graph.add_node("quality_checker",       container.quality_checker_node())
    graph.add_node("self_critic",           container.self_critic_node())

    # Phase 3 — Action Layer
    graph.add_node("decision_engine",       container.decision_engine_node())
    graph.add_node("human_approval",        container.human_approval_node())
    graph.add_node("action_executor",       container.action_executor_node())
    graph.add_node("mandatory_escalation",  container.mandatory_escalation_node())

    # Infrastructure
    graph.add_node("audit_logger",          container.audit_logger_node())
    graph.add_node("feedback",              container.feedback_node())

    # ── Define All Edges ───────────────────────────────────────────────────

    # Entry point
    graph.add_edge(START, "supervisor")

    # Supervisor → Search agents (conditional — based on search_strategy)
    graph.add_conditional_edges(
        "supervisor",
        route_search,
        {
            "local_graph":         "local_graph_search",
            "global_graph":        "global_graph_search",
            "hybrid":              "hybrid_search",
            "web":                 "web_search",
            # When multiple strategies needed, LangGraph Send API used
            # to fan out in parallel — handled inside route_search
        }
    )

    # All search agents → parent document fetch
    graph.add_edge("local_graph_search",   "parent_document")
    graph.add_edge("global_graph_search",  "parent_document")
    graph.add_edge("hybrid_search",        "parent_document")
    graph.add_edge("web_search",           "parent_document")

    # Parent document → synthesizer
    graph.add_edge("parent_document", "synthesizer")

    # Synthesizer → quality checker (CRAG)
    graph.add_edge("synthesizer", "quality_checker")

    # Quality checker routes (CRAG decision)
    graph.add_conditional_edges(
        "quality_checker",
        route_quality,
        {
            "synthesizer":    "synthesizer",     # ambiguous — try synthesis with same context
            "hybrid_search":  "hybrid_search",   # try different retrieval
            "supervisor":     "supervisor",       # bad — re-plan with web search
        }
    )

    # Self-critic routes (Self-RAG decision)
    graph.add_conditional_edges(
        "self_critic",
        route_critic,
        {
            "decision_engine":  "decision_engine",   # supported — proceed to action
            "synthesizer":      "synthesizer",        # hallucinated — regenerate
            "supervisor":       "supervisor",          # incomplete — get more context
        }
    )

    # Decision engine → risk-based routing
    graph.add_conditional_edges(
        "decision_engine",
        route_risk,
        {
            "action_executor":        "action_executor",        # TIER 1 — low risk
            "human_approval":         "human_approval",         # TIER 2 — medium/high
            "mandatory_escalation":   "mandatory_escalation",   # TIER 3 — critical
            "audit_logger":           "audit_logger",           # no action needed
        }
    )

    # Human approval → either execute or skip based on doctor decision
    graph.add_conditional_edges(
        "human_approval",
        lambda s: "action_executor" if s.get("action_approved") else "audit_logger",
        {
            "action_executor": "action_executor",
            "audit_logger":    "audit_logger",
        }
    )

    # All action paths → audit logger
    graph.add_edge("action_executor",       "audit_logger")
    graph.add_edge("mandatory_escalation",  "audit_logger")

    # Audit logger → feedback → END
    graph.add_edge("audit_logger", "feedback")
    graph.add_edge("feedback", END)

    # ── Compile with Checkpointing ─────────────────────────────────────────
    # PostgreSQL checkpointer enables:
    # - Resume after interrupt (human approval)
    # - Resume after crash
    # - Full state history per session

    checkpointer = AsyncPostgresSaver.from_conn_string(
        container.config().postgres_url()
    )

    return graph.compile(checkpointer=checkpointer)
```

---

## Parallel Execution — Send API

When supervisor decides multiple search strategies are needed, use LangGraph's `Send` API to execute in parallel:

**File**: `agents/routers/search_router.py`

```python
from langgraph.types import Send

def route_search(state: MedicalAgentState):
    """
    Routes to one or more search agents based on supervisor's strategy.
    When multiple strategies — executes them IN PARALLEL via Send API.
    """
    strategy = state.get("search_strategy", ["hybrid"])

    if len(strategy) == 1:
        # Single strategy — simple routing
        strategy_to_node = {
            "local_graph":  "local_graph_search",
            "global_graph": "global_graph_search",
            "hybrid":       "hybrid_search",
            "web":          "web_search",
        }
        return strategy_to_node.get(strategy[0], "hybrid_search")

    # Multiple strategies — parallel execution via Send
    sends = []
    for s in strategy:
        node_name = {
            "local_graph":  "local_graph_search",
            "global_graph": "global_graph_search",
            "hybrid":       "hybrid_search",
            "web":          "web_search",
        }.get(s)
        if node_name:
            sends.append(Send(node_name, state))

    return sends  # LangGraph runs all in parallel, merges state via reducer
```

---

## Complete State Transition Diagram

```
START
  │
  ▼
[supervisor]
  │
  ├──(local_graph)──► [local_graph_search]
  ├──(global_graph)─► [global_graph_search]  } parallel via Send API
  ├──(hybrid)───────► [hybrid_search]
  └──(web)──────────► [web_search]
                            │
                            ▼ (all converge)
                    [parent_document]
                            │
                            ▼
                    [synthesizer]
                            │
                            ▼
                    [quality_checker] ◄─────────────────────────────┐
                            │                                        │
                    good ───┤── ambiguous → [hybrid_search] ────────►│
                            │── bad       → [supervisor] ───────────►│ (loops)
                            │ (good)
                            ▼
                    [self_critic] ◄──────────────────────────────────┐
                            │                                        │
                supported ──┤── hallucinated → [synthesizer] ───────►│
                            │── incomplete   → [supervisor] ─────────►│ (loops)
                            │ (supported)
                            ▼
                    [decision_engine]
                            │
                  no action ┤── low risk    → [action_executor]
                            │── medium/high → [human_approval]
                            │                       │
                            │               approved ┤── rejected
                            │                       │         │
                            │── critical  → [mandatory_escalation]
                            │                       │
                            └───────────────────────┴──────────┐
                                                               ▼
                                                       [audit_logger]
                                                               │
                                                               ▼
                                                       [feedback]
                                                               │
                                                               ▼
                                                             END
```

---

## Session Management

Every query gets a session ID that links to checkpointed state:

```python
# Entry point — starting a new session
async def run_query(query: str, patient_context: dict) -> str:
    session_id = str(uuid4())

    initial_state = {
        "protocol_version": "v1",
        "query": query,
        "trigger_type": "manual",
        "patient_context": patient_context,
        "session_id": session_id,
        "iteration_count": 0,
        "messages": [],
        "reasoning_trace": [],
    }

    config = {"configurable": {"thread_id": session_id}}

    async for event in agent_graph.astream(initial_state, config=config):
        # Stream intermediate results
        pass

    # Get final state
    final_state = await agent_graph.aget_state(config)
    return final_state.values.get("final_answer")


# Resuming after human approval interrupt
async def resume_after_approval(session_id: str, doctor_response: dict) -> str:
    config = {"configurable": {"thread_id": session_id}}

    # This resumes from exactly where the interrupt paused
    async for event in agent_graph.astream(
        Command(resume=doctor_response),
        config=config
    ):
        pass

    final_state = await agent_graph.aget_state(config)
    return final_state.values.get("final_answer")
```

---

## LangGraph Configuration Summary

```python
# Key LangGraph behaviors configured:

# 1. Checkpointing — persist state between nodes (crash recovery + human approval)
checkpointer = AsyncPostgresSaver.from_conn_string(postgres_url)

# 2. Streaming — send partial results to caller as they arrive
graph.astream(state, stream_mode="values")

# 3. Interrupts — pause at human_approval node
# Configured by the human_approval_node calling interrupt()

# 4. Thread isolation — each session is independent
config = {"configurable": {"thread_id": session_id}}

# 5. State reducer — messages list uses operator.add to append, not replace
# Annotated[list, operator.add] in MedicalAgentState

# 6. Recursion limit — prevents infinite loops
graph.compile(recursion_limit=25)  # 25 total node executions per run
```
