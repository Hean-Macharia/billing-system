import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from app.core.dependencies import get_db
from app.main import app
from app.routes import mpesa
from app.services.mpesa_service import MpesaService


@pytest.mark.asyncio
async def test_concurrent_duplicate_callbacks_settle_only_once():
    client = AsyncMongoMockClient(tz_aware=True)
    db = client["mpesa_callback_test"]
    result = await db.mpesa_transactions.insert_one({
        "transaction_type": "hotspot_purchase",
        "checkout_request_id": "checkout-request-test",
        "hotspot_plan_id": "plan-id",
        "amount": 100,
        "phone_number": "254700000000",
        "account_reference": "plan",
        "transaction_desc": "HotSpot plan",
        "status": "processing",
        "callback_received": False,
        "settled": False,
    })
    service = MpesaService(db)
    service._settle_hotspot_purchase = AsyncMock()
    service.daraja.query_stk_status = Mock(return_value={
        "CheckoutRequestID": "checkout-request-test",
        "ResultCode": 0,
        "ResultDesc": "Success",
    })
    body = {
        "Body": {
            "stkCallback": {
                "CheckoutRequestID": "checkout-request-test",
                "ResultCode": 0,
                "ResultDesc": "Success",
            }
        }
    }

    await asyncio.gather(
        service.process_callback(body),
        service.process_callback(body),
    )

    service._settle_hotspot_purchase.assert_awaited_once()
    transaction = await db.mpesa_transactions.find_one({"_id": result.inserted_id})
    assert transaction["callback_received"] is True
    assert transaction["status"] == "success"
    client.close()


@pytest.mark.asyncio
async def test_callback_success_hint_does_not_settle_without_provider_success():
    client = AsyncMongoMockClient(tz_aware=True)
    db = client["mpesa_callback_verification_test"]
    result = await db.mpesa_transactions.insert_one({
        "transaction_type": "hotspot_purchase",
        "checkout_request_id": "checkout-request-test",
        "hotspot_plan_id": "plan-id",
        "amount": 100,
        "phone_number": "254700000000",
        "account_reference": "plan",
        "transaction_desc": "HotSpot plan",
        "status": "processing",
        "callback_received": False,
        "settled": False,
    })
    service = MpesaService(db)
    service._settle_hotspot_purchase = AsyncMock()
    service.daraja.query_stk_status = Mock(return_value={
        "CheckoutRequestID": "checkout-request-test",
        "ResultCode": 1032,
        "ResultDesc": "Cancelled",
    })

    transaction = await service.process_callback({
        "Body": {
            "stkCallback": {
                "CheckoutRequestID": "checkout-request-test",
                "ResultCode": 0,
                "CallbackMetadata": {"Item": [{"Name": "Amount", "Value": 100}]},
            }
        }
    })

    service._settle_hotspot_purchase.assert_not_awaited()
    assert transaction.status.value == "cancelled"
    stored = await db.mpesa_transactions.find_one({"_id": result.inserted_id})
    assert stored["amount"] == 100
    assert stored["callback_received"] is True
    client.close()


@pytest.mark.asyncio
async def test_callback_waits_when_provider_verification_is_unavailable():
    client = AsyncMongoMockClient(tz_aware=True)
    db = client["mpesa_callback_pending_test"]
    result = await db.mpesa_transactions.insert_one({
        "transaction_type": "hotspot_purchase",
        "checkout_request_id": "checkout-request-test",
        "hotspot_plan_id": "plan-id",
        "amount": 100,
        "phone_number": "254700000000",
        "account_reference": "plan",
        "transaction_desc": "HotSpot plan",
        "status": "processing",
        "callback_received": False,
        "settled": False,
    })
    service = MpesaService(db)
    service._settle_hotspot_purchase = AsyncMock()
    service.daraja.query_stk_status = Mock(return_value={
        "CheckoutRequestID": "another-checkout",
        "ResultCode": 0,
        "ResultDesc": "Success",
    })

    transaction = await service.process_callback({
        "Body": {
            "stkCallback": {
                "CheckoutRequestID": "checkout-request-test",
                "ResultCode": 0,
            }
        }
    })

    service._settle_hotspot_purchase.assert_not_awaited()
    assert transaction.status.value == "processing"
    stored = await db.mpesa_transactions.find_one({"_id": result.inserted_id})
    assert stored["callback_received"] is False
    assert stored["callback_verification_pending"] is True
    client.close()


@pytest.mark.asyncio
async def test_successful_provider_query_uses_initiated_amount_not_callback_amount():
    client = AsyncMongoMockClient(tz_aware=True)
    db = client["mpesa_callback_amount_test"]
    result = await db.mpesa_transactions.insert_one({
        "transaction_type": "hotspot_purchase",
        "checkout_request_id": "checkout-request-test",
        "hotspot_plan_id": "plan-id",
        "amount": 100,
        "phone_number": "254700000000",
        "account_reference": "plan",
        "transaction_desc": "HotSpot plan",
        "status": "processing",
        "callback_received": False,
        "settled": False,
    })
    service = MpesaService(db)
    service._settle_hotspot_purchase = AsyncMock()
    service.daraja.query_stk_status = Mock(return_value={
        "CheckoutRequestID": "checkout-request-test",
        "ResultCode": 0,
        "ResultDesc": "Success",
    })

    transaction = await service.process_callback({
        "Body": {
            "stkCallback": {
                "CheckoutRequestID": "checkout-request-test",
                "ResultCode": 0,
                "CallbackMetadata": {
                    "Item": [{"Name": "Amount", "Value": 100}, {"Name": "PhoneNumber", "Value": "255711111111"}],
                },
            }
        }
    })

    service._settle_hotspot_purchase.assert_awaited_once()
    assert service._settle_hotspot_purchase.await_args.args[2] == 100
    assert service._settle_hotspot_purchase.await_args.args[4] == "254700000000"
    assert transaction.status.value == "success"
    assert transaction.settlement_review_required is False
    stored = await db.mpesa_transactions.find_one({"_id": result.inserted_id})
    assert stored["amount"] == 100
    assert stored["phone_number"] == "254700000000"
    client.close()


@pytest.mark.asyncio
async def test_callback_amount_mismatch_requires_manual_review():
    client = AsyncMongoMockClient(tz_aware=True)
    db = client["mpesa_callback_amount_mismatch_test"]
    result = await db.mpesa_transactions.insert_one({
        "transaction_type": "hotspot_purchase",
        "checkout_request_id": "checkout-request-test",
        "hotspot_plan_id": "plan-id",
        "amount": 100,
        "phone_number": "254700000000",
        "account_reference": "plan",
        "transaction_desc": "HotSpot plan",
        "status": "processing",
        "callback_received": False,
        "settled": False,
    })
    service = MpesaService(db)
    service._settle_hotspot_purchase = AsyncMock()
    service.daraja.query_stk_status = Mock(return_value={
        "CheckoutRequestID": "checkout-request-test",
        "ResultCode": 0,
        "ResultDesc": "Success",
    })

    transaction = await service.process_callback({
        "Body": {
            "stkCallback": {
                "CheckoutRequestID": "checkout-request-test",
                "ResultCode": 0,
                "CallbackMetadata": {
                    "Item": [{"Name": "Amount", "Value": 99}],
                },
            }
        }
    })

    service._settle_hotspot_purchase.assert_not_awaited()
    assert transaction.status.value == "processing"
    assert transaction.settlement_review_required is True
    stored = await db.mpesa_transactions.find_one({"_id": result.inserted_id})
    assert stored["callback_received"] is False
    assert stored["settlement_review_required"] is True
    assert stored["callback_verification_pending"] is False
    assert await service.reconcile_pending(max_age_hours=0) == []
    client.close()


@pytest.mark.asyncio
async def test_recent_callback_verification_pending_is_reconciled():
    client = AsyncMongoMockClient(tz_aware=True)
    db = client["mpesa_callback_reconcile_test"]
    result = await db.mpesa_transactions.insert_one({
        "transaction_type": "hotspot_purchase",
        "checkout_request_id": "checkout-request-test",
        "hotspot_plan_id": "plan-id",
        "amount": 100,
        "phone_number": "254700000000",
        "account_reference": "plan",
        "transaction_desc": "HotSpot plan",
        "status": "processing",
        "callback_received": False,
        "callback_verification_pending": True,
        "settled": False,
    })
    service = MpesaService(db)
    service._settle_hotspot_purchase = AsyncMock()
    service.daraja.query_stk_status = Mock(return_value={
        "CheckoutRequestID": "checkout-request-test",
        "ResultCode": 0,
        "ResultDesc": "Success",
    })

    reconciled = await service.reconcile_pending(max_age_hours=24)

    assert len(reconciled) == 1
    service._settle_hotspot_purchase.assert_awaited_once()
    stored = await db.mpesa_transactions.find_one({"_id": result.inserted_id})
    assert stored["callback_received"] is True
    assert stored["callback_verification_pending"] is False
    client.close()


@pytest.mark.asyncio
async def test_failed_verified_settlement_is_retried_idempotently():
    client = AsyncMongoMockClient(tz_aware=True)
    db = client["mpesa_settlement_retry_test"]
    result = await db.mpesa_transactions.insert_one({
        "transaction_type": "hotspot_purchase",
        "checkout_request_id": "checkout-request-test",
        "hotspot_plan_id": "plan-id",
        "amount": 100,
        "phone_number": "254700000000",
        "device_mac": "AA:BB:CC:DD:EE:FF",
        "device_type": "this_device",
        "account_reference": "plan",
        "transaction_desc": "HotSpot plan",
        "status": "processing",
        "callback_received": False,
        "settled": False,
    })
    service = MpesaService(db)
    service._settle_hotspot_purchase = AsyncMock(
        side_effect=[RuntimeError("temporary storage error"), None]
    )
    service.daraja.query_stk_status = Mock(return_value={
        "CheckoutRequestID": "checkout-request-test",
        "ResultCode": 0,
        "ResultDesc": "Success",
    })
    body = {
        "Body": {
            "stkCallback": {
                "CheckoutRequestID": "checkout-request-test",
                "ResultCode": 0,
            }
        }
    }

    failed = await service.process_callback(body)
    retried = await service.process_callback(body)

    assert failed.settled is False
    assert failed.settlement_status == "failed"
    assert retried.settled is True
    assert retried.settlement_status == "completed"
    assert service._settle_hotspot_purchase.await_count == 2
    stored = await db.mpesa_transactions.find_one({"_id": result.inserted_id})
    assert stored["callback_received"] is True
    assert stored["settled"] is True
    client.close()


def test_public_callback_does_not_log_or_return_submitted_personal_data(caplog, monkeypatch):
    sensitive_values = (
        "callback-phone-marker",
        "callback-receipt-marker",
        "callback-request-marker",
    )

    async def unused_database_dependency():
        return None

    class FakeMpesaService:
        def __init__(self, _db):
            pass

        async def process_callback(self, body):
            assert sensitive_values[0] in str(body)
            return SimpleNamespace(status=SimpleNamespace(value="success"))

    monkeypatch.setitem(app.dependency_overrides, get_db, unused_database_dependency)
    monkeypatch.setattr(mpesa, "MpesaService", FakeMpesaService)
    caplog.set_level(logging.INFO, logger="app.routes.mpesa")

    response = TestClient(app).post(
        "/api/v1/mpesa/callback",
        json={
            "Body": {
                "stkCallback": {
                    "CheckoutRequestID": sensitive_values[2],
                    "CallbackMetadata": {
                        "Item": [
                            {"Name": "PhoneNumber", "Value": sensitive_values[0]},
                            {"Name": "MpesaReceiptNumber", "Value": sensitive_values[1]},
                        ]
                    },
                }
            }
        },
    )

    assert response.status_code == 200
    assert response.json()["data"] == {"status": "success"}
    assert all(value not in response.text for value in sensitive_values)
    assert all(value not in caplog.text for value in sensitive_values)
