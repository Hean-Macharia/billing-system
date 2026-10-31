# DEVZEN CREATIONS ISP Repair Status

**Date:** 2026-10-31  
**Scope:** Local source audit and isolated verification only. No production database, router, relay, payment provider, Render setting, or service was changed.

## Executive summary

The repository already contains the existing FastAPI, MongoDB, HotSpot, admin, customer portal, relay client, RADIUS, and M-Pesa architecture. This work did not replace it. Two local reliability improvements were made: DHCP device lookup now scans configured routers with bounded concurrency (maximum four simultaneous RouterOS lookups), and the HotSpot API wrapper now distinguishes HTTP authorization, validation, throttling, and server errors from network and timeout failures.

The user-observed site error is confirmed by the source as a backend configuration validation failure. It means at least one non-disabled router candidate did not resolve to a valid active site through its router/NAS mapping. The exact production router and site records cannot be identified from this checkout because no authorized production MongoDB connection or data export is available. The supplied “cannot reach API” text is not sufficient to prove a network failure: the previous read-only production page inspection found an older deployed frontend that collapsed request timeouts into that generic message. Current local code reports timeouts and HTTP errors separately, but has not been deployed.

The system is **not production-ready** based on available evidence. The code and mock tests cannot establish production site records, deployed relay support, a real MikroTik observation, M-Pesa settlement, RADIUS acceptance, or Internet access.

## Repository and deployed entry points

The repository is the canonical local checkout at `C:\Users\ADMIN\Documents\isp-billing`, on `main` tracking `origin/main`. Existing user changes were present before this work and retained. The working tree is not clean; no reset, commit, or push was performed.

The existing Phase A audit and endpoint inventory identify FastAPI-mounted customer/staff surfaces:

- `/hotspot/` → `hotspot/` (documented captive portal)
- `/admin/` → `admin/`
- `/portal/` → `portal/`
- `/` redirects to `/hotspot/`
- Root HTML/`js/` also contains a secondary captive checkout flow; it remains intact.

`frontend/`, `admin/assets/`, and `portal/assets/` include preview/legacy implementations and were not removed. Refer to `docs/frontend-rebuild-audit.md` and `docs/frontend-endpoint-inventory.md` for the existing route inventory and duplicate-tree details.

## Error 1 — router is not attached to an active site

### Confirmed source and behavior

`app/services/hotspot_attestation_service.py`, `HotspotAttestationService._candidate_routers()`, selects router records whose status is not `disabled`. It determines the site from `routers.site_id`, or from the attached `nas_clients.site_id` when the router has a `nas_client_id`. It rejects conflicting router/NAS site IDs, absent site mapping, missing/inactive NAS, malformed site IDs, missing site documents, or site documents whose status is not active.

The exact user-facing error is raised when the selected site ID does not resolve to an active document in `sites`. This is an application response after the portal reached FastAPI; it is not evidence of an API network failure.

Relevant collections/fields:

- `routers`: `_id`, `status`, `site_id`, `nas_client_id`
- `nas_clients`: `_id`, `status`, `site_id`, `ip_address`, `nas_identifier`
- `sites`: `_id`, `name`, `status`

RADIUS NAS resolution separately uses `app/services/nas_identity_service.py` and cross-checks router/NAS site mappings. The actual Nyaururu/Nakuru production records and whether their references are valid remain **unverified**. No IDs or records were fabricated.

### Required production diagnosis

An authorized read-only database operator must inspect all enabled/non-disabled router records, their attached NAS records, and the referenced site documents. For each router, confirm that the site ID is a valid MongoDB ObjectId, resolves to one active site, and agrees with the NAS site when both are set. Also check duplicate/ambiguous NAS identity mappings. The exact failing record must be established before any update. No production mutation is included here.

## Error 2 — “Cannot reach the billing API”

### Confirmed source and likely cause

`hotspot/js/app.js` calls `POST /api/v1/hotspot/devices/lookup` when opening checkout and `POST /api/v1/hotspot/devices/attest` for trusted context. The lookup body uses `ip_address` and `mac_address`; attestation uses the same fields. Both calls are same-origin by default (the frontend derives the current origin), unless an operator has overridden the API base in browser local storage.

`app/routes/hotspot.py` implements both routes. The lookup scans configured routers through `RouterService.get_dhcp_leases()`. In relay mode, `RouterService._resolve_client()` checks relay health before its DHCP request, so a slow scan over multiple routers can take multiple serial relay roundtrips. The previous deployed portal inspection showed an older frontend with a 15-second timeout and a catch path that presented timeout/network failures as “Cannot reach the billing API.” This makes a client timeout from a slow router/relay scan a plausible explanation; without the request’s network trace or Render logs for that timestamp, it is not a confirmed production root cause.

The same-origin request does not require CORS. A previous read-only OPTIONS probe returned a CORS denial for a preflight request, but that does not explain a same-origin JSON request. If `hotspot_api_base` was set to a different origin in the affected browser, CORS becomes a possible separate cause. No production request body or payment request was sent during this repair.

### Local corrections

- Router DHCP scans now execute with a semaphore bounded to four concurrent router lookups. The route still fails closed if any configured router cannot be checked, rejects ambiguous matches, and never returns a partial scan as verified.
- `hotspot/js/api-request.js` now classifies HTTP 401/403, 404, 422, 429, and 5xx responses, preserving a backend message where present. These responses are no longer confused with network failures. Abort timeouts retain their dedicated timeout error and ordinary fetch failures retain the network error.
- The locally modified portal already supplies a 30-second timeout for DHCP lookup and displays the timeout reason. The server-side bounded concurrency reduces avoidable serial latency; the timeout was not increased further.

These local changes are not proof that Render serves them. Earlier read-only inspection found the deployed `/hotspot/js/app.js` did not yet include the local request helper and still used the older generic timeout handling.

## Device verification and purchase security

The trusted flow in source is:

1. `hotspot/js/app.js` reads RouterOS URL hints (`ip`/aliases and `mac`/aliases); these are untrusted hints.
2. It posts them to `POST /api/v1/hotspot/devices/attest`.
3. `HotspotAttestationService` validates router and site records, creates a fresh nonce record per candidate, calls `RouterRelayClient.attest_hotspot_client()`, verifies the HMAC signature, issuer/audience, timestamps, router/site/client binding, evidence, and consumes the nonce atomically.
4. A random opaque five-minute context is stored server-side and returned to the browser.
5. Site-specific purchase requires `X-Hotspot-Context`; purchase calls `attest_purchase_device()` and performs fresh relay observation before starting the STK flow.
6. Payment callback processing queries Daraja’s status endpoint, applies idempotency/settlement claims, and only then issues a HotSpot voucher through `VoucherService`.

The separate `POST /api/v1/hotspot/devices/lookup` is a DHCP lookup, not trusted attestation. It must not be described as proof of router identity. For site-specific purchase, server-side trusted context and purchase-time re-attestation remain required. Global-plan compatibility may use the legacy DHCP lookup when no trusted context is present, as currently implemented.

The FastAPI source contains an attestation client for `POST /api/v1/router/attest`. The copied `phase-j-relay-source/server.py` contains an additive handler and the copied `routeros.py` contains the observation adapter, but these files are not evidence that the production VPS is running that implementation. The copy is configured for one explicit router/site mapping and cannot establish multi-site Nyaururu/Nakuru mapping without verified production records. The production relay deployment state remains **unverified**; do not mark relay attestation operational.

The signed login flow preserves RouterOS HTTP-CHAP helpers and tests for octal escapes and double-encoded `link-orig`. The RouterOS-served `hotspot/login.html` template is not present in the local checkout, so the device-side template and live RouterOS substitution remain unverified.

## Payments and activation

Source inspection found M-Pesa callback handling in `app/services/mpesa_service.py` queries provider status before applying callback settlement, guards duplicate callbacks, claims settlement atomically, and issues the HotSpot purchase voucher only after a verified successful result. No payment code was changed. Mock/unit tests pass, but no Daraja credentials, payment request, live callback, MikroTik authentication, or Internet-access test was performed.

## Files changed in this work

- `app/routes/hotspot.py` — bounded concurrent DHCP scan across routers.
- `tests/test_hotspot_device_verification.py` — verifies concurrency is >1 and ≤4 while preserving not-found semantics.
- `hotspot/js/api-request.js` — explicit HTTP error classification; this file was already an untracked user change before this work.
- `tests/hotspot-api-request.test.js` — covers 403/422/429/500 and the existing timeout/network behavior; this file was already an untracked user change before this work.

Other already-existing working-tree changes in `hotspot/index.html`, `hotspot/js/app.js`, and `docs/hotspot-device-verification-errors.md` were preserved and not rewritten in this task.

## Verification performed

Commands and exact outcomes:

- `python -m pytest -q` — **179 passed, 27 skipped**, 5 warnings, exit 0.
- Targeted HotSpot/security regression command (`tests/test_hotspot_device_verification.py`, `test_hotspot_attestation.py`, `test_router_relay_attestation_client.py`, `test_hotspot_site_package_selection.py`, `test_hotspot_trial.py`) — **52 passed**, 1 deprecation warning.
- `node --test` over all `tests/*.test.js` — **15 passed, 0 failed, 0 skipped**.
- `node --check` over repository JavaScript files — **95 files checked**, no syntax errors.
- `python -m compileall -q app` — passed.
- `git diff --check` — passed; Git emitted only line-ending conversion warnings for two edited Python files.

Skipped Python tests were reported as skipped, not counted as passing. No live integration tests were run.

## Component status

| Component | Status | Evidence / remaining requirement |
|---|---|---|
| FastAPI HotSpot contracts | IMPLEMENTED AND TESTED locally | Full suite and focused tests pass. |
| Router lookup latency/error handling | IMPLEMENTED AND TESTED locally | Bounded concurrency and frontend error classification covered by tests; not deployed. |
| Production router/site records | BLOCKED | Requires authorized read-only inspection of production `routers`, `nas_clients`, `sites`. |
| HMAC/nonce/context verifier | IMPLEMENTED AND TESTED locally | Existing source and tests; no live relay signature received. |
| VPS attestation endpoint | IMPLEMENTED IN LOCAL COPY; DEPLOYMENT UNVERIFIED | Production VPS source/runtime was not inspected or changed in this work. |
| Multi-site relay routing | BLOCKED | Verified Nyaururu/Nakuru router IDs and approved mappings are absent. No mapping was invented. |
| Deployed frontend error fix | IMPLEMENTED LOCALLY; NOT DEPLOYED | Prior production response served old JS. Requires approved Render deployment. |
| M-Pesa settlement/voucher issuance | IMPLEMENTED AND MOCK-TESTED | Full test suite passes; no real payment/callback performed. |
| RouterOS login template/HTTP-CHAP | PARTIALLY VERIFIED | Parser/CHAP tests pass; actual router template and live redirect parameters unavailable. |
| RADIUS/MikroTik Internet access | NOT LIVE-VERIFIED | Requires controlled test device and router after staging/deployment. |

## Remaining work and safe sequence

1. **Database configuration diagnosis:** authorized operator performs read-only inspection of `sites`, `routers`, and `nas_clients`; return only sanitized IDs, names, status, and reference-consistency results. Then prepare a specific change proposal if a relationship is confirmed invalid.
2. **Relay deployment verification:** inspect the running VPS relay version and its configured mapping without reading secrets. Confirm whether `/api/v1/router/attest` is present; if not, stage the local additive change and run cross-component tests before any restart/deploy request.
3. **Production artifact verification:** deploy the local frontend/backend change only after separate approval; verify deployed assets and use Render logs to identify whether any remaining request failures are 4xx, 5xx, timeout, or transport-level failures.
4. **Controlled live test:** with a test device and authorized router, verify DHCP and HotSpot observations, HMAC acceptance/rejection, replay rejection, site catalog, payment in a provider-approved sandbox, voucher issuance, RADIUS acceptance, and Internet access. No customer payments or live customer access changes are part of this work.
5. **Multi-site readiness:** obtain verified site/router records for both locations and implement/test the relay’s approved registry for each actual router. Current single-router configuration must not be extrapolated to Nakuru.

## Rollback

No production changes occurred. Local rollback is limited to reverting the bounded scan in `app/routes/hotspot.py`, its added test, and the error classification changes in `hotspot/js/api-request.js`/its tests. Because the latter two files were pre-existing untracked user work, preserve their prior contents when rolling back only this task’s delta. Do not delete them. If later deployed, restore the prior application artifact through the normal approved deployment procedure; do not alter the relay, database, RADIUS, VPN, or routers as part of rollback.
