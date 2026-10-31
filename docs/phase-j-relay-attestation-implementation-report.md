# Phase J — VPS Relay Attestation Implementation Report

**Status:** BLOCKED — RELAY SOURCE OR ACCESS UNAVAILABLE  
**Scope:** Local source/configuration inventory only. No VPS, production relay, router, firewall, VPN, FreeRADIUS, Render, MongoDB, or payment provider was contacted or modified.

## 1. Outcome

Implementation is blocked at the required first step. The available checkout contains the FastAPI-side relay client and attestation verifier, but it does not contain the VPS relay server source or `isp-relay.service` unit. A second local project copy under Downloads and the supplied project ZIP likewise contain billing-app code and a relay client, not the relay server. No approved read-only VPS session or relay source archive was available in this task environment.

The project instructions explicitly require stopping when relay source/access is unavailable and prohibit inventing a replacement server. Accordingly, no relay endpoint, framework, allowlist format, RouterOS query behavior, or service startup configuration has been guessed or implemented.

## 2. Existing relay architecture discovered from available source

### Verified in the billing repository

- FastAPI's `app/integrations/mikrotik/relay_client.py` is an HTTP client for the separately hosted relay.
- The client sends `Authorization: Bearer <configured token>` and requires `ROUTER_RELAY_URL` plus `ROUTER_RELAY_TOKEN`; only variable names were inspected, never values.
- Existing client calls include `GET /health`, `POST /api/v1/router/relay` with management actions, and the new `POST /api/v1/router/attest` request.
- The relay client defines calls for system identity/resource/health, interface listing, PPPoE active/secrets/add/disconnect, HotSpot active/users/add/disconnect, DHCP leases, and queues. These are caller-side contracts; they do not prove how the server authenticates or implements them.
- `app/services/router_service.py` prefers the relay when configured and reachable for ordinary router operations, with a direct RouterOS fallback under its configured legacy-router conditions. The attestation service calls the relay contract directly and fails closed; it does not treat a browser claim or DHCP-only lookup as trusted attestation.
- The FastAPI verifier defines the HMAC domain `devzen/relay-attestation/v1`, canonical sorted compact ASCII JSON, issuer `devzen-vps-relay`, audience `devzen-billing-api`, 60-second maximum signature lifetime, 30-second maximum issue age, 15-second observation freshness, and a five-minute opaque browser context. It expects same-router DHCP and HotSpot evidence.

### Not available and therefore unverified

- Relay language/framework, source tree, dependency lockfile, startup command, working directory, process user/group, listener address/port, and service dependencies.
- `isp-relay.service` unit contents and deployed application version.
- Relay authentication middleware implementation and constant-time token comparison behavior.
- Existing relay health implementation, logging policy, request-size/concurrency controls, and error handling.
- RouterOS API adapter, credential retrieval/storage, router/site allowlist, router selection logic, DHCP lease parsing, HotSpot host-table query, and observation-age calculation.
- VPS firewall/network policy, HTTPS terminator, actual VPN path/reachability, and system time synchronization.

No production or secret values were read. No SSH/network connection was attempted. The repository and local-copy search found no `isp-relay.service` file or relay server module.

## 3. FastAPI contract to implement after source is supplied

The billing client sends an authenticated `POST /api/v1/router/attest` request with:

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

The relay must resolve router and site only from its own trusted registry. It must not accept a caller-provided management address or credentials. A positive response must be a signed object matching the FastAPI verifier's exact schema and include current same-router DHCP and HotSpot host evidence. A reachable router with no matching client should return a signed negative observation. An unreachable router, invalid credentials, ambiguous mapping, or untrustworthy observation must return an error, not a negative observation.

The HMAC derivation already expected by FastAPI is:

```text
derived_key = HMAC-SHA256(key=ROUTER_RELAY_TOKEN,
                          message="devzen/relay-attestation/v1")
signature = HMAC-SHA256(key=derived_key,
                        message=canonical_attestation_json)
```

Canonical JSON uses sorted keys, compact separators, `ensure_ascii=True`, UTF-8 bytes, and lowercase hexadecimal output. The nonce must be echoed unchanged, and the relay must use server-generated timestamps and a non-reused attestation. This report does not claim the relay implements any part of this contract.

## 4. Testing status

No VPS relay tests or cross-component test were run because there is no relay implementation to import or start. The existing FastAPI attestation and relay-client tests cannot establish server-side compatibility by themselves. Previously reported billing-side mock results are not relay implementation results and are not repeated here as proof of Phase J.

Required once source is available:

1. Relay unit tests with mocked RouterOS DHCP and HotSpot host responses for positive, negative, stale, duplicate, mismatched, unbound, expired, malformed, timeout, and authentication-failure cases.
2. Bearer authentication, router allowlist, enabled status, site match, ambiguous mapping, request validation, payload-size, and concurrency tests.
3. Exact canonical HMAC compatibility test that passes the relay-produced payload/signature into `app.services.hotspot_attestation_service.verify_attestation_signature`.
4. Test that changes to each signed field and signature fail verification.
5. Regression tests for every existing relay action and its response format.
6. Run the FastAPI attestation regression tests in an isolated environment after contract integration.

## 5. Exact source/access required to continue

Provide either:

- The source repository/archive for the **currently deployed relay application**, with its dependency lockfile and existing tests; or
- An approved read-only VPS inspection session plus a sanitized copy of the deployed relay source.

Also provide, with all secret values redacted:

- The `isp-relay.service` unit or its `ExecStart`, working directory, service user/group, restart policy, and referenced environment-file paths. Do not include inline secret values.
- Relay route and authentication middleware source, health handler, RouterOS adapter, and router/site registry/configuration schema.
- Names of required environment variables and whether they are configured, without their values.
- Listener/reverse-proxy details and relevant VPN routing facts needed to establish the existing private router path. No firewall/VPN changes are requested.
- The normal local test/start commands and the deployed source revision identifier.

Do not send relay tokens, RouterOS passwords, signing keys, `.env` contents, customer data, or raw production logs. If the VPS is to be inspected directly, the authorization must explicitly allow read-only inspection; this task did not have that access.

## 6. Changes and deployment

- No relay or billing application code was changed.
- No production files, settings, service, network, firewall, VPN, router, RADIUS configuration, or credentials were changed.
- No package was installed.
- No deployment or service restart was performed.

After source access is supplied, the next safe step is to inspect that existing application and add the attestation route within its established framework and startup path. Build and test it in isolation first. Any staging or production deployment plan must be separate; production deployment and any service restart require separate explicit authorization.

## 7. Classification

# BLOCKED — RELAY SOURCE OR ACCESS UNAVAILABLE

