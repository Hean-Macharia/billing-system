from bson import ObjectId
from mongomock_motor import AsyncMongoMockClient
import pytest

from app.schemas.radius_auth import RadiusAccountingRequest
from app.services.radius_auth_service import RadiusAuthService


@pytest.fixture
def radius_db():
    client = AsyncMongoMockClient(tz_aware=True)
    yield client["radius_site_accounting_test"]
    client.close()


@pytest.mark.asyncio
async def test_start_interim_stop_retain_resolved_router_site_and_nas(radius_db):
    site_id = ObjectId()
    nas_id = ObjectId()
    router_id = ObjectId()
    await radius_db.sites.insert_one({"_id": site_id, "name": "Nakuru", "status": "active"})
    await radius_db.nas_clients.insert_one({
        "_id": nas_id,
        "name": "Nakuru NAS",
        "ip_address": "10.0.0.12",
        "nas_identifier": "NAK-EDGE-1",
        "site_id": str(site_id),
        "status": "active",
    })
    await radius_db.routers.insert_one({
        "_id": router_id,
        "name": "Nakuru Router",
        "ip_address": "172.20.0.12",
        "nas_client_id": str(nas_id),
        "site_id": str(site_id),
        "status": "online",
    })
    service = RadiusAuthService(radius_db)
    start = RadiusAccountingRequest.model_validate({
        "Acct-Status-Type": "Start",
        "Acct-Session-Id": "nakuru-session-1",
        "User-Name": "voucher-1",
        "NAS-IP-Address": "10.0.0.12",
        "NAS-Identifier": "NAK-EDGE-1",
        "Calling-Station-Id": "AA:BB:CC:DD:EE:FF",
    })

    await service.accounting(start)
    interim = RadiusAccountingRequest.model_validate({
        "Acct-Status-Type": "Interim-Update",
        "Acct-Session-Id": "nakuru-session-1",
        "User-Name": "voucher-1",
        # Missing NAS attrs on later events must not erase the Start mapping.
        "Acct-Session-Time": 120,
        "Acct-Input-Octets": 4096,
    })
    await service.accounting(interim)
    stop = RadiusAccountingRequest.model_validate({
        "Acct-Status-Type": "Stop",
        "Acct-Session-Id": "nakuru-session-1",
        "User-Name": "voucher-1",
        "Acct-Session-Time": 180,
        "Acct-Input-Octets": 8192,
        "Acct-Terminate-Cause": "User-Request",
    })
    await service.accounting(stop)

    accounting = await radius_db.radius_accounting.find_one({"acct_session_id": "nakuru-session-1"})
    session = await radius_db.radius_sessions.find_one({"acct_session_id": "nakuru-session-1"})
    assert accounting["nas_ip_address"] == "10.0.0.12"
    assert accounting["nas_identifier"] == "NAK-EDGE-1"
    assert accounting["router_id"] == str(router_id)
    assert accounting["site_id"] == str(site_id)
    assert session["nas_ip_address"] == "10.0.0.12"
    assert session["nas_identifier"] == "NAK-EDGE-1"
    assert session["router_id"] == str(router_id)
    assert session["site_id"] == str(site_id)
    assert session["status"] == "offline"
    assert session["acct_session_time"] == 180


@pytest.mark.asyncio
async def test_duplicate_start_does_not_replace_original_router_site(radius_db):
    first_site_id, second_site_id = ObjectId(), ObjectId()
    first_nas_id, second_nas_id = ObjectId(), ObjectId()
    first_router_id, second_router_id = ObjectId(), ObjectId()
    for site_id, label in ((first_site_id, "Nyaururu"), (second_site_id, "Nakuru")):
        await radius_db.sites.insert_one({"_id": site_id, "name": label, "status": "active"})
    await radius_db.nas_clients.insert_many([
        {"_id": first_nas_id, "ip_address": "10.0.0.11", "nas_identifier": "NYA-EDGE-1", "site_id": str(first_site_id), "status": "active"},
        {"_id": second_nas_id, "ip_address": "10.0.0.12", "nas_identifier": "NAK-EDGE-1", "site_id": str(second_site_id), "status": "active"},
    ])
    await radius_db.routers.insert_many([
        {"_id": first_router_id, "ip_address": "172.20.0.11", "nas_client_id": str(first_nas_id), "site_id": str(first_site_id), "status": "online"},
        {"_id": second_router_id, "ip_address": "172.20.0.12", "nas_client_id": str(second_nas_id), "site_id": str(second_site_id), "status": "online"},
    ])
    service = RadiusAuthService(radius_db)

    await service.accounting(RadiusAccountingRequest.model_validate({
        "Acct-Status-Type": "Start", "Acct-Session-Id": "duplicate-start-1",
        "User-Name": "voucher-1", "NAS-IP-Address": "10.0.0.11", "NAS-Identifier": "NYA-EDGE-1",
    }))
    await service.accounting(RadiusAccountingRequest.model_validate({
        "Acct-Status-Type": "Start", "Acct-Session-Id": "duplicate-start-1",
        "User-Name": "voucher-1", "NAS-IP-Address": "10.0.0.12", "NAS-Identifier": "NAK-EDGE-1",
    }))

    accounting = await radius_db.radius_accounting.find_one({"acct_session_id": "duplicate-start-1"})
    session = await radius_db.radius_sessions.find_one({"acct_session_id": "duplicate-start-1"})
    assert accounting["router_id"] == str(first_router_id)
    assert accounting["site_id"] == str(first_site_id)
    assert session["router_id"] == str(first_router_id)
    assert session["site_id"] == str(first_site_id)
