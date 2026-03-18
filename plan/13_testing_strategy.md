# 13 — Testing Strategy

## Test Pyramid

```
        ┌─────────────┐
        │     E2E     │  ← 5 scenarios, full system, real DB
        │   Tests     │
        ├─────────────┤
        │ Integration │  ← test each phase, real-ish dependencies
        │   Tests     │
        ├─────────────┤
        │    Unit     │  ← test each class in isolation, all mocked
        │   Tests     │
        └─────────────┘
```

**Rule**: Unit tests first. If a unit test passes, move to integration. Never rely on E2E tests to find bugs that unit tests should catch.

---

## Unit Tests

### Testing Nodes (Pure Functions with Mocked Dependencies)

**File**: `tests/unit/test_supervisor_node.py`

```python
import pytest
from unittest.mock import AsyncMock
from agents.nodes.supervisor_node import SupervisorNode
from config.settings import Settings

@pytest.fixture
def mock_llm():
    llm = AsyncMock()
    return llm

@pytest.fixture
def supervisor(mock_llm):
    config = Settings(max_iterations=5, _env_file=None)
    return SupervisorNode(llm=mock_llm, config=config)

@pytest.mark.asyncio
async def test_supervisor_classifies_entity_query(supervisor, mock_llm):
    mock_llm.generate_response.return_value = '''
    {
        "query_type": "entity",
        "reasoning_plan": ["find Warfarin entity", "get its interactions"],
        "search_strategy": ["local_graph", "hybrid"]
    }
    '''

    state = {
        "query": "What are the interactions of Warfarin?",
        "patient_context": {},
        "iteration_count": 0
    }

    result = await supervisor(state)

    assert result["query_type"] == "entity"
    assert "local_graph" in result["search_strategy"]
    assert result["iteration_count"] == 1

@pytest.mark.asyncio
async def test_supervisor_stops_at_max_iterations(supervisor, mock_llm):
    state = {
        "query": "What are the interactions of Warfarin?",
        "patient_context": {},
        "iteration_count": 5  # Already at max
    }

    result = await supervisor(state)

    assert result["confidence_score"] == 0.0
    mock_llm.generate_response.assert_not_called()  # Should not call LLM
```

**File**: `tests/unit/test_quality_checker_node.py`

```python
@pytest.mark.asyncio
async def test_quality_checker_rates_empty_context_as_bad(quality_checker, mock_llm):
    mock_llm.generate_response.return_value = '{"quality": "bad", "reason": "No evidence found"}'

    state = {
        "query": "Drug interaction between X and Y",
        "graph_entities": [],
        "graph_relationships": [],
        "vector_chunks": []
    }

    result = await quality_checker(state)

    assert result["retrieval_quality"] == "bad"

@pytest.mark.asyncio
async def test_quality_checker_rates_relevant_context_as_good(quality_checker, mock_llm):
    mock_llm.generate_response.return_value = '{"quality": "good", "reason": "Direct evidence found"}'

    state = {
        "query": "Warfarin interactions",
        "graph_entities": [{"name": "Warfarin", "type": "Drug"}],
        "graph_relationships": [{"source": "Warfarin", "target": "Aspirin", "type": "INTERACTS_WITH"}],
        "vector_chunks": [{"text": "Warfarin and Aspirin interaction..."}]
    }

    result = await quality_checker(state)
    assert result["retrieval_quality"] == "good"
```

**File**: `tests/unit/test_decision_engine_node.py`

```python
@pytest.mark.asyncio
async def test_decision_engine_forces_human_review_when_low_confidence(decision_engine, mock_llm):
    state = {
        "final_answer": "Potential interaction found",
        "confidence_score": 0.65,  # Below 0.80 threshold
        "patient_context": {"patient_id": "P001"},
        "sources": []
    }

    result = await decision_engine(state)

    # Should force medium risk regardless of what LLM says
    assert result["risk_level"] == "medium"
    mock_llm.generate_response.assert_not_called()  # Skips LLM call

@pytest.mark.asyncio
async def test_decision_engine_classifies_drug_interaction_as_medium_risk(decision_engine, mock_llm):
    mock_llm.generate_response.return_value = '''
    {
        "actionable_finding": true,
        "action_type": "recommend",
        "action_description": "Alert prescribing physician about interaction",
        "action_payload": {"patient_id": "P001", "drug_a": "Warfarin", "drug_b": "Aspirin"},
        "confidence": 0.92,
        "risk_level": "medium"
    }
    '''

    state = {
        "final_answer": "Major bleeding risk: Warfarin + Aspirin",
        "confidence_score": 0.92,
        "patient_context": {"patient_id": "P001"},
        "sources": ["study_001", "study_002"]
    }

    result = await decision_engine(state)

    assert result["actionable_finding"] == True
    assert result["risk_level"] == "medium"
```

**File**: `tests/unit/test_capability_guard.py`

```python
def test_guard_allows_authorized_capability():
    guard = CapabilityGuard()
    guard.authorize("local_graph_search", "graph:read")  # Should not raise

def test_guard_blocks_unauthorized_capability():
    guard = CapabilityGuard()
    with pytest.raises(UnauthorizedAgentAction):
        guard.authorize("local_graph_search", "ehr:write")

def test_guard_blocks_unknown_agent():
    guard = CapabilityGuard()
    with pytest.raises(UnknownAgentError):
        guard.authorize("nonexistent_agent", "graph:read")
```

**File**: `tests/unit/test_idempotency_manager.py`

```python
@pytest.mark.asyncio
async def test_idempotency_prevents_duplicate_execution():
    cache = MockCacheStore()
    manager = IdempotencyManager(cache=cache)
    payload = {"patient_id": "P001", "drug": "Warfarin"}
    result = {"alert_id": "A001"}

    key = manager.generate_key("write_ehr_alert", payload)

    # First call — no cached result
    cached = await manager.check(key)
    assert cached is None

    # Record the result
    await manager.record(key, result)

    # Second call — returns cached result
    cached = await manager.check(key)
    assert cached == result
```

---

## Integration Tests

### Pipeline Phase 1

**File**: `tests/integration/test_pipeline_e2e.py`

```python
@pytest.fixture
def test_container():
    """Container with real DB connections to test instances"""
    container = Container()
    container.config.from_dict({
        "neo4j_uri": "bolt://localhost:7688",  # Test Neo4j instance
        "lancedb_path": "/tmp/test_lancedb",
        "llm_provider": "mock",  # Use mock LLM for pipeline tests
    })
    return container

@pytest.mark.asyncio
@pytest.mark.integration
async def test_full_pipeline_ingests_and_builds_graph(test_container):
    runner = test_container.pipeline_runner()
    result = await runner.run_full_pipeline(["tests/fixtures/sample_medical_docs"])

    assert result.documents_processed > 0
    assert result.entities_created > 0
    assert result.relationships_created > 0

    # Verify graph contents
    graph_db = test_container.graph_db()
    warfarin = await graph_db.get_entity("Warfarin")
    assert warfarin is not None
    assert warfarin["type"] == "Drug"

@pytest.mark.asyncio
@pytest.mark.integration
async def test_pipeline_is_idempotent(test_container):
    """Running pipeline twice should produce same result, not duplicates"""
    runner = test_container.pipeline_runner()

    await runner.run_full_pipeline(["tests/fixtures/sample_medical_docs"])
    result1 = await test_container.graph_db().query("MATCH (n:Entity) RETURN count(n) as count")

    await runner.run_full_pipeline(["tests/fixtures/sample_medical_docs"])
    result2 = await test_container.graph_db().query("MATCH (n:Entity) RETURN count(n) as count")

    assert result1[0]["count"] == result2[0]["count"]  # No duplicates
```

### Phase 2 — CRAG Loop

**File**: `tests/integration/test_crag_loop.py`

```python
@pytest.mark.asyncio
@pytest.mark.integration
async def test_crag_loops_back_on_bad_retrieval(mock_graph_db, mock_llm):
    """When CRAG detects bad retrieval, it should loop back to supervisor"""

    # Mock: first retrieval returns empty, second returns good results
    mock_graph_db.traverse.side_effect = [[], [{"name": "Warfarin", "relations": [...]}]]

    # Mock quality checker: first call returns "bad", second returns "good"
    mock_llm.generate_response.side_effect = [
        '{"quality": "bad", "reason": "No relevant entities found"}',
        '{"quality": "good", "reason": "Direct evidence found"}',
        '...',  # synthesizer response
        '{"verdict": "supported", "confidence": 0.88}'  # self-critic response
    ]

    agent = build_medical_agent_graph(test_container)

    state = {
        "query": "Warfarin interaction with Aspirin",
        "patient_context": {},
        "session_id": "test_session_001",
        "iteration_count": 0
    }

    result = await agent.ainvoke(state, config={"configurable": {"thread_id": "test_001"}})

    # Verify loop happened
    assert result["iteration_count"] == 2
    assert result["retrieval_quality"] == "good"
    assert result["final_answer"] is not None
```

### Phase 3 — Action Tier Routing

**File**: `tests/integration/test_action_tier_routing.py`

```python
@pytest.mark.asyncio
@pytest.mark.integration
async def test_low_risk_action_executes_automatically(test_container):
    """TIER 1: Low risk actions should execute without human approval"""

    mock_ehr = MockEHRAdapter()
    test_container.ehr_client.override(providers.Object(mock_ehr))

    state = build_complete_state(
        final_answer="Minor interaction found",
        confidence_score=0.91,
        actionable_finding=True,
        action_type="inform",
        risk_level="low",
        action_payload={"patient_id": "P001", "message": "Minor interaction note"}
    )

    agent = build_medical_agent_graph(test_container)
    result = await agent.ainvoke(state, ...)

    assert result["action_executed"] == True
    assert result["action_approved"] == False  # No approval needed for low risk
    assert result["audit_recorded"] == True

@pytest.mark.asyncio
@pytest.mark.integration
async def test_medium_risk_action_pauses_for_approval(test_container):
    """TIER 2: Medium risk actions must wait for human approval"""

    agent = build_medical_agent_graph(test_container)

    state = build_complete_state(
        confidence_score=0.89,
        risk_level="medium",
        action_type="recommend"
    )

    config = {"configurable": {"thread_id": "test_tier2_001"}}

    # Run until interrupt
    with pytest.raises(GraphInterrupt) as exc_info:
        await agent.ainvoke(state, config=config)

    interrupt_value = exc_info.value.interrupts[0].value
    assert interrupt_value["type"] == "approval_required"
    assert "proposed_action" in interrupt_value
    assert "reasoning_trace" in interrupt_value

    # Resume with approval
    result = await agent.ainvoke(
        Command(resume={"decision": "APPROVE", "doctor_id": "DR001"}),
        config=config
    )

    assert result["action_executed"] == True
    assert result["approved_by"] == "DR001"

@pytest.mark.asyncio
@pytest.mark.integration
async def test_critical_risk_never_auto_executes(test_container):
    """TIER 3: Critical risk must never result in autonomous action"""

    state = build_complete_state(
        confidence_score=0.95,
        risk_level="critical",
        action_type="urgent"
    )

    agent = build_medical_agent_graph(test_container)
    result = await agent.ainvoke(state, ...)

    assert result["action_executed"] == False  # NEVER autonomous action
    assert result["audit_recorded"] == True
```

---

## Test Fixtures

**File**: `tests/fixtures/mock_patient_profiles.py`

```python
PATIENT_P001 = {
    "patient_id": "P001",
    "age": 72,
    "weight_kg": 65,
    "conditions": ["Atrial Fibrillation", "Type 2 Diabetes", "CKD Stage 2"],
    "medications": ["Aspirin 100mg", "Metformin 500mg", "Atorvastatin 40mg"],
    "allergies": ["Penicillin"],
    "lab_values": {"INR": 1.1, "eGFR": 55, "HbA1c": 7.2}
}

PATIENT_P002 = {
    "patient_id": "P002",
    "age": 45,
    "conditions": ["Hypertension"],
    "medications": ["Lisinopril 10mg"],
    "allergies": [],
    "lab_values": {"BP": "145/90"}
}
```

---

## Running Tests

```bash
# All unit tests (fast, no infrastructure)
make test-unit

# Integration tests (requires Docker services running)
make test-integration

# Full test suite
make test

# With coverage report
make test-coverage

# Single test file
pytest tests/unit/test_supervisor_node.py -v

# Marked tests only
pytest -m "not integration" -v
```

**Makefile targets**:
```makefile
test-unit:
    pytest tests/unit/ -v --tb=short

test-integration:
    pytest tests/integration/ -v --tb=short -m integration

test:
    pytest tests/ -v --tb=short

test-coverage:
    pytest tests/ --cov=. --cov-report=html --cov-fail-under=80
```
