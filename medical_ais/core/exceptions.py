"""
All custom exceptions for the Medical Autonomous Intelligence System.
Single file — easy to find every error type in the system.
"""
from __future__ import annotations


# ── Base ──────────────────────────────────────────────────────────────────────

class MAISError(Exception):
    """Base exception for all MAIS errors."""

    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


# ── Infrastructure ────────────────────────────────────────────────────────────

class ServiceUnavailableError(MAISError):
    """Raised when a required external service is unreachable."""


class CircuitBreakerOpenError(MAISError):
    """Raised when circuit breaker is in OPEN state — service is down."""


class ConfigurationError(MAISError):
    """Raised when required configuration is missing or invalid."""


# ── Graph Database ────────────────────────────────────────────────────────────

class GraphDBError(MAISError):
    """Base exception for graph database errors."""


class GraphDBUnavailableError(GraphDBError):
    """Raised when Neo4j/Memgraph is unreachable."""


class EntityNotFoundError(GraphDBError):
    """Raised when a requested entity does not exist in the graph."""

    def __init__(self, entity_name: str) -> None:
        super().__init__(f"Entity not found in knowledge graph: '{entity_name}'")
        self.entity_name = entity_name


# ── Vector Store ─────────────────────────────────────────────────────────────

class VectorStoreError(MAISError):
    """Base exception for vector store errors."""


class VectorStoreUnavailableError(VectorStoreError):
    """Raised when vector store is unreachable."""


# ── LLM ──────────────────────────────────────────────────────────────────────

class LLMError(MAISError):
    """Base exception for LLM provider errors."""


class LLMRateLimitError(LLMError):
    """Raised when LLM API rate limit is exceeded."""


class LLMInvalidResponseError(LLMError):
    """Raised when LLM returns an unparseable or invalid response."""

    def __init__(self, message: str, raw_response: str = "") -> None:
        super().__init__(message)
        self.raw_response = raw_response


# ── EHR ──────────────────────────────────────────────────────────────────────

class EHRError(MAISError):
    """Base exception for EHR integration errors."""


class EHRUnavailableError(EHRError):
    """Raised when the EHR system is unreachable."""


class PatientNotFoundError(EHRError):
    """Raised when a patient ID does not exist in EHR."""

    def __init__(self, patient_id: str) -> None:
        super().__init__(f"Patient not found in EHR: '{patient_id}'")
        self.patient_id = patient_id


# ── Security ──────────────────────────────────────────────────────────────────

class SecurityError(MAISError):
    """Base exception for security violations."""


class UnauthorizedAgentAction(SecurityError):
    """Raised when an agent attempts an action outside its capability manifest."""

    def __init__(self, agent_id: str, capability: str) -> None:
        super().__init__(
            f"Agent '{agent_id}' is not authorized to perform '{capability}'"
        )
        self.agent_id = agent_id
        self.capability = capability


class UnknownAgentError(SecurityError):
    """Raised when an agent ID is not registered in the capability registry."""

    def __init__(self, agent_id: str) -> None:
        super().__init__(f"Unknown agent ID: '{agent_id}'")
        self.agent_id = agent_id


class InputValidationError(SecurityError):
    """Raised when input fails schema validation at a trust boundary."""


# ── Tools ─────────────────────────────────────────────────────────────────────

class ToolError(MAISError):
    """Base exception for tool execution errors."""


class ToolNotFoundError(ToolError):
    """Raised when a requested tool name is not registered."""

    def __init__(self, tool_name: str) -> None:
        super().__init__(f"Tool not found in registry: '{tool_name}'")
        self.tool_name = tool_name


class ToolTimeoutError(ToolError):
    """Raised when a tool execution exceeds the timeout limit."""

    def __init__(self, tool_name: str, timeout_seconds: float) -> None:
        super().__init__(
            f"Tool '{tool_name}' timed out after {timeout_seconds}s"
        )
        self.tool_name = tool_name
        self.timeout_seconds = timeout_seconds


class ToolExecutionError(ToolError):
    """Raised when a tool fails during execution."""


# ── Agent / State Machine ─────────────────────────────────────────────────────

class AgentError(MAISError):
    """Base exception for agent execution errors."""


class MaxIterationsExceededError(AgentError):
    """Raised when agent exceeds max reasoning loop iterations."""

    def __init__(self, max_iterations: int) -> None:
        super().__init__(
            f"Agent exceeded maximum iterations: {max_iterations}"
        )
        self.max_iterations = max_iterations


class InvalidProtocolVersionError(AgentError):
    """Raised when an unsupported protocol version is encountered."""

    def __init__(self, version: str) -> None:
        super().__init__(f"Unsupported protocol version: '{version}'")
        self.version = version


# ── Pipeline ─────────────────────────────────────────────────────────────────

class PipelineError(MAISError):
    """Base exception for data pipeline errors."""


class DocumentIngestionError(PipelineError):
    """Raised when a document cannot be loaded or parsed."""


class EntityExtractionError(PipelineError):
    """Raised when entity/relationship extraction fails."""


# ── Action / Audit ────────────────────────────────────────────────────────────

class ActionError(MAISError):
    """Base exception for action execution errors."""


class ActionNotApprovedError(ActionError):
    """Raised when attempting to execute an action without required approval."""


class AuditStoreError(MAISError):
    """Raised when audit trail recording fails."""
