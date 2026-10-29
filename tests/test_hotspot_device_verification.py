import pytest
from bson import ObjectId
from mongomock_motor import AsyncMongoMockClient

from app.core.exceptions import NotFoundError
from app.routes import hotspot


@pytest.mark.asyncio
async def test_device_verification_normalizes_mac_from_router_lease(monkeypatch):
    client = AsyncMongoMockClient(tz_aware=True)
    db = client["hotspot_device_verification_test"]
    await db.routers.insert_one({"_id": ObjectId()})

    async def get_leases(_service, _router_id):
        return [{
            "address": "192.168.10.24",
            "mac_address": "aa-bb-cc-dd-ee-ff",
            "hostname": "customer-device",
        }]

    monkeypatch.setattr(hotspot.RouterService, "get_dhcp_leases", get_leases)
    device = await hotspot._resolve_hotspot_device(
        hotspot.HotspotDeviceLookupRequest(mac_address="AA:BB:CC:DD:EE:FF"),
        db,
    )

    assert device["mac_address"] == "AA:BB:CC:DD:EE:FF"
    assert device["ip_address"] == "192.168.10.24"
    client.close()


@pytest.mark.asyncio
async def test_device_verification_rejects_unleased_mac(monkeypatch):
    client = AsyncMongoMockClient(tz_aware=True)
    db = client["hotspot_unleased_device_test"]
    await db.routers.insert_one({"_id": ObjectId()})

    async def get_leases(_service, _router_id):
        return []

    monkeypatch.setattr(hotspot.RouterService, "get_dhcp_leases", get_leases)
    with pytest.raises(NotFoundError):
        await hotspot._resolve_hotspot_device(
            hotspot.HotspotDeviceLookupRequest(mac_address="AA:BB:CC:DD:EE:FF"),
            db,
        )
    client.close()
