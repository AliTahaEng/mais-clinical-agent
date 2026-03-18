"""Unit tests for the capability guard."""
from __future__ import annotations

import pytest

from medical_ais.core.exceptions import UnauthorizedAgentAction, UnknownAgentError
from medical_ais.security.capability_guard import CapabilityGuard


def test_known_agent_allowed_capability():
    guard = CapabilityGuard()
    guard.check("supervisor", "route_query")  # Should not raise


def test_known_agent_disallowed_capability():
    guard = CapabilityGuard()
    with pytest.raises(UnauthorizedAgentAction) as exc_info:
        guard.check("supervisor", "write_ehr_alert")
    assert exc_info.value.agent_id == "supervisor"
    assert exc_info.value.capability == "write_ehr_alert"


def test_unknown_agent_raises():
    guard = CapabilityGuard()
    with pytest.raises(UnknownAgentError):
        guard.check("nonexistent_agent", "any_capability")


def test_register_and_check():
    guard = CapabilityGuard()
    guard.register_agent("custom_agent", ["cap_a", "cap_b"])
    guard.check("custom_agent", "cap_a")  # Should not raise
    with pytest.raises(UnauthorizedAgentAction):
        guard.check("custom_agent", "cap_c")
