# HotSpot and MikroTik Integration Readiness — 2026-10-31

## Scope and status

This change set repairs local HotSpot retry behavior, legacy DHCP lookup diagnostics, router/NAS assignment validation, and administrator visibility of identity/health state. The Phase J relay implementation and FastAPI contract were exercised with mocks and a cross-component verifier test. No Render service, production MongoDB record, VPS, relay endpoint, MikroTik router, FreeRADIUS deployment, or payment provider was accessed or changed for this work.

**Overall classification: IMPLEMENTED BUT NOT DEPLOYED.** The local source and tests are in place. Production HotSpot attestation remains blocked because the production relay is reported to return HTTP 404 for `/api/v1/router/attest`, and the approved relay management target for the Nyaururu database router has not been confirmed. Nakuru has no verified site/router/NAS mapping.

## Confirmed local defects and repairs

### HotSpot retry and context handling

`hotspot/js/app.js` previously allowed repeated calls to the package-loading/verification path. The load operation is now single-flight, uses an `AbortController`, disables the retry button while retrying, ignores stale generations, and does not let a cancelled or outdated request update the current package UI. The current trusted context is cleared on page navigation. The page continues to call `/api/v1/hotspot/devices/attest`; purchase continues to send only the opaque context token and still requires purchase-time backend re-attestation.

`hotspot/js/api-request.js` now accepts caller cancellation signals and distinguishes `REQUEST_ABORTED` from `REQUEST_TIMEOUT`. HTTP responses continue to produce HTTP-specific errors instead of being mislabeled as network failures.

FastAPI assigns or validates a 32-character correlation ID for device attestation, echoes it in `X-Correlation-ID`, passes it through the attestation service and relay client, and assigns one for purchase-time re-attestation. Nonce values and client IP/MAC values are not written to these diagnostics.

### Legacy DHCP lookup conflict accuracy

`app/routes/hotspot.py::_resolve_hotspot_device()` previously described any combination of multiple records as “multiple routers,” including duplicate lease rows on one router. It now distinguishes:

- Records on multiple routers, noting whether those routers span multiple sites.
- Duplicate active lease rows on a single router.
- Conflicting active and expired rows on one router.
- A matching expired/unbound lease when no active match exists.

An unavailable router still causes a fail-closed service error; the code does not silently choose from a partial scan. This endpoint remains a legacy DHCP lookup and is not proof of trusted router identity. The mounted `/hotspot/` checkout does not call it.

### Router and NAS relationship validation

`RouterService` now checks site and linked NAS references when creating a router or changing its site/NAS relationship. It handles BSON ObjectId and historical string references, rejects missing/inactive site or NAS records, and rejects router/NAS site conflicts. `RadiusAdminService` checks a NAS’s selected site and prevents changing it to a site that conflicts with a router already linked to that NAS. These checks do not mutate or repair existing records.

The router administration response now reports site relationship status, NAS relationship status, cached health freshness, and an attestation configuration eligibility indicator. Cached health becomes `stale` after five minutes and `unknown` when no usable check time exists; this is an administrative diagnostic only. It does not establish live router reachability and does not replace the relay’s fresh observation.

## Existing attestation and relay boundary

FastAPI retains the signed-attestation contract, HMAC verification, audience/issuer checks, 60-second nonce record lifetime, atomic nonce consumption, replay rejection, short-lived opaque context, site restrictions, and purchase-time re-attestation. A failed atomic consume now emits a safe category (`replayed`, `expired_or_unknown`, or `not_pending`) without logging the nonce; the existing conflict response remains compatible.

The local `phase-j-relay-source/` implementation adds `POST /api/v1/router/attest` while preserving `/health` and `/api/v1/router/relay`. It uses the bearer token, strict request fields, router/site allowlisting, read-only DHCP lease and HotSpot host queries on one router, fresh evidence, and the exact domain-derived HMAC/canonical JSON contract. Its cross-component test signs with the relay code and validates/consumes using the actual FastAPI verifier.

The local relay source is not proof of the running VPS code. The production endpoint’s HTTP 404 is existing operator-reported evidence; this task did not re-request it or contact the VPS. The source bundle is prepared at [devzen-relay-staging-20261031.zip](</C:/Users/ADMIN/Documents/Codex/2026-10-29/i-wn/outputs/devzen-relay-staging-20261031.zip>). It contains only source, the non-deployable example registry, validator and README; it excludes relay environment files, tokens and credentials.

## Production configuration blockers

Known, operator-supplied Nyaururu records remain unchanged:

- Active site ID `6aa1c1318c57af83b37a0e49`.
- Online RB951 router ID `6ab587aa145e0b7ff9adcf49`, with DB management address `192.168.88.1:8728` and no NAS association.
- The NAS record is active but has no site ID or NAS-Identifier and is not linked from the router.
- Offline CCR2004 has dangling site reference `SITE-001`; it is not an attestation candidate.
- No verified Nakuru site/router/NAS configuration is available.

The relay allowlist must not be enabled until an operator confirms which management target the VPS can reach for this exact RB951 record over the existing network path. The supplied VPN peer `10.30.0.10` is not automatically interchangeable with the DB management address. Router API user/port and the correct staging credentials must also be confirmed by the authorized operator. No relay mapping or secrets were written into production or a deployment file. The example template remains placeholder-only.

## Files changed

- `admin/js/network.js`
- `app/integrations/mikrotik/relay_client.py`
- `app/routes/hotspot.py`
- `app/routes/routers.py`
- `app/services/hotspot_attestation_service.py`
- `app/services/radius_admin_service.py`
- `app/services/router_service.py`
- `hotspot/js/api-request.js`
- `hotspot/js/app.js`
- `tests/hotspot-api-request.test.js`
- `tests/hotspot-portal.test.js`
- `tests/test_hotspot_attestation.py`
- `tests/test_hotspot_device_verification.py`
- `tests/test_router_admin_diagnostics.py` (new)
- `tests/test_router_relationship_validation.py` (new)

These files were already modified or untracked before the current repair and remain part of the retained change set; they were not reverted: `phase-j-relay-source/server.py`, `phase-j-relay-source/routeros.py`, `phase-j-relay-source/tests/test_attestation.py`, `tests/test_router_relay_attestation_client.py`, `docs/multi-router-attestation-production-readiness.md`, `docs/relay-attestation-production-integration.md`, `phase-j-relay-source/README.md`, `phase-j-relay-source/attestation-routers.example.json`, `phase-j-relay-source/package-staging.ps1`, `phase-j-relay-source/scripts/`, and `phase-j-relay-source/tests/test_validate_attestation_config.py`.

## Tests and checks executed

| Command | Result |
| --- | --- |
| Focused HotSpot/attestation/device/site/relay tests | 69 passed, 0 failed, 1 warning |
| Relay attestation + config validator + FastAPI attestation/client/site + relationship/admin diagnostic tests | 118 passed, 0 failed, 1 warning |
| Full suite: `python -m pytest -q` | 220 passed, 27 skipped, 0 failed, 5 warnings |
| Frontend suite: `node --test tests/*.test.js tests/*.test.mjs` | 33 passed, 0 failed, 0 skipped |
| JavaScript syntax: `node --check` on repository frontend `.js` files | Passed |
| Python compile: `python -m compileall -q app phase-j-relay-source` | Passed |
| `git diff --check` | Passed; Git printed line-ending normalization warnings only |
| Relay staging package script | Passed; inspected archive members and confirmed no secrets/config files included |

Warnings were dependency deprecations from `pythonjsonlogger`, mongomock, and Starlette. The 27 skips are existing integration tests requiring external services; they were not counted as passes. All device, relay, RouterOS, RADIUS and payment-provider tests used local fixtures or mocks. No production behavior is inferred from them.

## Payment, voucher, RADIUS and RouterOS status

No payment settlement, voucher issuance, RADIUS policy, RouterOS operation, or payment code was changed in this repair. The full existing Python suite passed with mocks/fixtures, but no live STK request, callback, voucher authorization, RADIUS packet, router operation, or Internet session was performed. RouterOS 6 CHAP regression tests, including the supplied RouterOS-escaped URL case, passed in the frontend suite.

## Production remediation and deployment gates

1. Confirm the relay management target that reaches the RB951 router record and the approved RouterOS API username/port through the existing VPN. Do not infer it from the separate peer address.
2. Confirm/repair the Nyaururu NAS site and router association through the normal authorized admin process. The current code deliberately permits an unlinked NAS for HotSpot attestation but marks that configuration visible; RADIUS identity association remains a separate operational requirement.
3. Supply real Nakuru site/router/NAS records only after their IDs and network details are verified.
4. Build a staging `ATTESTATION_ROUTERS_JSON` from confirmed mappings and router-specific staging credential variable names. Run the validator only on the staging relay environment file.
5. Deploy the source bundle to a separate staging relay. Verify `/health`, existing management action behavior, authenticated positive and negative attestations, HMAC compatibility, and failure handling there.
6. Only after staging succeeds, request separate authorization for production relay backup/deployment and any service restart. The current production relay is reported to lack `/api/v1/router/attest`; the portal cannot complete trusted verification against that endpoint until a compatible relay is deployed.
7. Separately authorize Render deployment of the FastAPI/frontend changes. Then use a controlled test device and payment sandbox to verify package selection, purchase-time re-attestation, callback settlement, single voucher issuance, RADIUS authorization/accounting, and actual internet access.

Rollback for local/staging source: retain the current relay artifact and configuration, deploy the prior version in staging if verification fails, and keep the production relay untouched. Production rollback and restart commands must be written against the actual authorized deployment procedure after its service/reverse-proxy arrangement is confirmed; none were run here.

## Final readiness

- Local code and tests: **FIXED AND TESTED**.
- Relay endpoint in local source: **IMPLEMENTED BUT NOT DEPLOYED**.
- Production relay attestation: **BLOCKED BY MISSING PRODUCTION DEPLOYMENT/VERIFICATION** (reported 404).
- Nyaururu relay target: **BLOCKED BY MISSING CONFIRMATION of the management route/target association**.
- Nakuru: **BLOCKED BY MISSING VERIFIED SITE/ROUTER/NAS CONFIGURATION**.
- Production database repair, Render release, live MikroTik/RADIUS/payment journey: **REQUIRES PRODUCTION APPROVAL**.

The system is not classified production-ready. No production changes were performed.
