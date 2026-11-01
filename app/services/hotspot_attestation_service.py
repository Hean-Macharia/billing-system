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
from app.core.logging import get_logger
from app.integrations.mikrotik.relay_client import RouterRelayClient, RouterRelayError

ATTESTATION_ISSUER = "devzen-vps-relay"
ATTESTATION_AUDIENCE = "devzen-billing-api"
ATTESTATION_MAX_LIFETIME_SECONDS = 60
ATTESTATION_MAX_AGE_SECONDS = 30
CONTEXT_LIFETIME_SECONDS = 300
MAX_ROUTER_CANDIDATES = 64
_SIGNING_DOMAIN = b"devzen/relay-attestation/v1"
logger = get_logger(__name__)


@dataclass(frozen=True)
class TrustedRouterContext:
    router_id: str
    site_id: str
    client_ip: str
    client_mac: str
    context_token: Optional[str] = None
    purchase_context_mac: Optional[str] = None
    purchase_context_router_id: Optional[str] = None
    purchase_context_site_id: Optional[str] = None


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


def _id_text(value: Any) -> Optional[str]:
    """Normalize Mongo ObjectId and its string representation consistently."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    parsed = _oid(text)
    return str(parsed) if parsed is not None else text


def _id_query_values(value: Any) -> list[Any]:
    """Match legacy string references and BSON ObjectId references safely."""
    text = _id_text(value)
    if not text:
        return []
    parsed = _oid(text)
    return [parsed, text] if parsed is not None else [text]


async def _find_by_id(collection: Any, value: Any) -> Optional[dict]:
    candidates = _id_query_values(value)
    if not candidates:
        return None
    return await collection.find_one({"_id": {"$in": candidates}})


def _status_text(value: Any) -> str:
    if hasattr(value, "value"):
        value = value.value
    return str(value or "").strip().lower()


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

    async def _candidate_routers(self, correlation_id: Optional[str] = None) -> list[dict]:
        routers = await _rows(self.db.routers, {"status": "online"})
        if len(routers) > MAX_ROUTER_CANDIDATES:
            raise ServiceUnavailableError("Router context verification is unavailable for this router inventory")
        candidates = []
        router_ids = set()
        for router in routers:
            router_id = _id_text(router.get("_id")) or ""
            router_status = _status_text(router.get("status"))
            if router_status != "online":
                self._log_candidate_exclusion(router_id or "missing", f"router_not_online:{router_status or 'missing'}", correlation_id)
                continue
            parsed_router_id = _oid(router_id)
            if not parsed_router_id:
                self._log_candidate_exclusion(router_id or "missing", "invalid_router_identity", correlation_id)
                continue
            router_id = str(parsed_router_id)
            if router_id in router_ids:
                logger.error(
                    "Duplicate router identity prevents trusted HotSpot verification",
                    extra={"event": "hotspot_router_candidate_ambiguous", "router_id": router_id},
                )
                raise ServiceUnavailableError("Duplicate router identities prevent trusted HotSpot verification")
            router_ids.add(router_id)

            router_site = _id_text(router.get("site_id"))
            if not router_site:
                self._log_candidate_exclusion(router_id, "missing_router_site_mapping", correlation_id)
                continue
            nas_id = router.get("nas_client_id")
            if nas_id:
                nas = await _find_by_id(self.db.nas_clients, nas_id)
                if not nas or _status_text(nas.get("status") or "active") in {"inactive", "disabled"}:
                    self._log_candidate_exclusion(router_id, "missing_or_inactive_nas_mapping", correlation_id)
                    continue
                nas_site = _id_text(nas.get("site_id"))
                if not nas_site:
                    self._log_candidate_exclusion(router_id, "missing_nas_site_mapping", correlation_id)
                    continue
                if router_site != nas_site:
                    self._log_candidate_exclusion(router_id, "conflicting_router_nas_site_mapping", correlation_id)
                    continue
            site = await _find_by_id(self.db.sites, router_site)
            if not site or _status_text(site.get("status")) != "active":
                reason = "missing_site_record" if not site else "site_inactive"
                self._log_candidate_exclusion(router_id, reason, correlation_id)
                continue
            candidates.append({"router_id": router_id, "site_id": router_site, "doc": router})
        if not candidates:
            raise ServiceUnavailableError("No eligible routers with valid active-site mappings are available for HotSpot verification")
        if settings.router_connection_mode != "vps_relay":
            raise ServiceUnavailableError("Trusted hotspot verification requires the configured VPS relay")
        return candidates

    @staticmethod
    def _log_candidate_exclusion(router_id: str, reason: str, correlation_id: Optional[str] = None) -> None:
        logger.warning(
            "HotSpot attestation router candidate excluded",
            extra={
                "event": "hotspot_router_candidate_excluded",
                "router_id": router_id,
                "reason": reason,
                "correlation_id": correlation_id,
                "stage": "candidate_selection",
            },
        )

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
        correlation_id: Optional[str] = None,
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
        raw_attested_ip = payload["client_ip"]
        if raw_attested_ip is None:
            if challenge["client_ip"]:
                raise ServiceUnavailableError("The router relay attestation omitted the requested client IP")
            attested_ip = None
        else:
            attested_ip = normalize_client_ip(str(raw_attested_ip))
            if challenge["client_ip"] and attested_ip != challenge["client_ip"]:
                raise ServiceUnavailableError("The router relay attestation IP does not match the request")
        if not isinstance(payload["observed"], bool) or not isinstance(payload["evidence"], dict):
            raise ServiceUnavailableError("The router relay observation evidence is malformed")
        if payload["observed"] and attested_ip is None:
            raise ServiceUnavailableError("A positive router observation must include the resolved client IP")

        consumed = await self.db.router_attestation_nonces.find_one_and_update(
            {"nonce": nonce, "state": "pending", "expires_at": {"$gt": datetime.fromtimestamp(self.clock(), timezone.utc)}},
            {"$set": {"state": "consumed", "consumed_at": datetime.fromtimestamp(self.clock(), timezone.utc)}},
            return_document=ReturnDocument.AFTER,
        )
        if not consumed:
            now_dt = datetime.fromtimestamp(self.clock(), timezone.utc)
            prior = await self.db.router_attestation_nonces.find_one(
                {"nonce": nonce}, {"state": 1, "expires_at": 1}
            )
            prior_expiry = prior.get("expires_at") if prior else None
            if isinstance(prior_expiry, datetime) and prior_expiry.tzinfo is None:
                # Motor's default BSON decoder returns naive UTC datetimes.
                prior_expiry = prior_expiry.replace(tzinfo=timezone.utc)
            if not prior or not isinstance(prior_expiry, datetime) or prior_expiry <= now_dt:
                nonce_result = "expired_or_unknown"
            elif prior.get("state") == "consumed":
                nonce_result = "replayed"
            else:
                nonce_result = "not_pending"
            logger.warning(
                "HotSpot attestation challenge was not consumed",
                extra={
                    "event": "hotspot_attestation_nonce_rejected",
                    "nonce_result": nonce_result,
                    "router_id": candidate["router_id"],
                    "site_id": candidate["site_id"],
                    "correlation_id": correlation_id,
                    "stage": "nonce_consumption",
                },
            )
            raise ConflictError("The router verification challenge was already used or expired")

        return {
            "router_id": candidate["router_id"],
            "site_id": candidate["site_id"],
            "client_ip": attested_ip,
            "client_mac": challenge["client_mac"],
            "observed": payload["observed"],
            "evidence": payload["evidence"],
        }

    async def observe_device(
        self, client_ip: Optional[str], client_mac: str, correlation_id: Optional[str] = None
    ) -> TrustedRouterContext:
        started = time.monotonic()
        normalized_ip = normalize_client_ip(client_ip) if client_ip else None
        normalized_mac = normalize_mac(client_mac)
        candidates = await self._candidate_routers(correlation_id=correlation_id)
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
                    reply = await self.relay.attest_hotspot_client(request, correlation_id=correlation_id)
                except RouterRelayError as exc:
                    if exc.status_code == 403:
                        self._log_candidate_exclusion(candidate["router_id"], "relay_router_site_not_allowlisted")
                        return {"observed": False, "candidate_rejected": True}
                    logger.error(
                        "Router relay candidate check failed",
                        extra={
                            "event": "hotspot_router_relay_failed",
                            "router_id": candidate["router_id"],
                            "site_id": candidate["site_id"],
                            "relay_status": exc.status_code,
                        "correlation_id": correlation_id or exc.correlation_id,
                        "stage": "relay_observation",
                        },
                    )
                    raise ServiceUnavailableError("The authenticated router relay is unavailable") from exc
                except Exception as exc:
                    logger.error(
                        "Router relay candidate check failed",
                        extra={
                            "event": "hotspot_router_relay_failed",
                            "router_id": candidate["router_id"],
                            "site_id": candidate["site_id"],
                            "exception_class": type(exc).__name__,
                        },
                    )
                    raise ServiceUnavailableError("The authenticated router relay is unavailable") from exc
                verified = await self._verify_relay_reply(candidate, nonce, challenge, reply, correlation_id=correlation_id)
                logger.info(
                    "HotSpot router observation validated",
                    extra={
                        "event": "hotspot_router_observation_validated",
                        "router_id": candidate["router_id"],
                        "site_id": candidate["site_id"],
                        "observed": verified["observed"],
                        "correlation_id": correlation_id,
                        "stage": "signed_observation_validated",
                    },
                )
                return verified

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
            logger.error(
                "HotSpot device observation is ambiguous across routers",
                extra={
                    "event": "hotspot_router_observation_ambiguous",
                    "router_ids": sorted(item["router_id"] for item in matches),
                    "site_ids": sorted(item["site_id"] for item in matches),
                    "match_count": len(matches),
                    "correlation_id": correlation_id,
                    "duration_ms": round((time.monotonic() - started) * 1000, 1),
                    "stage": "uniqueness_check",
                },
            )
            raise ConflictError("This device was observed on multiple routers; contact support")
        if not matches and any(item.get("candidate_rejected") for item in results if isinstance(item, dict)):
            raise ServiceUnavailableError("The relay does not authorize every configured router/site candidate")
        if not matches:
            logger.info(
                "HotSpot trusted device observation completed without a matching client",
                extra={
                    "event": "hotspot_device_observation_complete",
                    "outcome": "not_observed",
                    "correlation_id": correlation_id,
                    "candidate_count": len(candidates),
                    "duration_ms": round((time.monotonic() - started) * 1000, 1),
                    "stage": "final_result",
                },
            )
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
        logger.info(
            "HotSpot trusted device observation completed",
            extra={
                "event": "hotspot_device_observation_complete",
                "outcome": "verified",
                "router_id": match["router_id"],
                "site_id": match["site_id"],
                "correlation_id": correlation_id,
                "candidate_count": len(candidates),
                "duration_ms": round((time.monotonic() - started) * 1000, 1),
                "stage": "final_result",
            },
        )
        return TrustedRouterContext(
            router_id=match["router_id"],
            site_id=match["site_id"],
            client_ip=match["client_ip"],
            client_mac=match["client_mac"],
        )

    async def create_context(
        self, client_ip: str, client_mac: str, correlation_id: Optional[str] = None
    ) -> dict:
        observation = await self.observe_device(client_ip, client_mac, correlation_id=correlation_id)
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
        router = await _find_by_id(self.db.routers, router_id)
        site = await _find_by_id(self.db.sites, site_id)
        if not router or _status_text(router.get("status")) != "online" or not site:
            return None
        router_site = _id_text(router.get("site_id"))
        if not router_site:
            return None
        if router.get("nas_client_id"):
            nas_id = router["nas_client_id"]
            nas = await _find_by_id(self.db.nas_clients, nas_id)
            if not nas or _status_text(nas.get("status") or "active") in {"inactive", "disabled"}:
                return None
            nas_site = _id_text(nas.get("site_id"))
            if not nas_site or router_site != nas_site:
                return None
        if (
            router_site != _id_text(site_id)
            or _status_text(site.get("status")) != "active"
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
        correlation_id: Optional[str] = None,
    ) -> TrustedRouterContext:
        context = await self.get_context(raw_token)
        if not context:
            raise ConflictError("The trusted hotspot context is missing or expired. Reopen the Wi-Fi sign-in page")
        normalized_mac = normalize_mac(client_mac)
        requested_ip = normalize_client_ip(client_ip) if client_ip else None
        current = await self.observe_device(context.client_ip, context.client_mac, correlation_id=correlation_id)
        if current.site_id != context.site_id or current.router_id != context.router_id:
            raise ConflictError("The captive device moved to another router; reload the Wi-Fi sign-in page")
        if device_type == "this_device":
            if normalized_mac != context.client_mac or (requested_ip and requested_ip != context.client_ip):
                raise ConflictError("The purchase device does not match the verified captive device")
            observed = current
        else:
            observed = await self.observe_device(requested_ip, normalized_mac, correlation_id=correlation_id)
        if observed.site_id != context.site_id:
            raise ConflictError("The purchase device is not connected at the verified site")
        return TrustedRouterContext(
            router_id=observed.router_id,
            site_id=observed.site_id,
            client_ip=observed.client_ip,
            client_mac=observed.client_mac,
            purchase_context_mac=context.client_mac,
            purchase_context_router_id=context.router_id,
            purchase_context_site_id=context.site_id,
        )
