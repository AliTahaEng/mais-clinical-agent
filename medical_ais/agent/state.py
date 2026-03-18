"""
LangGraph agent state definition.
Single TypedDict flows through the entire computation graph.
Nodes read from and write to this state — never to each other directly.
"""
from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


# ── Retrieval result container ─────────────────────────────────────────────────

class RetrievedChunk(TypedDict):
    id: str
    text: str
    score: float
    source: str          # "graph_local" | "graph_global" | "vector" | "bm25" | "web"
    metadata: dict


# ── Proposed action container ──────────────────────────────────────────────────

class ProposedAction(TypedDict):
    tool_name: str
    parameters: dict[str, Any]
    tier: int            # 1 | 2 | 3
    rationale: str
    idempotency_key: str


# ── Main agent state ───────────────────────────────────────────────────────────

class MedicalAgentState(TypedDict):
    # ── Input ─────────────────────────────────────────────────────────────────
    query: str
    patient_id: str | None
    session_id: str
    user_id: str | None          # Authenticated user ID (None for legacy/anonymous)

    # ── Conversation messages (LangGraph reducer appends new messages) ─────────
    messages: Annotated[list[BaseMessage], add_messages]

    # ── Retrieval ─────────────────────────────────────────────────────────────
    # operator.add reducer: lets 3 parallel search nodes write concurrently —
    # LangGraph concatenates their lists instead of raising INVALID_CONCURRENT_GRAPH_UPDATE.
    retrieved_chunks: Annotated[list[RetrievedChunk], operator.add]
    graph_context: str             # Serialised entity/relationship text
    community_context: str         # Community summary text

    # ── Reasoning ─────────────────────────────────────────────────────────────
    current_plan: str              # Supervisor's decomposed plan
    sub_queries: list[str]         # Parallel sub-questions for search agents
    iteration: int                 # Current reasoning loop count
    retrieval_quality: float       # CRAG score 0.0–1.0
    needs_web_search: bool         # CRAG flag: fall back to web

    # ── Answer generation ──────────────────────────────────────────────────────
    draft_answer: str              # Synthesizer's output
    fact_check_passed: bool        # Self-RAG verdict
    fact_check_issues: list[str]   # Claims that failed fact-check
    final_answer: str              # Final answer delivered to user

    # ── Action layer ──────────────────────────────────────────────────────────
    confidence_score: float        # Overall answer confidence 0.0–1.0
    proposed_actions: list[ProposedAction]
    approved_actions: list[ProposedAction]   # After human review
    executed_actions: list[dict]             # Results of executed tools
    requires_human_approval: bool
    human_feedback: str | None     # Feedback from human approval node

    # ── Control flow ──────────────────────────────────────────────────────────
    error: str | None              # Set by any node on unrecoverable error
    escalated: bool                # True when routed to mandatory escalation
