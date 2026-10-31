# HotSpot device verification errors

**Date:** 2026-10-31. Source-based diagnosis plus local tests; no production database or router was accessed.

## Error 1: router is not attached to an active site

FastAPI returns this message from `HotspotAttestationService._candidate_routers()` before requesting a relay observation. It loads configured, non-disabled router records and requires each candidate to resolve to an active site, either directly through `router.site_id` or through its active NAS relationship. A missing site ID, stale/nonexistent site ID, inactive site, or incomplete NAS/site mapping causes the request to fail closed. It must not infer the site from a browser IP/MAC or guess that the one known router belongs to a particular town.

**Required configuration correction:** an authorized administrator must inspect the existing site and router records, set the verified router-to-site relationship, ensure the referenced site is active, and ensure any attached NAS record agrees. Do not create fictional site/router IDs. After the records are corrected, reload the captive page and confirm attestation returns an opaque context. A trusted context also requires the relay allowlist to contain the same verified mapping.

## Error 2: “Cannot reach the billing API” during the package purchase sheet

The package sheet calls `POST /api/v1/hotspot/devices/lookup`, which checks router DHCP leases. Before the lookup, `RouterService` may call relay health and then query DHCP, each with a configured timeout. The captive page previously aborted all requests after 15 seconds and converted every fetch rejection—including its own timeout—into “Cannot reach the billing API.” Therefore the displayed message did not distinguish a browser/network failure from a slow router/relay lookup.

**Local correction:** a shared request helper now distinguishes HTTP errors, network failures and request timeouts. The DHCP lookup receives a bounded 30-second window; if it still exceeds that window, the UI explains that router/relay verification timed out. A genuine fetch failure still reports API reachability. This does not make an unavailable router reachable and does not weaken backend verification.

## Verification

- The exact supplied RouterOS redirect URL is covered by `tests/hotspot-portal.test.js`; its octal CHAP values are parsed as octal bytes and its double-encoded destination is normalized once.
- `tests/hotspot-api-request.test.js` covers timeout, transport failure, and backend HTTP error distinction.
- `tests/test_health.py` confirms both direct `/hotspot/` and the exact captive query serve the static page locally.
- Targeted results at time of change: HotSpot portal/API/static tests passed; attestation/device verification backend tests passed. No live DNS/TLS/Render request or RouterOS call was verified.

## Files changed for the local correction

- `hotspot/js/api-request.js`
- `hotspot/js/app.js`
- `hotspot/index.html`
- `tests/hotspot-api-request.test.js`
- `tests/hotspot-portal.test.js`
- `tests/test_health.py`

The backend active-site error is a configuration/data blocker, not a frontend defect. It cannot be repaired safely without verified router/site records and approved access to the relevant environment. The original `net::ERR_CONNECTION_CLOSED` remains a separate pre-page network/edge issue; local tests cannot establish its live cause.
