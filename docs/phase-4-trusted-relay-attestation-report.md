# Phase 4 — Trusted Relay Attestation Report

**Date:** 2026-10-31  
**Scope:** repository implementation and isolated mock tests. No production relay, VPS, Render service, MongoDB, MikroTik router, FreeRADIUS host, VPN, or M-Pesa provider was contacted or changed.

## 1. Executive summary

The repository contains FastAPI's relay client, but not the VPS relay server or the deployed `isp-relay.service`. The existing relay client authenticates FastAPI-to-relay requests with HTTPS and the existing bearer token, calls `GET /health` and `POST /api/v1/router/relay`, and exposes generic management actions. It has no signed captive observation operation. Existing relay-mode DHCP lookup does not pass a selected router ID to the relay: `RouterService.get_dhcp_leases(router_id)` resolves a database router, but the relay client calls the generic `dhcp.leases` action with no router selector. Its single-router target is configured outside that operation. Therefore the existing relay cannot currently attest multi-site device identity.

FastAPI now has a **mock-tested client and verifier contract** for `POST /api/v1/router/attest`. It verifies an HMAC derived from the existing relay token, active configured router/site relationships, client IP/MAC binding, issuer/audience/time/evidence, and consumes a unique challenge once in MongoDB. It then issues an opaque five-minute server-side context. The two captive frontends request this context when RouterOS provides both IP and MAC, send it only in `X-Hotspot-Context`, and fall back to the global catalog when context is absent or unavailable. Site-specific purchases require a valid context and a fresh relay observation before STK initiation; site/router IDs come from server-side verified context, never from browser request fields.

**The end-to-end feature is incomplete.** The relay server endpoint, relay-side router allowlist, RouterOS DHCP/HotSpot host query, HMAC signing, and live configuration are external and were not changed. The new client must receive the specified signed response before site-specific pages or purchases can succeed. No live connectivity claim is made.

## 2. Relay architecture inspected

### In-repository FastAPI → relay path

- `RouterRelayClient` sends JSON over HTTPS with `Authorization: Bearer <existing ROUTER_RELAY_TOKEN>`.
- Existing calls: `GET /health`; `POST /api/v1/router/relay` actions include `system.identity`, `system.resource`, `system.health`, `interface.list`, `pppoe.active`, `pppoe.secrets`, `pppoe.add`, `pppoe.disconnect`, `hotspot.active`, `hotspot.users`, `hotspot.add`, `hotspot.disconnect`, `dhcp.leases`, and `queue.list`.
- Admin router relay health checks use the configured relay URL and token.
- In `vps_relay` mode, `RouterService` prefers the relay and may fall back to the existing globally configured direct connection. Its general management relay client does not take a per-router identity.
- DHCP and HotSpot active-session reads exist. The checked-in RouterOS clients do not expose the HotSpot **host** table (`/ip/hotspot/host`), which is necessary for unauthenticated HotSpot host corroboration. There is no relay server source in the repository, no relay endpoint implementation, and no inspected VPS service code.
- `render.yaml` declares the existing relay URL/token as externally configured values; this phase did not inspect their values or alter deployment settings. No separate key or environment variable was added.

### RouterOS observation boundary

The repository has RouterOS v6 legacy API support and v7 REST support. RouterOS 6.49.21 must use the legacy API; no direct signing capability is assumed. MikroTik documentation describes `/ip/dhcp-server/lease` status/expiry/last-seen information and `/ip/hotspot/host` as the host table for HotSpot clients. This phase does not contact a router. References: [MikroTik DHCP](https://help.mikrotik.com/docs/spaces/ROS/pages/24805500/DHCP), [MikroTik HotSpot](https://help.mikrotik.com/docs/spaces/ROS/pages/56459266/HotSpot%2B-%2BCaptive%2Bportal).

## 3. Attestation protocol implemented on the FastAPI side

### Relay request contract (relay implementation required)

FastAPI chooses candidate routers from configured database records, verifies each is attached to an active site, then calls the authenticated relay once per candidate. Browser IP/MAC are sent as **untrusted query hints**. Browser router/site IDs are never accepted. The relay must independently check that the requested router ID and site ID exist in its own configured allowlist and correspond to the same router/site; it must never use request values as an arbitrary RouterOS address.

```http
POST /api/v1/router/attest
Authorization: Bearer <existing ROUTER_RELAY_TOKEN>
Content-Type: application/json
```

```json
{
  "router_id": "configured-router-object-id",
  "site_id": "configured-active-site-object-id",
  "client_ip": "192.168.89.100",
  "client_mac": "AA:BB:CC:DD:EE:FF",
  "nonce": "one-time-random-challenge-from-fastapi",
  "requested_at": 1798000000
}
```

The relay performs read-only observations on the selected router over its existing private/VPN path. It must match IP and MAC on the **same** current DHCP lease and the HotSpot host table; require a bound lease, current observation (the FastAPI contract accepts at most 15 seconds observation age), and active router/site. It returns a signed negative observation when the router is reachable but the client is not observed. If the router is unavailable, the relay returns an error; FastAPI fails closed, including if any candidate router cannot be checked, because uniqueness across sites is then unknown.

Expected response:

```json
{
  "success": true,
  "attestation": {
    "issuer": "devzen-vps-relay",
    "audience": "devzen-billing-api",
    "router_id": "configured-router-object-id",
    "site_id": "configured-active-site-object-id",
    "client_ip": "192.168.89.100",
    "client_mac": "AA:BB:CC:DD:EE:FF",
    "issued_at": 1798000000,
    "expires_at": 1798000030,
    "nonce": "one-time-random-challenge-from-fastapi",
    "observed": true,
    "evidence": {
      "dhcp_lease_match": true,
      "dhcp_lease_status": "bound",
      "hotspot_host_match": true,
      "observation_age_seconds": 2
    }
  },
  "signature": "64 lowercase hexadecimal characters"
}
```

### Authentication and signature

The existing relay token remains the only shared secret. FastAPI derives a purpose-specific HMAC key as:

```text
HMAC-SHA256(key=ROUTER_RELAY_TOKEN, message="devzen/relay-attestation/v1")
```

The relay signs the UTF-8 canonical JSON serialization of the complete `attestation` object (sorted keys, compact separators, ASCII escaping) with HMAC-SHA256 and returns lowercase hex. The client requires a configured token of at least 32 characters, verifies the signature with constant-time comparison, and validates issuer, audience, exact router/site/client IP/client MAC/nonce, issue time, expiry, and evidence. Lifetime is at most 60 seconds; future issue time beyond 5 seconds, issue age over 30 seconds, expired/oversized lifetime, altered claims, malformed response, invalid signature, or an unavailable relay is rejected.

HMAC is chosen because it fits the existing authenticated shared-token relay architecture and avoids introducing another secret. The same token rotation invalidates the derived signing key; it must remain private on both servers and must never enter browser code. HMAC assumes the relay and FastAPI are trusted peers that share that token; it is not non-repudiation. If independent signing authority is later required, a relay-private asymmetric key and FastAPI public verification key need a separately approved rotation/configuration design.

### Replay prevention and context handle

- FastAPI generates a cryptographically random nonce per candidate-router request and inserts a `pending` nonce document before calling the relay.
- After signature/claim/time validation, FastAPI atomically changes `pending` to `consumed` with a conditional Mongo `find_one_and_update`. Concurrent or repeated consumption yields one winner; subsequent use and expired challenges fail.
- A TTL index on `expires_at` removes expired nonce rows. Exact expiry checks remain in code; TTL deletion delay does not extend validity.
- Only when exactly one router reports fresh matching evidence does FastAPI create a 5-minute context. Mongo stores only SHA-256 of the random opaque token plus the trusted router/site/IP/MAC/expiry. The raw context token is returned once with `Cache-Control: no-store` and is held in browser `sessionStorage`, never in a URL.
- Package reads validate the context hash, expiry, and current router/site/NAS association. A context does not itself authorize purchase: purchase performs new relay observations for the current device and selected target, and requires the plan to be global or assigned to the observed site.

DHCP/HotSpot observation is still not cryptographic proof against a local MAC spoofing attacker. The relay proves that its configured router recently observed the values, not cryptographic possession by the customer device.

## 4. Captive portal and package/purchase integration

- `/hotspot/` remains the documented RouterOS captive portal. `/index.html` remains the second direct captive implementation with its standalone checkout. Neither was deleted or consolidated.
- Both scripts read the available RouterOS IP/MAC hints and submit them to `POST /api/v1/hotspot/devices/attest`. No router/site identity is submitted as authority and no MAC entry was added for a customer's current device.
- The returned opaque context is kept in `sessionStorage` under `dz_hotspot_context` and sent in `X-Hotspot-Context`. It is not placed in checkout query strings or localStorage.
- `GET /api/v1/hotspot/plans/public` ignores query-string `site_id`. It returns global plans without a valid context, and global plus matching site plans with a valid context. Invalid/expired context safely falls back to global plans only. Context catalog responses are `private, no-store`.
- `POST /api/v1/hotspot/purchase` does not accept `router_id` or `site_id` in its schema. Site plans reject before router fallback/device lookup unless the opaque context exists. The backend re-observes the current captive device; for a different target device it also re-observes that target and requires the same verified site. `MpesaService` independently checks selected plan/site compatibility before any STK call.
- Global plans keep the Phase 3 compatibility path if attestation is absent/unavailable; the existing DHCP verification remains required. Site-specific plans fail closed if relay context is missing or invalid. No production M-Pesa request was made.
- Pending transaction site/router values are populated only from the verified server result. Verified site/router are carried to the voucher batch and resulting voucher. Existing provider callback verification, settlement and reconciliation algorithms were not changed.
- Existing free-trial restrictions, voucher/RADIUS authorization, RouterOS HTTP-CHAP behavior, and customer/admin apps were not redesigned.

## 5. API and database changes

### New/changed API contract

- New public `POST /api/v1/hotspot/devices/attest` accepts `{ip_address, mac_address}` as untrusted hints and returns `{verified, context_token, expires_at}` only after signed relay verification.
- `GET /api/v1/hotspot/plans/public` optionally accepts `X-Hotspot-Context`; arbitrary `site_id` query remains ignored.
- `POST /api/v1/hotspot/purchase` optionally accepts `X-Hotspot-Context`; browser-provided router/site IDs are not schema fields. Existing request body remains compatible.
- New relay client contract: authenticated `POST /api/v1/router/attest` described above. It is **not implemented on the external relay**.

### Database

Two collections are added to normal startup index creation:

- `router_attestation_nonces`: unique nonce and TTL expiry index; holds pending/consumed challenges.
- `hotspot_trusted_contexts`: unique hash-only token index, TTL expiry index, and site/expiry lookup index; holds short-lived trusted context.

Existing transaction/voucher router/site snapshots from Phase 3 are used. No destructive migration, existing customer document rewrite, production index creation, or production database access occurred. Startup will create the two new collection indexes on the application's configured database when deployed; this is additive but should be reviewed as part of release rollout.

## 6. Phase 4J — health test and portal routing findings

The prior root test disagreed with `docs/deployment.md` and `docs/mikrotik-routeros6.md`, which both prescribe `/hotspot/` as the RouterOS/root captive entry. The production `render.yaml` runs the FastAPI Docker app; `app/main.py` previously redirected `/` to the alternate `/index.html` portal. The router guide is the specific captive deployment instruction, so the root redirect was aligned to `/hotspot/`. The secondary portal remains served at `/index.html` and retains `/checkout.html`.

The branding test incorrectly required the all-uppercase phrase in admin/customer HTML. The actual wordmark in those apps is `DevZen Creations`, while the captive hotspot wordmark is uppercase. The test now checks the actual branding used by each route. This does not alter branding or delete a portal.

## 7. Tests and exact results

- `python -m pytest -q`: **149 passed, 27 skipped, 5 warnings**. Skips are existing tests marked for unavailable local MongoDB/other integration dependencies; they were not counted as passed. Warnings are third-party deprecations.
- Focused new attestation/package/health set: **54 passed, 1 warning**.
- `python -m compileall -q app tests` and direct imports of `app.routes.hotspot`, `app.services.router_service`, and `app.services.hotspot_attestation_service`: **passed**.
- `node --check js/api.js js/api.config.js js/portal.js js/checkout.js hotspot/js/app.js` (executed as individual checks in one PowerShell command): **passed**.
- `node --test tests/hotspot-portal.test.js`: **7 passed, 0 failed, 0 skipped** (HTTP-CHAP regressions).
- `git diff --check`: **passed**; Git reported existing LF-to-CRLF working-copy notices only.
- New mocks cover valid HMAC, altered signature/claims, issuer/audience, timestamp expiry/future/lifetime, client IP/MAC/nonce/router/site binding, negative/missing/stale DHCP and HotSpot evidence, unreachable/unauthorized relay, inactive site, overlapping private LAN addresses, duplicate router observation, context expiry/site remapping, single-use nonce, concurrent replay, site catalog spoofing, and purchase plan/site rejection before mocked STK initiation.
- All new tests use `mongomock_motor` and fake relay clients. No production API or network request was made.

## 8. Files changed in Phase 4

- `app/integrations/mikrotik/relay_client.py` — relay attestation client call.
- `app/services/hotspot_attestation_service.py` — HMAC/claim/time/evidence validation, per-router challenges, atomic nonce consumption, context issuance and purchase re-attestation.
- `app/schemas/portal.py`, `app/routes/hotspot.py` — attestation API, trusted-context plan filtering, and server-side purchase validation.
- `app/core/database.py` — nonce/context collections and unique/TTL indexes.
- `app/services/mpesa_service.py`, `app/services/voucher_service.py` — verified router/site snapshots on pending transaction and voucher batch; no settlement algorithm change.
- `app/main.py` — documented root redirect to `/hotspot/`, retaining direct `/index.html` access.
- `js/api.config.js`, `js/api.js`, `js/portal.js`, `js/checkout.js`, `hotspot/js/app.js` — session-scoped context request/use in both captive implementations.
- `tests/test_hotspot_attestation.py`, `tests/test_router_relay_attestation_client.py`, `tests/test_hotspot_site_package_selection.py`, `tests/test_health.py` — isolated tests and corrected route/branding assertions.
- `docs/integration-audit.md`, `docs/phase-4-trusted-relay-attestation-report.md` — architecture documentation.

Other Phase 1/2/3 working-tree changes predate this phase and were preserved. Review `git status` before staging.

## 9. Relay deployment guide (separate, not performed)

The relay owner must implement and test the specified endpoint in the existing `isp-relay.service` codebase separately. It must:

1. Require the existing HTTPS bearer authentication and never log the token or context token.
2. Maintain a server-side allowlist mapping router IDs to site IDs and the existing private/VPN router connection details; reject unknown, disabled, or mismatched router/site IDs. Do not accept browser-supplied router identity.
3. On RouterOS 6.49.21 use the existing legacy API over the existing L2TP/VPN path. Read current DHCP lease and `/ip/hotspot/host` observations without modifying router state. Do not expose RouterOS management ports publicly or change VPN architecture.
4. Match the same normalized IP/MAC on the same router; require bound/current DHCP lease and a matching HotSpot host. Return signed negative observation for no match and an error for unreachable router.
5. Sign canonical response payload exactly as specified with the domain-derived HMAC key and return issuer/audience/router/site/client/time/nonce/evidence. Enforce a maximum 60-second expiry and avoid reflecting unvalidated request IDs.
6. Add isolated relay tests for valid/invalid bearer, invalid router/site pair, stale/mismatched lease, HotSpot host mismatch, signature canonicalization, replayed nonce, and unavailable router. Deploy only in a separately approved change; do not alter or restart the production service in this phase.

## 10. Known limitations and security considerations

- The new endpoint contract currently returns 404/unsupported from the external relay until it is implemented; this FastAPI phase intentionally fails closed for site-specific purchases. Global-only purchase remains available under its prior lease-verification path.
- All enabled configured routers are queried to prevent overlapping RFC1918 addresses from selecting the wrong site. If a candidate router is unreachable, verification fails rather than choosing another site. The current implementation caps candidates at 64 and limits concurrent relay requests to four; larger router fleets will need a batch relay observation contract or a reviewed routing strategy.
- DHCP and HotSpot host observations are not cryptographic proof against a local MAC spoof. The relay/API attestation proves only a recent observation from the configured router.
- A 5-minute context token is a bearer credential held in sessionStorage. It is hash-only in Mongo, excluded from URLs, and site purchases perform fresh relay checks. XSS or a compromised browser session could expose it; the token alone cannot set an arbitrary site/router.
- Existing shared-token compromise would also compromise attestation HMAC. Rotating the existing relay token invalidates old signatures. A future asymmetric signing design would reduce shared signing authority but requires new secret lifecycle approval.
- An untrusted browser can still submit arbitrary client hints to consume relay/database work. Add rate limiting/abuse controls in a separately reviewed change if public exposure warrants it.
- A success response means the relay observed the client and the backend verified context. It does not mean payment settled, RADIUS accepted login, or Internet access is working.

## 11. Feature status and live verification

**Implemented and tested with mocks:** FastAPI relay client contract; HMAC verification; issuer/audience/time/identity/evidence validation; atomic replay protection; short-lived context storage; site-aware package selection; purchase re-attestation/site checks; two captive frontends; root route/test alignment.

**Requires external relay changes:** `POST /api/v1/router/attest`, relay-side router/site allowlist, per-router selection, DHCP plus HotSpot host observation, matching HMAC signature, and relay tests.

**Requires live verification:** confirm relay response and signature with the deployed relay; prove correct router/site across Nyaururu and Nakuru (including overlapping LAN IPs); verify current phone identification, site packages, purchase-to-voucher site/router propagation, and fail-closed behavior on relay loss; then complete a separately approved customer RouterOS/RADIUS/Internet test. None was performed here. Therefore Phase 4 is **not end-to-end complete** and the ISP service is not claimed operational.

## 12. Rollback considerations

The new relay route is additive; until the external server supports it, site-specific catalog access/purchase stays fail-closed and global catalog fallback remains. Removing the route/context code returns the public catalog to global-only behavior. New Mongo collections/indexes are additive; expired rows are TTL-cleaned and no existing data is modified. The root redirect change aligns code with the documented RouterOS entry point; `/index.html` remains directly accessible if a supervised routing rollback is needed. No production relay/VPS/Render/Mongo/router/FreeRADIUS/payment configuration changed.
