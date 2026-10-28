import logging
from datetime import datetime, timedelta, timezone

import pytest
from mongomock_motor import AsyncMongoMockClient
from fastapi import HTTPException

from app.core.config import settings
from app.routes.radius_auth import verify_radius_secret
from app.schemas.radius_auth import RadiusAccountingRequest, RadiusAuthRequest
from app.services.radius_auth_service import RadiusAuthService


def test_radius_auth_request_flattens_freeradius_json_attributes():
    request = RadiusAuthRequest.model_validate({
        "request:User-Name": {"type": "string", "value": ["voucher-code"]},
        "User-Password": {"type": "string", "value": ["voucher-code"]},
        "Calling-Station-Id": {"type": "string", "value": ["aa-bb-cc-dd-ee-ff"]},
    })

    assert request.User_Name == "voucher-code"
    assert request.User_Password == "voucher-code"
    assert request.Calling_Station_Id == "aa-bb-cc-dd-ee-ff"


@pytest.mark.parametrize(
    ("request_model", "payload", "expected_port"),
    [
        (RadiusAuthRequest, {"NAS-Port": 17}, "17"),
        (RadiusAuthRequest, {"NAS-Port": "17"}, "17"),
        (
            RadiusAccountingRequest,
            {"Acct-Status-Type": "Start", "request:NAS-Port": {"type": "integer", "value": [17]}},
            "17",
        ),
        (
            RadiusAccountingRequest,
            {"Acct-Status-Type": "Start", "NAS-Port": "17"},
            "17",
        ),
    ],
)
def test_radius_requests_accept_integer_and_string_nas_port(request_model, payload, expected_port):
    request = request_model.model_validate(payload)

    assert request.NAS_Port == expected_port


def test_radius_accounting_request_flattens_freeradius_json_attributes():
    request = RadiusAccountingRequest.model_validate({
        "request:Acct-Status-Type": {"type": "string", "value": ["Interim-Update"]},
        "request:Acct-Session-Time": {"type": "integer", "value": ["120"]},
        "request:Acct-Session-Id": {"type": "string", "value": ["session-123"]},
    })

    assert request.Acct_Status_Type == "Interim-Update"
    assert request.Acct_Session_Time == 120
    assert request.Acct_Session_Id == "session-123"


@pytest.mark.parametrize(
    ("status_value", "expected_status"),
    [
        (1, "Start"),
        ("1", "Start"),
        (2, "Stop"),
        ("2", "Stop"),
        (3, "Interim-Update"),
        ("3", "Interim-Update"),
        ("Start", "Start"),
        ("Interim-Update", "Interim-Update"),
        ("Stop", "Stop"),
    ],
)
def test_accounting_request_accepts_integer_enum_status_and_string_labels(status_value, expected_status):
    request = RadiusAccountingRequest.model_validate({
        "request:Acct-Status-Type": {"type": "integer", "value": [status_value]},
    })

    assert request.Acct_Status_Type == expected_status


@pytest.mark.parametrize("numeric_value", [123, "123"])
def test_accounting_numeric_attributes_accept_integer_and_numeric_string(numeric_value):
    request = RadiusAccountingRequest.model_validate({
        "Acct-Status-Type": "Interim-Update",
        "NAS-Port": numeric_value,
        "Acct-Session-Time": numeric_value,
        "Acct-Input-Octets": numeric_value,
        "Acct-Output-Octets": numeric_value,
        "Acct-Input-Gigawords": numeric_value,
        "Acct-Output-Gigawords": numeric_value,
        "Event-Timestamp": numeric_value,
    })

    assert request.NAS_Port == "123"
    assert request.Acct_Session_Time == 123
    assert request.Acct_Input_Octets == 123
    assert request.Acct_Output_Octets == 123
    assert request.Acct_Input_Gigawords == 123
    assert request.Acct_Output_Gigawords == 123
    assert request.Event_Timestamp == 123


def test_radius_integer_enum_attributes_are_compatible_with_string_fields():
    request = RadiusAccountingRequest.model_validate({
        "Acct-Status-Type": "Start",
        "NAS-Port-Type": 19,
        "Service-Type": 2,
        "Framed-Protocol": 1,
        "Acct-Authentic": 1,
        "Acct-Terminate-Cause": 1,
        "Event-Timestamp": 1_798_000_000,
    })

    assert request.NAS_Port_Type == "19"
    assert request.Service_Type == "2"
    assert request.Framed_Protocol == "1"
    assert request.Acct_Authentic == "1"
    assert request.Acct_Terminate_Cause == "1"
    assert request.Event_Timestamp == 1_798_000_000


def test_radius_internal_api_requires_its_separate_secret(monkeypatch):
    monkeypatch.setattr(settings, "radius_api_secret", "private-api-secret")

    assert verify_radius_secret("private-api-secret") is True
    with pytest.raises(HTTPException) as error:
        verify_radius_secret("router-shared-secret")
    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_radius_user_auth_rejects_missing_password():
    client = AsyncMongoMockClient(tz_aware=True)
    db = client["radius_password_test"]
    await db.radius_users.insert_one({
        "username": "pppoe-user",
        "password": "correct-password",
        "user_type": "pppoe",
        "status": "active",
    })
    service = RadiusAuthService(db)

    reply = await service.authenticate(RadiusAuthRequest.model_validate({
        "User-Name": "pppoe-user",
        "NAS-IP-Address": "192.0.2.1",
    }))

    assert reply.control_Auth_Type == "Reject"
    client.close()


@pytest.mark.asyncio
async def test_used_voucher_allows_same_device_retry_but_rejects_another_device():
    client = AsyncMongoMockClient(tz_aware=True)
    db = client["radius_retry_test"]
    result = await db.vouchers.insert_one({
        "voucher_code": "retry-code",
        "status": "active",
    })
    service = RadiusAuthService(db)
    station = "AA:BB:CC:DD:EE:FF"

    voucher = await service._check_voucher("retry-code", station)
    assert voucher is not None
    first_reply = await service._authorize_voucher(voucher, "192.0.2.1", station)
    assert first_reply.control_Auth_Type == "Accept"

    retry_voucher = await service._check_voucher("retry-code", station)
    assert retry_voucher is not None
    retry_reply = await service._authorize_voucher(retry_voucher, "192.0.2.1", station)
    assert retry_reply.control_Auth_Type == "Accept"
    assert await service._check_voucher("retry-code", "11:22:33:44:55:66") is None

    stored = await db.vouchers.find_one({"_id": result.inserted_id})
    assert stored["status"] == "used"
    assert stored["calling_station_id"] == station
    client.close()


@pytest.mark.asyncio
async def test_voucher_lookup_diagnostics_distinguish_missing_code_without_logging_it(caplog):
    client = AsyncMongoMockClient(tz_aware=True)
    service = RadiusAuthService(client["radius_missing_voucher_test"])
    code = "SensitiveVoucherCode"
    caplog.set_level(logging.WARNING, logger="app.services.radius_auth_service")

    assert await service._check_voucher(code, "AA:BB:CC:DD:EE:FF") is None

    assert "reason=no_exact_match" in caplog.text
    assert "lowercase_characters=True" in caplog.text
    assert code not in caplog.text
    assert "AA:BB:CC:DD:EE:FF" not in caplog.text
    client.close()


@pytest.mark.asyncio
async def test_voucher_lookup_diagnostics_report_ineligible_status_without_logging_code(caplog):
    client = AsyncMongoMockClient(tz_aware=True)
    db = client["radius_ineligible_voucher_test"]
    code = "SensitiveGeneratedVoucher"
    await db.vouchers.insert_one({"voucher_code": code, "status": "generated"})
    service = RadiusAuthService(db)
    caplog.set_level(logging.WARNING, logger="app.services.radius_auth_service")

    assert await service._check_voucher(code, "") is None

    assert "reason=status_not_eligible status=generated" in caplog.text
    assert code not in caplog.text
    client.close()


@pytest.mark.asyncio
async def test_voucher_lookup_diagnostics_detect_case_and_whitespace_mismatch(caplog):
    client = AsyncMongoMockClient(tz_aware=True)
    db = client["radius_voucher_format_test"]
    stored_code = "SENSITIVEVOUCHERCODE"
    submitted_code = f" {stored_code.lower()} "
    await db.vouchers.insert_one({"voucher_code": stored_code, "status": "active"})
    service = RadiusAuthService(db)
    caplog.set_level(logging.WARNING, logger="app.services.radius_auth_service")

    assert await service._check_voucher(submitted_code, "") is None

    assert "reason=username_format_mismatch" in caplog.text
    assert "surrounding_whitespace=True" in caplog.text
    assert "lowercase_characters=True" in caplog.text
    assert stored_code not in caplog.text
    assert submitted_code not in caplog.text
    client.close()


@pytest.mark.asyncio
async def test_voucher_lookup_diagnostics_distinguish_device_binding_failure(caplog):
    client = AsyncMongoMockClient(tz_aware=True)
    db = client["radius_voucher_binding_test"]
    code = "SensitiveBoundVoucher"
    station = "AA:BB:CC:DD:EE:FF"
    await db.vouchers.insert_one({
        "voucher_code": code,
        "status": "active",
        "bound_mac": station,
    })
    service = RadiusAuthService(db)
    caplog.set_level(logging.WARNING, logger="app.services.radius_auth_service")

    assert await service._check_voucher(code, "11:22:33:44:55:66") is None

    assert "stage=device_binding reason=mac_mismatch" in caplog.text
    assert code not in caplog.text
    assert station not in caplog.text
    assert "11:22:33:44:55:66" not in caplog.text
    client.close()


@pytest.mark.asyncio
async def test_voucher_lookup_diagnostics_distinguish_expiry_failure(caplog):
    client = AsyncMongoMockClient(tz_aware=True)
    db = client["radius_voucher_expiry_test"]
    code = "SensitiveExpiredVoucher"
    await db.vouchers.insert_one({
        "voucher_code": code,
        "status": "active",
        "expiry_date": datetime.now(timezone.utc) - timedelta(minutes=1),
    })
    service = RadiusAuthService(db)
    caplog.set_level(logging.WARNING, logger="app.services.radius_auth_service")

    assert await service._check_voucher(code, "") is None

    assert "stage=expiry reason=expired" in caplog.text
    assert code not in caplog.text
    stored = await db.vouchers.find_one({"voucher_code": code})
    assert stored["status"] == "expired"
    client.close()


@pytest.mark.asyncio
async def test_voucher_retry_does_not_restart_expiry_or_data_quota():
    client = AsyncMongoMockClient(tz_aware=True)
    db = client["radius_quota_test"]
    expiry = datetime.now(timezone.utc) + timedelta(minutes=1)
    result = await db.vouchers.insert_one({
        "voucher_code": "quota-code",
        "status": "active",
        "duration_hours": 3,
        "data_allowance_mb": 6000,
        "expiry_date": expiry,
    })
    await db.radius_accounting.insert_many([
        {
            "voucher_id": str(result.inserted_id),
            "acct_input_octets": 3 * 1024 * 1024,
            "acct_output_octets": 0,
        },
        {
            "voucher_id": str(result.inserted_id),
            "acct_input_octets": 0,
            "acct_output_octets": 1024 * 1024,
        },
    ])
    service = RadiusAuthService(db)
    station = "AA:BB:CC:DD:EE:FF"
    voucher = await service._check_voucher("quota-code", station)
    assert voucher is not None

    reply = await service._authorize_voucher(voucher, "192.0.2.1", station)

    assert reply.control_Auth_Type == "Accept"
    assert reply.reply_Session_Timeout is not None
    assert reply.reply_Session_Timeout <= 60
    assert reply.reply_Mikrotik_Total_Limit is not None
    assert reply.reply_Mikrotik_Total_Limit_Gigawords == 1
    assert (
        reply.reply_Mikrotik_Total_Limit
        + reply.reply_Mikrotik_Total_Limit_Gigawords * (2**32)
        == 6000 * 1024 * 1024 - 4 * 1024 * 1024
    )

    saved = await db.vouchers.find_one({"_id": result.inserted_id})
    saved_expiry = saved["expiry_date"]
    retry_voucher = await service._check_voucher("quota-code", station)
    assert retry_voucher is not None
    retry_reply = await service._authorize_voucher(retry_voucher, "192.0.2.1", station)
    assert retry_reply.reply_Session_Timeout is not None
    assert retry_reply.reply_Session_Timeout <= 60
    saved_after_retry = await db.vouchers.find_one({"_id": result.inserted_id})
    assert saved_after_retry["expiry_date"] == saved_expiry
    client.close()
