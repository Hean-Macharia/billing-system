"""FastAPI-side verifier for observations signed by the existing VPS relay.

The relay server is deployed separately and is not part of this repository.
Until it implements ``POST /api/v1/router/attest`` this service fails closed.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import ipaddress
import json
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.core.config import settings
from app.core.exceptions import ConflictError, NotFoundError, ServiceUnavailableError, ValidationError
from app.integrations.mikrotik.relay_client import RouterRelayClient, RouterRelayError

ATTESTATION_ISSUER = "devzen-vps-relay"
ATTESTATION_AUDIENCE = "devzen-billing-api"
ATTESTATION_MAX_LIFETIME_SECONDS = 60
ATTESTATION_MAX_AGE_SECONDS = 30
CONTEXT_LIFETIME_SECONDS = 300
MAX_ROUTER_CANDIDATES = 64
_SIGNING_DOMAIN = b"devzen/relay-attestation/v1"


@dataclass(frozen=True)
class TrustedRouterContext:
    router_id: str
    site_id: str
    client_ip: str
    client_mac: str
    context_token: Optional[str] = None


def normalize_mac(value: str) -> str:
    normalized = value.strip().replace("-", ":").upper()
    parts = normalized.split(":")
    if len(parts) != 6 or any(len(part) != 2 for part in parts):
        raise ValidationError("A valid client MAC address is required")
    try:
        bytes(int(part, 16) for part in parts)
    except ValueError as exc:
        raise ValidationError("A valid client MAC address is required") from exc
    return normalized


def normalize_client_ip(value: str) -> str:
    try:
        address = ipaddress.ip_address(value.strip())
    except ValueError as exc:
        raise ValidationError("A valid client IP address is required") from exc
    if not address.is_private or address.is_loopback or address.is_link_local or address.is_multicast:
        raise ValidationError("The captive client IP must be a private hotspot address")
    return str(address)


def _canonical_payload(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _derived_signing_key(relay_token: str) -> bytes:
    if not relay_token or len(relay_token) < 32:
        raise ServiceUnavailableError("The authenticated router relay is not configured")
    return hmac.new(relay_token.encode("utf-8"), _SIGNING_DOMAIN, hashlib.sha256).digest()


def sign_attestation(payload: dict, relay_token: str) -> str:
    """Shared canonical HMAC contract helper, also used by isolated tests."""
    return hmac.new(_derived_signing_key(relay_token), _canonical_payload(payload), hashlib.sha256).hexdigest()


def verify_attestation_signature(payload: dict, signature: str, relay_token: str) -> bool:
    if not isinstance(signature, str) or len(signature) != 64:
        return False
    try:
        expected = sign_attestation(payload, relay_token)
    except ServiceUnavailableError:
        return False
    return hmac.compare_digest(expected, signature.lower())


def _oid(value: Any) -> Optional[ObjectId]:
    try:
        return ObjectId(str(value))
    except Exception:
        return None


async def _rows(collection: Any, query: dict, limit: int = MAX_ROUTER_CANDIDATES + 1) -> list[dict]:
    cursor = collection.find(query)
    if hasattr(cursor, "to_list"):
        return await cursor.to_list(length=limit)
    return [item async for item in cursor]


class HotspotAttestationService:
    """Verify relay observations and issue short-lived opaque context handles."""

    def __init__(self, db: Any, relay_client: Any = None, clock=time.time):
        self.db = db
        self.relay = relay_client or RouterRelayClient(
            base_url=settings.router_relay_url,
            token=settings.router_relay_token,
            timeout=settings.router_connection_timeout,
        )
        self.clock = clock

    async def _candidate_routers(self) -> list[dict]:
        routers = await _rows(self.db.routers, {"status": {"$ne": "disabled"}})
        if len(routers) > MAX_ROUTER_CANDIDATES:
            raise ServiceUnavailableError("Router context verification is unavailable for this router inventory")
        if not routers:
            raise ServiceUnavailableError("No configured MikroTik routers are available for verification")

        candidates = []
        for router in routers:
            router_id = str(router.get("_id") or "")
            if not _oid(router_id):
                raise ServiceUnavailableError("A configured router has an invalid identity")
            router_site = str(router.get("site_id") or "") or None
            nas_id = router.get("nas_client_id")
            if nas_id:
                nas_oid = _oid(nas_id)
                nas_query = {"_id": {"$in": [nas_id, nas_oid]}} if nas_oid else {"_id": nas_id}
                nas = await self.db.nas_clients.find_one(nas_query)
                if not nas or str(nas.get("status") or "active").lower() in {"inactive", "disabled"}:
                    raise ServiceUnavailableError("A configured router has no active NAS mapping")
                nas_site = str(nas.get("site_id") or "") or None
                if router_site and nas_site and router_site != nas_site:
                    raise ServiceUnavailableError("A configured router has conflicting site mappings")
                router_site = router_site or nas_site
            if not router_site:
                raise ServiceUnavailableError("A configured router has no site mapping")
            site = await self.db.sites.find_one({"_id": _oid(router_site)})
            if not site or str(site.get("status") or "active").lower() != "active":
                raise ServiceUnavailableError("A configured router is not attached to an active site")
            candidates.append({"router_id": router_id, "site_id": router_site, "doc": router})
        if settings.router_connection_mode != "vps_relay":
            raise ServiceUnavailableError("Trusted hotspot verification requires the configured VPS relay")
        return candidates

    async def _new_challenge(self, candidate: dict, client_ip: Optional[str], client_mac: str) -> tuple[str, dict]:
        now = datetime.fromtimestamp(self.clock(), timezone.utc)
        nonce = secrets.token_urlsafe(32)
        record = {
            "nonce": nonce,
            "state": "pending",
            "router_id": candidate["router_id"],
            "site_id": candidate["site_id"],
            "client_ip": client_ip,
            "client_mac": client_mac,
            "created_at": now,
            "expires_at": now + timedelta(seconds=ATTESTATION_MAX_LIFETIME_SECONDS),
        }
        try:
            await self.db.router_attestation_nonces.insert_one(record)
        except DuplicateKeyError as exc:
            raise ServiceUnavailableError("Could not allocate a unique router verification challenge") from exc
        return nonce, record

    async def _verify_relay_reply(
        self,
        candidate: dict,
        nonce: str,
        challenge: dict,
        reply: Any,
    ) -> dict:
        if not isinstance(reply, dict):
            raise ServiceUnavailableError("The router relay returned an invalid attestation")
        payload = reply.get("attestation")
        signature = reply.get("signature")
        if not isinstance(payload, dict) or not isinstance(signature, str):
            raise ServiceUnavailableError("The router relay returned an invalid attestation")
        if not verify_attestation_signature(payload, signature, settings.router_relay_token or ""):
            raise ServiceUnavailableError("The router relay attestation signature is invalid")

        required = {
            "issuer", "audience", "router_id", "site_id", "client_ip", "client_mac",
            "issued_at", "expires_at", "nonce", "observed", "evidence",
        }
        if not required.issubset(payload):
            raise ServiceUnavailableError("The router relay attestation is incomplete")
        now = int(self.clock())
        issued_at, expires_at = payload.get("issued_at"), payload.get("expires_at")
        if not isinstance(issued_at, int) or isinstance(issued_at, bool):
            raise ServiceUnavailableError("The router relay attestation timestamp is invalid")
        if not isinstance(expires_at, int) or isinstance(expires_at, bool):
            raise ServiceUnavailableError("The router relay attestation expiry is invalid")
        if payload["issuer"] != ATTESTATION_ISSUER or payload["audience"] != ATTESTATION_AUDIENCE:
            raise ServiceUnavailableError("The router relay attestation issuer or audience is invalid")
        if issued_at > now + 5 or now - issued_at > ATTESTATION_MAX_AGE_SECONDS:
            raise ServiceUnavailableError("The router relay attestation is stale or from the future")
        if expires_at <= now or expires_at <= issued_at or expires_at - issued_at > ATTESTATION_MAX_LIFETIME_SECONDS:
            raise ServiceUnavailableError("The router relay attestation has expired or has an invalid lifetime")
        if payload["nonce"] != nonce:
            raise ServiceUnavailableError("The router relay attestation challenge does not match")
        if str(payload["router_id"]) != candidate["router_id"] or str(payload["site_id"]) != candidate["site_id"]:
            raise ServiceUnavailableError("The router relay attestation identifies an unexpected router or site")
        if normalize_mac(str(payload["client_mac"])) != challenge["client_mac"]:
            raise ServiceUnavailableError("The router relay attestation MAC does not match the request")
        attested_ip = normalize_client_ip(str(payload["client_ip"]))
        if challenge["client_ip"] and attested_ip != challenge["client_ip"]:
            raise ServiceUnavailableError("The router relay attestation IP does not match the request")
        if not isinstance(payload["observed"], bool) or not isinstance(payload["evidence"], dict):
            raise ServiceUnavailableError("The router relay observation evidence is malformed")

        consumed = await self.db.router_attestation_nonces.find_one_and_update(
            {"nonce": nonce, "state": "pending", "expires_at": {"$gt": datetime.fromtimestamp(self.clock(), timezone.utc)}},
            {"$set": {"state": "consumed", "consumed_at": datetime.fromtimestamp(self.clock(), timezone.utc)}},
            return_document=ReturnDocument.AFTER,
        )
        if not consumed:
            raise ConflictError("The router verification challenge was already used or expired")

        return {
            "router_id": candidate["router_id"],
            "site_id": candidate["site_id"],
            "client_ip": attested_ip,
            "client_mac": challenge["client_mac"],
            "observed": payload["observed"],
            "evidence": payload["evidence"],
        }

    async def observe_device(self, client_ip: Optional[str], client_mac: str) -> TrustedRouterContext:
        normalized_ip = normalize_client_ip(client_ip) if client_ip else None
        normalized_mac = normalize_mac(client_mac)
        candidates = await self._candidate_routers()
        semaphore = asyncio.Semaphore(4)

        async def observe(candidate: dict) -> dict:
            async with semaphore:
                nonce, challenge = await self._new_challenge(candidate, normalized_ip, normalized_mac)
                request = {
                    "router_id": candidate["router_id"],
                    "site_id": candidate["site_id"],
                    "client_ip": normalized_ip,
                    "client_mac": normalized_mac,
                    "nonce": nonce,
                    "requested_at": int(self.clock()),
                }
                try:
                    reply = await self.relay.attest_hotspot_client(request)
                except (RouterRelayError, Exception) as exc:
                    raise ServiceUnavailableError("The authenticated router relay is unavailable") from exc
                return await self._verify_relay_reply(candidate, nonce, challenge, reply)

        results = await asyncio.gather(
            *(observe(candidate) for candidate in candidates),
            return_exceptions=True,
        )
        failure = next((item for item in results if isinstance(item, Exception)), None)
        if failure:
            if isinstance(failure, (ServiceUnavailableError, ConflictError)):
                raise failure
            raise ServiceUnavailableError("Trusted router verification failed") from failure

        matches = [item for item in results if item["observed"]]
        if len(matches) > 1:
            raise ConflictError("This device was observed on multiple routers; contact support")
        if not matches:
            raise NotFoundError("The router did not observe this client on an active HotSpot")

        match = matches[0]
        evidence = match["evidence"]
        age = evidence.get("observation_age_seconds")
        if (
            evidence.get("dhcp_lease_match") is not True
            or str(evidence.get("dhcp_lease_status") or "").lower() != "bound"
            or evidence.get("hotspot_host_match") is not True
            or not isinstance(age, (int, float))
            or isinstance(age, bool)
            or age < 0
            or age > 15
        ):
            raise NotFoundError("A current matching DHCP lease and HotSpot host were not confirmed")
        return TrustedRouterContext(
            router_id=match["router_id"],
            site_id=match["site_id"],
            client_ip=match["client_ip"],
            client_mac=match["client_mac"],
        )

    async def create_context(self, client_ip: str, client_mac: str) -> dict:
        observation = await self.observe_device(client_ip, client_mac)
        raw_token = secrets.token_urlsafe(32)
        now = datetime.fromtimestamp(self.clock(), timezone.utc)
        expires_at = now + timedelta(seconds=CONTEXT_LIFETIME_SECONDS)
        await self.db.hotspot_trusted_contexts.insert_one({
            "token_hash": hashlib.sha256(raw_token.encode("utf-8")).hexdigest(),
            "router_id": observation.router_id,
            "site_id": observation.site_id,
            "client_ip": observation.client_ip,
            "client_mac": observation.client_mac,
            "created_at": now,
            "expires_at": expires_at,
        })
        return {"verified": True, "context_token": raw_token, "expires_at": int(expires_at.timestamp())}

    async def get_context(self, raw_token: Optional[str]) -> Optional[TrustedRouterContext]:
        if not isinstance(raw_token, str) or not raw_token or len(raw_token) > 256:
            return None
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        now = datetime.fromtimestamp(self.clock(), timezone.utc)
        doc = await self.db.hotspot_trusted_contexts.find_one({"token_hash": token_hash, "expires_at": {"$gt": now}})
        if not doc:
            return None
        router_id, site_id = str(doc.get("router_id") or ""), str(doc.get("site_id") or "")
        router = await self.db.routers.find_one({"_id": _oid(router_id)})
        site = await self.db.sites.find_one({"_id": _oid(site_id)})
        if not router or str(router.get("status") or "").lower() == "disabled" or not site:
            return None
        router_site = str(router.get("site_id") or "") or None
        if router.get("nas_client_id"):
            nas_id = router["nas_client_id"]
            nas_oid = _oid(nas_id)
            nas_query = {"_id": {"$in": [nas_id, nas_oid]}} if nas_oid else {"_id": nas_id}
            nas = await self.db.nas_clients.find_one(nas_query)
            if not nas or str(nas.get("status") or "active").lower() in {"inactive", "disabled"}:
                return None
            nas_site = str(nas.get("site_id") or "") or None
            if router_site and nas_site and router_site != nas_site:
                return None
            router_site = router_site or nas_site
        if (
            router_site != site_id
            or str(site.get("status") or "active").lower() != "active"
        ):
            return None
        return TrustedRouterContext(
            router_id=router_id,
            site_id=site_id,
            client_ip=str(doc["client_ip"]),
            client_mac=normalize_mac(str(doc["client_mac"])),
        )

    async def attest_purchase_device(
        self,
        raw_token: str,
        device_type: str,
        client_ip: Optional[str],
        client_mac: str,
    ) -> TrustedRouterContext:
        context = await self.get_context(raw_token)
        if not context:
            raise ConflictError("The trusted hotspot context is missing or expired. Reopen the Wi-Fi sign-in page")
        normalized_mac = normalize_mac(client_mac)
        requested_ip = normalize_client_ip(client_ip) if client_ip else None
        current = await self.observe_device(context.client_ip, context.client_mac)
        if current.site_id != context.site_id or current.router_id != context.router_id:
            raise ConflictError("The captive device moved to another router; reload the Wi-Fi sign-in page")
        if device_type == "this_device":
            if normalized_mac != context.client_mac or (requested_ip and requested_ip != context.client_ip):
                raise ConflictError("The purchase device does not match the verified captive device")
            observed = current
        else:
            observed = await self.observe_device(requested_ip, normalized_mac)
        if observed.site_id != context.site_id:
            raise ConflictError("The purchase device is not connected at the verified site")
        return observed
