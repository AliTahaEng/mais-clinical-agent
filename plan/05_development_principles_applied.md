# 05 — Development Principles Applied to This System

## How All 20 Principles Map to Python + Medical AI System

---

### 1. Dependency Injection

**Rule**: Never instantiate dependencies directly. Receive through constructor.

**Applied in this system**:
```python
# agents/nodes/local_graph_search_node.py
class LocalGraphSearchNode:
    def __init__(self, graph_db: IGraphDB, embedding_model: IEmbeddingModel):
        self._graph_db = graph_db          # injected — can be Neo4j or mock
        self._embedding_model = embedding_model  # injected — can be BGE-M3 or mock

# NEVER do this inside the node:
# self._graph_db = Neo4jAdapter()  ← WRONG
```

**DI Container registration** (`core/container.py`):
```python
from dependency_injector import containers, providers

class Container(containers.DeclarativeContainer):
    config = providers.Configuration()

    graph_db = providers.Singleton(
        Neo4jAdapter,
        uri=config.neo4j.uri,
        username=config.neo4j.username,
        password=config.neo4j.password,
    )

    local_graph_search_node = providers.Factory(
        LocalGraphSearchNode,
        graph_db=graph_db,
        embedding_model=embedding_model,
    )
```

---

### 2. Interface Abstraction

**Rule**: Code against interfaces, never concrete implementations.

**Applied**: All external dependencies behind ABCs:
```python
# interfaces/i_graph_db.py
from abc import ABC, abstractmethod

class IGraphDB(ABC):
    @abstractmethod
    async def query(self, cypher: str, params: dict) -> list[dict]: ...

    @abstractmethod
    async def get_entity(self, name: str) -> dict | None: ...

    @abstractmethod
    async def traverse(self, entity_name: str, hops: int) -> list[dict]: ...

    @abstractmethod
    async def find_shortest_path(self, source: str, target: str) -> list[dict]: ...
```

**Benefit**: Swap Neo4j → Memgraph → MockGraph by changing one line in `container.py`.

---

### 3. Single Responsibility Principle

**Rule**: Each class does ONE thing.

**Applied**:
- `EntityExtractor` → extracts entities only
- `RelationshipExtractor` → extracts relationships only
- `EntityResolver` → deduplicates entities only
- `GraphWriter` → writes to Neo4j only
- `CommunitySummarizer` → generates community summaries only
- `SupervisorNode` → classifies query and builds plan only
- `SynthesizerNode` → merges context and drafts answer only
- `AuditLoggerNode` → records audit entries only

**Anti-pattern to avoid**:
```python
# WRONG — SRP violation
class BigMedicalService:
    def extract_entities(self): ...
    def write_to_graph(self): ...
    def search_vector_store(self): ...
    def generate_answer(self): ...
    def log_audit(self): ...
    # This class has 5 reasons to change = 5 responsibilities
```

---

### 4. Adapter Pattern

**Rule**: Wrap all external services in adapter classes.

**Applied**:
```python
# adapters/graph/neo4j_adapter.py
class Neo4jAdapter(IGraphDB):
    def __init__(self, uri: str, username: str, password: str):
        self._driver = AsyncGraphDatabase.driver(uri, auth=(username, password))

    async def query(self, cypher: str, params: dict) -> list[dict]:
        async with self._driver.session() as session:
            result = await session.run(cypher, params)
            return [record.data() async for record in result]

    async def traverse(self, entity_name: str, hops: int) -> list[dict]:
        cypher = f"""
            MATCH path = (start:Entity {{name: $name}})-[*1..{min(hops, 3)}]-(end)
            RETURN path, length(path) as hops
            ORDER BY hops LIMIT 50
        """
        return await self.query(cypher, {"name": entity_name})
```

**Benefit**: If Neo4j changes their driver API, only `Neo4jAdapter` changes.

---

### 5. Configuration Over Code

**Rule**: No hardcoded values. Use config + env vars.

**Applied** (`config/settings.py`):
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # LLM
    llm_provider: str = "claude"
    anthropic_api_key: str
    claude_model: str = "claude-3-5-sonnet-20241022"

    # Graph DB
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_username: str = "neo4j"
    neo4j_password: str

    # Thresholds
    confidence_threshold: float = 0.80      # Min confidence for auto-action
    max_iterations: int = 5                 # Max agent loop iterations
    max_hops: int = 3                       # Max graph traversal hops
    top_k_retrieval: int = 10               # Documents to retrieve

    class Config:
        env_file = ".env"
```

**Nothing hardcoded anywhere in agent or node code.**

---

### 6. Graceful Degradation

**Rule**: Optional features fail gracefully without crashing.

**Applied** — Fallback chain in `hybrid_search_node.py`:
```python
async def hybrid_search_node(state: MedicalAgentState) -> dict:
    results = []

    # Try primary: graph + vector
    try:
        graph_results = await self._graph_db.traverse(...)
        results.extend(graph_results)
    except GraphDBUnavailableError:
        logger.warning("Graph DB unavailable — falling back to vector only")

    # Try vector
    try:
        vector_results = await self._vector_store.similarity_search(...)
        results.extend(vector_results)
    except VectorStoreUnavailableError:
        logger.warning("Vector store unavailable — falling back to web search")

    # If both failed, try web search
    if not results:
        try:
            results = await self._web_search.search(state.query)
        except WebSearchError:
            logger.error("All retrieval methods failed")
            return {"retrieval_quality": "bad", "fallback_used": "none"}

    return {"retrieved_chunks": results}
```

---

### 7. Factory Pattern

**Rule**: Use factories for service creation. Never `new` in business logic.

**Applied** (`adapters/factories/llm_factory.py`):
```python
class LLMFactory:
    def __init__(self, config: Settings):
        self._config = config

    def create(self) -> ILLMProvider:
        match self._config.llm_provider:
            case "claude":
                return ClaudeAdapter(
                    api_key=self._config.anthropic_api_key,
                    model=self._config.claude_model
                )
            case "gpt4o":
                return GPT4oAdapter(
                    api_key=self._config.openai_api_key,
                    model=self._config.openai_model
                )
            case "gemini":
                return GeminiAdapter(
                    api_key=self._config.google_api_key
                )
            case _:
                raise ValueError(f"Unknown LLM provider: {self._config.llm_provider}")
```

---

### 8. Separation of Concerns (Layered Architecture)

**Rule**: Each layer knows only about the layer directly below.

**Applied layers in this system**:
```
API Layer         (api/)           ← only knows about Service Layer
    ↓
Service Layer     (agents/)        ← only knows about Interface Layer
    ↓
Interface Layer   (interfaces/)    ← contracts only, no implementations
    ↓
Adapter Layer     (adapters/)      ← wraps external libraries
    ↓
Infrastructure    (Neo4j, LanceDB, PostgreSQL)
```

Agent nodes NEVER import from `adapters/` directly.
Agent nodes import interfaces only.
Container wires the concrete implementations.

---

### 9. Event-Driven Architecture

**Rule**: Use events for loose coupling.

**Applied** (`core/message_bus.py`):
```python
class MedicalEventBus:
    def __init__(self):
        self._handlers: dict[str, list[Callable]] = {}

    def subscribe(self, event_type: str, handler: Callable) -> None:
        self._handlers.setdefault(event_type, []).append(handler)

    async def publish(self, event_type: str, payload: dict) -> None:
        for handler in self._handlers.get(event_type, []):
            await handler(payload)

# EHR webhook handler publishes event
await event_bus.publish("trigger.prescription", {
    "patient_id": "P12345",
    "drug": "Warfarin",
    "dose": "5mg",
    "prescriber_id": "DR789"
})

# LangGraph orchestration subscribes to trigger events
event_bus.subscribe("trigger.prescription", orchestrator.handle_prescription_trigger)
# Future: add pharmacy system subscriber without changing any existing code
```

---

### 10. Database Schema Versioning

**Rule**: Never modify schema directly. Use migration scripts.

**Applied** (`migrations/graph/001_initial_schema.cypher`):
```cypher
-- migration: 001_initial_schema
-- date: 2026-03-16
-- description: Create initial entity and relationship constraints

CREATE CONSTRAINT entity_name_unique IF NOT EXISTS
FOR (e:Entity) REQUIRE e.name IS UNIQUE;

CREATE CONSTRAINT drug_rxcui_unique IF NOT EXISTS
FOR (d:Drug) REQUIRE d.rxcui IS UNIQUE;

CREATE INDEX entity_type_index IF NOT EXISTS
FOR (e:Entity) ON (e.type);
```

`schema_migrator.py` tracks which migrations have been applied.

---

### 11. CQRS — Command/Query Separation

**Rule**: Reads and writes never mixed.

**Applied**:
```python
# QUERIES — pure reads, no side effects
class GetPatientHistoryQuery:
    async def execute(self, patient_id: str) -> list[dict]:
        return await self._audit_store.query_by_patient(patient_id)

class GetEntityQuery:
    async def execute(self, entity_name: str) -> dict | None:
        return await self._graph_db.get_entity(entity_name)

# COMMANDS — change state, emit events
class RecordAuditEntryCommand:
    async def execute(self, entry: AuditEntry) -> None:
        await self._audit_store.record(entry)
        await self._event_bus.publish("audit.recorded", entry.dict())

class ExecuteActionCommand:
    async def execute(self, action: ActionPayload) -> ActionResult:
        result = await self._action_tool.execute(action)
        await self._audit_store.record(...)
        return result
```

Agent nodes that retrieve data call Query classes.
Agent nodes that act call Command classes. Never mixed.

---

### 12. Message Bus for Agent Communication

**Rule**: Agents never call each other directly.

**Applied**: All inter-node communication in LangGraph goes through **shared state** (the TypedDict). No node imports another node. Nodes only read from state and write to state. LangGraph itself routes between nodes via edges.

For inter-service communication (outside LangGraph), the EventBus handles all messaging.

---

### 13. Idempotent Operations

**Rule**: Every action must be idempotent — running twice = same result.

**Applied** (`security/idempotency_manager.py`):
```python
class IdempotencyManager:
    def __init__(self, cache: ICacheStore):
        self._cache = cache

    def generate_key(self, action_type: str, payload: dict) -> str:
        content = f"{action_type}:{json.dumps(payload, sort_keys=True)}"
        return hashlib.sha256(content.encode()).hexdigest()

    async def check_and_record(self, key: str, result: dict) -> dict | None:
        existing = await self._cache.get(f"idempotency:{key}")
        if existing:
            return json.loads(existing)  # Already done — return cached result
        await self._cache.set(f"idempotency:{key}", json.dumps(result), ttl=86400)
        return None  # New execution

# In action_executor_node.py
key = idempotency_manager.generate_key("write_ehr_alert", payload)
cached = await idempotency_manager.check_and_record(key, {})
if cached:
    return cached  # Don't execute again
result = await ehr_client.write_alert(payload)
await idempotency_manager.check_and_record(key, result)
```

---

### 14. Capability-Based Security

**Rule**: Each agent has explicit capability manifest.

**Applied** (`security/capability_guard.py`):
```python
CAPABILITY_MANIFESTS = {
    "local_graph_search": {
        "allowed": ["graph:read", "vector:read"],
        "denied": ["ehr:write", "action:execute", "graph:write"],
    },
    "action_executor": {
        "allowed": ["ehr:write", "notification:send", "task:create"],
        "denied": ["graph:write", "patient:delete"],
    },
    "supervisor": {
        "allowed": ["state:read", "state:write"],
        "denied": ["ehr:write", "action:execute"],
    }
}

class CapabilityGuard:
    def authorize(self, agent_id: str, capability: str) -> None:
        manifest = CAPABILITY_MANIFESTS.get(agent_id)
        if not manifest:
            raise UnknownAgentError(agent_id)
        if capability in manifest["denied"]:
            raise UnauthorizedAgentAction(agent_id, capability)
        if capability not in manifest["allowed"]:
            raise UnauthorizedAgentAction(agent_id, capability)
```

---

### 15. Audit Trail

**Rule**: Every action logged. This is a first-class feature.

**Applied** — Every node ends with audit logging:
```python
# In audit_logger_node.py
async def audit_logger_node(state: MedicalAgentState) -> dict:
    entry = AuditEntry(
        id=str(uuid4()),
        session_id=state.session_id,
        patient_id=state.patient_context.get("patient_id"),
        trigger=state.trigger_type,
        query=state.query,
        retrieved_entities=len(state.graph_entities),
        retrieval_quality=state.retrieval_quality,
        final_answer=state.final_answer,
        confidence=state.confidence_score,
        action_type=state.action_type,
        risk_level=state.risk_level,
        action_approved=state.action_approved,
        action_executed=state.action_executed,
        approved_by=state.approved_by,
        timestamp=datetime.utcnow().isoformat()
    )
    await audit_store.record(entry)
    return {"audit_recorded": True}
```

---

### 16. Circuit Breaker

**Rule**: All external calls have retry + circuit breaker.

**Applied** (`core/circuit_breaker.py`):
```python
class CircuitBreaker:
    # States: CLOSED (normal) → OPEN (failing) → HALF_OPEN (testing)
    def __init__(self, failure_threshold=5, reset_timeout=60):
        self.state = "CLOSED"
        self.failure_count = 0
        self.failure_threshold = failure_threshold

    async def execute(self, fn: Callable, *args, **kwargs):
        if self.state == "OPEN":
            raise ServiceUnavailableError("Circuit breaker OPEN")
        try:
            # tenacity handles retry with exponential backoff
            result = await self._retry_with_backoff(fn, *args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise

# Every LLM call, Neo4j call, EHR call goes through CircuitBreaker
```

---

### 17. State Machine for Task Lifecycle

**Rule**: Strict state transitions. No skipping states.

**Applied** — LangGraph IS the state machine. Conditional edges enforce valid transitions:
```
RECEIVED → PLANNING → RETRIEVING → SYNTHESIZING → CHECKING → DECIDING → ACTING → DONE
              ↑            ↑                            |
              |            └── (CRAG bad) ──────────────|
              └──────────────── (Self-RAG incomplete) ──┘
```

Task lifecycle transitions are enforced by LangGraph's conditional edges. Invalid transitions are impossible — you can only go where edges allow.

---

### 18. Plugin Isolation (Tool Sandboxing)

**Rule**: Tools run in isolated context with timeout.

**Applied** (`tools/tool_registry.py`):
```python
class ToolSandbox:
    async def execute(self, tool: IActionTool, payload: dict, timeout: float = 30.0):
        try:
            result = await asyncio.wait_for(
                tool.execute(payload),
                timeout=timeout
            )
            return {"success": True, "result": result}
        except asyncio.TimeoutError:
            logger.error(f"Tool {tool.name} timed out after {timeout}s")
            return {"success": False, "error": "timeout", "tool": tool.name}
        except Exception as e:
            logger.error(f"Tool {tool.name} failed: {e}")
            return {"success": False, "error": str(e), "tool": tool.name}
```

---

### 19. Schema Validation at Boundaries

**Rule**: Validate everything crossing a boundary.

**Applied** — Pydantic models at every API boundary:
```python
# api/schemas/event_schema.py
class PrescriptionEvent(BaseModel):
    patient_id: str = Field(..., min_length=1, max_length=50)
    drug_name: str = Field(..., min_length=1, max_length=200)
    dose: str = Field(..., pattern=r"^\d+(\.\d+)?\s*(mg|mcg|g|ml|units)$")
    prescriber_id: str = Field(..., min_length=1)
    timestamp: datetime

    @validator("drug_name")
    def sanitize_drug_name(cls, v):
        return v.strip().title()
```

Pydantic raises `ValidationError` at the boundary. Nothing invalid enters the processing pipeline.

---

### 20. Versioned Agent Protocols

**Rule**: Agent message formats are versioned.

**Applied** — All state messages include protocol version:
```python
class MedicalAgentState(TypedDict):
    protocol_version: str    # "v1" — bump when state structure changes

# Router checks version compatibility
def route_supervisor(state: MedicalAgentState) -> str:
    if state.get("protocol_version") != "v1":
        raise UnsupportedProtocolError(state.get("protocol_version"))
    # ... routing logic
```

When state schema changes, bump to "v2" and add migration handler.
