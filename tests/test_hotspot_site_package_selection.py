from datetime import datetime, timedelta, timezone

from bson import ObjectId
from fastapi import Response
import hashlib
from mongomock_motor import AsyncMongoMockClient
import pytest

from app.core.exceptions import ConflictError, ValidationError
from app.routes.hotspot import list_public_hotspot_plans, purchase_hotspot_voucher
from app.schemas.portal import HotspotPurchaseRequest
from app.services.hotspot_service import HotspotService
from app.services.mpesa_service import MpesaService
from app.services.voucher_service import VoucherService


@pytest.fixture
def portal_db():
    client = AsyncMongoMockClient(tz_aware=True)
    yield client["hotspot_site_package_test"]
    client.close()


async def add_plan(db, name, site_id=None):
    plan_id = ObjectId()
    await db.hotspot_plans.insert_one({
        "_id": plan_id,
        "name": name,
        "site_id": str(site_id) if site_id else None,
        "duration_hours": 1,
        "data_allowance_mb": 500,
        "max_devices": 1,
        "price": 20,
        "currency": "KES",
        "is_active": True,
        "sort_order": 1,
    })
    return plan_id


@pytest.mark.asyncio
async def test_public_package_listing_ignores_browser_site_and_returns_global_only(portal_db):
    nakuru_id = ObjectId()
    nyahururu_id = ObjectId()
    global_id = await add_plan(portal_db, "Global 1 Hour")
    await add_plan(portal_db, "Nakuru 1 Hour", nakuru_id)
    await add_plan(portal_db, "Nyaururu 1 Hour", nyahururu_id)

    response = await list_public_hotspot_plans(
        request=None,
        response=Response(),
        site_id=str(nakuru_id),
        db=portal_db,
    )

    assert [plan["_id"] for plan in response["data"]] == [str(global_id)]


@pytest.mark.asyncio
async def test_trusted_site_catalog_query_includes_site_and_intentionally_global_plans(portal_db):
    nakuru_id = ObjectId()
    global_id = await add_plan(portal_db, "Global 1 Hour")
    nakuru_plan_id = await add_plan(portal_db, "Nakuru 1 Hour", nakuru_id)
    await add_plan(portal_db, "Nyaururu 1 Hour", ObjectId())

    plans = await HotspotService(portal_db).list_plans(
        site_id=str(nakuru_id), active_only=True, include_global=True
    )

    assert {plan.id for plan in plans} == {str(global_id), str(nakuru_plan_id)}


@pytest.mark.asyncio
async def test_public_catalog_uses_context_site_and_ignores_browser_site_override(portal_db):
    nakuru_id = ObjectId()
    nyahururu_id = ObjectId()
    global_id = await add_plan(portal_db, "Global 1 Hour")
    nakuru_plan_id = await add_plan(portal_db, "Nakuru 1 Hour", nakuru_id)
    await add_plan(portal_db, "Nyaururu 1 Hour", nyahururu_id)
    router_id = ObjectId()
    await portal_db.sites.insert_one({"_id": nakuru_id, "name": "Nakuru", "status": "active"})
    await portal_db.routers.insert_one({
        "_id": router_id, "name": "Nakuru Edge", "site_id": str(nakuru_id), "status": "online",
    })
    token = "local-test-context-token-which-is-long-enough"
    await portal_db.hotspot_trusted_contexts.insert_one({
        "token_hash": hashlib.sha256(token.encode()).hexdigest(),
        "router_id": str(router_id), "site_id": str(nakuru_id),
        "client_ip": "192.168.89.20", "client_mac": "AA:BB:CC:DD:EE:FF",
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=2),
    })

    response = await list_public_hotspot_plans(
        request=None,
        response=Response(),
        site_id=str(nyahururu_id),
        hotspot_context=token,
        db=portal_db,
    )

    assert {plan["_id"] for plan in response["data"]} == {str(global_id), str(nakuru_plan_id)}


@pytest.mark.asyncio
async def test_public_purchase_rejects_site_plan_without_trusted_context(portal_db):
    plan_id = await add_plan(portal_db, "Nakuru Only", ObjectId())
    service = MpesaService(portal_db)
    stk_called = False

    def unexpected_stk(**_kwargs):
        nonlocal stk_called
        stk_called = True
        return {"MerchantRequestID": "mock", "CheckoutRequestID": "mock"}

    service.daraja.initiate_stk_push = unexpected_stk
    with pytest.raises(ValidationError, match="trusted router context"):
        await service.initiate_hotspot_purchase(
            str(plan_id), "254700000000", "this_device", "AA:BB:CC:DD:EE:FF"
        )

    assert not stk_called
    assert await portal_db.mpesa_transactions.count_documents({}) == 0


@pytest.mark.asyncio
async def test_wrong_site_plan_is_rejected_before_any_stk_call(portal_db):
    plan_site = ObjectId()
    other_site = ObjectId()
    plan_id = await add_plan(portal_db, "Nakuru Only", plan_site)
    service = MpesaService(portal_db)
    stk_called = False

    def unexpected_stk(**_kwargs):
        nonlocal stk_called
        stk_called = True
        raise AssertionError("The mocked payment provider must not be called")

    service.daraja.initiate_stk_push = unexpected_stk
    with pytest.raises(ValidationError, match="not available at the verified router site"):
        await service.initiate_hotspot_purchase(
            str(plan_id), "254700000000", "this_device", "AA:BB:CC:DD:EE:FF",
            trusted_site_id=str(other_site), trusted_router_id=str(ObjectId()),
        )

    assert stk_called is False
    assert await portal_db.mpesa_transactions.count_documents({}) == 0


def test_browser_cannot_set_router_or_site_fields_on_purchase_schema():
    request = HotspotPurchaseRequest.model_validate({
        "plan_id": str(ObjectId()), "phone_number": "254700000000",
        "device_type": "this_device", "device_mac": "AA:BB:CC:DD:EE:FF",
        "site_id": str(ObjectId()), "router_id": str(ObjectId()),
    })
    assert not hasattr(request, "site_id")
    assert not hasattr(request, "router_id")


@pytest.mark.asyncio
async def test_site_purchase_without_context_is_rejected_before_device_or_payment_calls(portal_db, monkeypatch):
    site_id = ObjectId()
    plan_id = await add_plan(portal_db, "Nakuru Only", site_id)

    async def unexpected_lookup(*_args, **_kwargs):
        raise AssertionError("Device lookup must not substitute for trusted router context")

    monkeypatch.setattr("app.routes.hotspot._resolve_hotspot_device", unexpected_lookup)
    request = HotspotPurchaseRequest(
        plan_id=str(plan_id), phone_number="254700000000", device_type="this_device",
        device_mac="AA:BB:CC:DD:EE:FF",
    )
    with pytest.raises(ConflictError, match="trusted router context"):
        await purchase_hotspot_voucher(request, Response(), None, portal_db)


@pytest.mark.asyncio
async def test_global_purchase_snapshots_global_site_and_does_not_change_payment_flow(portal_db):
    plan_id = await add_plan(portal_db, "Global 1 Hour")
    service = MpesaService(portal_db)
    service.daraja.initiate_stk_push = lambda **_kwargs: {
        "MerchantRequestID": "merchant-mock",
        "CheckoutRequestID": "checkout-mock",
    }

    transaction = await service.initiate_hotspot_purchase(
        str(plan_id), "254700000000", "this_device", "AA:BB:CC:DD:EE:FF"
    )

    stored = await portal_db.mpesa_transactions.find_one({"_id": ObjectId(transaction.id)})
    assert transaction.site_id is None
    assert stored["site_id"] is None
    assert transaction.status.value == "processing"


@pytest.mark.asyncio
async def test_trusted_purchase_snapshots_verified_router_and_site(portal_db):
    site_id = ObjectId()
    router_id = ObjectId()
    plan_id = await add_plan(portal_db, "Nakuru 1 Hour", site_id)
    service = MpesaService(portal_db)
    service.daraja.initiate_stk_push = lambda **_kwargs: {
        "MerchantRequestID": "mock-trusted-site",
        "CheckoutRequestID": "mock-trusted-checkout",
    }

    transaction = await service.initiate_hotspot_purchase(
        str(plan_id), "254700000000", "this_device", "AA:BB:CC:DD:EE:FF",
        trusted_site_id=str(site_id), trusted_router_id=str(router_id),
    )

    stored = await portal_db.mpesa_transactions.find_one({"_id": ObjectId(transaction.id)})
    assert stored["site_id"] == str(site_id)
    assert stored["router_id"] == str(router_id)


@pytest.mark.asyncio
async def test_plan_site_is_copied_to_purchase_voucher_and_batch(portal_db):
    site_id = ObjectId()
    await portal_db.sites.insert_one({"_id": site_id, "name": "Nakuru", "status": "active"})
    plan_id = await add_plan(portal_db, "Nakuru 1 Hour", site_id)

    voucher = await VoucherService(portal_db).create_hotspot_purchase_voucher(
        purchase_transaction_id="txn-nakuru-1",
        plan_id=str(plan_id),
        device_mac="AA:BB:CC:DD:EE:FF",
        device_type="this_device",
    )
    batch = await portal_db.voucher_batches.find_one({"purchase_transaction_id": "txn-nakuru-1"})

    assert voucher["site_id"] == str(site_id)
    assert batch["site_id"] == str(site_id)


@pytest.mark.asyncio
async def test_purchase_site_snapshot_is_preserved_if_plan_changes_before_settlement(portal_db):
    later_site_id = ObjectId()
    await portal_db.sites.insert_one({"_id": later_site_id, "name": "Nakuru", "status": "active"})
    plan_id = await add_plan(portal_db, "Plan changed after purchase", later_site_id)

    voucher = await VoucherService(portal_db).create_hotspot_purchase_voucher(
        purchase_transaction_id="txn-global-snapshot",
        plan_id=str(plan_id),
        device_mac="AA:BB:CC:DD:EE:FF",
        device_type="this_device",
        site_id=None,
    )

    assert voucher["site_id"] is None


@pytest.mark.asyncio
async def test_purchase_router_snapshot_is_preserved_on_voucher_and_batch(portal_db):
    site_id = ObjectId()
    router_id = ObjectId()
    await portal_db.sites.insert_one({"_id": site_id, "name": "Nakuru", "status": "active"})
    await portal_db.routers.insert_one({"_id": router_id, "name": "Nakuru Edge", "site_id": str(site_id)})
    plan_id = await add_plan(portal_db, "Nakuru 1 Hour", site_id)
    voucher = await VoucherService(portal_db).create_hotspot_purchase_voucher(
        purchase_transaction_id="txn-router-snapshot",
        plan_id=str(plan_id),
        device_mac="AA:BB:CC:DD:EE:FF",
        device_type="this_device",
        site_id=str(site_id),
        router_id=str(router_id),
    )
    batch = await portal_db.voucher_batches.find_one({"purchase_transaction_id": "txn-router-snapshot"})

    assert voucher["site_id"] == str(site_id)
    assert voucher["router_id"] == str(router_id)
    assert batch["router_id"] == str(router_id)
