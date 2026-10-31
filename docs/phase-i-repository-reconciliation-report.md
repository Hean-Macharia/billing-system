# Phase I — Repository Reconciliation and Security Recovery

**Date:** 2026-10-31

**Scope:** Local repository inspection and isolated tests. No production service, database, payment provider, relay, VPS, FreeRADIUS host, or MikroTik router was contacted or changed.

## 1. Executive summary

The earlier “missing implementation” finding came from inspecting the extracted workspace copy at `Codex/2026-10-29/i-wn/work/billing-system/billing-system-main`, not the original Git checkout. The original checkout is available at `C:/Users/ADMIN/Documents/isp-billing` and contains the Phase A audit/inventory, Phase 3–5 reports, FastAPI attestation verifier, relay client contract, tests, and captive-portal integration.

The FastAPI-side attestation architecture is implemented in this working tree and its isolated tests pass. The external VPS relay endpoint `POST /api/v1/router/attest` is still not implemented or verifiable from this repository. Therefore site-specific HotSpot access remains dependent on that external relay work and has not been proven end-to-end.

During verification, JavaScript syntax checking found a duplicate `responsiveTable` export in `admin/js/ui.js`. I removed only the duplicate declaration; all other pre-existing changes were preserved.

## 2. Repository identity and Git state

- Original project checkout: `C:/Users/ADMIN/Documents/isp-billing`.
- It is a Git repository on branch `main`, tracking `origin/main` at commit `a837e96` (`updating the changess`). The configured remote is `origin` for the project GitHub repository.
- The working tree already contained many modified and untracked files before this reconciliation, including frontend work, backend identity changes, Phase A/III/IV/V reports, and tests. No reset, checkout, stage, commit, or push was performed.
- The Phase A audit and endpoint inventory exist in this checkout, along with the Phase 1/2, Phase 3, Phase 4, and Phase 5 reports.
- Attestation service/tests and the phase reports are untracked in the current working tree and are not present in the available branch history by those paths. Preserve them before any cleanup or branch switching; do not assume they are committed or recoverable from `origin/main`.
- The earlier extracted copy and `outputs/billing-system-rebuilt` are separate snapshots derived from the supplied ZIP and diverge from the original checkout. The extracted copy does not contain all subsequent repository work. It should not be treated as the canonical source for Phase I.
- Secret values were not read or printed. In particular, the checkout's `.env` file was not inspected.

## 3. Missing and recovered files

The actual Git checkout contains:

- `docs/frontend-rebuild-audit.md`
- `docs/frontend-endpoint-inventory.md`
- `docs/phase-3-router-site-identity-report.md`
- `docs/phase-4-trusted-relay-attestation-report.md`
- `docs/phase-5-relay-attestation-report.md`
- `app/services/hotspot_attestation_service.py`
- `app/services/nas_identity_service.py`
- `tests/test_hotspot_attestation.py`
- `tests/test_router_relay_attestation_client.py`
- `tests/test_hotspot_site_package_selection.py`
- `tests/test_nas_identity.py`
- `tests/test_radius_site_authorization.py`
- `tests/test_radius_site_accounting.py`
- `tests/test_mikrotik_dhcp_parser.py`

The VPS relay server source is not in this checkout or the supplied ZIP. The checked-in `RouterRelayClient` has an additive `attest_hotspot_client()` call to `/api/v1/router/attest`, but its own docstring correctly states that the external relay must implement the contract.

## 4. Security architecture status

| Area | Source finding | Status |
| --- | --- | --- |
| NAS identity | `nas_identity_service.py` resolves NAS IP and NAS-Identifier independently, requires them to agree when both are supplied, rejects duplicate/unknown/disabled mappings, maps to exactly one router, checks router/NAS site agreement, and requires an active site. | Implemented; mocked tests pass. |
| Router/site mapping | Attestation candidates come from server-side configured router and NAS/site records. Browser router/site parameters do not select the authoritative router. Missing or conflicting mappings fail closed. | Implemented in FastAPI; requires relay support for current observation. |
| Relay authentication | FastAPI sends the existing relay bearer token through `RouterRelayClient`; missing/failed relay configuration is an error. The relay server middleware cannot be inspected because its source is absent. | Client implemented; relay-side auth unverified. |
| HMAC | FastAPI derives the signing key using HMAC-SHA256 over `devzen/relay-attestation/v1`, canonicalizes sorted compact ASCII JSON, and verifies a lowercase hex signature with constant-time comparison. | Implemented and covered by tests. |
| Attestation claims | FastAPI validates issuer, audience, router/site, IP/MAC, nonce, issue/expiry times, and structured observation evidence. It requires bound DHCP evidence plus a matching HotSpot host observation no older than 15 seconds. | Implemented and covered by mocked tests; external relay must produce these observations and signature. |
| Replay and context lifetime | Nonces are inserted as pending and atomically consumed once; consumed/expired replay is rejected. Opaque context tokens are stored by hash and expire after five minutes. Current router/site active mapping is rechecked when retrieving context. | Implemented and covered by tests. |
| Site-aware package access | `GET /api/v1/hotspot/plans/public` ignores arbitrary `site_id`; valid `X-Hotspot-Context` enables that site's and global plans. Without a valid context it uses the global-only compatibility path. | Implemented and covered by tests. |
| Purchase attribution | Public purchase requires trusted context for a site-specific plan, re-attests the current device, checks router/site and client identity, and snapshots verified router/site onto the pending purchase before calling the existing M-Pesa flow. Global-plan compatibility remains. | Implemented and covered by mocked tests; no payment request was made. |
| Voucher authorization | RADIUS resolves NAS identity before allowing restricted vouchers; restricted voucher use fails closed on unknown/ambiguous NAS or wrong site. Global legacy vouchers remain compatible. Voucher device binding and expiry/revocation checks remain. | Implemented and covered by tests. |
| Accounting | NAS identity is resolved for session/accounting identity; Start/Interim/Stop preserve the session's router/site association, and duplicate starts do not replace original identity. | Implemented and covered by tests. |
| Relay/router unavailable | FastAPI fails closed for trusted site-specific access and purchase. The global compatibility path may still use DHCP lease lookup; it does not establish trusted site identity. | Correctly limited; end-to-end site access blocked until relay exists. |

These are source/test findings only. DHCP and HotSpot tables are observations, not cryptographic proof against a capable local MAC-spoofing attacker.

## 5. Frontend compatibility

- Mounted HotSpot `hotspot/js/app.js` and root captive `js/portal.js` call `POST /api/v1/hotspot/devices/attest` with RouterOS IP/MAC hints. The browser receives only an opaque context token.
- Site catalogs and purchases pass the token as `X-Hotspot-Context`; the server ignores browser-supplied site IDs and performs purchase-time verification.
- The old `/devices/lookup` DHCP endpoint remains in source for compatibility/admin/diagnostic use. It is not substituted for trusted attestation in the mounted HotSpot purchase flow.
- Payment UI polls `/api/v1/hotspot/purchase/status/{checkout_request_id}` and only displays a voucher after the backend reports successful status and a voucher code. STK initiation alone is not treated as settlement.
- Voucher credentials are returned by the backend. Browser code does not generate vouchers.
- RouterOS HTTP-CHAP parsing and login submission remain in place, including octal-escaped CHAP challenge parsing; the frontend unit tests cover this parser/response behavior.
- Frontend compatibility is source- and mock-tested only. No deployed Render page or live MikroTik login was exercised.

## 6. Changes made in this reconciliation

- `admin/js/ui.js`: removed one duplicate `responsiveTable` function export that prevented the browser module from parsing. Retained the existing implementation.
- Added this report.

All other modified/untracked files shown by the initial `git status` were already present before this reconciliation and were left unchanged. No source was copied from the extracted ZIP over the original checkout.

## 7. Test results

Executed in `C:/Users/ADMIN/Documents/isp-billing`:

1. Full Python suite, `python -m pytest -q`: **149 passed, 27 skipped, 0 failed**, 5 dependency deprecation warnings.
2. Focused security/regression suite, including attestation, relay-client contract, site package selection, device lookup, purchase/voucher, trial, DHCP parser, NAS mapping, voucher site authorization, accounting, RADIUS payload, M-Pesa idempotency/callback, and health tests: **137 passed, 0 skipped, 0 failed**, 2 deprecation warnings.
3. Frontend/API and static/HotSpot CHAP suite, `node --test tests/shared-api.test.mjs tests/frontend-static-paths.test.mjs tests/hotspot-portal.test.js`: **14 passed, 0 skipped, 0 failed**.
4. JavaScript syntax, `node --check` over `admin/js`, `portal/js`, `hotspot/js`, and root `js`: initially found the duplicate export in `admin/js/ui.js`; after its removal, **49 files passed**.
5. `python -m compileall -q app tests`: passed.
6. `git diff --check`: passed. Git emitted LF-to-CRLF working-copy notices only.
7. No tests contacted Render, production MongoDB, a router, the VPS, FreeRADIUS, or M-Pesa. The 27 skipped tests remain skipped and are not counted as passes.

## 8. Outstanding risks and recommended next phase

1. **Phase 5 relay implementation remains the critical blocker.** Obtain the relay source or approved read-only inspection access, then add the endpoint in the existing relay application with its current authentication and router-management patterns. Do not guess its framework or alter the systemd/VPN/firewall setup.
2. Implement allowlist-backed router/site selection and current same-router DHCP plus HotSpot host observation in the relay; sign the exact Phase 4 payload and add compatibility tests against the FastAPI verifier.
3. Until that is complete, do not describe site-specific captive packages or the customer Internet path as operational. The global-package/DHCP compatibility behavior is not trusted router attestation.
4. Protect the current dirty Git worktree. The new FastAPI service, test suite, and reports are untracked; review and stage/commit them only through the project's normal workflow after separate review. This reconciliation did not stage or commit.
5. Continue with staging-only end-to-end verification after the relay is implemented. Live router connectivity, RADIUS authentication/accounting, Render-to-VPS integration, voucher login, and Internet access remain unverified.

## 9. Final classification

# PARTIALLY RECONCILED — SOME COMPONENTS MISSING

The correct Git checkout and Phase A documents are present. FastAPI-side trusted attestation, nonce/context checks, router/site and voucher/accounting logic, frontend token flow, and isolated tests are present and verified locally. The external VPS relay implementation and live integration are unavailable, so end-to-end trusted captive identification is incomplete.
