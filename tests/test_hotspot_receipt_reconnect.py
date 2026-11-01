from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import Response

from app.core.exceptions import ConflictError
from app.routes import hotspot
from app.schemas.portal import HotspotReconnectRequest


@pytest.mark.asyncio
async def test_receipt_reconnect_re_attests_context_and_returns_only_login_username(monkeypatch):
    context = SimpleNamespace(
        router_id="router-1", site_id="site-1", client_ip="192.168.89.10",
        client_mac="AA:BB:CC:DD:EE:FF",
    )
    attestation = SimpleNamespace(
        get_context=AsyncMock(return_value=context),
        attest_purchase_device=AsyncMock(return_value=context),
    )
    transaction = SimpleNamespace(
        router_id="router-1", site_id="site-1", mpesa_receipt_number="UK1G00O1RX",
        voucher_code="INTERNAL-CODE", account_reference="Daily bundle",
    )
    voucher = {
        "router_id": "router-1", "site_id": "site-1",
        "authorized_macs": ["AA:BB:CC:DD:EE:FF"], "available_device_slots": 0,
        "expiry_date": datetime(2030, 1, 1, tzinfo=timezone.utc),
    }

    class FakeAttestation:
        def __init__(self, _db):
            pass

        async def get_context(self, token):
            return await attestation.get_context(token)

        async def attest_purchase_device(self, **kwargs):
            return await attestation.attest_purchase_device(**kwargs)

    class FakeMpesa:
        def __init__(self, _db):
            pass

        async def resolve_hotspot_receipt(self, receipt, phone_number=None):
            assert receipt == "uk1g00o1rx"
            assert phone_number == "254700000000"
            return transaction, voucher

    monkeypatch.setattr(hotspot, "HotspotAttestationService", FakeAttestation)
    monkeypatch.setattr("app.services.mpesa_service.MpesaService", FakeMpesa)

    result = await hotspot.reconnect_hotspot_purchase(
        HotspotReconnectRequest(receipt="uk1g00o1rx", phone_number="254700000000"),
        Response(),
        "opaque-context-token",
        object(),
    )

    assert result["data"]["verified"] is True
    assert result["data"]["access_token"] == "UK1G00O1RX"
    assert result["data"]["login_username"] == "INTERNAL-CODE"
    assert "password" not in result["data"]
    attestation.attest_purchase_device.assert_awaited_once_with(
        raw_token="opaque-context-token",
        device_type="this_device",
        client_ip="192.168.89.10",
        client_mac="AA:BB:CC:DD:EE:FF",
    )


@pytest.mark.asyncio
async def test_receipt_reconnect_rejects_context_for_another_site(monkeypatch):
    context = SimpleNamespace(router_id="router-2", site_id="site-2", client_ip="192.168.89.10", client_mac="AA:BB:CC:DD:EE:FF")

    class FakeAttestation:
        def __init__(self, _db):
            pass

        async def get_context(self, _token):
            return context

    class FakeMpesa:
        def __init__(self, _db):
            pass

        async def resolve_hotspot_receipt(self, *_args, **_kwargs):
            return SimpleNamespace(router_id="router-1", site_id="site-1"), {"router_id": "router-1", "site_id": "site-1"}

    monkeypatch.setattr(hotspot, "HotspotAttestationService", FakeAttestation)
    monkeypatch.setattr("app.services.mpesa_service.MpesaService", FakeMpesa)

    with pytest.raises(ConflictError, match="different verified Wi-Fi site"):
        await hotspot.reconnect_hotspot_purchase(
            HotspotReconnectRequest(receipt="UK1G00O1RX"), Response(), "opaque-context-token", object()
        )


@pytest.mark.asyncio
async def test_receipt_reconnect_requires_live_trusted_context(monkeypatch):
    class FakeAttestation:
        def __init__(self, _db):
            pass

        async def get_context(self, _token):
            return None

    monkeypatch.setattr(hotspot, "HotspotAttestationService", FakeAttestation)
    with pytest.raises(ConflictError, match="missing or expired"):
        await hotspot.reconnect_hotspot_purchase(
            HotspotReconnectRequest(receipt="UK1G00O1RX"), Response(), "expired-context", object()
        )


@pytest.mark.asyncio
async def test_purchase_status_does_not_disclose_access_before_settlement(monkeypatch):
    transaction = SimpleNamespace(
        status=SimpleNamespace(value="success"), settled=False,
        settlement_status="processing", callback_received=True,
        settlement_review_required=False, voucher_code="UK1G00O1RX",
        mpesa_receipt_number="UK1G00O1RX", account_reference="bundle", amount=5,
        result_desc="confirmed", id="transaction-id", router_id="router-1",
        site_id="site-1", device_mac="AA:BB:CC:DD:EE:FF",
    )

    class FakeMpesa:
        def __init__(self, _db):
            pass

        async def get_by_checkout_id(self, _checkout):
            return transaction

    monkeypatch.setattr("app.services.mpesa_service.MpesaService", FakeMpesa)
    monkeypatch.setattr(hotspot, "HotspotAttestationService", lambda _db: SimpleNamespace(
        get_context=AsyncMock(return_value=SimpleNamespace(
            router_id="router-1", site_id="site-1", client_mac="AA:BB:CC:DD:EE:FF"
        ))
    ))
    response = Response()
    result = await hotspot.purchase_status("checkout-id", response, "opaque-context", object())
    assert result["data"]["status"] == "success"
    assert result["data"]["settled"] is False
    assert result["data"]["access_token"] is None
    assert result["data"]["login_username"] is None
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.asyncio
async def test_purchase_status_releases_receipt_only_after_completed_settlement(monkeypatch):
    transaction = SimpleNamespace(
        status=SimpleNamespace(value="success"), settled=True,
        settlement_status="completed", callback_received=True,
        settlement_review_required=False, voucher_code="UK1G00O1RX",
        mpesa_receipt_number="UK1G00O1RX", account_reference="bundle", amount=5,
        result_desc="confirmed", id="transaction-id", router_id="router-1",
        site_id="site-1", device_mac="AA:BB:CC:DD:EE:FF",
    )

    class FakeMpesa:
        def __init__(self, _db):
            pass

        async def get_by_checkout_id(self, _checkout):
            return transaction

    class FakeVouchers:
        async def find_one(self, _query, _projection):
            return {"expiry_date": datetime(2030, 1, 1, tzinfo=timezone.utc)}

    class FakeDb:
        vouchers = FakeVouchers()

    monkeypatch.setattr("app.services.mpesa_service.MpesaService", FakeMpesa)
    monkeypatch.setattr(hotspot, "HotspotAttestationService", lambda _db: SimpleNamespace(
        get_context=AsyncMock(return_value=SimpleNamespace(
            router_id="router-1", site_id="site-1", client_mac="AA:BB:CC:DD:EE:FF"
        ))
    ))
    result = await hotspot.purchase_status("checkout-id", Response(), "opaque-context", FakeDb())
    assert result["data"]["settled"] is True
    assert result["data"]["access_token"] == "UK1G00O1RX"
    assert result["data"]["login_username"] == "UK1G00O1RX"
    assert result["data"]["expires_at"] == "2030-01-01T00:00:00+00:00"


@pytest.mark.asyncio
async def test_purchase_status_rejects_missing_trusted_context(monkeypatch):
    class FakeMpesa:
        def __init__(self, _db):
            pass

        async def get_by_checkout_id(self, _checkout):
            return SimpleNamespace(router_id="router-1", site_id="site-1", device_mac="AA:BB:CC:DD:EE:FF")

    monkeypatch.setattr("app.services.mpesa_service.MpesaService", FakeMpesa)
    with pytest.raises(ConflictError, match="context is required"):
        await hotspot.purchase_status("checkout-id", Response(), None, object())


@pytest.mark.asyncio
async def test_purchase_status_rejects_context_for_different_device(monkeypatch):
    class FakeMpesa:
        def __init__(self, _db):
            pass

        async def get_by_checkout_id(self, _checkout):
            return SimpleNamespace(router_id="router-1", site_id="site-1", device_mac="AA:BB:CC:DD:EE:FF")

    class FakeAttestation:
        def __init__(self, _db):
            pass

        async def get_context(self, _token):
            return SimpleNamespace(router_id="router-1", site_id="site-1", client_mac="11:22:33:44:55:66")

    monkeypatch.setattr("app.services.mpesa_service.MpesaService", FakeMpesa)
    monkeypatch.setattr(hotspot, "HotspotAttestationService", FakeAttestation)
    with pytest.raises(ConflictError, match="does not belong"):
        await hotspot.purchase_status("checkout-id", Response(), "opaque-context", object())

