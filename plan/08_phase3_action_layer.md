# 08 — Phase 3: Action Layer

## Purpose
Take the verified answer from Phase 2 and determine if action is needed, what that action is, what risk level it carries, execute it through the correct tier (auto / approval / escalation), log everything, and track outcomes.

---

## The Three-Tier Safety Model

This is the most critical design decision in the entire system. Never deviate from it.

```
TIER 1 — LOW RISK    → Auto-execute. Log. Notify after.
TIER 2 — MEDIUM RISK → Propose to doctor. Show full reasoning. Wait for approval.
TIER 3 — HIGH/CRITICAL → Alert immediately. Block action. Human MUST act.

OVERRIDE: confidence < 0.80 → always escalate to TIER 2 minimum, regardless of risk level
```

---

## Node 1: Decision Engine Node

**File**: `agents/nodes/decision_engine_node.py`

**Responsibility**: Read the verified answer. Extract what action (if any) should be taken. Classify risk level.

```python
DECISION_ENGINE_PROMPT = """
You are a medical action decision expert.

Given a verified medical analysis, determine:

1. actionable_finding: true/false
   - true only if the analysis reveals something that requires clinical action
   - false for purely informational answers

2. action_type: "inform" | "recommend" | "urgent" | "critical"
   - inform    : log or send informational alert (low risk)
   - recommend : suggest care plan change, needs doctor approval (medium risk)
   - urgent    : potential patient harm if not addressed soon (high risk)
   - critical  : immediate danger, irreversible consequence possible

3. action_description: exactly what should be done

4. action_payload: structured data for the action (patient_id, drug_name, etc.)

5. risk_level: "low" | "medium" | "high" | "critical"
   - low:      informational, fully reversible
   - medium:   modifies care recommendation, needs doctor review
   - high:     potential patient harm if missed
   - critical: immediate safety risk, irreversible if delayed

6. urgency_hours: how many hours before this becomes critical (null if not time-sensitive)

Output valid JSON only.
"""

async def __call__(self, state: MedicalAgentState) -> dict:
    # If confidence is too low, force human review regardless of risk
    if state.get("confidence_score", 0) < 0.80:
        return {
            "actionable_finding": True,
            "action_type": "recommend",
            "risk_level": "medium",      # force at least medium risk
            "action_payload": {
                "reason": "Low confidence — human review required",
                "confidence": state.get("confidence_score")
            }
        }

    response = await self._llm.generate_response(
        system=DECISION_ENGINE_PROMPT,
        user=f"""
Final Analysis: {state['final_answer']}
Confidence: {state['confidence_score']}
Patient Context: {state['patient_context']}
Evidence Sources: {state['sources']}
        """
    )

    result = DecisionEngineResult.model_validate_json(response)

    return {
        "actionable_finding": result.actionable_finding,
        "action_type": result.action_type,
        "action_payload": result.action_payload,
        "risk_level": result.risk_level,
        "reasoning_trace": state.get("reasoning_trace", []) + [{
            "step": "decision_engine",
            "action_type": result.action_type,
            "risk_level": result.risk_level
        }]
    }
```

---

## Risk Router

**File**: `agents/routers/risk_router.py`

```python
def route_by_risk(state: MedicalAgentState) -> str:
    if not state.get("actionable_finding"):
        return "audit_logger"          # No action needed — just log

    risk = state.get("risk_level", "medium")
    confidence = state.get("confidence_score", 0)

    # Safety override: low confidence always requires human approval
    if confidence < 0.80:
        return "human_approval"

    if risk == "low":
        return "action_executor"       # TIER 1: auto-execute
    elif risk in ("medium", "high"):
        return "human_approval"        # TIER 2: need approval
    else:  # "critical"
        return "mandatory_escalation"  # TIER 3: never auto-act
```

---

## Node 2: Human Approval Node (TIER 2)

**File**: `agents/nodes/human_approval_node.py`

**Responsibility**: Pause execution (LangGraph interrupt), present the proposed action with full reasoning to the doctor, wait for their response.

```python
from langgraph.types import interrupt

async def human_approval_node(state: MedicalAgentState) -> dict:
    # Build approval request with full context
    approval_request = {
        "type": "approval_required",
        "session_id": state["session_id"],
        "patient_context": state["patient_context"],

        # What the system found
        "analysis": state["final_answer"],
        "confidence": state["confidence_score"],
        "sources": state["sources"],

        # What the system wants to do
        "proposed_action": state["action_type"],
        "action_details": state["action_payload"],
        "risk_level": state["risk_level"],

        # Full reasoning trace for transparency
        "reasoning_trace": state["reasoning_trace"],

        # Options for the doctor
        "options": ["APPROVE", "REJECT", "MODIFY", "ESCALATE", "REQUEST_MORE_INFO"]
    }

    # THIS IS THE LANGGRAPH INTERRUPT
    # Execution pauses here. The state is checkpointed.
    # The doctor's response resumes execution.
    doctor_response = interrupt(approval_request)

    # Process the response
    decision = doctor_response.get("decision")
    reason = doctor_response.get("reason", "")
    doctor_id = doctor_response.get("doctor_id")

    return {
        "action_approved": decision == "APPROVE",
        "approved_by": doctor_id if decision == "APPROVE" else None,
        "human_override_reason": reason if decision != "APPROVE" else None,
        "reasoning_trace": state.get("reasoning_trace", []) + [{
            "step": "human_approval",
            "decision": decision,
            "doctor_id": doctor_id,
            "reason": reason
        }]
    }
```

**What the doctor sees in their dashboard**:
```
┌─────────────────────────────────────────────────────────┐
│  ⚠️  Action Approval Required                           │
│                                                         │
│  Patient: [ID redacted for display]                     │
│  Risk Level: MEDIUM                                     │
│  Confidence: 87%                                        │
│                                                         │
│  Analysis:                                              │
│  High bleeding risk detected. Warfarin + Aspirin +      │
│  CKD Stage 2 → 3.2x baseline bleeding risk.             │
│  47 studies support this finding. [Sources]             │
│                                                         │
│  Proposed Action:                                       │
│  Send drug interaction alert to prescribing physician.  │
│  Suggest Apixaban as safer alternative for this         │
│  patient profile.                                       │
│                                                         │
│  [APPROVE] [REJECT] [MODIFY] [REQUEST MORE INFO]        │
└─────────────────────────────────────────────────────────┘
```

---

## Node 3: Mandatory Escalation Node (TIER 3)

**File**: `agents/nodes/mandatory_escalation_node.py`

**Responsibility**: For critical risk findings — alert immediately, involve multiple people, NEVER execute any action autonomously.

```python
async def mandatory_escalation_node(state: MedicalAgentState) -> dict:
    patient_id = state["patient_context"].get("patient_id")

    # 1. Immediately alert attending physician (auto — this is TIER 1 within escalation)
    await self._notification_tool.send_urgent_alert(
        recipients=["attending_physician", "charge_nurse"],
        urgency="CRITICAL",
        patient_id=patient_id,
        message=self._format_critical_alert(state),
        requires_immediate_action=True
    )

    # 2. Flag patient record
    await self._ehr_client.flag_patient_record(
        patient_id=patient_id,
        flag_type="CRITICAL_ALERT",
        description=state["final_answer"],
        flagged_by="MAIS_SYSTEM"
    )

    # 3. Create mandatory follow-up task
    await self._task_tool.create_mandatory_task(
        patient_id=patient_id,
        priority="CRITICAL",
        title=f"Critical finding requires immediate review",
        description=state["final_answer"],
        assignee="attending_physician",
        due_within_minutes=15
    )

    return {
        "action_executed": False,        # No autonomous action was taken
        "action_approved": False,        # Human must approve any actual action
        "reasoning_trace": state.get("reasoning_trace", []) + [{
            "step": "mandatory_escalation",
            "alerts_sent": ["attending_physician", "charge_nurse"],
            "autonomous_action": False
        }]
    }
```

---

## Node 4: Action Executor Node

**File**: `agents/nodes/action_executor_node.py`

**Responsibility**: Execute the approved action using the appropriate tool. Check idempotency. Handle failures gracefully.

```python
class ActionExecutorNode:
    def __init__(
        self,
        tool_registry: ToolRegistry,
        idempotency_manager: IdempotencyManager,
        capability_guard: CapabilityGuard,
        audit_store: IAuditStore
    ):
        self._registry = tool_registry
        self._idempotency = idempotency_manager
        self._capability_guard = capability_guard

    async def __call__(self, state: MedicalAgentState) -> dict:
        action_type = state["action_type"]
        payload = state["action_payload"]

        # Security: verify this action is allowed
        self._capability_guard.authorize("action_executor", f"ehr:{action_type}")

        # Idempotency: check if already executed
        idem_key = self._idempotency.generate_key(action_type, payload)
        cached = await self._idempotency.check(idem_key)
        if cached:
            return {"action_executed": True, "action_result": cached}

        # Get the right tool
        tool = self._registry.get_tool(action_type)
        if not tool:
            return {
                "action_executed": False,
                "action_error": f"No tool found for action type: {action_type}"
            }

        # Execute with sandbox (timeout protection)
        result = await self._registry.sandbox.execute(tool, payload, timeout=30.0)

        if result["success"]:
            # Record idempotency key so we don't run again
            await self._idempotency.record(idem_key, result["result"])
            return {
                "action_executed": True,
                "action_result": result["result"]
            }
        else:
            return {
                "action_executed": False,
                "action_error": result["error"]
            }
```

---

## Action Tools

**File**: `tools/action_tools/`

Each tool implements `IActionTool`:

```python
# tools/action_tools/write_ehr_alert_tool.py
class WriteEHRAlertTool(IActionTool):
    name = "write_ehr_alert"
    required_capability = "ehr:write"

    def __init__(self, ehr_client: IEHRClient):
        self._ehr = ehr_client

    async def execute(self, payload: dict) -> dict:
        validated = WriteEHRAlertPayload.model_validate(payload)
        result = await self._ehr.write_alert(
            patient_id=validated.patient_id,
            alert_type=validated.alert_type,
            severity=validated.severity,
            message=validated.message,
            source_analysis=validated.source_analysis
        )
        return {"alert_id": result.id, "status": "written"}

# tools/action_tools/send_notification_tool.py
class SendNotificationTool(IActionTool):
    name = "send_notification"
    required_capability = "notification:send"

    async def execute(self, payload: dict) -> dict:
        validated = NotificationPayload.model_validate(payload)
        # Send via hospital notification system
        ...

# tools/action_tools/create_clinical_task_tool.py
class CreateClinicalTaskTool(IActionTool):
    name = "create_clinical_task"
    required_capability = "task:create"

    async def execute(self, payload: dict) -> dict:
        validated = ClinicalTaskPayload.model_validate(payload)
        # Create task in EHR workflow system
        ...
```

---

## Node 5: Audit Logger Node

**File**: `agents/nodes/audit_logger_node.py`

**Responsibility**: Write complete, immutable audit record for every execution.

```python
async def audit_logger_node(state: MedicalAgentState) -> dict:
    entry = AuditEntry(
        id=str(uuid4()),
        session_id=state["session_id"],
        protocol_version=state.get("protocol_version", "v1"),
        timestamp=datetime.utcnow().isoformat(),

        # Input
        trigger_type=state["trigger_type"],
        query=state["query"],
        patient_id=state["patient_context"].get("patient_id"),

        # Retrieval
        entities_retrieved=len(state.get("graph_entities", [])),
        relationships_retrieved=len(state.get("graph_relationships", [])),
        chunks_retrieved=len(state.get("vector_chunks", [])),
        retrieval_quality=state.get("retrieval_quality"),
        iterations=state.get("iteration_count", 0),

        # Answer
        final_answer=state.get("final_answer"),
        confidence_score=state.get("confidence_score"),
        sources=state.get("sources", []),
        answer_supported=state.get("answer_supported"),

        # Decision
        actionable_finding=state.get("actionable_finding"),
        action_type=state.get("action_type"),
        risk_level=state.get("risk_level"),

        # Execution
        action_approved=state.get("action_approved"),
        approved_by=state.get("approved_by"),
        human_override_reason=state.get("human_override_reason"),
        action_executed=state.get("action_executed"),

        # Full trace for debugging
        reasoning_trace=state.get("reasoning_trace", []),
    )

    await self._audit_store.record(entry)
    return {"audit_recorded": True}
```

---

## Node 6: Feedback Node

**File**: `agents/nodes/feedback_node.py`

**Responsibility**: Track action outcomes over time and update the system.

```python
async def feedback_node(state: MedicalAgentState) -> dict:
    """
    This node fires after enough time has passed to observe an outcome.
    Called by a scheduled job, not inline.
    """
    session_id = state["session_id"]

    # Query EHR for outcome (was the alert acted on? was the patient affected?)
    outcome = await self._ehr_client.get_outcome(
        patient_id=state["patient_context"].get("patient_id"),
        alert_session_id=session_id
    )

    feedback_record = FeedbackRecord(
        session_id=session_id,
        action_was_correct=outcome.get("alert_acted_on"),
        doctor_override_was_justified=outcome.get("override_outcome"),
        patient_outcome=outcome.get("patient_status"),
        notes=outcome.get("clinician_notes")
    )

    await self._feedback_store.record(feedback_record)

    # If doctor frequently overrides a specific action type → log for review
    override_rate = await self._feedback_store.get_override_rate(
        action_type=state.get("action_type")
    )
    if override_rate > 0.30:  # 30% override rate triggers review
        await self._event_bus.publish("system.review_required", {
            "action_type": state.get("action_type"),
            "override_rate": override_rate
        })

    return {}
```

---

## Phase 3 Verification Checklist

Before full integration, verify:
- [ ] Decision engine correctly classifies action types for test scenarios
- [ ] Confidence < 0.80 always routes to TIER 2 regardless of risk
- [ ] TIER 1 actions execute automatically and log correctly
- [ ] TIER 2 interrupt correctly pauses LangGraph and presents to doctor
- [ ] TIER 2 resumes correctly after doctor approval
- [ ] TIER 2 respects rejection — no action taken when rejected
- [ ] TIER 3 sends alerts and flags record but takes no autonomous action
- [ ] Idempotency prevents duplicate action execution on retry
- [ ] Capability guard blocks unauthorized tool calls
- [ ] Audit log contains complete record for every execution path
- [ ] Tool sandbox enforces 30-second timeout
