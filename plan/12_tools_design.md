# 12 — Tools Design

## Every Tool the Agents Can Call

All tools implement `IActionTool`. All tools run inside `ToolSandbox` (30s timeout). All tools are registered in `ToolRegistry` with a capability manifest.

---

## Tool Registry

**File**: `tools/tool_registry.py`

```python
class ToolRegistry:
    def __init__(self, sandbox: ToolSandbox, capability_guard: CapabilityGuard):
        self._tools: dict[str, IActionTool] = {}
        self.sandbox = sandbox
        self._guard = capability_guard

    def register(self, tool: IActionTool) -> None:
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> IActionTool | None:
        return self._tools.get(name)

    async def execute(self, agent_id: str, tool_name: str, payload: dict) -> dict:
        tool = self.get_tool(tool_name)
        if not tool:
            raise ToolNotFoundError(tool_name)

        # Security: verify agent is allowed to use this tool
        self._guard.authorize(agent_id, tool.required_capability)

        # Execute in sandbox
        return await self.sandbox.execute(tool, payload, timeout=30.0)
```

---

## Graph Traversal Tools (Used by Search Nodes)

### FindEntityTool
```python
class FindEntityTool(IActionTool):
    name = "find_entity"
    required_capability = "graph:read"

    async def execute(self, payload: dict) -> dict:
        validated = FindEntityPayload.model_validate(payload)
        # Search by name or alias
        entity = await self._graph_db.get_entity(validated.name)
        if not entity:
            # Try full-text search
            results = await self._graph_db.query(
                "CALL db.index.fulltext.queryNodes('entity_name_fulltext', $query) "
                "YIELD node RETURN node LIMIT 5",
                {"query": validated.name}
            )
            return {"entities": results, "exact_match": False}
        return {"entities": [entity], "exact_match": True}

class FindEntityPayload(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
```

### TraverseRelationshipsTool
```python
class TraverseRelationshipsTool(IActionTool):
    name = "traverse_relationships"
    required_capability = "graph:read"

    async def execute(self, payload: dict) -> dict:
        validated = TraversePayload.model_validate(payload)
        hops = min(validated.hops, 3)  # Hard limit: max 3 hops

        results = await self._graph_db.traverse(validated.entity_name, hops=hops)

        return {
            "entity": validated.entity_name,
            "hops_explored": hops,
            "relationships": results,
            "relationship_count": len(results)
        }

class TraversePayload(BaseModel):
    entity_name: str
    hops: int = Field(default=2, ge=1, le=3)
```

### FindConnectionTool
```python
class FindConnectionTool(IActionTool):
    name = "find_connection"
    required_capability = "graph:read"

    async def execute(self, payload: dict) -> dict:
        """Find shortest path between two entities"""
        validated = FindConnectionPayload.model_validate(payload)

        path = await self._graph_db.find_shortest_path(
            validated.entity_a,
            validated.entity_b
        )

        if not path:
            return {
                "connected": False,
                "entity_a": validated.entity_a,
                "entity_b": validated.entity_b,
                "path": []
            }

        return {
            "connected": True,
            "entity_a": validated.entity_a,
            "entity_b": validated.entity_b,
            "path": path,
            "hops": len(path[0].get("nodes", [])) - 1 if path else 0
        }

class FindConnectionPayload(BaseModel):
    entity_a: str
    entity_b: str
```

### GetCommunityContextTool
```python
class GetCommunityContextTool(IActionTool):
    name = "get_community_context"
    required_capability = "graph:read"

    async def execute(self, payload: dict) -> dict:
        """Get community summary at specified level for an entity"""
        validated = GetCommunityPayload.model_validate(payload)

        # Get entity's community at level
        community_data = await self._graph_db.query(
            "MATCH (e:Entity {name: $name})-[:MEMBER_OF {level: $level}]->(c:Community) "
            "RETURN c.community_id, c.label, c.summary",
            {"name": validated.entity_name, "level": validated.level}
        )

        if not community_data:
            return {"community": None, "found": False}

        return {
            "community": community_data[0],
            "found": True,
            "level": validated.level
        }

class GetCommunityPayload(BaseModel):
    entity_name: str
    level: int = Field(default=1, ge=0, le=2)
```

---

## Search Tools (Used by Search Nodes)

### HybridSearchTool
```python
class HybridSearchTool(IActionTool):
    name = "hybrid_search"
    required_capability = "vector:read"

    async def execute(self, payload: dict) -> dict:
        validated = HybridSearchPayload.model_validate(payload)

        # Parallel BM25 + vector
        bm25_results, vector_results = await asyncio.gather(
            self._search_engine.keyword_search(validated.query, top_k=20),
            self._vector_store.similarity_search(
                embedding=await self._embedding_model.embed_text(validated.query),
                filter={"type": "chunk"},
                top_k=20
            )
        )

        # Reciprocal Rank Fusion
        fused = self._rrf(bm25_results, vector_results, top_k=20)

        # Rerank
        reranked = await self._reranker.rerank(validated.query, fused, top_k=validated.top_k)

        return {"chunks": reranked, "total_found": len(reranked)}

class HybridSearchPayload(BaseModel):
    query: str
    top_k: int = Field(default=10, ge=1, le=50)
```

### WebSearchTool
```python
class WebSearchTool(IActionTool):
    name = "web_search"
    required_capability = "web:search"

    async def execute(self, payload: dict) -> dict:
        validated = WebSearchPayload.model_validate(payload)

        results = await self._tavily_client.search(
            query=validated.query,
            search_depth="advanced",
            max_results=5,
            include_domains=["pubmed.ncbi.nlm.nih.gov", "who.int", "nih.gov", "cochrane.org"]
        )

        return {
            "results": [
                {
                    "title": r["title"],
                    "content": r["content"],
                    "url": r["url"],
                    "score": r.get("score", 0)
                }
                for r in results.get("results", [])
            ]
        }

class WebSearchPayload(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
```

---

## Action Tools (Used by Action Executor)

### WriteEHRAlertTool
```python
class WriteEHRAlertTool(IActionTool):
    name = "write_ehr_alert"
    required_capability = "ehr:write"

    async def execute(self, payload: dict) -> dict:
        validated = WriteEHRAlertPayload.model_validate(payload)

        result = await self._ehr_client.write_alert(
            patient_id=validated.patient_id,
            alert={
                "type": validated.alert_type,
                "severity": validated.severity,
                "message": validated.message,
                "source": "MAIS_SYSTEM",
                "analysis_summary": validated.source_analysis,
                "requires_action": validated.requires_action
            }
        )
        return {"alert_id": result["flag_id"], "status": "written"}

class WriteEHRAlertPayload(BaseModel):
    patient_id: str
    alert_type: str          # "drug_interaction" | "contraindication" | "lab_critical"
    severity: str            # "info" | "warning" | "critical"
    message: str = Field(..., max_length=2000)
    source_analysis: str
    requires_action: bool = False
```

### SendNotificationTool
```python
class SendNotificationTool(IActionTool):
    name = "send_notification"
    required_capability = "notification:send"

    async def execute(self, payload: dict) -> dict:
        validated = NotificationPayload.model_validate(payload)

        # Route to correct notification channel based on urgency
        if validated.urgency == "critical":
            # Use hospital pager system
            await self._pager_client.page(validated.recipients, validated.message)
        else:
            # Use dashboard notification
            await self._notification_client.send(
                recipients=validated.recipients,
                subject=validated.subject,
                body=validated.message,
                metadata=validated.metadata
            )

        return {"status": "sent", "recipients": validated.recipients}

class NotificationPayload(BaseModel):
    recipients: list[str]
    subject: str
    message: str = Field(..., max_length=5000)
    urgency: str = Field(default="normal")  # "normal" | "urgent" | "critical"
    metadata: dict = Field(default_factory=dict)
```

### CreateClinicalTaskTool
```python
class CreateClinicalTaskTool(IActionTool):
    name = "create_clinical_task"
    required_capability = "task:create"

    async def execute(self, payload: dict) -> dict:
        validated = ClinicalTaskPayload.model_validate(payload)

        result = await self._ehr_client.create_task(
            patient_id=validated.patient_id,
            task={
                "title": validated.title,
                "description": validated.description,
                "priority": validated.priority,
                "assignee": validated.assignee,
                "due_at": validated.due_at,
                "source": "MAIS_SYSTEM",
                "analysis_session": validated.session_id
            }
        )
        return {"task_id": result["task_id"], "status": "created"}

class ClinicalTaskPayload(BaseModel):
    patient_id: str
    title: str
    description: str
    priority: str = "normal"   # "low" | "normal" | "high" | "critical"
    assignee: str
    due_at: str | None = None  # ISO datetime string
    session_id: str
```

### ScheduleTestTool
```python
class ScheduleTestTool(IActionTool):
    name = "schedule_test"
    required_capability = "test:request"

    async def execute(self, payload: dict) -> dict:
        validated = ScheduleTestPayload.model_validate(payload)

        result = await self._ehr_client.create_order(
            patient_id=validated.patient_id,
            order_type="lab" if validated.test_category == "lab" else "imaging",
            test_name=validated.test_name,
            priority=validated.priority,
            clinical_indication=validated.indication
        )
        return {"order_id": result["order_id"], "status": "ordered"}

class ScheduleTestPayload(BaseModel):
    patient_id: str
    test_name: str
    test_category: str      # "lab" | "imaging" | "procedure"
    priority: str = "routine"  # "routine" | "urgent" | "stat"
    indication: str
```

---

## Tool Sandbox

**File**: `tools/tool_registry.py`

```python
class ToolSandbox:
    async def execute(self, tool: IActionTool, payload: dict, timeout: float = 30.0) -> dict:
        try:
            result = await asyncio.wait_for(
                tool.execute(payload),
                timeout=timeout
            )
            return {"success": True, "result": result, "tool": tool.name}

        except asyncio.TimeoutError:
            return {
                "success": False,
                "error": f"Tool '{tool.name}' timed out after {timeout}s",
                "tool": tool.name
            }
        except ValidationError as e:
            return {
                "success": False,
                "error": f"Invalid payload for tool '{tool.name}': {e}",
                "tool": tool.name
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "tool": tool.name
            }
```

---

## Tool Capability Summary

| Tool | Required Capability | Risk | Who Calls It |
|---|---|---|---|
| find_entity | graph:read | None | local_graph_search_node |
| traverse_relationships | graph:read | None | local_graph_search_node |
| find_connection | graph:read | None | local_graph_search_node |
| get_community_context | graph:read | None | global_graph_search_node |
| hybrid_search | vector:read | None | hybrid_search_node |
| web_search | web:search | None | web_search_node |
| write_ehr_alert | ehr:write | Medium | action_executor_node |
| send_notification | notification:send | Low | action_executor_node |
| create_clinical_task | task:create | Medium | action_executor_node |
| schedule_test | test:request | Medium | action_executor_node |
