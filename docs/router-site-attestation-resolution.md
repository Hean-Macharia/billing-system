# Router/Site Attestation Discrepancy — Investigation and Local Fix

**Date:** 2026-10-31  
**Scope:** Local source, isolated Mongo mocks, and tests. No production database or router records were modified. No VPS, Render, payment, RADIUS, or router configuration was changed.

## Finding

The admin Network & Devices page does not validate a router's site relationship in the backend. `GET /api/v1/routers` is implemented by `app/routes/routers.py::list_routers()` and `RouterService.list_routers()` in `app/services/router_service.py`. The service queries the `routers` collection with an optional exact `site_id` filter and paginates it. `_router_to_response()` returns the router's `site_id`; it does not join or validate a `sites` record.

`admin/js/network.js` separately calls `GET /api/v1/sites`, then renders the site name by comparing `String(site._id || site.id)` with `String(router.site_id)`. Therefore, the dashboard label establishes that the displayed IDs match as strings in those API responses; it does not establish that every router considered by HotSpot attestation is valid, active, or free of a conflicting NAS mapping.

Before this change, `HotspotAttestationService._candidate_routers()` loaded up to 65 router documents using `{"status": {"$ne": "disabled"}}`. It then validated each document and failed the entire request on the first missing/inactive site or conflicting NAS site. Since `offline` is a distinct `RouterStatus` from `disabled`, an offline router remained a candidate. Thus, an unrelated offline CCR2004 with an obsolete/missing site relationship could cause the generic error before the active RB951 was queried. This is a confirmed code-path defect and matches the reported symptom. The screenshot alone cannot prove that this exact production record is the trigger.

## Production record verification

The production records could not be queried from this local environment. No authorized production MongoDB read-only connection or sanitized record export was available. I did not inspect secret files or attempt a production data mutation. Consequently, these production values remain unconfirmed:

- RB951 router `_id`, stored `site_id`, `status`, and `nas_client_id`.
- Nyaururu site `_id` and status.
- Attached NAS `_id`, status, and `site_id`.
- Whether the offline CCR2004 exists, its site/NAS references, and whether duplicate/ambiguous records exist.

The supplied dashboard evidence identifies an online RB951 labeled Nyaururu Main Site and an active Nyaururu site. It does not identify which additional router candidates the attestation query loads. An authorized read-only check should compare those fields directly before any database correction is proposed.

## ID representation analysis

Before this change, the service converted references to strings for comparisons, then queried `sites._id` using only an `ObjectId`. It handled the common case where a string reference points to a BSON ObjectId document, but did not support the reverse legacy representation where `_id` is stored as a 24-character string. It also used inconsistent query construction for linked NAS records.

The router list endpoint itself does no site lookup. Its front-end display compares string representations only. So a dashboard label is not the same check as the attestation service's database lookup and active-site status validation.

## Local implementation

In `app/services/hotspot_attestation_service.py`:

1. Added shared ID normalization and lookup helpers. Site and NAS references normalize ObjectId values and their string forms consistently. Lookups match BSON ObjectId and string `_id` forms where valid.
2. Candidate selection now excludes routers marked `offline` as well as `disabled`. An offline router cannot currently provide a captive observation, and it no longer blocks an unrelated online site due to stale site metadata.
3. Remaining eligible routers still require a valid router ID, an active NAS mapping when linked, no conflicting router/NAS site IDs, and a site document with explicit `status == "active"`. Missing and inactive site relationships still fail closed for eligible routers.
4. `get_context()` uses the same ID normalization and requires an explicitly active site, so context revalidation follows the same identity rules.
5. No browser-supplied router or site identity was introduced. HMAC, nonce, evidence, context lifetime, and purchase-time re-attestation checks were not weakened.

This preserves multiple-site selection: each eligible online router is independently observed, and a uniquely matching signed observation selects the router. Multiple matches remain rejected.

## Regression tests

Added tests for:

- Active site and router accepted.
- Router site reference stored as ObjectId while site `_id` is a string.
- Inactive site rejected.
- Missing site rejected.
- Conflicting router/NAS site IDs rejected.
- Correct signed observation selected among multiple online routers.
- Offline unrelated router with stale site reference does not block the online RB951 candidate.

## Separate timeout and relay status

The current local `hotspot/js/app.js` gives the DHCP lookup a 30-second timeout override; the shared `hotspot/js/api-request.js` default remains 15 seconds, including the attestation request. The previously observed deployed HotSpot JavaScript had the older 15-second generic error behavior. The local API helper distinguishes timeout, network failure, and HTTP errors, but those local frontend changes must be deployed before production benefits from them.

The repository has a Phase J relay source copy implementing `POST /api/v1/router/attest` for a single explicitly configured router/site. Its deployment on the production VPS was not verified. The relay copy does not establish a verified multi-router allowlist for Nyaururu and Nakuru. Do not assume this local source is running in production.

## Test results

- `python -m pytest -q` — **186 passed, 27 skipped**, 5 warnings, exit 0.
- `node --test` over repository `tests/*.test.js` — **17 passed, 0 failed, 0 skipped**.
- `node --check` over repository JavaScript — **96 files checked**, no syntax errors.
- `python -m compileall -q app` — passed.
- `git diff --check` — passed (Git reported line-ending conversion warnings only).

All tests are local/mock tests; none connect to production MongoDB, the VPS relay, MikroTik, Render, RADIUS, or M-Pesa.

## Files changed

- `app/services/hotspot_attestation_service.py`
- `tests/test_hotspot_attestation.py`
- `docs/router-site-attestation-resolution.md`

Other untracked HotSpot login-template files from the prior task were preserved.

## Remaining steps

1. Obtain an authorized read-only production record check for the RB951, Nyaururu site, linked NAS, and any offline CCR2004. Confirm IDs, statuses, and references; do not create duplicate records.
2. Verify the running VPS relay endpoint and its allowlist/mapping without exposing secrets.
3. Deploy the reviewed local change only after normal deployment authorization. No production deployment occurred here.
4. In a controlled test window, request device attestation and confirm only the RB951 returns a valid signed observation, site packages resolve to Nyaururu, replay is rejected, and purchase-time re-attestation remains enforced.
5. Verify voucher login through RADIUS and actual Internet access with a test device. Unit tests cannot prove this.
