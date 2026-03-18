"""
Input sanitizer for trust-boundary validation.
All user-supplied inputs pass through here before entering the agent graph.
"""
from __future__ import annotations

import re

from pydantic import BaseModel, field_validator, model_validator

from medical_ais.core.exceptions import InputValidationError

# Maximum character lengths
_MAX_QUERY_LEN = 2000
_MAX_PATIENT_ID_LEN = 64
_MAX_SESSION_ID_LEN = 128

# Allowlist: patient IDs are alphanumeric + hyphens only
_PATIENT_ID_RE = re.compile(r"^[A-Za-z0-9\-_]+$")

# Patterns that indicate prompt injection attempts
_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(previous|all|above)\s+instructions?", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+", re.IGNORECASE),
    re.compile(r"act\s+as\s+(if\s+)?you\s+", re.IGNORECASE),
    re.compile(r"system\s*:\s*", re.IGNORECASE),
    re.compile(r"<\|im_start\|>", re.IGNORECASE),
    re.compile(r"\[INST\]", re.IGNORECASE),
]


class QueryInput(BaseModel):
    """Validated, sanitised query coming from the API layer."""

    query: str
    patient_id: str | None = None
    session_id: str | None = None

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Query must not be empty")
        if len(v) > _MAX_QUERY_LEN:
            raise ValueError(f"Query exceeds {_MAX_QUERY_LEN} characters")
        for pattern in _INJECTION_PATTERNS:
            if pattern.search(v):
                raise ValueError("Query contains disallowed content (injection pattern detected)")
        return v

    @field_validator("patient_id")
    @classmethod
    def validate_patient_id(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if len(v) > _MAX_PATIENT_ID_LEN:
            raise ValueError(f"patient_id exceeds {_MAX_PATIENT_ID_LEN} characters")
        if not _PATIENT_ID_RE.match(v):
            raise ValueError("patient_id contains invalid characters")
        return v

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if len(v) > _MAX_SESSION_ID_LEN:
            raise ValueError(f"session_id exceeds {_MAX_SESSION_ID_LEN} characters")
        return v.strip()


def sanitize_query(
    query: str,
    patient_id: str | None = None,
    session_id: str | None = None,
) -> QueryInput:
    """
    Validate and sanitise an incoming query.
    Raises InputValidationError if validation fails.
    """
    try:
        return QueryInput(query=query, patient_id=patient_id, session_id=session_id)
    except Exception as exc:
        raise InputValidationError(f"Input validation failed: {exc}") from exc
