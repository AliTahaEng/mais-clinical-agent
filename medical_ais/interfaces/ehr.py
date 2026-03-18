"""
Abstract interface for EHR / FHIR integration.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PatientRecord:
    patient_id: str
    name: str
    date_of_birth: str
    conditions: list[str] = field(default_factory=list)
    medications: list[str] = field(default_factory=list)
    allergies: list[str] = field(default_factory=list)
    lab_values: dict[str, Any] = field(default_factory=dict)
    recent_visits: list[dict] = field(default_factory=list)


class IEHRClient(ABC):
    """Contract every EHR adapter must satisfy."""

    @abstractmethod
    async def get_patient(self, patient_id: str) -> PatientRecord:
        """
        Fetch patient record by ID.
        Raises PatientNotFoundError if not found.
        """

    @abstractmethod
    async def write_alert(
        self,
        patient_id: str,
        alert_type: str,
        message: str,
        severity: str = "medium",
    ) -> str:
        """Write a clinical alert. Returns the created alert ID."""

    @abstractmethod
    async def update_medication_list(
        self,
        patient_id: str,
        medications: list[str],
        action: str = "add",
    ) -> None:
        """Add or remove medications from the patient's active list."""

    @abstractmethod
    async def health_check(self) -> bool:
        """Return True if the EHR system is reachable."""
