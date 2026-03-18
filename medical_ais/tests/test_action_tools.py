"""Unit tests for action tools and the tool registry."""
from __future__ import annotations

import pytest

from medical_ais.core.exceptions import ToolNotFoundError, UnauthorizedAgentAction
from medical_ais.interfaces.action_tool import ActionTier


@pytest.mark.asyncio
async def test_send_notification_tool(tool_registry):
    result = await tool_registry.execute(
        "send_notification",
        {"recipient": "dr_smith", "message": "Drug interaction alert for patient P001"},
        agent_id="action_agent",
    )
    assert result.success is True
    assert result.output["status"] == "sent"


@pytest.mark.asyncio
async def test_write_ehr_alert_tool(tool_registry):
    result = await tool_registry.execute(
        "write_ehr_alert",
        {"patient_id": "P001", "message": "Warfarin-Aspirin interaction detected", "severity": "high"},
        agent_id="action_agent",
    )
    assert result.success is True
    assert "alert_id" in result.output


@pytest.mark.asyncio
async def test_unknown_tool_raises(tool_registry):
    with pytest.raises(ToolNotFoundError):
        await tool_registry.execute("nonexistent_tool", {})


@pytest.mark.asyncio
async def test_unauthorized_agent_raises(tool_registry):
    with pytest.raises(UnauthorizedAgentAction):
        await tool_registry.execute(
            "write_ehr_alert",
            {"patient_id": "P001", "message": "test"},
            agent_id="supervisor",  # supervisor lacks write_ehr_alert capability
        )


def test_tool_tiers(tool_registry):
    tools = tool_registry.list_tools()
    notification_tool = next(t for t in tools if t["name"] == "send_notification")
    ehr_tool = next(t for t in tools if t["name"] == "write_ehr_alert")
    assert notification_tool["tier"] == ActionTier.TIER_1
    assert ehr_tool["tier"] == ActionTier.TIER_2
