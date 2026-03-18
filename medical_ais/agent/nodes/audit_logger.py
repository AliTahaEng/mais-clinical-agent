"""
Audit logger node — records every agent action in the append-only audit trail.
"""
from __future__ import annotations

from datetime import datetime

import structlog

from medical_ais.agent.state import MedicalAgentState
from medical_ais.interfaces.audit import AuditRecord, IAuditStore

logger = structlog.get_logger(__name__)


async def audit_logger_node(
    state: MedicalAgentState,
    *,
    audit_store: IAuditStore,
) -> dict:
    """
    Write a comprehensive audit record for this session's execution.
    Called at the end of every run — whether or not actions were taken.
    """
    executed = state.get("executed_actions", [])

    record = AuditRecord(
        event_type="session.completed",
        agent_id="mais_system",
        session_id=state.get("session_id", ""),
        user_id=state.get("user_id") or "",
        payload={
            "query": state.get("query", ""),
            "patient_id": state.get("patient_id"),
            "user_id": state.get("user_id"),
            "confidence_score": state.get("confidence_score", 0.0),
            "fact_check_passed": state.get("fact_check_passed", True),
            "fact_check_issues": state.get("fact_check_issues", []),
            "iterations": state.get("iteration", 0),
            "retrieval_quality": state.get("retrieval_quality", 0.0),
            "chunks_retrieved": len(state.get("retrieved_chunks", [])),
            "actions_proposed": len(state.get("proposed_actions", [])),
            "actions_executed": len(executed),
            "escalated": state.get("escalated", False),
            "requires_human_approval": state.get("requires_human_approval", False),
            "final_answer_length": len(state.get("final_answer", "")),
        },
        timestamp=datetime.utcnow(),
        idempotency_key=f"session:{state.get('session_id', '')}:completed",
    )

    try:
        await audit_store.record(record)
        logger.info("audit_logger.recorded", session_id=record.session_id)
    except Exception as exc:
        logger.error("audit_logger.failed", error=str(exc))

    # Log each executed action separately
    for action in executed:
        action_record = AuditRecord(
            event_type="action.executed",
            agent_id="action_agent",
            session_id=state.get("session_id", ""),
            payload=action,
            timestamp=datetime.utcnow(),
            idempotency_key=f"action:{state.get('session_id', '')}:{action.get('tool', '')}",
        )
        try:
            await audit_store.record(action_record)
        except Exception:
            pass  # Best-effort for individual action records

    return {}  # Audit node doesn't modify state
