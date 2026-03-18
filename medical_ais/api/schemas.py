"""
Pydantic request/response schemas for the FastAPI layer.
All external inputs are validated here before entering the graph.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ── Auth schemas ──────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    username: str = Field(..., min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_\-]+$")
    password: str = Field(..., min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: str = Field(..., max_length=254)
    password: str = Field(..., max_length=128)


class UserResponse(BaseModel):
    id: str
    email: str
    username: str
    role: str  # "user" | "admin"


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


# ── Request schemas ────────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    patient_id: str | None = Field(None, pattern=r"^[A-Za-z0-9\-_]+$", max_length=64)
    session_id: str | None = Field(None, max_length=128)


class ApprovalRequest(BaseModel):
    """Resume a paused graph with human approval/rejection of proposed actions."""
    session_id: str
    approved_indices: list[int] = Field(default_factory=list)
    feedback: str = Field(default="Approved", max_length=1000)


class IngestRequest(BaseModel):
    documents_dir: str | None = None  # Uses settings default if omitted


# ── Response schemas ───────────────────────────────────────────────────────────

class QueryResponse(BaseModel):
    session_id: str
    answer: str
    confidence_score: float
    fact_check_passed: bool
    retrieval_quality: float
    chunks_used: int
    actions_proposed: int
    actions_executed: int
    requires_human_approval: bool
    status: str  # "complete" | "awaiting_approval" | "escalated" | "error"


class ActionSummary(BaseModel):
    tool_name: str
    tier: int
    rationale: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class ApprovalResponse(BaseModel):
    session_id: str
    approved_count: int
    executed_count: int
    status: str


class HealthResponse(BaseModel):
    status: str  # "healthy" | "degraded" | "unhealthy"
    timestamp: datetime
    services: dict[str, bool] = Field(default_factory=dict)


class IngestResponse(BaseModel):
    status: str
    documents_loaded: int
    entities_written: int
    relationships_written: int
    communities_found: int
    chunks_embedded: int
    errors: list[str] = Field(default_factory=list)


# ── Approval management schemas ────────────────────────────────────────────────

class ApprovalDecisionRequest(BaseModel):
    """Submit a human approval/rejection decision."""
    approved_indices: list[int] = Field(default_factory=list)
    feedback: str = Field(default="Approved", max_length=1000)


class ApprovalDecisionResponse(BaseModel):
    session_id: str
    approved_count: int
    executed_count: int
    status: str


class ApprovalDetailResponse(BaseModel):
    session_id: str
    message: str = ""
    proposed_actions: list[dict] = Field(default_factory=list)
    status: str = "pending"
    approved_indices: list[int] = Field(default_factory=list)
    feedback: str = ""


class ApprovalListResponse(BaseModel):
    items: list[ApprovalDetailResponse] = Field(default_factory=list)
    total: int = 0
