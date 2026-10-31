# Phase J2–J6 — Relay Attestation Implementation Report

**Classification:** BLOCKED — ROUTER/SITE CONFIGURATION MISSING

**Date:** 2026-10-31
**Scope:** Retrieved relay source inspection, local implementation, mocked tests, and FastAPI cross-component tests only. No VPS connection, router connection, production deployment, payment, or infrastructure change was performed.

## 1. Executive summary

The supplied `phase-j-relay-source/server.py` and `routeros.py` removed the source-unavailable blocker. I read both files completely, preserving credential-related lines from output by redacting their values. Their actual implementation is Python `BaseHTTPRequestHandler` with `ThreadingHTTPServer` and a RouterOS binary API socket adapter. I added an authenticated, additive attestation handler and read-only DHCP/HotSpot observations in that existing application copy, plus isolated tests. A cross-component test passes the relay-generated signature and claim object through the actual FastAPI verifier.

The **code path is implemented and mock/cross-component tested**, but the trusted single-router IDs and site association are not verified. The only RouterOS management target visible in the retrieved adapter is `10.30.0.10:8728` with the existing configured username; the source contains no router ID, site ID, enabled-state registry, or evidence that the router belongs to Nyaururu or Nakuru. To avoid inventing those values, the new handler requires four explicit `relay.env` settings before it can sign anything. They have not been set or checked against actual billing records.

Therefore it is not ready for staging integration or production. Multi-site mapping remains blocked. No real router observation or deployed service behavior is claimed.

## 2. Existing relay architecture discovered from retrieved files

### `server.py`

- Python standard-library `BaseHTTPRequestHandler` and `ThreadingHTTPServer`.
- Binds to `127.0.0.1:8765`; existing routes are `GET /health` and `POST /api/v1/router/relay`.
- Reads the bearer token from the existing `~/.config/isp-relay/relay.token` path, rejects a token shorter than 32 characters, and compares bearer values with `hmac.compare_digest`.
- Applies a per-client-IP limit of 60 POST requests per minute.
- Requires JSON content type, enforces a 16,384-byte request-body maximum, parses an object, and only permits named RouterOS actions.
- Reads the existing RouterOS password from `relay.env` and does not log authorization headers, request bodies, credentials, or tracebacks.
- Existing relay responses use `{success, data}`; the new attestation route returns the root `{attestation, signature}` object expected by FastAPI.

### `routeros.py`

- Implements the RouterOS binary API directly over a Python socket with an eight-second existing default timeout and serializes commands using a lock.
- The inspected adapter fixes the router target at `10.30.0.10:8728` and uses the existing configured username. The password is read from the relay process environment.
- Existing operations are selected through `run_action`; HTTP callers cannot submit arbitrary RouterOS commands. Existing read actions include system, interfaces, PPPoE, HotSpot active/users, DHCP leases, and queues. Mutating actions currently raise `NotImplementedError`.
- No existing `/ip/hotspot/host/print` action existed. It is now called only by the new internal read-only observation helper.

The user-provided systemd startup command, service state, and VPS/network details were not independently verified from a unit file or VPS session. No `isp-relay.service` file accompanied the two retrieved source files.

The prompt listed `test_router_api.py` among the VPS files, but it was not present in the copied directory. Thus the relay's original test suite could not be run; the added tests cover the copied server/adapter and mocked existing endpoint behavior.

## 3. Implementation changes

Files in the copied relay source tree:

- `phase-j-relay-source/server.py`
- `phase-j-relay-source/routeros.py`
- `phase-j-relay-source/tests/test_attestation.py`

### Endpoint and preservation

- Added `POST /api/v1/router/attest` as an additive route in the existing `RelayHandler.do_POST` path.
- Existing bearer-token authentication, IP rate limit, content-type check, body-size validation, JSON parsing, safe responses, health handler, and existing router-action dispatch are preserved.
- Added a bounded attestation semaphore (four concurrent observations; bounded wait). Existing management actions do not use it or change behavior.
- No browser-supplied management host, port, username, password, RouterOS command, or arbitrary extra request field is accepted.

### Single-router allowlist and missing mapping

The supplied `routeros.py` has one fixed target (`10.30.0.10:8728`), so the implementation retains it and does not introduce a second target. The handler compares the request IDs with this server-side configuration read from the existing relay environment file:

- `ATTESTATION_ROUTER_ID` — configured Mongo router ObjectId as 24 hex characters.
- `ATTESTATION_SITE_ID` — configured site ObjectId as 24 hex characters.
- `ATTESTATION_ROUTER_ENABLED=true` — explicit enable switch.
- `ATTESTATION_SITE_ACTIVE=true` — explicit active-site switch.

These settings are a code-level configuration contract only. They were **not added to production `relay.env`**, because the correct IDs/statuses are unavailable. Missing/invalid settings fail closed. Router/site request mismatches return forbidden. This is a single-router mapping, not multi-site support. Before staging, operators must establish that the configured IDs refer to the actual router/site records and that the management IP remains approved.

### DHCP and HotSpot observations

`observe_hotspot_client()` opens the existing fixed RouterOS target and performs only:

- `/ip/dhcp-server/lease/print`
- `/ip/hotspot/host/print`

It normalizes and validates private client IP and MAC, rejects duplicate/conflicting observations, requires DHCP `status=bound`, and requires matching IP+MAC on both tables from that same RouterOS connection. A reachable router with no matching device returns a negative observation. Router API/query failures and inconsistent observations raise errors and are not signed as a successful negative result. Router resources close in `finally`.

The adapter has no explicit RouterOS record timestamp field or cache. Both tables are queried directly and `observation_age_seconds` is issued as zero at the time the completed live reads are signed. This assumption must be checked against real RouterOS output in staging. The attestation query uses a three-second RouterOS API socket timeout; FastAPI's relay client timeout and actual network latency still require staging validation.

## 4. HMAC and FastAPI compatibility

The relay implementation follows the existing FastAPI helper:

- Key: `HMAC-SHA256(ROUTER_RELAY_TOKEN, b"devzen/relay-attestation/v1")`.
- Canonical payload: sorted keys, compact separators, `ensure_ascii=True`, UTF-8.
- Signature: HMAC-SHA256 over the complete attestation object, lowercase hexadecimal.
- Claims include exact issuer/audience, configured router/site IDs, client IP/MAC, server issue/expiry times, original nonce, observation bool, and evidence object.
- Attestation lifetime is 45 seconds, below FastAPI's 60-second maximum. Request age is checked against 30 seconds and five seconds future tolerance. Evidence age must be 0–15 seconds.
- Positive observations must include bound DHCP and matching HotSpot evidence. A negative observation is signed only after both RouterOS read queries complete successfully.
- The current FastAPI request model requires a client IP even though an earlier illustrative contract allowed null. The relay enforces the actual FastAPI schema and never returns null IP in signed output.

The cross-component test imports `HotspotAttestationService` and `verify_attestation_signature` from the canonical billing app, verifies a relay-generated positive response through `_verify_relay_reply`, checks router/site/device/nonce binding and nonce consumption, and verifies that a modified signed claim fails. No FastAPI security checks were weakened.

## 5. Automated tests and exact results

Executed from `C:/Users/ADMIN/Documents/isp-billing`:

1. `python -m pytest -q phase-j-relay-source/tests/test_attestation.py` — **27 passed, 0 failed, 0 skipped**, 1 third-party deprecation warning.
2. `python -m pytest -q phase-j-relay-source/tests/test_attestation.py tests/test_hotspot_attestation.py tests/test_router_relay_attestation_client.py tests/test_hotspot_site_package_selection.py` — **68 passed, 0 failed, 0 skipped**, 1 third-party deprecation warning.
3. `python -m compileall -q app phase-j-relay-source/tests phase-j-relay-source/server.py phase-j-relay-source/routeros.py` — passed.
4. `git diff --check` for tracked modified files — passed. Note: the new relay source files are untracked, so `git diff --check` does not inspect them; source syntax and tests cover them.

Mock coverage includes bearer missing/malformed/invalid, existing `/health` and `/api/v1/router/relay` response compatibility, positive and signed negative observations, configured router/site allowlisting, inactive/disabled configuration, arbitrary target fields, invalid/expired/future requests, IP/MAC validation, mocked DHCP/HotSpot query commands, unbound/expired/missing leases, absent/mismatched host, duplicate leases, HMAC tampering, and FastAPI cross-verification.

No VPS, RouterOS, Render, MongoDB, M-Pesa, FreeRADIUS, or staging test was run. The mock IDs and test token are local fixtures only; they are not production configuration.

## 6. Remaining risks and missing configuration

1. Actual router/site ObjectIds and active/enable state are not available in the copied files. Confirm the `ATTESTATION_ROUTER_ID` and `ATTESTATION_SITE_ID` values against the canonical billing inventory before configuring staging.
2. `routeros.py` has one fixed `10.30.0.10:8728` target. No Nyaururu/Nakuru mapping is established. Do not map both sites to this one target without proof. Multi-site support remains unimplemented.
3. `ATTESTATION_ROUTER_ENABLED` and `ATTESTATION_SITE_ACTIVE` are static flags in `relay.env`, not dynamic reads from MongoDB. Operational status changes require careful configuration management until a trusted registry mechanism is supplied.
4. The source-level RouterOS response fields/status semantics, including `status=bound`, HotSpot host table behavior, and observation-age interpretation, have only been checked with mocks.
5. The code reads only configured IDs/flags from `relay.env`; this phase did not access the actual file. Existing RouterOS password and relay token handling remain as in the supplied relay.
6. The copied source files are an untracked local directory and have not been merged into the canonical VPS source repository or deployed.

## 7. Staging deployment preparation (not performed)

### Required before staging

1. Confirm the correct single router ObjectId and site ObjectId from the billing system's approved records using a separately authorized, non-secret procedure. Confirm the site is active and that this fixed RouterOS target is its approved router.
2. Add the four attestation mapping/status variables to a **staging-only** relay environment file. Do not put token/password values in source control or this report. Preserve the existing secret store.
3. Check that staging FastAPI uses the same relay token value through its approved secret manager, without displaying it, and uses a compatible relay timeout.
4. Review the complete source diff in the original relay checkout and run its existing test command plus the copied tests.

### Suggested staged rollout

1. Back up the staging relay source and configuration metadata (never include secret contents in the backup report).
2. Install the additive `server.py` / `routeros.py` changes in a staging copy using the existing interpreter and service command; do not alter the production service.
3. Start the staging relay on a non-production localhost port or isolated host; keep it unreachable from the public Internet.
4. Verify `/health`, authenticated existing management actions, invalid token rejection, then mock-to-staging attestation responses.
5. With a controlled test router only after separate authorization, check current DHCP and HotSpot table evidence and FastAPI signature acceptance.
6. Roll back by restoring the saved staging source files and prior staging environment file, then restart only the staging process.

No production deployment, source upload, secret change, service restart, firewall/VPN change, or router change is authorized or performed here. Production rollback would require a separately approved maintenance procedure for the existing `isp-relay.service`.

## 8. Production readiness and classification

The implementation is **not ready for staging or production** until the actual single-router/site IDs are confirmed and configured. Multi-site router identity cannot be implemented safely from current evidence. Production HotSpot authentication, customer connectivity, and Internet access remain unverified.

# BLOCKED — ROUTER/SITE CONFIGURATION MISSING

The endpoint and adapter code are implemented and pass local mocked and cross-component verification, but deployment/use is blocked until the single router/site mapping is verified. Nyaururu/Nakuru multi-site mapping remains explicitly unimplemented.
