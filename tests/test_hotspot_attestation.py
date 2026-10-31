import asyncio
from datetime import datetime, timezone

from bson import ObjectId
from mongomock_motor import AsyncMongoMockClient
import pytest

from app.core.exceptions import ConflictError, NotFoundError, ServiceUnavailableError, ValidationError
from app.core.config import settings
from app.integrations.mikrotik.relay_client import RouterRelayError
from app.services.hotspot_attestation_service import (
    ATTESTATION_AUDIENCE,
    ATTESTATION_ISSUER,
    HotspotAttestationService,
    sign_attestation,
    verify_attestation_signature,
)

TOKEN = "local-test-relay-shared-token-abcdefghijklmnopqrstuvwxyz"
NOW = 1_798_000_000
CLIENT_IP = "192.168.89.100"
CLIENT_MAC = "AA:BB:CC:DD:EE:FF"


@pytest.fixture
def attestation_db():
    client = AsyncMongoMockClient(tz_aware=True)
    db = client["hotspot_attestation_test"]
    yield db
    client.close()


async def seed_router(db, name, site_name, *, status="online", site_status="active"):
    site_id = ObjectId()
    router_id = ObjectId()
    await db.sites.insert_one({"_id": site_id, "name": site_name, "status": site_status})
    await db.routers.insert_one({
        "_id": router_id,
        "name": name,
        "ip_address": f"10.10.0.{1 if site_name == 'Nyaururu' else 2}",
        "site_id": str(site_id),
        "status": status,
    })
    return str(router_id), str(site_id)


class FakeRelay:
    def __init__(self, observed_router_ids=(), *, evidence=None, mutate=None, unavailable=()):
        self.observed_router_ids = set(observed_router_ids)
        self.evidence = evidence or {
            "dhcp_lease_match": True,
            "dhcp_lease_status": "bound",
            "hotspot_host_match": True,
            "observation_age_seconds": 2,
        }
        self.mutate = mutate
        self.unavailable = set(unavailable)
        self.requests = []

    async def attest_hotspot_client(self, request):
        self.requests.append(request)
        if request["router_id"] in self.unavailable:
            raise RuntimeError("mock relay unavailable")
        payload = {
            "issuer": ATTESTATION_ISSUER,
            "audience": ATTESTATION_AUDIENCE,
            "router_id": request["router_id"],
            "site_id": request["site_id"],
            "client_ip": request["client_ip"] or CLIENT_IP,
            "client_mac": request["client_mac"],
            "issued_at": NOW,
            "expires_at": NOW + 30,
            "nonce": request["nonce"],
            "observed": request["router_id"] in self.observed_router_ids,
            "evidence": self.evidence,
        }
        if self.mutate:
            self.mutate(payload)
        return {"attestation": payload, "signature": sign_attestation(payload, TOKEN)}


def make_service(db, relay, monkeypatch):
    monkeypatch.setattr(settings, "router_connection_mode", "vps_relay")
    monkeypatch.setattr(settings, "router_relay_token", TOKEN)
    service = HotspotAttestationService(db, relay_client=relay, clock=lambda: NOW)
    return service


async def create_nonce_index(db):
    await db.router_attestation_nonces.create_index("nonce", unique=True)


@pytest.mark.asyncio
async def test_valid_relay_attestation_issues_short_lived_context(attestation_db, monkeypatch):
    nyahururu_id, nyahururu_site = await seed_router(attestation_db, "Nyaururu edge", "Nyaururu")
    await seed_router(attestation_db, "Nakuru edge", "Nakuru")
    await create_nonce_index(attestation_db)
    relay = FakeRelay({nyahururu_id})

    result = await make_service(attestation_db, relay, monkeypatch).create_context(CLIENT_IP, CLIENT_MAC)

    assert result["verified"] is True
    assert result["expires_at"] == NOW + 300
    assert "router_id" not in result and "site_id" not in result
    context = await HotspotAttestationService(
        attestation_db, relay_client=relay, clock=lambda: NOW
    ).get_context(result["context_token"])
    assert context.router_id == nyahururu_id
    assert context.site_id == nyahururu_site
    assert len(relay.requests) == 2  # both sites checked to prevent overlap confusion


@pytest.mark.asyncio
async def test_overlapping_private_ip_across_sites_is_not_ambiguous_without_matching_mac(attestation_db, monkeypatch):
    nyahururu_id, _ = await seed_router(attestation_db, "Nyaururu edge", "Nyaururu")
    await seed_router(attestation_db, "Nakuru edge", "Nakuru")
    await create_nonce_index(attestation_db)
    result = await make_service(attestation_db, FakeRelay({nyahururu_id}), monkeypatch).create_context(
        CLIENT_IP, CLIENT_MAC
    )
    assert result["verified"] is True


@pytest.mark.asyncio
async def test_duplicate_router_observations_are_rejected(attestation_db, monkeypatch):
    first, _ = await seed_router(attestation_db, "Nyaururu edge", "Nyaururu")
    second, _ = await seed_router(attestation_db, "Nakuru edge", "Nakuru")
    await create_nonce_index(attestation_db)
    with pytest.raises(ConflictError, match="multiple routers"):
        await make_service(attestation_db, FakeRelay({first, second}), monkeypatch).create_context(
            CLIENT_IP, CLIENT_MAC
        )


@pytest.mark.asyncio
async def test_relay_unavailability_fails_closed(attestation_db, monkeypatch):
    first, _ = await seed_router(attestation_db, "Nyaururu edge", "Nyaururu")
    second, _ = await seed_router(attestation_db, "Nakuru edge", "Nakuru")
    await create_nonce_index(attestation_db)
    relay = FakeRelay({first}, unavailable={second})
    with pytest.raises(ServiceUnavailableError, match="relay is unavailable"):
        await make_service(attestation_db, relay, monkeypatch).create_context(CLIENT_IP, CLIENT_MAC)


@pytest.mark.asyncio
@pytest.mark.parametrize("evidence", [
    {"dhcp_lease_match": False, "dhcp_lease_status": "bound", "hotspot_host_match": True, "observation_age_seconds": 1},
    {"dhcp_lease_match": True, "dhcp_lease_status": "waiting", "hotspot_host_match": True, "observation_age_seconds": 1},
    {"dhcp_lease_match": True, "dhcp_lease_status": "bound", "hotspot_host_match": False, "observation_age_seconds": 1},
    {"dhcp_lease_match": True, "dhcp_lease_status": "bound", "hotspot_host_match": True, "observation_age_seconds": 16},
])
async def test_stale_or_incomplete_router_observation_fails_closed(attestation_db, monkeypatch, evidence):
    router_id, _ = await seed_router(attestation_db, "Nakuru edge", "Nakuru")
    await create_nonce_index(attestation_db)
    service = make_service(attestation_db, FakeRelay({router_id}, evidence=evidence), monkeypatch)
    with pytest.raises(NotFoundError):
        await service.create_context(CLIENT_IP, CLIENT_MAC)


@pytest.mark.asyncio
@pytest.mark.parametrize("mutate", [
    lambda payload: payload.update(issuer="unknown-relay"),
    lambda payload: payload.update(audience="wrong-api"),
    lambda payload: payload.update(issued_at=NOW + 10),
    lambda payload: payload.update(expires_at=NOW - 1),
    lambda payload: payload.update(expires_at=NOW + 120),
    lambda payload: payload.update(client_ip="192.168.89.101"),
    lambda payload: payload.update(client_mac="10:20:30:40:50:60"),
    lambda payload: payload.update(nonce="altered-nonce"),
    lambda payload: payload.update(site_id=str(ObjectId())),
    lambda payload: payload.pop("evidence"),
    lambda payload: payload.pop("expires_at"),
])
async def test_signed_but_invalid_attestation_claims_are_rejected(attestation_db, monkeypatch, mutate):
    router_id, _ = await seed_router(attestation_db, "Nakuru edge", "Nakuru")
    await create_nonce_index(attestation_db)
    with pytest.raises(ServiceUnavailableError):
        await make_service(attestation_db, FakeRelay({router_id}, mutate=mutate), monkeypatch).create_context(
            CLIENT_IP, CLIENT_MAC
        )


@pytest.mark.asyncio
async def test_bad_signature_and_malformed_response_are_rejected(attestation_db, monkeypatch):
    router_id, _ = await seed_router(attestation_db, "Nakuru edge", "Nakuru")
    await create_nonce_index(attestation_db)

    class BadSignatureRelay(FakeRelay):
        async def attest_hotspot_client(self, request):
            result = await super().attest_hotspot_client(request)
            result["signature"] = "0" * 64
            return result

    service = make_service(attestation_db, BadSignatureRelay({router_id}), monkeypatch)
    with pytest.raises(ServiceUnavailableError, match="signature"):
        await service.create_context(CLIENT_IP, CLIENT_MAC)

    class MalformedRelay:
        async def attest_hotspot_client(self, _request):
            return {"success": True, "data": []}

    service = make_service(attestation_db, MalformedRelay(), monkeypatch)
    with pytest.raises(ServiceUnavailableError, match="invalid attestation"):
        await service.create_context(CLIENT_IP, CLIENT_MAC)


@pytest.mark.asyncio
async def test_concurrent_replay_only_consumes_nonce_once(attestation_db, monkeypatch):
    router_id, site_id = await seed_router(attestation_db, "Nakuru edge", "Nakuru")
    await create_nonce_index(attestation_db)
    service = make_service(attestation_db, FakeRelay({router_id}), monkeypatch)
    candidate = {"router_id": router_id, "site_id": site_id}
    nonce, challenge = await service._new_challenge(candidate, CLIENT_IP, CLIENT_MAC)
    reply = await service.relay.attest_hotspot_client({
        "router_id": router_id,
        "site_id": site_id,
        "client_ip": CLIENT_IP,
        "client_mac": CLIENT_MAC,
        "nonce": nonce,
    })

    async def consume():
        try:
            return await service._verify_relay_reply(candidate, nonce, challenge, reply)
        except Exception as exc:  # gathered to assert exactly one atomic winner
            return exc

    results = await asyncio.gather(consume(), consume())
    assert sum(isinstance(value, dict) for value in results) == 1
    assert sum(isinstance(value, ConflictError) for value in results) == 1


@pytest.mark.asyncio
async def test_expired_challenge_cannot_be_consumed(attestation_db, monkeypatch):
    router_id, site_id = await seed_router(attestation_db, "Nakuru edge", "Nakuru")
    await create_nonce_index(attestation_db)
    service = make_service(attestation_db, FakeRelay({router_id}), monkeypatch)
    nonce, challenge = await service._new_challenge(
        {"router_id": router_id, "site_id": site_id}, CLIENT_IP, CLIENT_MAC
    )
    await attestation_db.router_attestation_nonces.update_one(
        {"nonce": nonce}, {"$set": {"expires_at": datetime.fromtimestamp(NOW - 1, timezone.utc)}}
    )
    reply = await service.relay.attest_hotspot_client({
        "router_id": router_id, "site_id": site_id, "client_ip": CLIENT_IP,
        "client_mac": CLIENT_MAC, "nonce": nonce,
    })
    with pytest.raises(ConflictError, match="already used or expired"):
        await service._verify_relay_reply({"router_id": router_id, "site_id": site_id}, nonce, challenge, reply)


def test_hmac_authentication_is_canonical_and_tamper_evident():
    payload = {"issuer": ATTESTATION_ISSUER, "nonce": "challenge", "issued_at": NOW}
    signature = sign_attestation(payload, TOKEN)
    assert verify_attestation_signature(payload, signature, TOKEN)
    assert verify_attestation_signature(payload, signature, TOKEN + "wrong") is False
    assert verify_attestation_signature({**payload, "issuer": "forged"}, signature, TOKEN) is False


@pytest.mark.asyncio
async def test_expired_context_and_router_site_change_do_not_expose_site(attestation_db, monkeypatch):
    router_id, site_id = await seed_router(attestation_db, "Nakuru edge", "Nakuru")
    await create_nonce_index(attestation_db)
    service = make_service(attestation_db, FakeRelay({router_id}), monkeypatch)
    context = await service.create_context(CLIENT_IP, CLIENT_MAC)
    stored = await attestation_db.hotspot_trusted_contexts.find_one({})
    await attestation_db.hotspot_trusted_contexts.update_one(
        {"_id": stored["_id"]}, {"$set": {"expires_at": datetime.fromtimestamp(NOW - 1, timezone.utc)}}
    )
    assert await service.get_context(context["context_token"]) is None

    await attestation_db.hotspot_trusted_contexts.update_one(
        {"_id": stored["_id"]}, {"$set": {"expires_at": datetime.fromtimestamp(NOW + 30, timezone.utc)}}
    )
    await attestation_db.routers.update_one({"_id": ObjectId(router_id)}, {"$set": {"site_id": str(ObjectId())}})
    assert await service.get_context(context["context_token"]) is None


@pytest.mark.asyncio
async def test_inactive_or_unmapped_site_router_is_not_queried(attestation_db, monkeypatch):
    await seed_router(attestation_db, "Planned edge", "Planned", site_status="inactive")
    relay = FakeRelay()
    with pytest.raises(ServiceUnavailableError, match="active site"):
        await make_service(attestation_db, relay, monkeypatch).create_context(CLIENT_IP, CLIENT_MAC)
    assert relay.requests == []


@pytest.mark.asyncio
async def test_invalid_client_ip_or_mac_is_rejected_before_relay(attestation_db, monkeypatch):
    router_id, _ = await seed_router(attestation_db, "Nakuru edge", "Nakuru")
    relay = FakeRelay({router_id})
    service = make_service(attestation_db, relay, monkeypatch)
    with pytest.raises(ValidationError, match="private hotspot address"):
        await service.observe_device("8.8.8.8", CLIENT_MAC)
    with pytest.raises(ValidationError, match="valid client MAC"):
        await service.observe_device(CLIENT_IP, "not-a-mac")
    assert relay.requests == []


@pytest.mark.asyncio
async def test_relay_authentication_failure_is_not_a_fallback(attestation_db, monkeypatch):
    router_id, _ = await seed_router(attestation_db, "Nakuru edge", "Nakuru")

    class UnauthorizedRelay:
        async def attest_hotspot_client(self, _request):
            raise RouterRelayError("Relay authentication failed")

    service = make_service(attestation_db, UnauthorizedRelay(), monkeypatch)
    with pytest.raises(ServiceUnavailableError, match="relay is unavailable"):
        await service.create_context(CLIENT_IP, CLIENT_MAC)


@pytest.mark.asyncio
async def test_purchase_target_must_remain_at_the_verified_site(attestation_db, monkeypatch):
    first_router, first_site = await seed_router(attestation_db, "Nyaururu edge", "Nyaururu")
    second_router, _ = await seed_router(attestation_db, "Nakuru edge", "Nakuru")
    await create_nonce_index(attestation_db)
    service = make_service(attestation_db, FakeRelay({first_router}), monkeypatch)
    context = await service.create_context(CLIENT_IP, CLIENT_MAC)

    class PurchaseRelay:
        async def attest_hotspot_client(self, request):
            observed_router = first_router if request["client_mac"] == CLIENT_MAC else second_router
            return await FakeRelay({observed_router}).attest_hotspot_client(request)

    service.relay = PurchaseRelay()

    with pytest.raises(ConflictError, match="not connected at the verified site"):
        await service.attest_purchase_device(
            context["context_token"], "other", "192.168.89.120", "10:20:30:40:50:60"
        )
    assert first_site

