"""
Concrete action tools — EHR writes, notifications, clinical task creation.
Each implements IActionTool and declares its tier + required capabilities.
"""
from __future__ import annotations

from typing import Any

import structlog

from medical_ais.interfaces.action_tool import ActionResult, ActionTier, IActionTool
from medical_ais.interfaces.ehr import IEHRClient

logger = structlog.get_logger(__name__)


class WriteEHRAlertTool(IActionTool):
    """Write a clinical alert to the patient's EHR record (TIER 2)."""

    def __init__(self, ehr_client: IEHRClient) -> None:
        self._ehr = ehr_client

    @property
    def name(self) -> str:
        return "write_ehr_alert"

    @property
    def description(self) -> str:
        return "Write a clinical alert to the patient's EHR record"

    @property
    def tier(self) -> ActionTier:
        return ActionTier.TIER_2

    @property
    def required_capabilities(self) -> list[str]:
        return ["write_ehr_alert"]

    async def execute(self, parameters: dict[str, Any]) -> ActionResult:
        patient_id = parameters["patient_id"]
        alert_type = parameters.get("alert_type", "clinical_alert")
        message = parameters["message"]
        severity = parameters.get("severity", "medium")

        alert_id = await self._ehr.write_alert(patient_id, alert_type, message, severity)
        logger.info("tool.write_ehr_alert", patient_id=patient_id, alert_id=alert_id)
        return ActionResult(
            success=True,
            tool_name=self.name,
            output={"alert_id": alert_id},
        )


class SendNotificationTool(IActionTool):
    """Send a notification to a clinician (TIER_1 — informational only)."""

    @property
    def name(self) -> str:
        return "send_notification"

    @property
    def description(self) -> str:
        return "Send a notification to a clinician or care team"

    @property
    def tier(self) -> ActionTier:
        return ActionTier.TIER_1

    @property
    def required_capabilities(self) -> list[str]:
        return ["send_notification"]

    async def execute(self, parameters: dict[str, Any]) -> ActionResult:
        recipient = parameters.get("recipient", "care_team")
        message = parameters["message"]
        # In production: integrate with messaging system (e.g., FHIR Communication)
        logger.info("tool.send_notification", recipient=recipient, message=message[:100])
        return ActionResult(
            success=True,
            tool_name=self.name,
            output={"status": "sent", "recipient": recipient},
        )


class CreateClinicalTaskTool(IActionTool):
    """Create a clinical task or order (TIER 2 — requires approval)."""

    def __init__(self, ehr_client: IEHRClient) -> None:
        self._ehr = ehr_client

    @property
    def name(self) -> str:
        return "create_clinical_task"

    @property
    def description(self) -> str:
        return "Create a clinical task or follow-up order in the EHR"

    @property
    def tier(self) -> ActionTier:
        return ActionTier.TIER_2

    @property
    def required_capabilities(self) -> list[str]:
        return ["create_clinical_task"]

    async def execute(self, parameters: dict[str, Any]) -> ActionResult:
        patient_id = parameters["patient_id"]
        task_type = parameters.get("task_type", "follow_up")
        description = parameters["description"]

        alert_id = await self._ehr.write_alert(
            patient_id,
            alert_type=task_type,
            message=description,
            severity="low",
        )
        return ActionResult(
            success=True,
            tool_name=self.name,
            output={"task_id": alert_id, "task_type": task_type},
        )


class ScheduleTestTool(IActionTool):
    """Schedule a diagnostic test order (TIER 3 — mandatory human review)."""

    def __init__(self, ehr_client: IEHRClient) -> None:
        self._ehr = ehr_client

    @property
    def name(self) -> str:
        return "schedule_test"

    @property
    def description(self) -> str:
        return "Schedule a diagnostic test or procedure (requires mandatory physician review)"

    @property
    def tier(self) -> ActionTier:
        return ActionTier.TIER_3

    @property
    def required_capabilities(self) -> list[str]:
        return ["schedule_test"]

    async def execute(self, parameters: dict[str, Any]) -> ActionResult:
        patient_id = parameters["patient_id"]
        test_name = parameters["test_name"]
        reason = parameters.get("reason", "")

        alert_id = await self._ehr.write_alert(
            patient_id,
            alert_type="test_order",
            message=f"Order: {test_name}. Reason: {reason}",
            severity="high",
        )
        logger.warning(
            "tool.schedule_test",
            patient_id=patient_id,
            test_name=test_name,
            alert_id=alert_id,
        )
        return ActionResult(
            success=True,
            tool_name=self.name,
            output={"order_id": alert_id, "test": test_name},
        )
