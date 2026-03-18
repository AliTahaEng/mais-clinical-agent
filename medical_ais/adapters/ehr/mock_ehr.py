"""
Mock EHR adapter for development and testing.
Returns realistic-looking patient records without a FHIR server.
"""
from __future__ import annotations

import uuid

from medical_ais.core.exceptions import PatientNotFoundError
from medical_ais.interfaces.ehr import IEHRClient, PatientRecord

_MOCK_PATIENTS: dict[str, PatientRecord] = {
    "P001": PatientRecord(
        patient_id="P001",
        name="Alice Johnson",
        date_of_birth="1975-03-12",
        conditions=["Type 2 Diabetes", "Hypertension"],
        medications=["Metformin 500mg", "Lisinopril 10mg"],
        allergies=["Penicillin"],
        lab_values={
            "HbA1c": 7.2,
            "creatinine": 0.9,
            "eGFR": 85,
            "blood_pressure_systolic": 138,
        },
        recent_visits=[
            {"date": "2024-11-01", "reason": "Routine follow-up", "provider": "Dr. Smith"}
        ],
    ),
    "P002": PatientRecord(
        patient_id="P002",
        name="Bob Martinez",
        date_of_birth="1960-07-25",
        conditions=["Atrial Fibrillation", "Heart Failure", "CKD Stage 3"],
        medications=["Warfarin 5mg", "Furosemide 40mg", "Carvedilol 12.5mg"],
        allergies=["Aspirin", "NSAIDs"],
        lab_values={
            "INR": 2.4,
            "creatinine": 1.8,
            "eGFR": 42,
            "BNP": 350,
            "potassium": 4.1,
        },
        recent_visits=[
            {"date": "2024-12-10", "reason": "Shortness of breath", "provider": "Dr. Patel"}
        ],
    ),
}


class MockEHRAdapter(IEHRClient):
    """In-memory EHR client for tests and local development."""

    def __init__(self) -> None:
        self._patients: dict[str, PatientRecord] = dict(_MOCK_PATIENTS)
        self._alerts: list[dict] = []

    async def get_patient(self, patient_id: str) -> PatientRecord:
        if patient_id not in self._patients:
            raise PatientNotFoundError(patient_id)
        return self._patients[patient_id]

    async def write_alert(
        self,
        patient_id: str,
        alert_type: str,
        message: str,
        severity: str = "medium",
    ) -> str:
        alert_id = str(uuid.uuid4())
        self._alerts.append(
            {
                "id": alert_id,
                "patient_id": patient_id,
                "type": alert_type,
                "message": message,
                "severity": severity,
            }
        )
        return alert_id

    async def update_medication_list(
        self,
        patient_id: str,
        medications: list[str],
        action: str = "add",
    ) -> None:
        if patient_id not in self._patients:
            raise PatientNotFoundError(patient_id)
        patient = self._patients[patient_id]
        if action == "add":
            patient.medications.extend(
                m for m in medications if m not in patient.medications
            )
        elif action == "remove":
            patient.medications = [m for m in patient.medications if m not in medications]

    async def health_check(self) -> bool:
        return True
