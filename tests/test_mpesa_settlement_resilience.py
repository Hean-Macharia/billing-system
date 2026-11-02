import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from bson import ObjectId
from mongomock_motor import AsyncMongoMockClient

from app.services.mpesa_service import MpesaService
from app.services.notification_service import NotificationService


def _confirmed_hotspot_tx():
    return {
        "transaction_type": "hotspot_purchase",
        "checkout_request_id": "checkout-resilience-test",
        "hotspot_plan_id": "plan-id",
        "amount": 10,
        "phone_number": "254700000000",
        "device_mac": "AA:BB:CC:DD:EE:FF",
        "device_type": "this_device",
        "account_reference": "Test bundle",
        "transaction_desc": "HotSpot test purchase",
        "status": "success",
        "callback_received": True,
        "settled": False,
        "settlement_status": "pending",
        "mpesa_receipt_number": "TST1234567",
        "site_id": "site-test",
        "router_id": "router-test",
    }


@pytest.mark.asyncio
async def test_notification_database_failure_is_best_effort(caplog):
    class BrokenNotifications:
        async def insert_one(self, _doc):
            raise RuntimeError("database unavailable")

    service = NotificationService(SimpleNamespace(notifications=BrokenNotifications()))
    service._sms_configured = lambda: False
    caplog.set_level(logging.WARNING, logger="app.services.notification_service")

    result = await service.notify(subject="Purchase", body="Paid access ready")

    assert result.id is None
    assert "notification_persistence_failed" in caplog.text
    assert "database unavailable" not in caplog.text


@pytest.mark.asyncio
async def test_notification_persistence_failure_does_not_reverse_paid_voucher_settlement(monkeypatch):
    client = AsyncMongoMockClient(tz_aware=True)
    db = client["mpesa_notification_resilience_test"]
    inserted = await db.mpesa_transactions.insert_one(_confirmed_hotspot_tx())
    created_vouchers = []

    class FakeVoucherService:
        USE_PLAN_SITE = object()

        def __init__(self, _db):
            pass

        async def create_hotspot_purchase_voucher(self, **kwargs):
            created_vouchers.append(kwargs["purchase_transaction_id"])
            return {"voucher_code": "TST1234567"}

    class FailingNotificationService:
        def __init__(self, _db):
            pass

        async def notify(self, **_kwargs):
            raise RuntimeError("notification database unavailable")

    monkeypatch.setattr("app.services.voucher_service.VoucherService", FakeVoucherService)
    monkeypatch.setattr("app.services.notification_service.NotificationService", FailingNotificationService)

    transaction = await MpesaService(db)._settle_verified_success(
        await db.mpesa_transactions.find_one({"_id": inserted.inserted_id})
    )

    assert transaction.status.value == "success"
    assert transaction.settled is True
    assert transaction.settlement_status == "completed"
    assert transaction.voucher_code == "TST1234567"
    assert created_vouchers == [str(inserted.inserted_id)]
    client.close()


@pytest.mark.asyncio
async def test_hotspot_status_retries_a_recoverable_settlement_without_requerying_daraja(monkeypatch):
    client = AsyncMongoMockClient(tz_aware=True)
    db = client["mpesa_status_settlement_retry_test"]
    inserted = await db.mpesa_transactions.insert_one(_confirmed_hotspot_tx())
    service = MpesaService(db)
    service.daraja.query_stk_status = Mock(side_effect=AssertionError("must not query Daraja while polling"))
    settlement_calls = []

    async def settle(_doc):
        settlement_calls.append(True)
        await db.mpesa_transactions.update_one(
            {"_id": inserted.inserted_id},
            {"$set": {"settled": True, "settlement_status": "completed", "voucher_code": "TST1234567"}},
        )
        return await service.get_by_id(str(inserted.inserted_id))

    monkeypatch.setattr(service, "_settle_verified_success", settle)
    transaction = await service.get_hotspot_purchase_status("checkout-resilience-test")

    assert transaction.settled is True
    assert transaction.voucher_code == "TST1234567"
    assert settlement_calls == [True]
    service.daraja.query_stk_status.assert_not_called()
    client.close()


@pytest.mark.asyncio
async def test_settlement_retry_is_backed_off_and_then_recovers_existing_voucher(monkeypatch):
    client = AsyncMongoMockClient(tz_aware=True)
    db = client["mpesa_partial_settlement_recovery_test"]
    inserted = await db.mpesa_transactions.insert_one(_confirmed_hotspot_tx())
    service = MpesaService(db)
    existing_voucher = {"voucher_code": "TST1234567"}
    voucher_creation_attempts = []

    class IdempotentVoucherService:
        USE_PLAN_SITE = object()

        def __init__(self, _db):
            pass

        async def create_hotspot_purchase_voucher(self, **kwargs):
            voucher_creation_attempts.append(kwargs["purchase_transaction_id"])
            return existing_voucher

    class SafeNotificationService:
        def __init__(self, _db):
            pass

        async def notify(self, **_kwargs):
            return None

    monkeypatch.setattr("app.services.voucher_service.VoucherService", IdempotentVoucherService)
    monkeypatch.setattr("app.services.notification_service.NotificationService", SafeNotificationService)

    # Simulate an interruption after the idempotent voucher operation returned,
    # but before the transaction could persist its voucher reference.
    original_update_one = service.collection.update_one
    fail_once = {"pending": True}

    async def fail_voucher_reference_once(query, update, *args, **kwargs):
        if fail_once["pending"] and "voucher_code" in update.get("$set", {}):
            fail_once["pending"] = False
            raise RuntimeError("temporary database write failure")
        return await original_update_one(query, update, *args, **kwargs)

    monkeypatch.setattr(service.collection, "update_one", fail_voucher_reference_once)
    first = await service._settle_verified_success(
        await db.mpesa_transactions.find_one({"_id": inserted.inserted_id})
    )
    assert first.status.value == "success"
    assert first.settled is False
    assert first.settlement_status == "failed"

    await db.mpesa_transactions.update_one(
        {"_id": inserted.inserted_id},
        {"$set": {"settlement_retry_after": datetime.now(timezone.utc) - timedelta(seconds=1)}},
    )
    recovered = await service.get_hotspot_purchase_status("checkout-resilience-test")

    assert recovered.settled is True
    assert recovered.settlement_status == "completed"
    assert recovered.voucher_code == "TST1234567"
    assert len(voucher_creation_attempts) == 2
    client.close()


@pytest.mark.asyncio
async def test_daraja_status_http_errors_are_diagnosed_without_logging_response_secrets(caplog):
    secret_marker = "DO_NOT_LOG_ACCESS_TOKEN"

    class FakeResponse:
        status_code = 401

        def json(self):
            return {"ResponseCode": "1001", "errorCode": secret_marker, "errorMessage": secret_marker}

    class FakeHttpError(Exception):
        response = FakeResponse()

    service = MpesaService.__new__(MpesaService)
    service.daraja = SimpleNamespace(query_stk_status=Mock(side_effect=FakeHttpError()))
    caplog.set_level(logging.WARNING, logger="app.services.mpesa_service")

    result = await service._query_provider_status("checkout-private-value")

    assert result is None
    assert "http_error" in caplog.text
    assert "401" in caplog.text
    assert "1001" in caplog.text
    assert secret_marker not in caplog.text
    assert "checkout-private-value" not in caplog.text
