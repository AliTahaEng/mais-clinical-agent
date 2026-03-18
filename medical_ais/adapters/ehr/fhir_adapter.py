"""
FHIR R4 EHR adapter.
Communicates with a real FHIR server using httpx.
"""
from __future__ import annotations

import structlog
import httpx

from medical_ais.core.exceptions import EHRUnavailableError, PatientNotFoundError
from medical_ais.interfaces.ehr import IEHRClient, PatientRecord

logger = structlog.get_logger(__name__)


class FHIRAdapter(IEHRClient):
    """IEHRClient backed by a FHIR R4 server."""

    def __init__(self, server_url: str, api_key: str = "", client_id: str = "") -> None:
        self._base_url = server_url.rstrip("/")
        self._headers = {"Content-Type": "application/fhir+json"}
        if api_key:
            self._headers["Authorization"] = f"Bearer {api_key}"
        self._client_id = client_id
        self._http: httpx.AsyncClient | None = None

    async def connect(self) -> None:
        self._http = httpx.AsyncClient(
            base_url=self._base_url,
            headers=self._headers,
            timeout=30.0,
        )

    async def close(self) -> None:
        if self._http:
            await self._http.aclose()

    # ── IEHRClient ────────────────────────────────────────────────────────────

    async def get_patient(self, patient_id: str) -> PatientRecord:
        self._ensure_connected()
        try:
            r = await self._http.get(f"/Patient/{patient_id}")
        except httpx.RequestError as exc:
            raise EHRUnavailableError(f"FHIR server unreachable: {exc}") from exc

        if r.status_code == 404:
            raise PatientNotFoundError(patient_id)
        r.raise_for_status()

        resource = r.json()
        return self._parse_patient(resource)

    async def write_alert(
        self,
        patient_id: str,
        alert_type: str,
        message: str,
        severity: str = "medium",
    ) -> str:
        self._ensure_connected()
        flag_resource = {
            "resourceType": "Flag",
            "status": "active",
            "category": [{"text": alert_type}],
            "subject": {"reference": f"Patient/{patient_id}"},
            "description": {"text": message},
            "extension": [
                {
                    "url": "http://example.com/fhir/StructureDefinition/severity",
                    "valueString": severity,
                }
            ],
        }
        try:
            r = await self._http.post("/Flag", json=flag_resource)
        except httpx.RequestError as exc:
            raise EHRUnavailableError(f"FHIR server unreachable: {exc}") from exc
        r.raise_for_status()
        return r.json().get("id", "")

    async def update_medication_list(
        self,
        patient_id: str,
        medications: list[str],
        action: str = "add",
    ) -> None:
        # Real FHIR implementations would create/cancel MedicationRequest resources
        # Simplified: log intent only — production would implement full FHIR workflow
        logger.info(
            "fhir.medication_update",
            patient_id=patient_id,
            action=action,
            medications=medications,
        )

    async def health_check(self) -> bool:
        try:
            self._ensure_connected()
            r = await self._http.get("/metadata")
            return r.status_code == 200
        except Exception:
            return False

    # ── helpers ───────────────────────────────────────────────────────────────

    def _ensure_connected(self) -> None:
        if self._http is None:
            raise EHRUnavailableError("FHIRAdapter not connected — call connect() first")

    @staticmethod
    def _parse_patient(resource: dict) -> PatientRecord:
        name_parts = resource.get("name", [{}])[0]
        given = " ".join(name_parts.get("given", []))
        family = name_parts.get("family", "")
        return PatientRecord(
            patient_id=resource.get("id", ""),
            name=f"{given} {family}".strip(),
            date_of_birth=resource.get("birthDate", ""),
            conditions=[],   # Would require querying Condition resources
            medications=[],  # Would require querying MedicationRequest resources
            allergies=[],    # Would require querying AllergyIntolerance resources
        )
