import pytest
from unittest.mock import Mock
from bson import ObjectId
from mongomock_motor import AsyncMongoMockClient

from app.services.voucher_service import VoucherService
from app.services.mpesa_service import MpesaService


@pytest.mark.asyncio
async def test_multiple_hotspot_purchases_work_with_sparse_checkout_index():
    client = AsyncMongoMockClient(tz_aware=True)
    db = client["hotspot_checkout_index_test"]
    await db.mpesa_transactions.create_index(
        [("checkout_request_id", 1)],
        unique=True,
        sparse=True,
    )
    plan_id = ObjectId()
    await db.hotspot_plans.insert_one({
        "_id": plan_id,
        "name": "Daily",
        "duration_hours": 24,
        "price": 100,
        "is_active": True,
    })
    service = MpesaService(db)
    service.daraja.initiate_stk_push = Mock(side_effect=[
        {"MerchantRequestID": "merchant-1", "CheckoutRequestID": "checkout-1"},
        {"MerchantRequestID": "merchant-2", "CheckoutRequestID": "checkout-2"},
    ])

    first = await service.initiate_hotspot_purchase(
        str(plan_id), "254700000000", "this_device", "AA:BB:CC:DD:EE:FF"
    )
    second = await service.initiate_hotspot_purchase(
        str(plan_id), "254700000001", "this_device", "AA:BB:CC:DD:EE:01"
    )

    assert first.checkout_request_id == "checkout-1"
    assert second.checkout_request_id == "checkout-2"
    assert await db.mpesa_transactions.count_documents({}) == 2
    client.close()


@pytest.mark.asyncio
async def test_hotspot_purchase_retry_returns_one_device_bound_voucher():
    client = AsyncMongoMockClient(tz_aware=True)
    db = client["hotspot_purchase_voucher_test"]
    plan_id = ObjectId()
    await db.hotspot_plans.insert_one({
        "_id": plan_id,
        "name": "Daily",
        "duration_hours": 24,
        "data_allowance_mb": 2048,
        "rate_limit": "2M/5M",
        "max_devices": 1,
        "price": 100,
        "currency": "KES",
    })
    service = VoucherService(db)

    first = await service.create_hotspot_purchase_voucher(
        "transaction-123",
        str(plan_id),
        "AA:BB:CC:DD:EE:FF",
        "this_device",
    )
    retried = await service.create_hotspot_purchase_voucher(
        "transaction-123",
        str(plan_id),
        "AA:BB:CC:DD:EE:FF",
        "this_device",
    )

    assert first["voucher_code"] == retried["voucher_code"]
    assert first["batch_id"] == retried["batch_id"]
    assert retried["bound_mac"] == "AA:BB:CC:DD:EE:FF"
    assert await db.vouchers.count_documents({
        "purchase_transaction_id": "transaction-123",
    }) == 1
    client.close()
