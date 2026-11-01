# Relay attestation and production integration status

**Date:** 2026-10-31  
**Repository:** `C:\Users\ADMIN\Documents\isp-billing`  
**Scope:** Local FastAPI/HotSpot/relay-source implementation, mocks, and staging preparation. No production host, database, router, payment provider, or Render service was contacted or changed during this work.

## Executive status

Local implementation and tests are complete for the changes in this report. Production integration is **not complete**: the production observation supplied for this task says the running relay returns `404` for `POST /api/v1/router/attest`, so it does not currently support the FastAPI flow. The local relay source is still a copied source tree and was not deployed. The real Nakuru router/site mapping and per-router credentials have not been provided or verified.

Classification: **IMPLEMENTED BUT NOT DEPLOYED** locally; **BLOCKED BY MISSING PRODUCTION MAPPING AND DEPLOYMENT APPROVAL** for end-to-end operation. This is not a production-readiness claim.

## What the production evidence does and does not establish

Facts supplied by the operator for this task: the existing loopback relay health endpoint returns 200; `/api/v1/router/relay` works for some actions; `/api/v1/router/attest` currently returns 404; and direct read-only RouterOS tests for identity, resource, interface list, DHCP leases, and HotSpot active succeeded over the current L2TP path to the configured peer. These facts were not independently retested here.

The supplied 404 confirms that the active relay route is absent at the time of that observation. The source copy in this checkout does not prove what code is installed under `/home/opc/.config/isp-relay`.

The supplied 502 symptom cannot be tied to one historical failure from available evidence. The previous relay catch-all returned a generic 502 without logging the exception class or operation category, so the prior failure could have been a timeout, socket failure, RouterOS authentication/command failure, malformed observation, missing configuration, or an internal defect. No historic relay journal was accessed. The local handler now emits a safe correlation ID and structured category so a staging failure can be attributed without logging exception text, device IP/MAC, tokens, or credentials.

## Contract comparison

FastAPI sends `POST /api/v1/router/attest` with the exact six fields: `router_id`, `site_id`, `client_ip`, `client_mac`, `nonce`, and `requested_at`, authenticated with the existing bearer token. The copied relay validates that exact shape and resolves `(router_id, site_id)` to one server-side allowlist entry; the request cannot provide a host, port, username, password, or RouterOS command.

The response consumed by FastAPI is exactly `{ "attestation": ..., "signature": ... }`. The complete attestation includes the issuer `devzen-vps-relay`, audience `devzen-billing-api`, router/site IDs, client IP/MAC, issue/expiry times, original nonce, `observed`, and the DHCP/HotSpot evidence fields. It uses the existing derived HMAC key, sorted compact ASCII-escaped UTF-8 JSON, and lowercase HMAC-SHA256 hex signature. Relay lifetime is 45 seconds; FastAPI continues validating signature, claims, challenge, age, evidence, and atomic nonce consumption.

The relay performs read-only `/ip/dhcp-server/lease/print` and `/ip/hotspot/host/print` operations on the same selected RouterOS API connection. Positive evidence requires a unique bound lease and a matching HotSpot host with the same IP/MAC. A reachable router with no current match yields a signed negative result; inability to query either table is an error, never a negative result. Evidence age conservatively covers connection establishment and both table reads, and is rejected above 15 seconds.

## Multi-router selection and the observed 409

FastAPI candidates are now sourced from router records explicitly marked `online`; each candidate independently requires a valid router ID, an active site, and an active linked NAS whose site matches the router site. Invalid records are logged as structured exclusion categories and do not interrupt other candidate evaluation. Trusted-context retrieval repeats online/site/NAS validation. Duplicate IDs remain a fail-closed data-integrity error.

When one candidate receives an explicit relay HTTP 403 because its pair is not configured in the relay allowlist, FastAPI excludes that candidate and continues according to the existing tested policy. Relay authentication errors, router timeouts, connection failures, malformed observations, and other unavailable candidates are **not** ignored: they fail the overall verification because uniqueness cannot be established. More than one valid signed positive observation remains an explicit HTTP 409 ambiguity. The diagnostic log records router/site IDs and match count, never the client IP, MAC, nonce, or voucher.

The code establishes how an attestation 409 is produced: multiple routers each returned a valid signed positive observation for the same challenge. It cannot establish which production router caused the reported event without the current site/router/NAS records and correlation logs. There is also a separate low-trust `POST /api/v1/hotspot/devices/lookup` that can return 409 for matching DHCP leases alone. The captive checkout no longer calls that DHCP-only endpoint as a purchase prerequisite after trusted attestation; the backend still re-attests at purchase time. The lookup endpoint itself remains available for other callers and does not authorize a purchase.

An unavailable candidate still blocks attestation. An unconfigured relay candidate's explicit 403 may be skipped only as described above; a successful signed match is still required. Overlapping private LAN IPs remain supported because each observation is scoped to an exact router/site pair and verified by signed evidence. Multiple positive observations remain rejected.

## Changes implemented

- `app/services/hotspot_attestation_service.py`
  - Online-only candidates, independent router/site/NAS validation, structured exclusion logs, strict context mapping revalidation, and safe ambiguity diagnostics.
  - Relay 403 allowlist rejection is distinguished from 401/auth, 5xx, timeout, and transport failures using `RouterRelayError` status metadata. Non-403 failures continue to fail closed.
- `app/integrations/mikrotik/relay_client.py`
  - Generates and forwards a random correlation ID, retains relay HTTP status and returned correlation ID, and logs transport/status failures with safe metadata only.
- `hotspot/js/app.js`
  - Uses only the trusted opaque context to gate checkout. It no longer issues a duplicate DHCP-only lookup from the purchase sheet, which could return a misleading multiple-lease 409 before the attestation result is used. The backend continues fresh verification.
- `phase-j-relay-source/server.py` and `phase-j-relay-source/routeros.py`
  - Additive attestation handler, explicit multi-router allowlist, exact HMAC response, bounded attestation concurrency, one-router read-only observations, typed RouterOS failure categories, correlation IDs, and safe structured logs.
  - Existing `/health`, `/api/v1/router/relay`, existing management actions, bearer auth, per-client rate limiting, body limit, legacy single-router defaults, and loopback binding remain. Optional staging-only `ISP_RELAY_PORT`, `ISP_RELAY_TOKEN_FILE`, and `ISP_RELAY_ENV_FILE` overrides allow an isolated loopback staging process without changing the production defaults.
- `phase-j-relay-source/attestation-routers.example.json`
  - Non-deployable Nyaururu/Nakuru schema template with explicit placeholders. It contains no real IDs, addresses, or credentials.
- `phase-j-relay-source/scripts/validate_attestation_config.py`
  - Validates a supplied staging env file and credential presence without printing credential values.
- `phase-j-relay-source/package-staging.ps1`
  - Builds a source-only staging zip, refuses to overwrite an existing artifact, and excludes relay tokens, environment files, and router passwords.
- `phase-j-relay-source/README.md`
  - Configuration, test, and staging guidance.
- Regression tests updated/added in `phase-j-relay-source/tests/test_attestation.py`, `phase-j-relay-source/tests/test_validate_attestation_config.py`, `tests/test_router_relay_attestation_client.py`, `tests/test_hotspot_attestation.py`, and `tests/hotspot-portal.test.js`.

No MongoDB records, schemas, indexes, Render configuration, production environment variables, VPN settings, MikroTik settings, RADIUS settings, or M-Pesa settlement behavior were changed.

## Exact production values still required

Before staging the real sites, an authorized read-only operator must confirm for **each** site:

1. The canonical 24-hex `sites._id` and exact active status.
2. The canonical 24-hex router `_id`, explicit online/enabled status, `site_id`, and `nas_client_id`.
3. The linked NAS `_id`, active status, and matching `site_id` (where the router has a NAS association).
4. The router's approved API management address reachable from the VPS over the existing L2TP route, port, username, RouterOS API type, and site assignment.
5. The matching per-router password variable stored only in the approved staging secret file/manager.
6. Existing relay token agreement between staging FastAPI and staging relay, checked without printing either value.
7. Time synchronization on FastAPI/VPS and connectivity from the relay to each approved private RouterOS target.

The supplied current VPN peer `10.30.0.10` is the only router target identified in the task facts. Do not assume it represents Nakuru or any additional router. The template intentionally does not fill it in. No duplicate database records should be created to make the template pass.

## Safe local verification performed

Executed after the implementation:

| Command | Result |
|---|---:|
| `python -m pytest -q` | **212 passed, 27 skipped, 5 warnings** |
| `python -m pytest phase-j-relay-source/tests/test_attestation.py phase-j-relay-source/tests/test_validate_attestation_config.py tests/test_router_relay_attestation_client.py tests/test_hotspot_attestation.py tests/test_hotspot_site_package_selection.py -q` | **101 passed, 0 failed, 0 skipped, 1 warning** |
| `node --test tests/*.test.js tests/*.test.mjs` | **31 passed, 0 failed, 0 skipped** |
| `node --check` for all discovered JS/MJS files | **98 files passed** |
| `python -m compileall -q app phase-j-relay-source` | Passed |
| PowerShell parser for `package-staging.ps1` | Passed |
| Staging bundle build and archive listing | Passed; contents were source, template, validator, README only; generated test archive removed |
| `git diff --check` | Passed; Git emitted LF/CRLF conversion notices only |

The 27 skipped Python tests are existing tests requiring external MongoDB. All relay/router/payment integrations in tests are mocked. No staging, live router, production MongoDB, Render, FreeRADIUS, M-Pesa, customer payment, or Internet access test was run.

## Staging procedure (not executed)

1. Review the relay diff and collect the exact router/site/NAS records through authorized read-only access. Complete the template with only verified values; create a single-line `ATTESTATION_ROUTERS_JSON` entry per actual router, no more than 64. Store each router's password in its generated `MIKROTIK_API_PASSWORD_<UPPERCASE_ROUTER_ID>` variable. Keep the relay token in its existing token file/approved secret store.
2. In a staging copy of `relay.env`, run:

   ```sh
   python3 scripts/validate_attestation_config.py --env-file /secure/staging/path/relay.env
   ```

   The validator reports only IDs for missing credential variables and never prints credential values. Use staging credentials, not production.
3. From the billing repository, run the relay/cross-component tests documented in `phase-j-relay-source/README.md`. Build a source-only archive on Windows:

   ```powershell
   .\phase-j-relay-source\package-staging.ps1 -OutputPath C:\staging\devzen-relay-attestation.zip
   ```

4. Copy the reviewed archive to a separate staging directory on an approved staging host. Do not overwrite `/home/opc/.config/isp-relay` or touch the active service. Launch a distinct staging process bound to loopback and a different port, using staging-only paths:

   ```sh
   ISP_RELAY_PORT=18765 \
   ISP_RELAY_TOKEN_FILE=/secure/staging/path/relay.token \
   ISP_RELAY_ENV_FILE=/secure/staging/path/relay.env \
   python3 server.py
   ```

   The shell command contains only paths; it does not display secrets. The listener is still fixed to `127.0.0.1`. Use an isolated staging FastAPI instance configured with the same staging relay token through its approved secret store.
5. Check staging health, authentication rejection, existing management operation compatibility, an attestation 400/403 validation case, then positive/negative mocked observations and a controlled test router. Inspect logs by correlation ID/category only. A controlled live test device is a separate operational approval.
6. Do not call this end-to-end verified until the valid response is accepted by the staging FastAPI verifier, tampering and replay are rejected, and the controlled device successfully passes MikroTik/RADIUS authentication and Internet checks.

## Production deployment and rollback

No production deployment is included or authorized by this local work. Before production deployment, the owner must approve a maintenance plan covering exact source commit, secret-store references, verified router/site mappings, backup, downtime/health checks, and rollback.

When separately authorized, deploy to a versioned staging artifact first. Back up the existing relay source/config metadata securely without printing or copying secrets into the release artifact. Verify existing `/health` and `/api/v1/router/relay` before enabling the new attestation path. Then deploy with the normal approved process and restart only if the approved deployment method requires it. Keep the existing listener loopback-only and do not alter VPN, firewall, FreeRADIUS, router config, or customer payments.

Rollback: restore the previous known-good relay artifact and environment-file version through the approved service process, verify `/health` and existing management actions, then restore the previous FastAPI/frontend artifact if needed. This procedure requires separate authorization before touching `isp-relay.service` or Render. No service was restarted here.

## Production verification gates

1. Authorized read-only check confirms each live site/router/NAS relationship and no conflicting/duplicate records.
2. Running VPS service is confirmed to use the reviewed relay revision; unauthenticated `POST /api/v1/router/attest` returns 401 rather than 404, without sending any token or causing router queries.
3. Staging registry validates, and each router target is reached over the existing L2TP path with private API access only.
4. Staging positive and negative observations, HMAC verification, altered signature rejection, nonce replay rejection, expiration, and freshness checks all pass against the real FastAPI verifier.
5. Controlled captive portal test confirms correct site packages, purchase-time re-attestation, M-Pesa sandbox settlement, voucher activation, RADIUS accounting, and Internet access. No live payment is needed for this until an explicitly approved operational test.
6. Nyaururu and Nakuru are verified independently. The provided evidence currently establishes only a single VPN peer; Nakuru remains unverified.

Until all gates pass, the customer-facing system is **not production-ready for multi-site attestation**. The user prompt provided in this turn ends mid-requirement after “Site-specific packages appear on”; any requirements after that cutoff were not available for implementation.
