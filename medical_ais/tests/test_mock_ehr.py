"""Unit tests for the mock EHR adapter."""
from __future__ import annotations

import pytest

from medical_ais.adapters.ehr.mock_ehr import MockEHRAdapter
from medical_ais.core.exceptions import PatientNotFoundError


@pytest.mark.asyncio
async def test_get_known_patient():
    ehr = MockEHRAdapter()
    patient = await ehr.get_patient("P001")
    assert patient.patient_id == "P001"
    assert "Type 2 Diabetes" in patient.conditions
    assert "Penicillin" in patient.allergies


@pytest.mark.asyncio
async def test_get_unknown_patient_raises():
    ehr = MockEHRAdapter()
    with pytest.raises(PatientNotFoundError) as exc_info:
        await ehr.get_patient("UNKNOWN")
    assert exc_info.value.patient_id == "UNKNOWN"


@pytest.mark.asyncio
async def test_write_alert_returns_id():
    ehr = MockEHRAdapter()
    alert_id = await ehr.write_alert("P001", "drug_interaction", "Warfarin + Aspirin", "high")
    assert isinstance(alert_id, str)
    assert len(alert_id) > 0
    assert len(ehr._alerts) == 1


@pytest.mark.asyncio
async def test_add_medication():
    ehr = MockEHRAdapter()
    await ehr.update_medication_list("P001", ["Insulin 10 units"], action="add")
    patient = await ehr.get_patient("P001")
    assert "Insulin 10 units" in patient.medications


@pytest.mark.asyncio
async def test_health_check():
    ehr = MockEHRAdapter()
    assert await ehr.health_check() is True
