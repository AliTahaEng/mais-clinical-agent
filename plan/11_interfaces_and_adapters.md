# 11 — Interfaces and Adapters

## All Python ABCs, Adapter Classes, and DI Container

---

## All Interface Contracts

### ILLMProvider
**File**: `interfaces/i_llm_provider.py`
```python
from abc import ABC, abstractmethod

class ILLMProvider(ABC):
    @abstractmethod
    async def generate_response(
        self, system: str, user: str, temperature: float = 0.1
    ) -> str: ...

    @abstractmethod
    async def generate_structured(
        self, system: str, user: str, output_schema: type
    ) -> dict: ...

    @abstractmethod
    async def stream_response(
        self, system: str, user: str
    ): ...    # async generator
```

### IGraphDB
**File**: `interfaces/i_graph_db.py`
```python
class IGraphDB(ABC):
    @abstractmethod
    async def query(self, cypher: str, params: dict = None) -> list[dict]: ...

    @abstractmethod
    async def get_entity(self, name: str) -> dict | None: ...

    @abstractmethod
    async def traverse(self, entity_name: str, hops: int = 2) -> list[dict]: ...

    @abstractmethod
    async def find_shortest_path(self, source: str, target: str) -> list[dict]: ...

    @abstractmethod
    async def write_entity(self, entity: dict) -> None: ...

    @abstractmethod
    async def write_relationship(self, rel: dict) -> None: ...

    @abstractmethod
    async def get_community_members(self, community_id: str) -> list[dict]: ...
```

### IVectorStore
**File**: `interfaces/i_vector_store.py`
```python
class IVectorStore(ABC):
    @abstractmethod
    async def similarity_search(
        self, embedding: list[float], filter: dict = None, top_k: int = 10
    ) -> list[dict]: ...

    @abstractmethod
    async def upsert(self, records: list[dict]) -> None: ...

    @abstractmethod
    async def get_by_id(self, record_id: str) -> dict | None: ...

    @abstractmethod
    async def delete(self, record_id: str) -> None: ...
```

### ISearchEngine
**File**: `interfaces/i_search_engine.py`
```python
class ISearchEngine(ABC):
    @abstractmethod
    async def keyword_search(self, query: str, top_k: int = 20) -> list[dict]: ...

    @abstractmethod
    async def index_document(self, doc_id: str, content: str, metadata: dict) -> None: ...

    @abstractmethod
    async def delete_document(self, doc_id: str) -> None: ...
```

### IEmbeddingModel
**File**: `interfaces/i_embedding_model.py`
```python
class IEmbeddingModel(ABC):
    @abstractmethod
    async def embed_text(self, text: str) -> list[float]: ...

    @abstractmethod
    async def embed_batch(self, texts: list[str], batch_size: int = 256) -> list[list[float]]: ...

    @property
    @abstractmethod
    def embedding_dim(self) -> int: ...
```

### IReranker
**File**: `interfaces/i_reranker.py`
```python
class IReranker(ABC):
    @abstractmethod
    async def rerank(
        self, query: str, documents: list[dict], top_k: int = 10
    ) -> list[dict]: ...
```

### IEHRClient
**File**: `interfaces/i_ehr_client.py`
```python
class IEHRClient(ABC):
    @abstractmethod
    async def get_patient(self, patient_id: str) -> dict: ...

    @abstractmethod
    async def get_medications(self, patient_id: str) -> list[dict]: ...

    @abstractmethod
    async def get_conditions(self, patient_id: str) -> list[dict]: ...

    @abstractmethod
    async def write_alert(self, patient_id: str, alert: dict) -> dict: ...

    @abstractmethod
    async def create_task(self, patient_id: str, task: dict) -> dict: ...

    @abstractmethod
    async def flag_patient_record(self, patient_id: str, flag: dict) -> None: ...

    @abstractmethod
    async def get_outcome(self, patient_id: str, session_id: str) -> dict: ...
```

### IAuditStore
**File**: `interfaces/i_audit_store.py`
```python
class IAuditStore(ABC):
    @abstractmethod
    async def record(self, entry: AuditEntry) -> None: ...

    @abstractmethod
    async def query_by_session(self, session_id: str) -> list[dict]: ...

    @abstractmethod
    async def query_by_patient(self, patient_id: str) -> list[dict]: ...
```

### IActionTool
**File**: `interfaces/i_action_tool.py`
```python
class IActionTool(ABC):
    name: str
    required_capability: str

    @abstractmethod
    async def execute(self, payload: dict) -> dict: ...
```

---

## Adapter Implementations

### ClaudeAdapter
**File**: `adapters/llm/claude_adapter.py`
```python
from anthropic import AsyncAnthropic

class ClaudeAdapter(ILLMProvider):
    def __init__(self, api_key: str, model: str, circuit_breaker: CircuitBreaker):
        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model
        self._cb = circuit_breaker

    async def generate_response(self, system: str, user: str, temperature: float = 0.1) -> str:
        async def _call():
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=4096,
                temperature=temperature,
                system=system,
                messages=[{"role": "user", "content": user}]
            )
            return response.content[0].text

        return await self._cb.execute(_call)

    async def generate_structured(self, system: str, user: str, output_schema: type) -> dict:
        enhanced_system = system + f"\n\nYou MUST respond with valid JSON matching this schema: {output_schema.schema_json()}"
        response = await self.generate_response(enhanced_system, user, temperature=0.0)
        return output_schema.model_validate_json(response).model_dump()
```

### Neo4jAdapter
**File**: `adapters/graph/neo4j_adapter.py`
```python
from neo4j import AsyncGraphDatabase

class Neo4jAdapter(IGraphDB):
    def __init__(self, uri: str, username: str, password: str, circuit_breaker: CircuitBreaker):
        self._driver = AsyncGraphDatabase.driver(uri, auth=(username, password))
        self._cb = circuit_breaker

    async def query(self, cypher: str, params: dict = None) -> list[dict]:
        async def _call():
            async with self._driver.session() as session:
                result = await session.run(cypher, params or {})
                return [record.data() async for record in result]
        return await self._cb.execute(_call)

    async def traverse(self, entity_name: str, hops: int = 2) -> list[dict]:
        cypher = f"""
            MATCH path = (start:Entity {{name: $name}})-[*1..{min(hops, 3)}]-(end)
            RETURN
                [n in nodes(path) | n.name] as node_names,
                [r in relationships(path) | type(r)] as rel_types,
                length(path) as hops
            ORDER BY hops LIMIT 50
        """
        return await self.query(cypher, {"name": entity_name})

    async def find_shortest_path(self, source: str, target: str) -> list[dict]:
        cypher = """
            MATCH path = shortestPath(
                (a:Entity {name: $source})-[*..5]-(b:Entity {name: $target})
            )
            RETURN
                [n in nodes(path) | n.name] as nodes,
                [r in relationships(path) | type(r)] as relationships,
                length(path) as length
        """
        return await self.query(cypher, {"source": source, "target": target})
```

### LanceDBAdapter
**File**: `adapters/vector/lancedb_adapter.py`
```python
import lancedb

class LanceDBAdapter(IVectorStore):
    def __init__(self, db_path: str):
        self._db = lancedb.connect(db_path)
        self._table_name = "medical_embeddings"

    async def similarity_search(self, embedding: list[float], filter: dict = None, top_k: int = 10) -> list[dict]:
        table = self._db.open_table(self._table_name)
        query = table.search(embedding).limit(top_k)

        if filter:
            for key, value in filter.items():
                query = query.where(f"{key} = '{value}'")

        results = query.to_list()
        return [
            {"id": r["id"], "text": r["text"], "metadata": r["metadata"], "score": r["_distance"]}
            for r in results
        ]

    async def upsert(self, records: list[dict]) -> None:
        table = self._db.open_table(self._table_name)
        table.add(records, mode="overwrite")
```

### FHIREHRAdapter
**File**: `adapters/ehr/fhir_adapter.py`
```python
import fhirclient.models.patient as p
import fhirclient.models.medicationrequest as mr

class FHIREHRAdapter(IEHRClient):
    def __init__(self, fhir_server_url: str, api_key: str, circuit_breaker: CircuitBreaker):
        self._server_url = fhir_server_url
        self._cb = circuit_breaker

    async def get_patient(self, patient_id: str) -> dict:
        async def _call():
            # FHIR R4 GET /Patient/{patient_id}
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self._server_url}/Patient/{patient_id}",
                    headers={"Authorization": f"Bearer {self._api_key}"}
                )
                response.raise_for_status()
                return self._parse_fhir_patient(response.json())
        return await self._cb.execute(_call)

    async def write_alert(self, patient_id: str, alert: dict) -> dict:
        async def _call():
            # FHIR R4 POST /Flag
            flag_resource = self._build_fhir_flag(patient_id, alert)
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self._server_url}/Flag",
                    json=flag_resource,
                    headers={"Authorization": f"Bearer {self._api_key}"}
                )
                response.raise_for_status()
                return {"flag_id": response.json()["id"], "status": "created"}
        return await self._cb.execute(_call)
```

### MockEHRAdapter (for testing)
**File**: `adapters/ehr/mock_ehr_adapter.py`
```python
class MockEHRAdapter(IEHRClient):
    """In-memory EHR for testing — no real hospital system needed"""

    MOCK_PATIENTS = {
        "P001": {
            "patient_id": "P001",
            "age": 72,
            "conditions": ["Atrial Fibrillation", "Type 2 Diabetes", "CKD Stage 2"],
            "medications": ["Aspirin 100mg", "Metformin 500mg", "Atorvastatin 40mg"],
            "allergies": ["Penicillin"]
        }
    }

    async def get_patient(self, patient_id: str) -> dict:
        return self.MOCK_PATIENTS.get(patient_id, {})

    async def write_alert(self, patient_id: str, alert: dict) -> dict:
        return {"flag_id": f"mock_flag_{patient_id}", "status": "mock_created"}
```

---

## DI Container

**File**: `core/container.py`

```python
from dependency_injector import containers, providers
from config.settings import Settings

class Container(containers.DeclarativeContainer):

    # ── Configuration ─────────────────────────────────────────────────────
    config = providers.Singleton(Settings)

    # ── Infrastructure ────────────────────────────────────────────────────
    circuit_breaker = providers.Factory(
        CircuitBreaker,
        failure_threshold=5,
        reset_timeout=60
    )

    # ── LLM Providers ─────────────────────────────────────────────────────
    llm_provider = providers.Singleton(
        LLMFactory,
        config=config,
        circuit_breaker=circuit_breaker,
    )

    # Cheap LLM for classification tasks
    llm_classifier = providers.Singleton(
        ClaudeHaikuAdapter,
        api_key=config.provided.anthropic_api_key,
    )

    # ── Graph DB ──────────────────────────────────────────────────────────
    graph_db = providers.Singleton(
        Neo4jAdapter,
        uri=config.provided.neo4j_uri,
        username=config.provided.neo4j_username,
        password=config.provided.neo4j_password,
        circuit_breaker=circuit_breaker,
    )

    # ── Vector Store ──────────────────────────────────────────────────────
    vector_store = providers.Singleton(
        LanceDBAdapter,
        db_path=config.provided.lancedb_path,
    )

    # ── Search ────────────────────────────────────────────────────────────
    search_engine = providers.Singleton(
        ElasticsearchAdapter,
        url=config.provided.elasticsearch_url,
    )

    # ── Embedding ─────────────────────────────────────────────────────────
    embedding_model = providers.Singleton(
        BGEM3Adapter,
        model_name="BAAI/bge-m3",
    )

    reranker = providers.Singleton(
        CrossEncoderAdapter,
        model_name="cross-encoder/ms-marco-MiniLM-L-6-v2",
    )

    # ── EHR ───────────────────────────────────────────────────────────────
    ehr_client = providers.Singleton(
        EHRClientFactory,
        config=config,
        circuit_breaker=circuit_breaker,
    )

    # ── Storage ───────────────────────────────────────────────────────────
    audit_store = providers.Singleton(
        PostgresAuditAdapter,
        connection_string=config.provided.postgres_url,
    )

    cache_store = providers.Singleton(
        RedisCacheAdapter,
        url=config.provided.redis_url,
    )

    # ── Security ──────────────────────────────────────────────────────────
    capability_guard = providers.Singleton(CapabilityGuard)

    idempotency_manager = providers.Singleton(
        IdempotencyManager,
        cache=cache_store,
    )

    # ── Message Bus ───────────────────────────────────────────────────────
    event_bus = providers.Singleton(MedicalEventBus)

    # ── Agent Nodes ───────────────────────────────────────────────────────
    supervisor_node = providers.Factory(
        SupervisorNode,
        llm=llm_classifier,
        config=config,
    )

    local_graph_search_node = providers.Factory(
        LocalGraphSearchNode,
        graph_db=graph_db,
        embedding_model=embedding_model,
        vector_store=vector_store,
        config=config,
    )

    hybrid_search_node = providers.Factory(
        HybridSearchNode,
        search_engine=search_engine,
        vector_store=vector_store,
        embedding_model=embedding_model,
        reranker=reranker,
    )

    synthesizer_node = providers.Factory(
        SynthesizerNode,
        llm=llm_provider,
    )

    quality_checker_node = providers.Factory(
        QualityCheckerNode,
        llm=llm_classifier,
    )

    self_critic_node = providers.Factory(
        SelfCriticNode,
        llm=llm_provider,
    )

    decision_engine_node = providers.Factory(
        DecisionEngineNode,
        llm=llm_classifier,
        config=config,
    )

    action_executor_node = providers.Factory(
        ActionExecutorNode,
        tool_registry=tool_registry,
        idempotency_manager=idempotency_manager,
        capability_guard=capability_guard,
    )

    audit_logger_node = providers.Factory(
        AuditLoggerNode,
        audit_store=audit_store,
    )
```
