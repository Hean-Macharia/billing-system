# Phase 2 — Automatic device identification and MikroTik connectivity

**Date:** 2026-10-31  
**Scope:** Captive portal source, FastAPI device/lease lookup, RouterOS API clients/parsers, site/router models, and repository documentation/tests. No live router, VPS relay, `isp-relay.service`, Render, production MongoDB, or FreeRADIUS system was contacted or changed. No secrets were read or printed.

## Findings at a glance

- The current router guide prescribes `/hotspot/`; the root portal and `/checkout.html` remain a second served flow. Both read the RouterOS redirect context automatically. Current phone/laptop users are not asked to type their MAC.
- MikroTik provides the client `ip`, `mac`, login links, and HTTP-CHAP values through HotSpot page variables. The repository’s deployed router-side `hotspot/login.html` is **absent**. The only example is a setup snippet in `docs/mikrotik-routeros6.md`; therefore those values reach the hosted page only if an operator installed an equivalent RouterOS `login.html` on the router.
- Before this phase the API returned the first DHCP lease matching either IP or MAC from any router. This could select an unrelated site on overlapping LANs, and a partial router outage could still result in a misleading match. It did not reject expired/unbound leases or duplicate cross-router matches.
- Lookup now requires each supplied identifier to match the same lease, normalizes legacy/REST/relay DHCP records, scans enabled configured routers, returns the matched router/site and explicit verification metadata, and fails closed on ambiguous, expired, missing, or partially unavailable results. The portal displays separate identifying/verifying/verified/failed states.
- This is a **lease match**, not cryptographic proof of device or router possession. The public API accepts browser-supplied IP/MAC, and no signed router/site context exists in the current contract. An attacker able to spoof/learn another live lease’s values could still submit them. A router-authenticated context mechanism is needed before calling this identity proof.
- The RADIUS request stores `NAS-IP-Address`, but `radius_sessions.site_id` is written as `None` and never resolved through `nas_clients`/`routers`. Purchase status also does not persist the matched router/site into the voucher/auth path. Multi-site identity is not preserved end to end yet.
- Secure additional-device pairing is not implemented. Do not treat the existing “TV / other device” MAC-and-lease check as pairing an existing voucher. Free trials remain one-device and MAC-bound.

## Value-by-value path and source

| Value | Source in RouterOS | Router-side transfer | Hosted page/API handling |
|---|---|---|---|
| Client IP | HotSpot `$(ip)` (or `$(host-ip)` for host-table context) | Guide’s `login.html` sample posts `ip` as a hidden field to the hosted portal. RouterOS may also include it on the captive redirect. | `hotspot/js/app.js` and `js/portal.js` read `ip`, `client_ip`, or `address`; standalone `js/checkout.js` reads the same. Current flow sends IP together with MAC when both exist. Backend validates private IP syntax and lease-matches it. |
| Client MAC | HotSpot `$(mac)` | Guide’s sample posts `mac` as a hidden field. RouterOS redirects may include it as `mac`. | The same JS reads `mac`, `client_mac`, `mac-address`, or `calling_station_id`. It is treated as an untrusted lookup hint and is not shown as verified until the backend returns a unique matching DHCP lease. |
| Router identity | RouterOS has `$(identity)`, server name, and interface name variables; NAS identity is separately sent by RADIUS as `NAS-IP-Address` / `NAS-Identifier` depending on configuration. | The checked-in guide’s form does not forward a router identity. `hotspot/login.html` is absent. No current captive API field carries a signed router identifier. | The backend loads configured `routers` records and checks enabled router DHCP leases. It returns the matched database `router_id`, router name, and configured `site_id`. RADIUS accounting saves `nas_ip_address`, but currently hardcodes session `site_id: None`. |
| Captive login URL | `$(link-login-only)` or `$(link-login)` | Guide’s sample forwards `link-login-only` in a hidden field. | `MikrotikLogin.parseRedirectParameters` reads `link-login-only`, `link-login`, or `login_url`; validates `/login`, scheme, port, and host; resulting URL is used as the POST form action. |
| Original destination | `$(link-orig)` (or escaped form `$(link-orig-esc)`) | Guide sample forwards `link-orig`; browser form URL-encoding transports it. | Parser reads `link-orig`, `link-orig-esc`, or `dst`, passes the query-decoded value to `URL`, accepts only HTTP(S), then includes `dst` as a hidden login form field. The browser form encodes it for POST. Invalid destinations are omitted. |
| CHAP ID | `$(chap-id)`; MikroTik documentation says this variable is available on the RouterOS login page only | The guide sample forwards it from `login.html`; if the router template is not installed as described, hosted page may not receive it. | `URLSearchParams` percent-decodes query values. The CHAP helper converts RouterOS `\ooo` escapes into their byte values before calculating the digest. |
| CHAP challenge | `$(chap-challenge)`; login-page-only RouterOS value | Same as CHAP ID | Same decoder/hash path; included in the digest bytes. |

MikroTik’s current docs specify HTTP-CHAP as MD5 of `chap-id || password || chap-challenge`, in that order. The client sends the resulting hex digest as the RouterOS `password` field; the voucher code is the username. The browser’s native `application/x-www-form-urlencoded` POST serializes `username`, `password`, and `dst`. The new regression test uses RouterOS-style octal values and an independently calculated byte sequence. See [MikroTik HotSpot customization](https://help.mikrotik.com/docs/spaces/ROS/pages/87162881/Hotspot%2Bcustomisation) and [HotSpot captive portal](https://help.mikrotik.com/docs/spaces/ROS/pages/56459266/HotSpot%20-%20Captive%20portal).

The login URL validator currently accepts private IPv4 and `.lan`/`.local`/`.hotspot` names. A public-looking DNS name such as the guide’s illustrative `wifi.example.com` would not pass this local-host check. Do not loosen it to arbitrary hostnames: add a deployment-specific trusted-host mapping after confirming the actual RouterOS DNS name and TLS setup. No live router login template was installed or changed.

## Router and site selection

Router records have optional `site_id`; HotSpot plans and vouchers also have optional site fields. `GET /api/v1/hotspot/plans/public` accepts `site_id`, but the two captive UIs currently list plans before resolving a device and do not supply that filter. Device lookup previously scanned every router and returned immediately on the first IP-or-MAC match. This phase now:

1. Queries all configured routers other than `status=disabled` (including legacy records whose status is absent).
2. Calls `RouterService.get_dhcp_leases(router_id)` for each, which uses the configured legacy RouterOS API, REST API, or existing authenticated VPS relay path.
3. Normalizes the legacy, REST, and relay DHCP field shapes.
4. Requires every supplied identifier to match a single lease; when both IP and MAC are present, both must match.
5. Requires a lease to contain an IP and MAC and rejects non-bound or expired leases.
6. Rejects multiple matching router leases with HTTP 409. If any configured router could not be checked, returns HTTP 503 even if another router had a match, because global uniqueness is unknown.
7. Returns `verification_status`, `verification_method`, lease values/status/expiry, and matched router/site metadata.

This prevents “first router wins” on overlapping LANs and avoids silently verifying while a site is unreachable. It cannot prove that a browser’s query parameters came from the matched router. The backend must not use this metadata as a secure router identity until a signed/otherwise authenticated RouterOS-to-portal context is designed.

RADIUS accounting currently stores the NAS IP, but session records set `site_id=None`; no code maps NAS IP to `nas_clients` then to router/site. The hotspot payment request is revalidated against the IP/MAC pair when IP was supplied, but `MpesaService` does not persist matched `router_id`/`site_id`, the voucher gets no such router association, and RADIUS auth does not compare NAS site against voucher site. These are end-to-end multi-site mapping gaps. They were documented rather than expanding payment settlement or FreeRADIUS authorization in this phase.

## Additional-device pairing

**Not implemented.** Existing purchase can target an additional device that has a current DHCP lease, but entering its MAC is not a secure proof of control and does not pair a second device to an already-issued voucher. The backend has no short-lived pairing challenge/approval contract. Do not advertise a QR/code pairing flow yet.

Required future contract, before implementation:

1. Authenticated primary voucher/device submits a pairing request; backend verifies voucher validity, active primary Calling-Station-Id, and remaining distinct-device allowance.
2. Backend issues a cryptographically random, single-use code with a short expiry and stores a hash plus voucher/site/router context; creating a pending code does not consume a slot.
3. New device must open the captive portal from the same router/site; backend validates the request against a current DHCP/HotSpot host entry and binds the new MAC to the pending code.
4. Atomic consume checks expiry, one-time use, voucher allowance, site/router match and duplicate MAC, and only then claims a slot.
5. RADIUS checks that paired MAC against the voucher; expired/reused codes fail closed. Rate limiting and response privacy are required.

This requires new backend models/routes and NAS/site context. The free-trial service remains unchanged: unique MAC claim, one device, three-minute entitlement.

## Files changed

- `app/routes/hotspot.py` — unique all-router matching, lease state/expiry handling, structured result, fail-closed errors; purchase revalidation now uses IP+MAC when provided.
- `app/schemas/portal.py` — optional client IP on captive purchase request.
- `app/services/router_service.py` — normalize REST DHCP results to the same shape as legacy results.
- `app/integrations/mikrotik/parsers.py` — normalize legacy/REST/relay DHCP field aliases and expiry values.
- `hotspot/js/app.js`, `js/portal.js`, `js/checkout.js` — automatic IP+MAC lookup, explicit identification states, structured verification consumption, and stale-request protection.
- `js/api.js` — pass the optional verified client IP through standalone purchase.
- `js/mikrotik-login.js`, `hotspot/mikrotik-login.js` — decode RouterOS octal CHAP byte substitutions before MD5. The two helper files remain identical.
- `tests/test_hotspot_device_verification.py` — source-isolated tests for lease match, wrong-site overlap, duplicates, expiry, missing values and unavailable routers.
- `tests/test_mikrotik_dhcp_parser.py` — DHCP normalization tests.
- `tests/hotspot-portal.test.js` — octal CHAP vector test.
- `docs/phase-2-device-mikrotik-report.md` — this report.

Other modified files shown in the working tree predate Phase 2 and were not changed as part of this phase.

## Tests and verification

Checks run for this phase:

- `node --test tests/hotspot-portal.test.js` — **passed, 7/7**. Includes the RouterOS octal-escape CHAP digest vector and redirect parsing/submission cases.
- `python -m compileall -q app tests` — **passed** (Python syntax compilation only; does not import/run application behavior).
- `node --check` across JavaScript files in `js/`, `admin/js/`, `portal/js/`, `portal/assets/js/`, `admin/assets/js/`, `hotspot/js/`, and `frontend/js/` — **passed, 84 files**.
- `git diff --check` — **passed**, no whitespace errors.
- `python -m pytest -q tests/test_hotspot_device_verification.py tests/test_mikrotik_dhcp_parser.py` — **could not complete**. The process produced no output and stalled while importing `app.routes.hotspot`; it was interrupted after approximately 20 seconds. A direct `from app.routes import hotspot` import also stalled. Therefore, the new Python behavioral tests are present but **not reported as passed**.
- The existing `tests/test_hotspot_trial.py` Free-trial binding test and pairing security tests were **not run**. Pairing has no implementation/API to test; the trial behavior was not modified. Full pytest/backend behavior remains unverified in this environment.

No check in this section connects to a live RouterOS device or proves customer Internet access.

## Live verification still required

1. Confirm the production RouterOS HotSpot profile’s `html-directory`, `login.html`, `dns-name`, `login-by`, and walled-garden entries. The repository does not contain the router-side `hotspot/login.html` file and no router was accessed.
2. From one device on each site, inspect the hosted URL query without exposing secrets: confirm IP/MAC, correct login URL, original destination, CHAP ID and challenge arrive as expected.
3. Confirm each device lookup returns the expected router/site, and exercise duplicate and router-unreachable cases during a supervised maintenance/test window.
4. Confirm the FastAPI Render host can reach the configured relay and that the unchanged `isp-relay.service` can reach each site router over its existing private path.
5. Complete one controlled voucher login on each test site; correlate RouterOS active HotSpot session, FreeRADIUS Access-Accept and Accounting Start/Interim/Stop.
6. Confirm DNS, NAT, firewall, queues and actual Internet access from the customer device.

No live connectivity or customer Internet session is claimed by this source/test work.
