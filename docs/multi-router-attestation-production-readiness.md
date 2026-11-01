# Multi-router attestation and production verification

> **Superseded for current implementation and test results:** see [relay-attestation-production-integration.md](relay-attestation-production-integration.md). This earlier note records the previous local test snapshot and is retained as history.

**Date:** 2026-10-31  
**Scope:** Local source, isolated mocks, and operational preparation only. No Render, production MongoDB, VPS, MikroTik, FreeRADIUS, or payment system was contacted.

## Result

The local billing application now evaluates only explicitly online routers, validates each router/site/NAS relationship independently, and skips an individual relay `403` allowlist rejection while continuing to check other eligible routers. It still fails closed when there is no signed match, when a router is unreachable, when relay authentication fails, when signed claims are invalid, or when multiple signed observations match.

The copied relay source can read an explicit multi-router allowlist and query each configured RouterOS target without changing the legacy router-management target. This is **local code only**. The copied directory is not proof that the VPS service has this code or configuration. Actual Nakuru router identity, management address, and approved credentials remain unverified; no production mapping was invented.

## Changes made

- `app/services/hotspot_attestation_service.py`
  - Queries the online router set; offline, disabled, and unknown-state routers are not eligible.
  - Excludes malformed router identities, missing/inactive NAS associations, absent router/NAS site references, conflicting site references, and absent/inactive sites independently, with structured safe diagnostic fields.
  - Requires an attached NAS site to match the router site.
  - Revalidates online status, active site, and attached NAS/site consistency when reading a trusted context.
  - Treats the relay's explicit HTTP 403 router/site allowlist rejection as a candidate exclusion. Other relay errors still fail closed. If there is no valid signed match and a candidate was rejected by relay configuration, returns a service-unavailable diagnostic rather than claiming that the device was absent.
  - Preserves HMAC, audience/issuer, nonce consumption, observation evidence, context expiry, and purchase-time re-attestation.
- `app/integrations/mikrotik/relay_client.py`
  - Retains HTTP status on relay errors so an allowlist rejection can be distinguished from authentication and connectivity failures.
- `app/routes/hotspot.py`
  - Requires trusted context for every paid HotSpot purchase, including globally available packages. It re-attests before calling the existing M-Pesa purchase service. No payment settlement logic was changed.
- `hotspot/js/app.js`, `hotspot/js/api-request.js`
  - Requires the backend's opaque, unexpired trusted context before enabling purchase; DHCP lookup is shown only as a hint.
  - Uses a 30-second attestation timeout with timeout-specific copy. HTTP errors remain distinguishable from fetch/network errors.
  - Validates the trusted-context response before storing it in session storage.
- `phase-j-relay-source/server.py`, `phase-j-relay-source/routeros.py`
  - Adds `POST /api/v1/router/attest` to the existing copied relay implementation, with a strict server-side allowlist and per-router credential variable names. Existing `/health`, `/api/v1/router/relay`, bearer auth, rate limiting, request size checks, and RouterOS management defaults remain in place.
  - The observation performs read-only DHCP lease and HotSpot host queries to one allowlisted router and signs the full attestation with the existing HMAC contract. Observation age is conservatively measured from connection start through both RouterOS reads.
- Tests were added or updated in `tests/test_hotspot_attestation.py`, `tests/test_hotspot_site_package_selection.py`, `tests/hotspot-api-request.test.js`, and `phase-j-relay-source/tests/test_attestation.py`.

## Multi-site configuration contract

The copied relay supports a one-line, server-side `ATTESTATION_ROUTERS_JSON` registry with up to 64 entries. Each entry has exactly:

```json
{"router_id":"<approved 24-hex Mongo router id>","site_id":"<approved 24-hex Mongo site id>","host":"<approved private management IP>","port":8728,"username":"<approved RouterOS API username>","enabled":true,"site_active":true}
```

The string above is a schema template, not deployable configuration. The client request cannot supply or override a management target. A per-router password is read from the existing relay environment file using variable name `MIKROTIK_API_PASSWORD_<UPPERCASE_ROUTER_ID>`; the legacy single-router configuration remains supported. Do not copy secrets into source, logs, this report, or shell output. Allowlist IDs, site status and target addresses must be checked against authorized current records before staging. No Nakuru entry is provided here because its router record and approved management target were not available.

RouterOS API traffic remains on the existing private network path. The listener remains on loopback. Do not expose TCP 8728/8729 to the public Internet. RouterOS 6 legacy API is not encrypted by itself; it must remain confined to the existing protected VPN path.

## Database and purchase behavior

No MongoDB records, schemas, or indexes were changed. Router/site/NAS consistency is enforced at candidate selection and again when a trusted context is loaded. Existing site-restricted package authorization and payment settlement remain backend controlled. The HotSpot purchase route now fails before M-Pesa initiation if the opaque trusted context is missing, expired, invalid, or cannot be freshly re-attested. A successful STK initiation is still not payment success.

## Automated results

Local tests use isolated MongoDB mocks, mock relay calls, mocked RouterOS responses, and payment-service stubs. They do not prove production configuration or Internet access.

| Check | Result |
|---|---:|
| Focused attestation, relay-client, purchase/site selection, and relay suite | 89 passed, 0 failed, 0 skipped, 1 warning |
| Full Python suite | 200 passed, 27 skipped, 5 warnings |
| Copied relay attestation suite | 31 passed, 0 failed, 0 skipped, 1 warning |
| Node frontend suite | 30 passed, 0 failed, 0 skipped |
| Python compilation | Passed |
| JavaScript syntax checks | 98 files checked, no syntax errors |
| `git diff --check` | Passed; Git emitted only LF/CRLF conversion notices |

The 27 skipped Python tests are existing tests gated on external MongoDB availability. No production or staging tests were run. The Node suite ran 30 tests, all passed, with none skipped. Python compilation completed successfully. `git diff --check` completed successfully; Git emitted only LF/CRLF conversion notices.

## Production status and exact safe verification sequence

Current classification: **IMPLEMENTED BUT NOT DEPLOYED** for local code; **BLOCKED BY MISSING ACCESS** for production records and running relay verification. There is no evidence here that production has the copied relay endpoint or multi-router configuration. No Nyaururu/Nakuru production mapping was read or changed.

### 1. Render read-only checks

From an authorized workstation, request only public GET endpoints and inspect status codes and headers:

```powershell
curl.exe -sS -o NUL -w "health HTTP %{http_code}`n" https://billing-system-5ckp.onrender.com/health/ready
curl.exe -sS -o NUL -w "portal HTTP %{http_code}`n" https://billing-system-5ckp.onrender.com/hotspot/
curl.exe -sS -I https://billing-system-5ckp.onrender.com/hotspot/js/app.js
```

The last response should be checked for the deployed asset's cache/version headers. Do not include request headers carrying credentials in transcripts.

### 2. Read-only router/site/NAS record comparison

Only an operator with approved read-only production database access should run this. It projects non-secret relationship fields only and never prints router passwords or RADIUS secrets:

```javascript
const d = db.getSiblingDB("isp_billing");
const sites = d.sites.find({}, {_id: 1, name: 1, code: 1, status: 1}).toArray();
const routers = d.routers.find({}, {_id: 1, name: 1, status: 1, site_id: 1, nas_client_id: 1, ip_address: 1, port: 1, model_name: 1, routeros_version: 1}).toArray();
const nas = d.nas_clients.find({}, {_id: 1, name: 1, status: 1, site_id: 1, ip_address: 1, nas_identifier: 1}).toArray();
printjson({sites, routers, nas});
```

Compare each enabled/online router's `site_id` to an active `sites._id`, then compare its linked NAS `site_id` to the same site. Confirm Nakuru only when the actual approved router and site records exist. Do not create or edit records from this check. Redact management IPs and customer data from shared output as appropriate.

### 3. VPS service and route checks (read-only)

Run only through the already approved VPS administrative access; these commands do not restart or modify services:

```sh
sudo systemctl is-active isp-relay.service
sudo systemctl show isp-relay.service -p ActiveState -p SubState -p MainPID -p User -p Group -p ExecStart
ip -brief address show ppp0
ss -ltnp | grep -E '127\.0\.0\.1:8765|:8765'
curl --silent --show-error --output /dev/null --write-out 'health HTTP %{http_code}\n' http://127.0.0.1:8765/health
```

To check whether the unauthenticated route is mounted without disclosing the relay token, an authorized operator may send an empty JSON object without Authorization to the local endpoint. A mounted route should reject authentication; a 404 indicates the path is absent. This request does not contact a router but does count toward relay rate limiting:

```sh
curl --silent --show-error --output /dev/null --write-out 'attest unauthenticated HTTP %{http_code}\n' \
  -H 'Content-Type: application/json' -d '{}' http://127.0.0.1:8765/api/v1/router/attest
```

Do not use a real bearer token in a shell command, report, ticket or terminal transcript. To verify authenticated route behavior or the allowlist safely, use the approved secret manager and a controlled staging environment; do not probe production by causing RouterOS lookups.

### 4. Network and RADIUS checks (read-only)

These checks only establish local service/listener state; they do not prove authentication:

```sh
ip route get 10.30.0.10
sudo systemctl is-active freeradius
ss -lun | grep -E ':(1812|1813)\b'
```

Do not run a RouterOS login or test a live customer voucher as part of read-only verification. Actual API queries, HotSpot login, RADIUS auth/accounting, and Internet access require a controlled test device and explicit operational approval.

## Staging/deployment and rollback

1. Obtain review approval and source-control custody for `phase-j-relay-source`; it is a copied source tree, not established as the VPS's deployment checkout.
2. Obtain an approved read-only export of site/router/NAS IDs and approved management targets. Configure an allowlist entry for each confirmed site/router. Do not infer a Nakuru target from Nyaururu.
3. Configure staging relay token/password references through a secret manager/environment file using existing secret-handling practices. Do not print values. Ensure FastAPI staging uses the same relay token, and run the copied relay tests plus cross-component tests before starting staging.
4. Back up staging source and configuration metadata securely. Keep secret material in the existing secure store; document only backup location/owner, not content.
5. Deploy to a separate staging process/listener, loopback-bound and not publicly exposed. Confirm health, existing management route compatibility, auth rejection, then use a controlled test router for a positive and negative attestation.
6. Deploy the reviewed FastAPI/frontend and relay changes only under separately approved change windows. Use a canary/staging first. No deployment occurred here.
7. Rollback: restore the backed-up staging files and prior staging config, stop only the staging process, and confirm its health/route behavior. A production rollback involving `isp-relay.service` or Render requires explicit approval and its own maintenance plan; do not restart production as part of this document.

## Remaining acceptance work

- Run the final focused and full test suites after all changes (including the new relay 403 tests).
- Verify real production site/router/NAS records with authorized read-only access.
- Confirm the active relay source and route in the running VPS service without inspecting secrets.
- Populate and validate a staging allowlist for each real router/site; Nakuru mapping is currently unavailable.
- Execute staging RouterOS API, DHCP/HotSpot evidence, cross-component HMAC, replay, and controlled customer-flow tests.
- Confirm the production frontend deployment contains current assets only after an approved deployment.
- With an explicitly approved test device and payment sandbox, verify payment settlement, voucher activation, RADIUS authentication/accounting, and Internet access. Do not use live customer payments.

Until these external steps are complete, do not classify the ISP service as production-ready or claim Nyaururu/Nakuru end-to-end operation.
