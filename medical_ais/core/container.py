"""
Dependency Injection container.
Single place where all concrete adapters are wired together.
All other modules receive dependencies via constructor injection —
they never import concrete adapter classes or create instances themselves.
"""
from __future__ import annotations

import structlog

from medical_ais.adapters.factory import AdapterFactory
from medical_ais.agent.graph import build_graph, compile_graph
from medical_ais.config.settings import Settings
from medical_ais.core.circuit_breaker import CircuitBreaker
from medical_ais.interfaces.action_tool import ActionTier
from medical_ais.security.capability_guard import CapabilityGuard
from medical_ais.security.idempotency_manager import IdempotencyManager
from medical_ais.tools.action_tools import (
    CreateClinicalTaskTool,
    ScheduleTestTool,
    SendNotificationTool,
    WriteEHRAlertTool,
)
from medical_ais.tools.tool_registry import ToolRegistry

logger = structlog.get_logger(__name__)


class Container:
    """
    Application-level DI container.
    Created once at startup; lives for the lifetime of the process.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._factory = AdapterFactory(settings)
        self._built = False
        self._pg_conn = None  # psycopg3 connection for LangGraph checkpointer

        # Populated by build()
        self.llm = None
        self.classifier_llm = None
        self.graph_db = None
        self.vector_store = None
        self.search_engine = None
        self.embedding_model = None
        self.reranker = None
        self.ehr_client = None
        self.audit_store = None
        self.cache = None
        self.capability_guard: CapabilityGuard | None = None
        self.idempotency_manager: IdempotencyManager | None = None
        self.tool_registry: ToolRegistry | None = None
        self.compiled_graph = None
        self.approval_store = None
        self.pipeline_job_store = None
        self.user_store = None

        # Circuit breakers per external service
        self._cb_llm = CircuitBreaker(name="llm", failure_threshold=5, reset_timeout=60.0)
        self._cb_graph = CircuitBreaker(name="graph_db", failure_threshold=3, reset_timeout=30.0)
        self._cb_ehr = CircuitBreaker(name="ehr", failure_threshold=3, reset_timeout=60.0)

    async def build(self) -> None:
        """
        Initialise all adapters, connect to external services,
        wire the tool registry, and compile the LangGraph graph.
        """
        if self._built:
            return

        logger.info("container.building")

        # ── Adapters ──────────────────────────────────────────────────────────
        self.llm = self._factory.make_llm()
        self.classifier_llm = self._factory.make_classifier_llm()
        self.graph_db = self._factory.make_graph_db()
        self.vector_store = self._factory.make_vector_store()
        self.search_engine = self._factory.make_search_engine()
        self.embedding_model = self._factory.make_embedding_model()
        self.reranker = self._factory.make_reranker()
        self.ehr_client = self._factory.make_ehr_client()
        self.audit_store = self._factory.make_audit_store()
        self.cache = self._factory.make_cache()

        # ── Approval Store ────────────────────────────────────────────────────
        from medical_ais.services.approval_store import ApprovalStore
        self.approval_store = ApprovalStore(self.cache)

        # ── Pipeline Job Store ────────────────────────────────────────────────
        from medical_ais.services.pipeline_job_store import PipelineJobStore
        self.pipeline_job_store = PipelineJobStore(self.cache)

        # ── User Store (auth) ─────────────────────────────────────────────────
        from medical_ais.auth.user_store import UserStore
        self.user_store = UserStore(self._settings.postgres_url)

        # ── Connect to external services ──────────────────────────────────────
        await self._connect_services()

        # ── Security ──────────────────────────────────────────────────────────
        self.capability_guard = CapabilityGuard()
        self.idempotency_manager = IdempotencyManager(self.cache)

        # ── Tool Registry ─────────────────────────────────────────────────────
        self.tool_registry = ToolRegistry(
            capability_guard=self.capability_guard,
            timeout_seconds=self._settings.tool_timeout_seconds,
        )
        self.tool_registry.register(WriteEHRAlertTool(self.ehr_client))
        self.tool_registry.register(SendNotificationTool())
        self.tool_registry.register(CreateClinicalTaskTool(self.ehr_client))
        self.tool_registry.register(ScheduleTestTool(self.ehr_client))

        # ── LangGraph graph ───────────────────────────────────────────────────
        graph = build_graph(
            llm=self.llm,
            classifier_llm=self.classifier_llm,
            graph_db=self.graph_db,
            vector_store=self.vector_store,
            search_engine=self.search_engine,
            embedding_model=self.embedding_model,
            reranker=self.reranker,
            ehr_client=self.ehr_client,
            tool_registry=self.tool_registry,
            audit_store=self.audit_store,
            idempotency_manager=self.idempotency_manager,
            settings=self._settings,
            approval_store=self.approval_store,
        )

        # Compile with checkpointer if Postgres is available
        checkpointer = await self._make_checkpointer()
        interrupt_before = []
        if self._settings.force_human_approval:
            interrupt_before = ["human_approval", "mandatory_escalation"]

        self.compiled_graph = compile_graph(
            graph,
            checkpointer=checkpointer,
            interrupt_before=interrupt_before,
        )

        self._built = True
        logger.info("container.built")

    async def close(self) -> None:
        """Gracefully close all external connections."""
        if self.graph_db:
            try:
                await self.graph_db.close()
            except Exception:
                pass
        if self.cache and hasattr(self.cache, "close"):
            try:
                await self.cache.close()
            except Exception:
                pass
        if self.audit_store and hasattr(self.audit_store, "close"):
            try:
                await self.audit_store.close()
            except Exception:
                pass
        if self.ehr_client and hasattr(self.ehr_client, "close"):
            try:
                await self.ehr_client.close()
            except Exception:
                pass
        if self._pg_conn:
            try:
                await self._pg_conn.close()
            except Exception:
                pass
        if self.user_store:
            try:
                await self.user_store.close()
            except Exception:
                pass
        logger.info("container.closed")

    # ── Private helpers ───────────────────────────────────────────────────────

    async def _connect_services(self) -> None:
        """Connect adapters that require an async connect() call."""
        errors: list[str] = []

        for name, adapter in [
            ("graph_db", self.graph_db),
            ("ehr_client", self.ehr_client),
        ]:
            if hasattr(adapter, "connect"):
                try:
                    await adapter.connect()
                    logger.info(f"container.{name}.connected")
                except Exception as exc:
                    logger.warning(f"container.{name}.connect_failed", error=str(exc))
                    errors.append(f"{name}: {exc}")

        if hasattr(self.audit_store, "connect"):
            try:
                await self.audit_store.connect()
            except Exception as exc:
                logger.warning("container.audit_store.connect_failed", error=str(exc))

        if hasattr(self.cache, "connect"):
            try:
                await self.cache.connect()
            except Exception as exc:
                logger.warning("container.cache.connect_failed", error=str(exc))

        if self.user_store:
            try:
                await self.user_store.connect()
                await self._seed_admin()
            except Exception as exc:
                logger.warning("container.user_store.connect_failed", error=str(exc))

    async def _seed_admin(self) -> None:
        """Create the default admin account if no admin exists yet."""
        try:
            if await self.user_store.exists_any_admin():
                return
            admin = await self.user_store.create_user(
                email=self._settings.admin_email,
                username="admin",
                plain_password=self._settings.admin_password,
                role="admin",
            )
            logger.info("container.admin_seeded", email=admin.email)
        except Exception as exc:
            logger.warning("container.admin_seed_failed", error=str(exc))

    async def _make_checkpointer(self):
        """Try to create a Postgres checkpointer; fall back to in-memory."""
        try:
            import psycopg
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

            # psycopg3 uses plain postgresql:// — strip SQLAlchemy's +asyncpg qualifier
            conn_str = (
                self._settings.postgres_url
                .replace("postgresql+asyncpg://", "postgresql://")
                .replace("postgres+asyncpg://", "postgres://")
            )
            # Open a persistent autocommit connection for the lifetime of the app
            self._pg_conn = await psycopg.AsyncConnection.connect(
                conn_str, autocommit=True
            )
            checkpointer = AsyncPostgresSaver(self._pg_conn)
            await checkpointer.setup()
            logger.info("container.checkpointer.postgres")
            return checkpointer
        except Exception as exc:
            logger.warning("container.checkpointer.fallback_memory", error=str(exc))
            from langgraph.checkpoint.memory import MemorySaver
            return MemorySaver()
