from datetime import datetime, timedelta, timezone
import hashlib

import pytest
from bson import ObjectId
from mongomock_motor import AsyncMongoMockClient

from app.core.crypto import decrypt_value, encrypt_value
from app.core.exceptions import ValidationError
from app.schemas.pppoe import PppoeSubscriberCreate
from app.schemas.radius_auth import RadiusAccountingRequest, RadiusAuthRequest
from app.services.pppoe_service import PppoeService
from app.services.radius_auth_service import RadiusAuthService


@pytest.fixture
def db():
    client = AsyncMongoMockClient(tz_aware=True)
    yield client["pppoe_lifecycle_test"]
    client.close()


async def seed_network(db, *, expires=None, subscription_status="active", plan_status="active"):
    now = datetime.now(timezone.utc)
    site_id, router_id, nas_id, plan_id, sub_id, customer_id = (ObjectId() for _ in range(6))
    await db.customers.insert_one({"_id": customer_id, "full_name": "Test subscriber", "status": "active"})
    await db.sites.insert_one({"_id": site_id, "name": "Test site", "status": "active"})
    await db.nas_clients.insert_one({
        "_id": nas_id, "name": "Test NAS", "ip_address": "10.20.0.1",
        "nas_identifier": "TEST-EDGE", "site_id": str(site_id), "status": "active",
    })
    await db.routers.insert_one({
        "_id": router_id, "name": "Test router", "ip_address": "192.0.2.1",
        "nas_client_id": str(nas_id), "site_id": str(site_id), "status": "online",
    })
    await db.service_plans.insert_one({
        "_id": plan_id, "name": "Home 10", "plan_code": "HOME10",
        "service_type": "ftth", "status": plan_status, "download_speed_mbps": 10,
        "upload_speed_mbps": 5, "base_price_kes": 1500, "billing_cycle": "monthly",
        "available_site_ids": [str(site_id)],
    })
    await db.subscriptions.insert_one({
        "_id": sub_id, "customer_id": str(customer_id), "plan_id": str(plan_id),
        "service_id": str(plan_id), "service_type": "pppoe", "status": subscription_status,
        "site_id": str(site_id), "router_id": str(router_id), "nas_client_id": str(nas_id),
        "end_date": expires or now + timedelta(days=30), "data_used_bytes": 0,
    })
    return site_id, router_id, nas_id, plan_id, sub_id


def request(payload=None, **overrides):
    body = {
        "User-Name": "home-001", "User-Password": "A-secure-test-password",
        "NAS-IP-Address": "10.20.0.1", "NAS-Identifier": "TEST-EDGE",
        "Service-Type": "Framed-User", "Framed-Protocol": "PPP",
    }
    body.update(payload or {})
    body.update(overrides)
    return RadiusAuthRequest.model_validate(body)


async def seed_radius_user(db, site_id, router_id, nas_id, sub_id, **overrides):
    from app.core.crypto import encrypt_value

    doc = {
        "username": "home-001", "password": encrypt_value("A-secure-test-password"),
        "password_encrypted": True, "user_type": "pppoe", "status": "active",
        "customer_id": str((await db.subscriptions.find_one({"_id": sub_id}))["customer_id"]), "subscription_id": str(sub_id),
        "site_id": str(site_id), "router_id": str(router_id),
        "nas_client_id": str(nas_id), "rate_limit": "5M/10M",
        "framed_ip_pool": "pppoe-pool",
    }
    doc.update(overrides)
    await db.radius_users.insert_one(doc)


@pytest.mark.asyncio
async def test_pppoe_auth_accepts_encrypted_password_only_on_assigned_nas(db):
    site, router, nas, plan, sub = await seed_network(db)
    await seed_radius_user(db, site, router, nas, sub)

    response = await RadiusAuthService(db).authenticate(request())

    assert response.control_Auth_Type == "Accept"
    assert response.reply_Service_Type == "Framed-User"
    assert response.reply_Framed_Protocol == "PPP"
    assert response.reply_Mikrotik_Rate_Limit == "5M/10M"
    assert response.reply_Acct_Interim_Interval == 300
    assert response.reply_Session_Timeout and response.reply_Session_Timeout > 0


@pytest.mark.asyncio
async def test_pppoe_rejects_incorrect_nas_site_or_router(db):
    site, router, nas, plan, sub = await seed_network(db)
    await seed_radius_user(db, site, router, nas, sub)
    response = await RadiusAuthService(db).authenticate(request(None, **{
        "NAS-IP-Address": "10.20.0.99", "NAS-Identifier": "UNKNOWN",
    }))
    assert response.control_Auth_Type == "Reject"


@pytest.mark.asyncio
async def test_pppoe_accounting_start_is_idempotent_and_site_bound(db):
    site, router, nas, plan, sub = await seed_network(db)
    await seed_radius_user(db, site, router, nas, sub)
    service = RadiusAuthService(db)
    packet = RadiusAccountingRequest.model_validate({
        "Acct-Status-Type": "Start", "Acct-Session-Id": "ppp-session-1",
        "User-Name": "home-001", "NAS-IP-Address": "10.20.0.1",
        "NAS-Identifier": "TEST-EDGE", "Service-Type": "Framed-User",
        "Framed-Protocol": "PPP", "Framed-IP-Address": "198.51.100.10",
    })
    await service.accounting(packet)
    await service.accounting(packet)
    assert await db.radius_accounting.count_documents({"acct_session_id": "ppp-session-1"}) == 1
    assert await db.radius_sessions.count_documents({"acct_session_id": "ppp-session-1"}) == 1
    record = await db.radius_accounting.find_one({"acct_session_id": "ppp-session-1"})
    assert record["site_id"] == str(site)
    assert record["router_id"] == str(router)


@pytest.mark.asyncio
async def test_pppoe_accounting_rejects_conflicting_nas_identity(db):
    site, router, nas, plan, sub = await seed_network(db)
    await seed_radius_user(db, site, router, nas, sub)
    packet = RadiusAccountingRequest.model_validate({
        "Acct-Status-Type": "Start", "Acct-Session-Id": "ppp-session-invalid",
        "User-Name": "home-001", "NAS-IP-Address": "10.20.0.99",
        "NAS-Identifier": "TEST-EDGE", "Service-Type": "Framed-User",
        "Framed-Protocol": "PPP",
    })
    from app.core.exceptions import ValidationError
    with pytest.raises(ValidationError):
        await RadiusAuthService(db).accounting(packet)


@pytest.mark.asyncio
async def test_accounting_session_ids_are_scoped_to_nas_for_multi_router_sites(db):
    service = RadiusAuthService(db)
    for nas_ip, nas_id in (("10.20.0.1", "TEST-EDGE"), ("10.30.0.1", "OTHER-EDGE")):
        packet = RadiusAccountingRequest.model_validate({
            "Acct-Status-Type": "Start", "Acct-Session-Id": "router-local-session-1",
            "NAS-IP-Address": nas_ip, "NAS-Identifier": nas_id,
            "User-Name": "not-a-pppoe-test-account",
        })
        await service._accounting_start(packet)

    assert await db.radius_accounting.count_documents({"acct_session_id": "router-local-session-1"}) == 2
    assert await db.radius_sessions.count_documents({"acct_session_id": "router-local-session-1"}) == 2


@pytest.mark.asyncio
async def test_pppoe_rejects_subscription_expiry_and_inactive_plan(db):
    site, router, nas, plan, sub = await seed_network(db, expires=datetime.now(timezone.utc)-timedelta(seconds=1))
    await seed_radius_user(db, site, router, nas, sub)
    response = await RadiusAuthService(db).authenticate(request())
    assert response.control_Auth_Type == "Reject"
    assert response.reply_Reply_Message == "Subscription expired"


@pytest.mark.asyncio
async def test_pppoe_rejects_inactive_package(db):
    site, router, nas, plan, sub = await seed_network(db, plan_status="inactive")
    await seed_radius_user(db, site, router, nas, sub)
    response = await RadiusAuthService(db).authenticate(request())
    assert response.control_Auth_Type == "Reject"
    assert response.reply_Reply_Message == "Service package inactive"


@pytest.mark.asyncio
async def test_pppoe_rejects_hotspot_voucher_namespace(db):
    await db.vouchers.insert_one({"voucher_code": "home-001", "status": "active"})
    response = await RadiusAuthService(db).authenticate(request())
    assert response.control_Auth_Type == "Reject"


@pytest.mark.asyncio
async def test_pppoe_chap_response_is_verified_against_server_credential(db):
    site, router, nas, plan, sub = await seed_network(db)
    await seed_radius_user(db, site, router, nas, sub)
    chap_id = b"\x07"
    challenge = bytes(range(16))
    digest = hashlib.md5(chap_id + b"A-secure-test-password" + challenge).digest()
    response_value = (chap_id + digest).hex()
    chap_req = request({
        "User-Password": None,
        "CHAP-Password": response_value,
        "CHAP-Challenge": challenge.hex(),
    })
    response = await RadiusAuthService(db).authenticate(chap_req)
    assert response.control_Auth_Type == "Accept"
    invalid = request({
        "User-Password": None,
        "CHAP-Password": (chap_id + bytes(16)).hex(),
        "CHAP-Challenge": challenge.hex(),
    })
    assert (await RadiusAuthService(db).authenticate(invalid)).control_Auth_Type == "Reject"


@pytest.mark.asyncio
async def test_encrypted_max_length_password_fits_radius_model_and_authenticates(db):
    site, router, nas, plan, sub = await seed_network(db)
    password = "P" * 128
    await seed_radius_user(db, site, router, nas, sub, password=encrypt_value(password))
    await db.radius_users.update_one({"username": "home-001"}, {"$set": {"password_encrypted": True}})
    response = await RadiusAuthService(db).authenticate(request({"User-Password": password}))
    assert response.control_Auth_Type == "Accept"


@pytest.mark.asyncio
async def test_pppoe_provisioning_is_pending_and_encrypts_radius_credential(db):
    site = ObjectId(); router = ObjectId(); nas = ObjectId(); plan = ObjectId(); customer = ObjectId()
    await db.sites.insert_one({"_id": site, "status": "active", "name": "Test"})
    await db.customers.insert_one({"_id": customer, "full_name": "Test Subscriber", "status": "active"})
    await db.nas_clients.insert_one({"_id": nas, "site_id": str(site), "status": "active", "ip_address": "10.20.0.2"})
    await db.routers.insert_one({"_id": router, "site_id": str(site), "nas_client_id": str(nas), "status": "offline"})
    await db.service_plans.insert_one({
        "_id": plan, "name": "Home", "plan_code": "HOME", "status": "active",
        "service_type": "ftth", "download_speed_mbps": 10, "upload_speed_mbps": 5,
        "base_price_kes": 1500, "billing_cycle": "monthly", "available_site_ids": [str(site)],
    })
    payload = PppoeSubscriberCreate(
        customer_id=str(customer), plan_id=str(plan), site_id=str(site),
        router_id=str(router), nas_client_id=str(nas), username="home-001",
        password="A-secure-test-password", ip_address=None,
    )

    subscriber = await PppoeService(db).create_subscriber(payload)

    user = await db.radius_users.find_one({"username": "home-001"})
    stored_sub = await db.subscriptions.find_one({"pppoe_username": "home-001"})
    assert subscriber["status"] == "pending"
    assert stored_sub["pppoe_password"] is None
    assert user["password_encrypted"] is True
    assert user["password"] != "A-secure-test-password"
    assert decrypt_value(user["password"]) == "A-secure-test-password"
    assert user["status"] == "pending"
    assert user["site_id"] == str(site)
    assert user["router_id"] == str(router)
    # A retry after a process interruption returns the same subscription.
    retried = await PppoeService(db).create_subscriber(payload)
    assert retried["_id"] == subscriber["_id"]
    assert await db.radius_users.count_documents({"username": "home-001"}) == 1

    # Recover a process interruption after the subscription insert but before
    # its RADIUS row was persisted; a single account is restored.
    await db.radius_users.delete_one({"username": "home-001"})
    recovered = await PppoeService(db).create_subscriber(payload)
    assert recovered["_id"] == subscriber["_id"]
    assert await db.radius_users.count_documents({"username": "home-001"}) == 1


@pytest.mark.asyncio
async def test_pppoe_provisioning_retry_with_different_package_is_conflict(db):
    site = ObjectId(); router = ObjectId(); nas = ObjectId(); plan = ObjectId(); other_plan = ObjectId(); customer = ObjectId()
    await db.sites.insert_one({"_id": site, "status": "active"})
    await db.customers.insert_one({"_id": customer, "status": "active"})
    await db.nas_clients.insert_one({"_id": nas, "site_id": str(site), "status": "active", "ip_address": "10.20.0.2"})
    await db.routers.insert_one({"_id": router, "site_id": str(site), "nas_client_id": str(nas), "status": "online"})
    for plan_id, name in ((plan, "Home"), (other_plan, "Faster")):
        await db.service_plans.insert_one({"_id": plan_id, "name": name, "status": "active", "service_type": "ftth",
            "download_speed_mbps": 10, "upload_speed_mbps": 5, "base_price_kes": 1500})
    base = dict(customer_id=str(customer), site_id=str(site), router_id=str(router), nas_client_id=str(nas), username="unique-ppp", password="A-secure-test-password")
    service = PppoeService(db)
    await service.create_subscriber(PppoeSubscriberCreate(plan_id=str(plan), **base))
    from app.core.exceptions import ConflictError
    with pytest.raises(ConflictError):
        await service.create_subscriber(PppoeSubscriberCreate(plan_id=str(other_plan), **base))


@pytest.mark.asyncio
async def test_pppoe_provisioning_rejects_mismatched_site_router_nas(db):
    site, router, nas, plan, sub = await seed_network(db)
    customer = ObjectId()
    await db.customers.insert_one({"_id": customer, "status": "active"})
    other_site = ObjectId()
    await db.sites.insert_one({"_id": other_site, "status": "active"})
    payload = PppoeSubscriberCreate(
        customer_id=str(customer), plan_id=str(plan), site_id=str(other_site),
        router_id=str(router), nas_client_id=str(nas), username="wrong-site",
        password="A-secure-test-password",
    )
    with pytest.raises(ValidationError):
        await PppoeService(db).create_subscriber(payload)

