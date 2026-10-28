import logging

import pytest
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from app.core.dependencies import get_db
from app.main import app
from app.routes.radius_auth import verify_radius_secret
from app.services.radius_auth_service import RadiusAuthService


@pytest.fixture
def radius_db():
    client = AsyncMongoMockClient(tz_aware=True)
    yield client["radius_accounting_endpoint_test"]
    client.close()


@pytest.mark.parametrize(
    ("status_code", "expected_status"),
    [(1, "Start"), (3, "Interim-Update"), (2, "Stop")],
)
def test_accounting_endpoint_accepts_freeradius_numeric_payloads(
    status_code,
    expected_status,
    monkeypatch,
    radius_db,
):
    received = []

    async def unused_database_dependency():
        return radius_db

    async def capture_accounting(_service, request):
        received.append(request)

    monkeypatch.setitem(app.dependency_overrides, get_db, unused_database_dependency)
    monkeypatch.setitem(app.dependency_overrides, verify_radius_secret, lambda: True)
    monkeypatch.setattr(RadiusAuthService, "accounting", capture_accounting)

    response = TestClient(app).post(
        "/api/v1/radius/accounting",
        json={
            "request:Acct-Status-Type": {"type": "integer", "value": [status_code]},
            "request:Acct-Session-Id": {"type": "string", "value": ["session-test"]},
            "request:NAS-Port": {"type": "integer", "value": [7]},
            "request:Acct-Session-Time": {"type": "integer", "value": [120]},
            "request:Acct-Input-Octets": {"type": "integer", "value": [2048]},
            "request:Acct-Output-Octets": {"type": "integer", "value": [4096]},
            "request:Acct-Input-Gigawords": {"type": "integer", "value": [1]},
            "request:Acct-Output-Gigawords": {"type": "integer", "value": [2]},
            "request:Framed-IP-Address": {"type": "ipaddr", "value": ["198.51.100.10"]},
            "request:Calling-Station-Id": {"type": "string", "value": ["AA:BB:CC:DD:EE:FF"]},
            "request:Called-Station-Id": {"type": "string", "value": ["ssid"]},
        },
    )

    assert response.status_code == 204
    assert len(received) == 1
    assert received[0].Acct_Status_Type == expected_status
    assert received[0].Acct_Session_Id == "session-test"
    assert received[0].NAS_Port == "7"
    assert received[0].Acct_Session_Time == 120
    assert received[0].Acct_Input_Octets == 2048
    assert received[0].Acct_Output_Octets == 4096
    assert received[0].Acct_Input_Gigawords == 1
    assert received[0].Acct_Output_Gigawords == 2
    assert received[0].Framed_IP_Address == "198.51.100.10"
    assert received[0].Calling_Station_Id == "AA:BB:CC:DD:EE:FF"
    assert received[0].Called_Station_Id == "ssid"


def test_accounting_endpoint_accepts_missing_optional_attributes(monkeypatch, radius_db):
    received = []

    async def unused_database_dependency():
        return radius_db

    async def capture_accounting(_service, request):
        received.append(request)

    monkeypatch.setitem(app.dependency_overrides, get_db, unused_database_dependency)
    monkeypatch.setitem(app.dependency_overrides, verify_radius_secret, lambda: True)
    monkeypatch.setattr(RadiusAuthService, "accounting", capture_accounting)

    response = TestClient(app).post(
        "/api/v1/radius/accounting",
        json={"Acct-Status-Type": "Start"},
    )

    assert response.status_code == 204
    assert len(received) == 1
    assert received[0].Acct_Status_Type == "Start"
    assert received[0].Acct_Session_Id is None


def test_accounting_validation_diagnostics_redact_invalid_input(caplog, monkeypatch, radius_db):
    sensitive_value = "accounting-sensitive-marker"
    received = []

    async def unused_database_dependency():
        return radius_db

    async def capture_accounting(_service, request):
        received.append(request)

    monkeypatch.setitem(app.dependency_overrides, get_db, unused_database_dependency)
    monkeypatch.setitem(app.dependency_overrides, verify_radius_secret, lambda: True)
    monkeypatch.setattr(RadiusAuthService, "accounting", capture_accounting)
    caplog.set_level(logging.WARNING, logger="app.main")

    response = TestClient(app).post(
        "/api/v1/radius/accounting",
        json={
            "Acct-Status-Type": "Interim-Update",
            "Acct-Session-Time": sensitive_value,
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": [
            {"loc": ["body", "Acct-Session-Time"], "type": "int_parsing"},
        ],
    }
    assert sensitive_value not in response.text
    assert sensitive_value not in caplog.text
    assert "/api/v1/radius/accounting" in caplog.text
    assert "Acct-Session-Time" in caplog.text
    assert "int_parsing" in caplog.text
    assert received == []
