import asyncio
from bson import ObjectId
import pytest

from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ServiceUnavailableError,
    ValidationError,
)
from app.routes import hotspot


class FakeCursor(list):
    async def to_list(self, length=None):
        return self[:length] if length is not None else list(self)


class FakeRouters:
    def __init__(self, routers):
        self._routers = routers

    def find(self, *_args, **_kwargs):
        return FakeCursor(self._routers)


class FakeDatabase:
    def __init__(self, routers):
        self.routers = FakeRouters(routers)


def router(name, site_id):
    return {"_id": ObjectId(), "name": name, "site_id": site_id}


@pytest.mark.asyncio
async def test_device_ip_and_mac_must_match_same_router_lease(monkeypatch):
    naivasha = router("Nakuru", "nakuru-site")
    nyahururu = router("Nyahururu", "nyahururu-site")
    leases = {
        str(naivasha["_id"]): [{
            "address": "192.168.10.24", "mac_address": "11:22:33:44:55:66",
            "status": "bound", "expires_seconds": 300,
        }],
        str(nyahururu["_id"]): [{
            "address": "192.168.10.24", "mac_address": "aa-bb-cc-dd-ee-ff",
            "status": "bound", "expires_seconds": 300,
        }],
    }

    async def get_leases(_service, router_id):
        return leases[router_id]

    monkeypatch.setattr(hotspot.RouterService, "get_dhcp_leases", get_leases)
    result = await hotspot._resolve_hotspot_device(
        hotspot.HotspotDeviceLookupRequest(
            ip_address="192.168.10.24", mac_address="AA:BB:CC:DD:EE:FF"
        ),
        FakeDatabase([naivasha, nyahururu]),
    )

    assert result["verification_status"] == "verified"
    assert result["verification_method"] == "router_dhcp_lease"
    assert result["router_id"] == str(nyahururu["_id"])
    assert result["site_id"] == "nyahururu-site"
    assert result["mac_address"] == "AA:BB:CC:DD:EE:FF"


@pytest.mark.asyncio
async def test_mac_only_lookup_finds_and_normalizes_router_lease(monkeypatch):
    mikrotik = router("Nakuru AP", "nakuru")

    async def get_leases(_service, _router_id):
        return [{
            "address": "10.20.0.8", "mac_address": "aa-bb-cc-dd-ee-ff",
            "status": "bound", "expires_seconds": 120,
        }]

    monkeypatch.setattr(hotspot.RouterService, "get_dhcp_leases", get_leases)
    result = await hotspot._resolve_hotspot_device(
        hotspot.HotspotDeviceLookupRequest(mac_address="AA:BB:CC:DD:EE:FF"),
        FakeDatabase([mikrotik]),
    )

    assert result["ip_address"] == "10.20.0.8"
    assert result["mac_address"] == "AA:BB:CC:DD:EE:FF"
    assert result["router_name"] == "Nakuru AP"


@pytest.mark.asyncio
async def test_unrelated_site_lease_does_not_match_when_both_values_supplied(monkeypatch):
    nakuru = router("Nakuru", "nakuru")
    nyahururu = router("Nyahururu", "nyahururu")

    async def get_leases(_service, router_id):
        if router_id == str(nakuru["_id"]):
            return [{"address": "192.168.1.5", "mac_address": "00:11:22:33:44:55", "status": "bound"}]
        return []

    monkeypatch.setattr(hotspot.RouterService, "get_dhcp_leases", get_leases)
    with pytest.raises(NotFoundError):
        await hotspot._resolve_hotspot_device(
            hotspot.HotspotDeviceLookupRequest(
                ip_address="192.168.1.5", mac_address="AA:BB:CC:DD:EE:FF"
            ),
            FakeDatabase([nakuru, nyahururu]),
        )


@pytest.mark.asyncio
async def test_ambiguous_same_device_lease_is_rejected(monkeypatch):
    routers = [router("Nakuru", "nakuru"), router("Nyahururu", "nyahururu")]

    async def get_leases(_service, _router_id):
        return [{"address": "192.168.1.5", "mac_address": "AA:BB:CC:DD:EE:FF", "status": "bound"}]

    monkeypatch.setattr(hotspot.RouterService, "get_dhcp_leases", get_leases)
    with pytest.raises(ConflictError, match="multiple routers"):
        await hotspot._resolve_hotspot_device(
            hotspot.HotspotDeviceLookupRequest(
                ip_address="192.168.1.5", mac_address="AA:BB:CC:DD:EE:FF"
            ),
            FakeDatabase(routers),
        )


@pytest.mark.asyncio
async def test_unavailable_router_makes_multi_site_lookup_unverifiable(monkeypatch):
    online, unavailable = router("Online", "site-a"), router("Unavailable", "site-b")

    async def get_leases(_service, router_id):
        if router_id == str(unavailable["_id"]):
            raise RuntimeError("router unavailable")
        return [{"address": "10.0.0.5", "mac_address": "AA:BB:CC:DD:EE:FF", "status": "bound"}]

    monkeypatch.setattr(hotspot.RouterService, "get_dhcp_leases", get_leases)
    with pytest.raises(ServiceUnavailableError, match="one or more configured routers"):
        await hotspot._resolve_hotspot_device(
            hotspot.HotspotDeviceLookupRequest(
                ip_address="10.0.0.5", mac_address="AA:BB:CC:DD:EE:FF"
            ),
            FakeDatabase([online, unavailable]),
        )


@pytest.mark.asyncio
async def test_expired_lease_is_not_verified(monkeypatch):
    mikrotik = router("Nakuru", "nakuru")

    async def get_leases(_service, _router_id):
        return [{
            "address": "10.0.0.5", "mac_address": "AA:BB:CC:DD:EE:FF",
            "status": "bound", "expires_seconds": 0,
        }]

    monkeypatch.setattr(hotspot.RouterService, "get_dhcp_leases", get_leases)
    with pytest.raises(ConflictError, match="no longer active"):
        await hotspot._resolve_hotspot_device(
            hotspot.HotspotDeviceLookupRequest(
                ip_address="10.0.0.5", mac_address="AA:BB:CC:DD:EE:FF"
            ),
            FakeDatabase([mikrotik]),
        )


@pytest.mark.asyncio
async def test_missing_device_information_is_rejected():
    with pytest.raises(ValidationError, match="IP address or MAC"):
        await hotspot._resolve_hotspot_device(
            hotspot.HotspotDeviceLookupRequest(), FakeDatabase([])
        )


@pytest.mark.asyncio
async def test_no_configured_routers_returns_unavailable():
    with pytest.raises(ServiceUnavailableError, match="No MikroTik routers"):
        await hotspot._resolve_hotspot_device(
            hotspot.HotspotDeviceLookupRequest(mac_address="AA:BB:CC:DD:EE:FF"),
            FakeDatabase([]),
        )


@pytest.mark.asyncio
async def test_router_scans_run_concurrently_with_a_bounded_limit(monkeypatch):
    routers = [router(f"Router {index}", f"site-{index}") for index in range(7)]
    active = 0
    peak = 0

    async def get_leases(_service, _router_id):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1
        return []

    monkeypatch.setattr(hotspot.RouterService, "get_dhcp_leases", get_leases)
    with pytest.raises(NotFoundError):
        await hotspot._resolve_hotspot_device(
            hotspot.HotspotDeviceLookupRequest(mac_address="AA:BB:CC:DD:EE:FF"),
            FakeDatabase(routers),
        )

    assert 1 < peak <= 4
