from datetime import datetime, timedelta, timezone

from bson import ObjectId
from mongomock_motor import AsyncMongoMockClient
import pytest

from app.schemas.radius_auth import RadiusAuthRequest
from app.services.radius_auth_service import RadiusAuthService


@pytest.fixture
def radius_db():
    client = AsyncMongoMockClient(tz_aware=True)
    yield client["radius_site_auth_test"]
    client.close()


async def seed_site_nas(db, *, site_name, nas_ip, nas_identifier):
    site_id = ObjectId()
    nas_id = ObjectId()
    router_id = ObjectId()
    await db.sites.insert_one({"_id": site_id, "name": site_name, "status": "active"})
    await db.nas_clients.insert_one({
        "_id": nas_id,
        "name": f"{site_name} NAS",
        "ip_address": nas_ip,
        "nas_identifier": nas_identifier,
        "site_id": str(site_id),
        "status": "active",
    })
    await db.routers.insert_one({
        "_id": router_id,
        "name": f"{site_name} Router",
        "ip_address": f"172.20.0.{1 if site_name == 'Nyaururu' else 2}",
        "nas_client_id": str(nas_id),
        "site_id": str(site_id),
        "status": "online",
    })
    return site_id, router_id


async def seed_voucher(db, *, site_id=None, status="active", authorized_macs=None, max_devices=2):
    voucher_id = ObjectId()
    await db.vouchers.insert_one({
        "_id": voucher_id,
        "voucher_code": "SITE-CODE-01",
        "status": status,
        "site_id": str(site_id) if site_id else None,
        "expiry_date": datetime.now(timezone.utc) + timedelta(hours=2),
        "duration_hours": 2,
        "max_devices": max_devices,
        "available_device_slots": max_devices,
        "authorized_macs": authorized_macs or [],
    })
    return voucher_id


def auth_request(nas_ip=None, nas_identifier=None, calling_station="AA:BB:CC:DD:EE:FF"):
    payload = {
        "User-Name": "SITE-CODE-01",
        "Calling-Station-Id": calling_station,
    }
    if nas_ip is not None:
        payload["NAS-IP-Address"] = nas_ip
    if nas_identifier is not None:
        payload["NAS-Identifier"] = nas_identifier
    return RadiusAuthRequest.model_validate(payload)


@pytest.mark.asyncio
async def test_site_restricted_voucher_accepts_only_its_mapped_site(radius_db):
    nyahururu_id, router_id = await seed_site_nas(
        radius_db, site_name="Nyaururu", nas_ip="10.0.0.11", nas_identifier="NYA-EDGE-1"
    )
    await seed_site_nas(
        radius_db, site_name="Nakuru", nas_ip="10.0.0.12", nas_identifier="NAK-EDGE-1"
    )
    await seed_voucher(radius_db, site_id=nyahururu_id)

    allowed = await RadiusAuthService(radius_db).authenticate(
        auth_request("10.0.0.11", "NYA-EDGE-1")
    )
    assert allowed.control_Auth_Type == "Accept"
    saved = await radius_db.vouchers.find_one({"voucher_code": "SITE-CODE-01"})
    assert saved["last_router_id"] == str(router_id)
    assert saved["last_site_id"] == str(nyahururu_id)


@pytest.mark.asyncio
async def test_site_restricted_voucher_rejects_another_site_without_claiming_mac(radius_db):
    nyahururu_id, _ = await seed_site_nas(
        radius_db, site_name="Nyaururu", nas_ip="10.0.0.11", nas_identifier="NYA-EDGE-1"
    )
    await seed_site_nas(
        radius_db, site_name="Nakuru", nas_ip="10.0.0.12", nas_identifier="NAK-EDGE-1"
    )
    await seed_voucher(radius_db, site_id=nyahururu_id)

    reply = await RadiusAuthService(radius_db).authenticate(
        auth_request("10.0.0.12", "NAK-EDGE-1")
    )

    assert reply.control_Auth_Type == "Reject"
    assert reply.reply_Reply_Message == "Voucher is not valid at this site"
    voucher = await radius_db.vouchers.find_one({"voucher_code": "SITE-CODE-01"})
    assert voucher["status"] == "active"
    assert voucher["authorized_macs"] == []


@pytest.mark.asyncio
async def test_unknown_or_disagreeing_nas_cannot_bypass_voucher_site_restriction(radius_db):
    nyahururu_id, _ = await seed_site_nas(
        radius_db, site_name="Nyaururu", nas_ip="10.0.0.11", nas_identifier="NYA-EDGE-1"
    )
    await seed_site_nas(
        radius_db, site_name="Nakuru", nas_ip="10.0.0.12", nas_identifier="NAK-EDGE-1"
    )
    await seed_voucher(radius_db, site_id=nyahururu_id)
    service = RadiusAuthService(radius_db)

    unknown = await service.authenticate(auth_request("10.0.0.99", "UNKNOWN"))
    conflict = await service.authenticate(auth_request("10.0.0.11", "NAK-EDGE-1"))

    assert unknown.control_Auth_Type == "Reject"
    assert unknown.reply_Reply_Message == "Unable to verify the access site"
    assert conflict.control_Auth_Type == "Reject"
    assert conflict.reply_Reply_Message == "Unable to verify the access site"
    voucher = await radius_db.vouchers.find_one({"voucher_code": "SITE-CODE-01"})
    assert voucher["status"] == "active"
    assert voucher["authorized_macs"] == []


@pytest.mark.asyncio
async def test_global_legacy_voucher_remains_usable_without_nas_mapping(radius_db):
    await seed_voucher(radius_db, site_id=None)

    reply = await RadiusAuthService(radius_db).authenticate(auth_request())

    assert reply.control_Auth_Type == "Accept"
    voucher = await radius_db.vouchers.find_one({"voucher_code": "SITE-CODE-01"})
    assert voucher["site_id"] is None
    assert "last_router_id" not in voucher


@pytest.mark.asyncio
async def test_revoked_and_expired_vouchers_remain_rejected(radius_db):
    await seed_voucher(radius_db, status="disabled")
    reply = await RadiusAuthService(radius_db).authenticate(auth_request())
    assert reply.control_Auth_Type == "Reject"

    await radius_db.vouchers.update_one(
        {"voucher_code": "SITE-CODE-01"},
        {"$set": {"status": "active", "expiry_date": datetime.now(timezone.utc) - timedelta(seconds=1)}},
    )
    expired = await RadiusAuthService(radius_db).authenticate(auth_request())
    assert expired.control_Auth_Type == "Reject"
