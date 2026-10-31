# Phase 5 — VPS Relay Attestation Inspection and Readiness Report

**Date:** 2026-10-31  
**Result:** **IMPLEMENTATION INCOMPLETE — VPS relay source and read-only VPS access were unavailable.**  
**Scope:** Read-only inspection of the available billing-system repository and isolated billing-side contract tests. No VPS, production relay, systemd service, router, VPN, firewall, FreeRADIUS host, Render service, production database, or payment provider was contacted or changed.

## 1. Executive summary

The available repository contains the FastAPI relay client and Phase 4 FastAPI attestation verifier. It does **not** contain the VPS relay server source, an `isp-relay.service` unit file, or a VPS deployment checkout. No SSH/VPS inspection session or relay source archive was provided. Consequently, the relay's language/framework, startup command, work directory, service account, listening ports, authentication middleware, RouterOS implementation, firewall state, L2TP state, and actual environment-variable configuration cannot be verified here.

I did not create a second relay application or guess a language/framework. That would risk replacing or bypassing the existing production relay and would not meet the requirement to extend it additively. No production or relay code was changed. The Phase 4 FastAPI attestation, relay-client, and site-package tests ran locally: **41 passed, 1 warning**. Those tests validate the billing-side contract only; they do not prove that the external relay implements the endpoint.

**Deployment readiness: Not ready.** The existing relay owner/source and a read-only inspection path are required before a safe relay implementation can begin.

## 2. Initial architecture inspection

### Available source and what it establishes

- `app/integrations/mikrotik/relay_client.py` is the checked-in Python client used by FastAPI. It sends HTTPS JSON requests with the existing `Authorization: Bearer ...` header.
- Existing client operations include `GET /health` and `POST /api/v1/router/relay` for management actions such as system identity/resource/health, interfaces, PPPoE, HotSpot active/users, DHCP leases, and queues.
- The Phase 4 client adds `POST /api/v1/router/attest` through `RouterRelayClient.attest_hotspot_client(request)`. The checked-in method delegates to the generic HTTP request helper and does not implement the server endpoint.
- `app/services/hotspot_attestation_service.py` is the FastAPI-side trust boundary. It selects router/site pairs from the billing database, sends the challenge to the relay, verifies HMAC and claims, consumes a nonce, and returns a short-lived opaque context.
- The repository contains RouterOS client integrations for the billing application. These are not evidence of the code or RouterOS library used by the VPS relay. The checked-in clients do not establish that the relay can read the RouterOS DHCP lease and HotSpot host tables.
- Repository docs describe `ROUTER_RELAY_URL` and `ROUTER_RELAY_TOKEN` by name and describe the intended Render-to-VPS relay architecture. No secret values were inspected or printed.

### Not verifiable from this checkout

No `isp-relay.service`, VPS relay server module, VPS deployment manifest, or relay-specific RouterOS configuration is present in the repository. Without read-only VPS access or the exact deployed source snapshot, the following requested findings remain unknown:

- Actual relay language, framework, entry point, working directory, service user/group, and service dependencies.
- Bound/listening addresses and ports, existing endpoint routes, authentication middleware, RouterOS API library, router registry, and request/response formats.
- Runtime environment-variable names on the VPS (the repository only declares billing-side relay variables), secret-file locations, and logging configuration.
- VPS firewall state, current L2TP interface/peer state, route to the router, and whether RouterOS API access is restricted to the VPN.
- Whether `/ip/dhcp-server/lease` and `/ip/hotspot/host` are already queried by the relay.

The supplied addresses and RouterOS details were treated as reference values only and were not tested against live infrastructure.

## 3. Phase 4 FastAPI contract, verified from source

### Request

The client calls the following endpoint with the existing relay bearer token:

```http
POST /api/v1/router/attest
Authorization: Bearer <ROUTER_RELAY_TOKEN>
Content-Type: application/json
```

The request body assembled by `HotspotAttestationService.observe_device` contains:

```json
{
  "router_id": "configured-router-id",
  "site_id": "configured-site-id",
  "client_ip": "private-client-ip-or-null",
  "client_mac": "AA:BB:CC:DD:EE:FF",
  "nonce": "fresh-server-generated-challenge",
  "requested_at": 0
}
```

Router/site IDs are chosen by FastAPI from configured records, not from browser fields. The relay must treat them as selectors only after validating them against its own server-controlled router/site registry. It must resolve the management address from that registry, never from a request-supplied address.

### Response and signature

The expected response is a JSON object containing `attestation` and `signature`. The signed `attestation` object has required fields:

`issuer`, `audience`, `router_id`, `site_id`, `client_ip`, `client_mac`, `issued_at`, `expires_at`, `nonce`, `observed`, and `evidence`.

The verifier requires issuer `devzen-vps-relay`, audience `devzen-billing-api`, exact router/site/client/MAC/nonce binding, and a valid HMAC. `evidence` must include `dhcp_lease_match`, `dhcp_lease_status`, `hotspot_host_match`, and numeric `observation_age_seconds`. A positive result must prove the same IP and MAC on a bound DHCP lease and the HotSpot host observation, with observation age no greater than 15 seconds. A reachable router with no client observation should return a signed negative result; inability to query the router must return an error so the API fails closed.

Phase 4 does not require a separate top-level observation timestamp. Its freshness contract uses signed `issued_at`/`expires_at` plus signed `evidence.observation_age_seconds`. Adding a new field is unnecessary unless separately versioned and accepted by FastAPI.

The key derivation and canonical signing rules in `app/services/hotspot_attestation_service.py` are:

```text
derived_key = HMAC-SHA256(key=ROUTER_RELAY_TOKEN,
                          message="devzen/relay-attestation/v1")
canonical = JSON(attestation, sorted keys, compact separators, ASCII escaping)
signature = lowercase_hex(HMAC-SHA256(derived_key, UTF8(canonical)))
```

The verifier accepts at most a 60-second attestation lifetime, issue time no more than 5 seconds in the future, issue age no more than 30 seconds, and evidence age no more than 15 seconds. FastAPI consumes the challenge atomically in MongoDB; the relay must echo the nonce unchanged and must not reuse/copy an attestation between requests. The 5-minute browser context lifetime is enforced by FastAPI, not by the relay.

## 4. Compatibility and security assessment

### Confirmed in source

- The client uses the existing relay URL/token configuration names and bearer-header format.
- The attestation path and JSON body are implemented by the client, and the HMAC verification rules are implemented by FastAPI.
- FastAPI fails closed for site-specific catalog/purchase paths when relay verification is missing or invalid. Global-plan compatibility fallback is retained as documented in Phase 4.
- The expected router/site are server-selected. The relay must independently allowlist and validate them before connecting to a router.
- Client IP/MAC hints are bound to the signed attestation; DHCP alone is not treated as proof.

### Not confirmed / risks before relay implementation

- Relay token comparison and middleware behavior cannot be reviewed without its source. It must use constant-time comparison where practicable and avoid logging authorization headers.
- Router allowlisting, enabled/disabled state, site association, management-address resolution, and multi-site support are not present in the available VPS code because that code is absent.
- Router query timeouts, API authentication failure handling, malformed response handling, duplicate observations, stale DHCP leases, and HotSpot host corroboration are not verified.
- A shared HMAC key means compromise of the existing bearer token compromises attestation signing too. Do not create or rotate production keys in this phase.
- Public attestation requests can generate router and database load. Before exposure, review existing rate limits, request concurrency, maximum body size, and safe per-router timeouts in the actual relay and billing service.
- DHCP/HotSpot records are observations, not cryptographic proof against an attacker capable of spoofing a local MAC address.
- Overlapping private address ranges are safe only if each router is independently selected by trusted router ID and separately queried; an IP match must never choose a router/site by itself.

## 5. Implementation and test results

### VPS implementation

No VPS relay code was created or modified because the deployed relay implementation was unavailable for inspection. No implementation language, framework, dependency, endpoint, registry, or systemd behavior was guessed. No test was represented as a VPS relay test.

### Executed local tests

Command:

```text
python -m pytest -q tests/test_hotspot_attestation.py tests/test_router_relay_attestation_client.py tests/test_hotspot_site_package_selection.py
```

Result: **41 passed, 0 failed, 0 skipped, 1 warning** (third-party deprecation). These are billing-side tests using local fixtures/mocks. They do not call the relay, a router, Render, production MongoDB, or M-Pesa.

### Not run

- VPS relay unit/integration tests: relay source unavailable.
- Systemd/service, socket, process-user, firewall, and L2TP inspection: no VPS session.
- Actual relay-to-RouterOS or Render-to-relay integration: deliberately not attempted.
- RouterOS API tests and controlled customer-device tests: no live router access.
- M-Pesa: no payment request made.

## 6. Files changed

Only this report was added:

- `docs/phase-5-relay-attestation-report.md`

All pre-existing Phase 1–4 modified/untracked working-tree files were left untouched. No dependency, database, API, relay, deployment, or systemd file was changed.

## 7. Deployment plan (not authorized or performed)

Deployment cannot be planned to an executable file-level procedure until the actual service source and unit are inspected. The safe follow-up sequence is:

1. Obtain a read-only copy of the deployed relay source and systemd unit, or a read-only VPS inspection session. Do not print secret values. Record only environment-variable names and whether required variables are configured.
2. Map existing routes, middleware, router target selection, RouterOS API client, process user, ports, service dependencies, logs, and health checks.
3. Implement the endpoint additively in that same application, using its existing router management integration and existing bearer token. Do not touch VPN, firewall, FreeRADIUS, router config, or current endpoints.
4. Add a server-side explicit router/site allowlist. Resolve RouterOS management addresses only from that configuration. Store API credentials using the existing secure mechanism; never log them.
5. Add mocked tests for authentication, allowlist/site checks, same-router lease and HotSpot matching, stale/unbound/mismatched observations, signed negative vs router errors, HMAC interoperability, malformed RouterOS responses, and concurrency/replay behavior.
6. Run the existing relay test suite and compatibility tests for every existing relay action. Compare the generated signature directly with `app.services.hotspot_attestation_service.sign_attestation` in a local integration test.
7. Prepare a source backup, staged artifact, service-specific health check, and rollback to the prior artifact. Do not restart or replace `isp-relay.service` until a separate deployment approval is given.
8. In an approved staging environment, test relay health and existing management actions before testing attestation. Only then perform a controlled, authorized router test.

No new environment variable is currently required by the Phase 4 contract. The relay needs access to the existing `ROUTER_RELAY_TOKEN` through its established secret mechanism and a server-controlled router/site registry. Whether those are already available cannot be determined from this repository. No firewall change is indicated by the contract; RouterOS API traffic must remain on the existing private/VPN path.

## 8. Controlled end-to-end verification plan

After relay code is available and separately approved for staging:

1. Unit-test the RouterOS response parser with fixtures: one bound lease and matching HotSpot host, no lease, lease/host mismatch, unbound/expired lease, stale observation, malformed response, and timeout/auth failures.
2. Unit-test HMAC using the exact Phase 4 key derivation and canonical JSON; confirm FastAPI accepts valid output and rejects modified claims/signatures.
3. Test unknown/disabled router, router/site mismatch, overlapping LAN IPs, nonce echo, stale/future/expired timestamps, and signed negative observations.
4. In staging, verify relay health and preserve existing relay management action behavior.
5. Under separate approval, use a controlled test router and test device to prove VPN-path API reachability and read-only DHCP/HotSpot observations.
6. Verify Render-to-relay auth, valid attestation, tamper rejection, nonce replay rejection, stale-evidence rejection, global fallback, and correct site-only catalog selection.
7. Use a payment mock only to verify purchase re-attestation and transaction/voucher site/router persistence. Do not trigger a real STK push.
8. A separate live customer-impact review is required before any production captive portal or payment flow is enabled.

These stages distinguish unit/mocked proof from actual VPS-to-router, Render-to-VPS, captive portal, and customer Internet-access proof. None of the live stages has been completed.

## 9. Remaining work and final status

### Required before implementation can continue

- Provide the VPS relay source tree/archive and its dependency/test instructions, **or** arrange read-only inspection of the VPS and relay service files.
- Provide the existing deployment workflow/documentation and a sanitized systemd unit (environment values redacted; variable names retained).
- Confirm the relay's existing server-controlled router/site registry or provide its schema/configuration source with credentials redacted.

### Required before staging readiness

- Implement the endpoint inside the existing relay application.
- Add allowlist-backed router/site resolution and RouterOS DHCP plus HotSpot host observations.
- Match/sign the Phase 4 schema exactly and integrate tests with the FastAPI verifier.
- Pass relay regression tests without changing service startup or existing endpoint contracts.

### Required before production deployment

- Separately approve any required service restart, secret access/change, firewall change, or network change.
- Back up the exact prior relay release and confirm rollback.
- Deploy only after staging tests and existing relay functionality checks pass.

### Final status

**1. IMPLEMENTATION INCOMPLETE.** The checked-in FastAPI side is implemented and its relevant mocked tests pass, but the requested VPS endpoint is not implemented or inspected. There is no evidence of VPS-to-router connectivity, Render-to-VPS attestation, a real MikroTik observation, a successful customer purchase, RADIUS acceptance, or Internet access. This work is **not ready for staging** and does not claim the service is operational.
