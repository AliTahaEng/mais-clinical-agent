"""Public re-exports for the interfaces package."""
from medical_ais.interfaces.action_tool import ActionResult, ActionTier, IActionTool
from medical_ais.interfaces.audit import AuditRecord, IAuditStore
from medical_ais.interfaces.cache import ICacheStore
from medical_ais.interfaces.ehr import IEHRClient, PatientRecord
from medical_ais.interfaces.embedding import IEmbeddingModel
from medical_ais.interfaces.graph_db import IGraphDB
from medical_ais.interfaces.llm import ILLMProvider, LLMMessage, LLMResponse
from medical_ais.interfaces.reranker import IReranker, RankedResult
from medical_ais.interfaces.search import ISearchEngine, SearchResult
from medical_ais.interfaces.vector_store import IVectorStore, VectorDocument, VectorSearchResult

__all__ = [
    # LLM
    "ILLMProvider", "LLMMessage", "LLMResponse",
    # Graph DB
    "IGraphDB",
    # Vector Store
    "IVectorStore", "VectorDocument", "VectorSearchResult",
    # Search
    "ISearchEngine", "SearchResult",
    # Embedding
    "IEmbeddingModel",
    # Reranker
    "IReranker", "RankedResult",
    # EHR
    "IEHRClient", "PatientRecord",
    # Audit
    "IAuditStore", "AuditRecord",
    # Cache
    "ICacheStore",
    # Action Tool
    "IActionTool", "ActionTier", "ActionResult",
]
