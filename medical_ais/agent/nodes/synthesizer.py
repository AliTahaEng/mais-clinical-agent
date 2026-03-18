"""
Synthesizer node — composes the final answer from all retrieved evidence.
"""
from __future__ import annotations

import json

import structlog
from langchain_core.messages import AIMessage

from medical_ais.agent.prompts.synthesizer_prompt import SYNTHESIZER_HUMAN, SYNTHESIZER_SYSTEM
from medical_ais.agent.state import MedicalAgentState, ProposedAction
from medical_ais.interfaces.ehr import IEHRClient
from medical_ais.interfaces.llm import ILLMProvider, LLMMessage

logger = structlog.get_logger(__name__)


async def synthesizer_node(
    state: MedicalAgentState,
    *,
    llm: ILLMProvider,
    ehr_client: IEHRClient | None = None,
) -> dict:
    """
    Build a comprehensive answer from all retrieved evidence.
    Produces draft_answer, confidence_score, and proposed_actions.
    """
    # Build context text from retrieved chunks
    chunks = state.get("retrieved_chunks", [])
    context_parts = [
        f"[Source {i+1}] ({c['source']}, score={c['score']:.2f})\n{c['text']}"
        for i, c in enumerate(chunks[:15])
    ]
    context = "\n\n---\n\n".join(context_parts)

    # Get patient info if available
    patient_info = "No patient record available."
    if state.get("patient_id") and ehr_client:
        try:
            from medical_ais.interfaces.ehr import PatientRecord
            patient = await ehr_client.get_patient(state["patient_id"])
            patient_info = (
                f"Patient: {patient.name} (DOB: {patient.date_of_birth})\n"
                f"Conditions: {', '.join(patient.conditions) or 'None'}\n"
                f"Medications: {', '.join(patient.medications) or 'None'}\n"
                f"Allergies: {', '.join(patient.allergies) or 'None'}\n"
                f"Labs: {json.dumps(patient.lab_values, indent=2)}"
            )
        except Exception as exc:
            logger.warning("synthesizer.ehr_fetch_failed", error=str(exc))

    messages = [
        LLMMessage(role="system", content=SYNTHESIZER_SYSTEM),
        LLMMessage(
            role="human",
            content=SYNTHESIZER_HUMAN.format(
                query=state["query"],
                context=context or "No context retrieved.",
                graph_context=state.get("graph_context") or "None",
                community_context=state.get("community_context") or "None",
                patient_info=patient_info,
            ),
        ),
    ]

    try:
        result = await llm.complete_json(messages, temperature=0.1, max_tokens=4096)
    except Exception as exc:
        logger.error("synthesizer.llm_error", error=str(exc))
        return {
            "draft_answer": f"Unable to synthesize answer due to error: {exc}",
            "confidence_score": 0.0,
            "proposed_actions": [],
        }

    draft_answer = result.get("answer", "No answer generated.")
    confidence = float(result.get("confidence_score", 0.5))

    # Parse proposed actions
    proposed_actions: list[ProposedAction] = []
    for action in result.get("proposed_actions", []):
        if action.get("tool_name"):
            import hashlib, json as _json
            ikey = hashlib.sha256(
                _json.dumps({"tool": action["tool_name"], "params": action.get("parameters", {})}, sort_keys=True).encode()
            ).hexdigest()
            proposed_actions.append(
                ProposedAction(
                    tool_name=action["tool_name"],
                    parameters=action.get("parameters", {}),
                    tier=int(action.get("tier", 1)),
                    rationale=action.get("rationale", ""),
                    idempotency_key=ikey,
                )
            )

    logger.info(
        "synthesizer.done",
        confidence=confidence,
        actions=len(proposed_actions),
        answer_len=len(draft_answer),
    )

    return {
        "draft_answer": draft_answer,
        "confidence_score": confidence,
        "proposed_actions": proposed_actions,
        "messages": [AIMessage(content=draft_answer)],
    }
