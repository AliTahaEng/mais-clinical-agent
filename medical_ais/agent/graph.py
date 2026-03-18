"""
LangGraph computation graph — wires all nodes and edges together.
This is the main entry point for processing a medical query.

Architecture:
  supervisor → [parallel: local_graph_search, global_graph_search, hybrid_search]
             → quality_checker → (CRAG routing)
             → synthesizer → self_critic → (Self-RAG routing)
             → decision_engine → (action routing)
             → [human_approval | mandatory_escalation | action_executor]
             → audit_logger → END
"""
from __future__ import annotations

import functools
import uuid
from typing import Any

import structlog
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, StateGraph

from medical_ais.agent.nodes.action_executor import action_executor_node
from medical_ais.agent.nodes.audit_logger import audit_logger_node
from medical_ais.agent.nodes.decision_engine import decision_engine_node
from medical_ais.agent.nodes.escalation import mandatory_escalation_node
from medical_ais.agent.nodes.feedback import feedback_node
from medical_ais.agent.nodes.graph_search import (
    global_graph_search_node,
    local_graph_search_node,
)
from medical_ais.agent.nodes.human_approval import human_approval_node
from medical_ais.agent.nodes.hybrid_search import hybrid_search_node, web_search_node
from medical_ais.agent.nodes.quality_checker import quality_checker_node
from medical_ais.agent.nodes.self_critic import self_critic_node
from medical_ais.agent.nodes.supervisor import supervisor_node
from medical_ais.agent.nodes.synthesizer import synthesizer_node
from medical_ais.agent.routers import (
    route_after_action_executor,
    route_after_decision_engine,
    route_after_human_approval,
    route_after_quality_check,
    route_after_self_critic,
)
from medical_ais.agent.state import MedicalAgentState

logger = structlog.get_logger(__name__)


def build_graph(
    *,
    llm,
    classifier_llm,
    graph_db,
    vector_store,
    search_engine,
    embedding_model,
    reranker,
    ehr_client,
    tool_registry,
    audit_store,
    idempotency_manager,
    settings,
    approval_store=None,
) -> StateGraph:
    """
    Construct and compile the LangGraph StateGraph.
    All dependencies are injected — no global state.
    """
    graph = StateGraph(MedicalAgentState)

    # ── Node registration ─────────────────────────────────────────────────────
    # Each node is a partial that binds its dependencies at build time.

    graph.add_node(
        "supervisor",
        functools.partial(
            supervisor_node,
            llm=llm,
            max_iterations=settings.max_iterations,
        ),
    )

    graph.add_node(
        "local_graph_search",
        functools.partial(
            local_graph_search_node,
            graph_db=graph_db,
            max_hops=settings.max_hops,
        ),
    )

    graph.add_node(
        "global_graph_search",
        functools.partial(global_graph_search_node, graph_db=graph_db),
    )

    graph.add_node(
        "hybrid_search",
        functools.partial(
            hybrid_search_node,
            vector_store=vector_store,
            search_engine=search_engine,
            embedding_model=embedding_model,
            reranker=reranker,
            top_k=settings.top_k_retrieval,
        ),
    )

    graph.add_node(
        "web_search",
        functools.partial(
            web_search_node,
            tavily_api_key=settings.tavily_api_key,
        ),
    )

    graph.add_node(
        "quality_checker",
        functools.partial(quality_checker_node, llm=classifier_llm),
    )

    graph.add_node(
        "synthesizer",
        functools.partial(synthesizer_node, llm=llm, ehr_client=ehr_client),
    )

    graph.add_node(
        "self_critic",
        functools.partial(self_critic_node, llm=classifier_llm),
    )

    graph.add_node(
        "decision_engine",
        functools.partial(
            decision_engine_node,
            llm=llm,
            tool_registry=tool_registry,
            confidence_threshold=settings.confidence_threshold,
            enable_action_execution=settings.enable_action_execution,
        ),
    )

    graph.add_node(
        "human_approval",
        functools.partial(human_approval_node, approval_store=approval_store),
    )
    graph.add_node("mandatory_escalation", mandatory_escalation_node)

    graph.add_node(
        "action_executor",
        functools.partial(
            action_executor_node,
            tool_registry=tool_registry,
            idempotency_manager=idempotency_manager,
        ),
    )

    graph.add_node(
        "audit_logger",
        functools.partial(audit_logger_node, audit_store=audit_store),
    )

    graph.add_node("feedback", feedback_node)

    # ── Edges ─────────────────────────────────────────────────────────────────

    # Entry
    graph.set_entry_point("supervisor")

    # Supervisor → parallel retrieval fan-out
    graph.add_edge("supervisor", "local_graph_search")
    graph.add_edge("supervisor", "global_graph_search")
    graph.add_edge("supervisor", "hybrid_search")

    # Parallel retrieval → quality checker (all must complete first)
    graph.add_edge("local_graph_search", "quality_checker")
    graph.add_edge("global_graph_search", "quality_checker")
    graph.add_edge("hybrid_search", "quality_checker")

    # CRAG routing
    graph.add_conditional_edges(
        "quality_checker",
        route_after_quality_check,
        {
            "web_search": "web_search",
            "supervisor": "supervisor",
            "synthesizer": "synthesizer",
            "audit_logger": "audit_logger",
        },
    )

    # Web search always feeds synthesizer
    graph.add_edge("web_search", "synthesizer")

    # Self-RAG routing
    graph.add_edge("synthesizer", "self_critic")
    graph.add_conditional_edges(
        "self_critic",
        route_after_self_critic,
        {
            "supervisor": "supervisor",
            "decision_engine": "decision_engine",
        },
    )

    # Action routing
    graph.add_conditional_edges(
        "decision_engine",
        route_after_decision_engine,
        {
            "mandatory_escalation": "mandatory_escalation",
            "human_approval": "human_approval",
            "action_executor": "action_executor",
            "audit_logger": "audit_logger",
        },
    )

    # Human approval → executor or audit
    graph.add_conditional_edges(
        "human_approval",
        route_after_human_approval,
        {
            "action_executor": "action_executor",
            "audit_logger": "audit_logger",
        },
    )

    # Mandatory escalation always ends (interrupt handles the pause)
    graph.add_edge("mandatory_escalation", "audit_logger")

    # Post-execution routing
    graph.add_conditional_edges(
        "action_executor",
        route_after_action_executor,
        {
            "feedback": "feedback",
            "audit_logger": "audit_logger",
        },
    )

    graph.add_edge("feedback", "audit_logger")
    graph.add_edge("audit_logger", END)

    return graph


def compile_graph(
    graph: StateGraph,
    checkpointer=None,
    interrupt_before: list[str] | None = None,
    interrupt_after: list[str] | None = None,
):
    """Compile the graph with optional checkpointing and interrupts."""
    return graph.compile(
        checkpointer=checkpointer,
        interrupt_before=interrupt_before or [],
        interrupt_after=interrupt_after or [],
    )


async def run_query(
    compiled_graph,
    query: str,
    *,
    patient_id: str | None = None,
    session_id: str | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    """
    Execute a single query through the compiled graph.
    Returns the final state.
    """
    sid = session_id or str(uuid.uuid4())
    initial_state = MedicalAgentState(
        query=query,
        patient_id=patient_id,
        session_id=sid,
        user_id=user_id,
        messages=[HumanMessage(content=query)],
        retrieved_chunks=[],
        graph_context="",
        community_context="",
        current_plan="",
        sub_queries=[],
        iteration=0,
        retrieval_quality=0.0,
        needs_web_search=False,
        draft_answer="",
        fact_check_passed=False,
        fact_check_issues=[],
        final_answer="",
        confidence_score=0.0,
        proposed_actions=[],
        approved_actions=[],
        executed_actions=[],
        requires_human_approval=False,
        human_feedback=None,
        error=None,
        escalated=False,
    )

    # Use user_id as checkpoint namespace to isolate each user's history
    config = {
        "configurable": {"thread_id": sid, "checkpoint_ns": user_id or ""},
        "recursion_limit": 25,
    }

    logger.info("graph.run_start", session_id=sid, query=query[:100])
    final_state = await compiled_graph.ainvoke(initial_state, config=config)
    logger.info("graph.run_complete", session_id=sid)
    return final_state
