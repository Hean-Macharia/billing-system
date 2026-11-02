import asyncio
import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from app.core.dependencies import get_db
from app.core.exceptions import NotFoundError
from app.main import app
from app.routes import mpesa
from app.services.mpesa_service import MpesaService


def test_callback_enqueue_is_durable_and_duplicate_safe():
    class FakeCollection:
        def __init__(self):
            self.doc = {
                "_id": "mock-transaction-id",
                "checkout_request_id": "checkout-enqueue-test",
                "callback_received": False,
                "callback_verification_pending": False,
            }

        async def find_one(self, query):
            return dict(self.doc) if query.get("checkout_request_id") == self.doc["checkout_request_id"] else None

        async def update_one(self, query, update):
            if (
                query.get("_id") == self.doc["_id"]
                and self.doc["callback_received"] is not True
                and self.doc["callback_verification_pending"] is not True
            ):
                self.doc.update(update["$set"])
                return SimpleNamespace(modified_count=1)
            return SimpleNamespace(modified_count=0)

    async def run_case():
        service = MpesaService.__new__(MpesaService)
        service.collection = FakeCollection()
        body = {"Body": {"stkCallback": {"CheckoutRequestID": "checkout-enqueue-test"}}}
        first = await service.enqueue_callback(body)
        duplicate = await service.enqueue_callback(body)
        assert first == "checkout-enqueue-test"
        assert duplicate is None
        assert service.collection.doc["callback_verification_pending"] is True
        assert service.collection.doc["callback_enqueued_at"] is not None

    asyncio.run(run_case())


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
                "CallbackMetadata": {"Item": [{"Name": "MpesaReceiptNumber", "Value": "TST1234567"}]},
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
                    "Item": [
                        {"Name": "Amount", "Value": 100},
                        {"Name": "PhoneNumber", "Value": "255711111111"},
                        {"Name": "MpesaReceiptNumber", "Value": "TST2345678"},
                    ],
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
    service._settle_hotspot_purchase.assert_not_awaited()
    stored = await db.mpesa_transactions.find_one({"_id": result.inserted_id})
    assert stored["callback_received"] is True
    assert stored["callback_verification_pending"] is False
    assert stored["settlement_review_required"] is True
    client.close()


@pytest.mark.asyncio
async def test_hotspot_success_without_verified_receipt_is_held_for_review():
    client = AsyncMongoMockClient(tz_aware=True)
    db = client["mpesa_missing_receipt_review_test"]
    inserted = await db.mpesa_transactions.insert_one({
        "transaction_type": "hotspot_purchase",
        "checkout_request_id": "checkout-no-receipt",
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
        "CheckoutRequestID": "checkout-no-receipt",
        "ResultCode": 0,
        "ResultDesc": "Success",
    })

    result = await service.process_callback({"Body": {"stkCallback": {
        "CheckoutRequestID": "checkout-no-receipt",
        "CallbackMetadata": {"Item": [{"Name": "Amount", "Value": 100}]},
    }}})

    service._settle_hotspot_purchase.assert_not_awaited()
    assert result.status.value == "success"
    assert result.settlement_review_required is True
    assert result.settled is False
    stored = await db.mpesa_transactions.find_one({"_id": inserted.inserted_id})
    assert stored.get("mpesa_receipt_number") is None
    client.close()


@pytest.mark.asyncio
async def test_duplicate_receipt_cannot_issue_a_second_hotspot_voucher():
    client = AsyncMongoMockClient(tz_aware=True)
    db = client["mpesa_duplicate_receipt_test"]
    inserted = await db.mpesa_transactions.insert_one({
        "transaction_type": "hotspot_purchase",
        "checkout_request_id": "checkout-duplicate-receipt",
        "hotspot_plan_id": "plan-id",
        "amount": 100,
        "phone_number": "254700000000",
        "account_reference": "plan",
        "transaction_desc": "HotSpot plan",
        "status": "processing",
        "callback_received": False,
        "settled": False,
    })
    await db.mpesa_transactions.insert_one({
        "transaction_type": "hotspot_purchase",
        "checkout_request_id": "another-checkout",
        "mpesa_receipt_number": "DUP1234567",
    })
    service = MpesaService(db)
    service._settle_hotspot_purchase = AsyncMock()
    service.daraja.query_stk_status = Mock(return_value={
        "CheckoutRequestID": "checkout-duplicate-receipt",
        "ResultCode": 0,
        "ResultDesc": "Success",
    })

    result = await service.process_callback({"Body": {"stkCallback": {
        "CheckoutRequestID": "checkout-duplicate-receipt",
        "CallbackMetadata": {"Item": [
            {"Name": "Amount", "Value": 100},
            {"Name": "MpesaReceiptNumber", "Value": "dup1234567"},
        ]},
    }}})

    service._settle_hotspot_purchase.assert_not_awaited()
    assert result.settlement_review_required is True
    assert result.settled is False
    stored = await db.mpesa_transactions.find_one({"_id": inserted.inserted_id})
    assert stored["callback_received"] is True
    client.close()


@pytest.mark.asyncio
async def test_confirmed_callback_uses_verified_receipt_as_active_radius_username(monkeypatch):
    client = AsyncMongoMockClient(tz_aware=True)
    db = client["mpesa_receipt_voucher_settlement_test"]
    plan_id = ObjectId()
    await db.hotspot_plans.insert_one({
        "_id": plan_id, "name": "Receipt bundle", "duration_hours": 1,
        "data_allowance_mb": None, "rate_limit": "1M/1M", "max_devices": 1,
        "price": 5, "currency": "KES", "is_active": True,
    })
    inserted = await db.mpesa_transactions.insert_one({
        "transaction_type": "hotspot_purchase",
        "checkout_request_id": "checkout-receipt-settlement",
        "hotspot_plan_id": str(plan_id),
        "site_id": "site-1", "router_id": "router-1",
        "device_mac": "AA:BB:CC:DD:EE:FF", "device_type": "this_device",
        "amount": 5, "phone_number": "254700000000",
        "account_reference": "Receipt bundle", "transaction_desc": "HotSpot plan",
        "status": "processing", "callback_received": False, "settled": False,
    })

    class NoopNotification:
        def __init__(self, _db):
            pass

        async def notify(self, **_kwargs):
            return None

    monkeypatch.setattr("app.services.notification_service.NotificationService", NoopNotification)
    service = MpesaService(db)
    service.daraja.query_stk_status = Mock(return_value={
        "CheckoutRequestID": "checkout-receipt-settlement",
        "ResultCode": 0,
        "ResultDesc": "Success",
    })

    result = await service.process_callback({"Body": {"stkCallback": {
        "CheckoutRequestID": "checkout-receipt-settlement",
        "CallbackMetadata": {"Item": [
            {"Name": "Amount", "Value": 5},
            {"Name": "MpesaReceiptNumber", "Value": "uk1g00o1rx"},
        ]},
    }}})

    assert result.status.value == "success"
    assert result.settled is True
    assert result.settlement_status == "completed"
    assert result.mpesa_receipt_number == "UK1G00O1RX"
    assert result.voucher_code == "UK1G00O1RX"
    voucher = await db.vouchers.find_one({
        "voucher_code": "UK1G00O1RX",
        "purchase_transaction_id": str(inserted.inserted_id),
    })
    assert voucher["status"] == "active"
    assert voucher["site_id"] == "site-1"
    assert voucher["router_id"] == "router-1"
    assert voucher["authorized_macs"] == ["AA:BB:CC:DD:EE:FF"]
    client.close()


@pytest.mark.asyncio
async def test_hotspot_purchase_idempotency_key_reuses_same_checkout_without_second_stk():
    client = AsyncMongoMockClient(tz_aware=True)
    db = client["hotspot_purchase_idempotency_test"]
    plan_id = ObjectId()
    await db.hotspot_plans.insert_one({
        "_id": plan_id, "name": "Hourly", "duration_hours": 1,
        "price": 5, "is_active": True,
    })
    service = MpesaService(db)
    service.daraja.initiate_stk_push = Mock(return_value={
        "MerchantRequestID": "merchant-idem", "CheckoutRequestID": "checkout-idem",
    })
    args = dict(
        plan_id=str(plan_id), phone_number="254700000000", device_type="this_device",
        device_mac="AA:BB:CC:DD:EE:FF", trusted_site_id="site-a",
        trusted_router_id="router-a", idempotency_key="stable-checkout-key-1234",
    )

    first = await service.initiate_hotspot_purchase(**args)
    second = await service.initiate_hotspot_purchase(**args)

    assert first.checkout_request_id == second.checkout_request_id == "checkout-idem"
    service.daraja.initiate_stk_push.assert_called_once()
    assert await db.mpesa_transactions.count_documents({"transaction_type": "hotspot_purchase"}) == 1
    client.close()


@pytest.mark.asyncio
async def test_receipt_resolves_only_a_fully_settled_active_voucher():
    client = AsyncMongoMockClient(tz_aware=True)
    db = client["hotspot_receipt_resolve_test"]
    tx_id = ObjectId()
    await db.mpesa_transactions.insert_one({
        "_id": tx_id,
        "transaction_type": "hotspot_purchase",
        "checkout_request_id": "checkout-receipt",
        "hotspot_plan_id": "plan-id",
        "amount": 10,
        "phone_number": "254700000000",
        "account_reference": "Bundle",
        "transaction_desc": "HotSpot plan",
        "status": "success",
        "callback_received": True,
        "settled": True,
        "settlement_status": "completed",
        "mpesa_receipt_number": "UK1G00O1RX",
        "voucher_code": "UK1G00O1RX",
        "site_id": "site-a",
        "router_id": "router-a",
    })
    await db.vouchers.insert_one({
        "voucher_code": "UK1G00O1RX",
        "purchase_transaction_id": str(tx_id),
        "status": "active",
        "expiry_date": datetime.now(timezone.utc) + timedelta(hours=1),
        "site_id": "site-a",
        "router_id": "router-a",
        "authorized_macs": ["AA:BB:CC:DD:EE:FF"],
        "available_device_slots": 0,
    })

    transaction, voucher = await MpesaService(db).resolve_hotspot_receipt("uk1g00o1rx", "254700000000")
    assert transaction.mpesa_receipt_number == "UK1G00O1RX"
    assert voucher["voucher_code"] == "UK1G00O1RX"
    with pytest.raises(NotFoundError, match="those details"):
        await MpesaService(db).resolve_hotspot_receipt("UK1G00O1RX", "254711111111")
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
                "CallbackMetadata": {"Item": [{"Name": "MpesaReceiptNumber", "Value": "TST3456789"}]},
            }
        }
    }

    failed = await service.process_callback(body)
    await db.mpesa_transactions.update_one(
        {"_id": result.inserted_id},
        {"$set": {"settlement_retry_after": datetime.now(timezone.utc) - timedelta(seconds=1)}},
    )
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

        async def enqueue_callback(self, body):
            assert sensitive_values[0] in str(body)
            return sensitive_values[2]

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
    assert response.json()["data"] == {"status": "accepted"}
    assert all(value not in response.text for value in sensitive_values)
    assert all(value not in caplog.text for value in sensitive_values)
