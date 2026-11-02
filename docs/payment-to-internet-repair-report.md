# Payment-to-Internet Repair Report

Date: 2026-11-01

Scope: local source and isolated tests only. No production database, payment provider, router, relay, RADIUS server, or deployment was contacted or changed during this work.

## Findings from the supplied production logs

The log sequence supplied in this chat shows the STK request was accepted, the callback reached the callback route, provider verification returned success, a purchase voucher batch was generated, and `_settle_hotspot_purchase()` logged a successful settlement. Repeated `GET /api/v1/hotspot/purchase/status/{checkout_request_id}` requests nevertheless returned HTTP 409 before the portal received its login username. Thus, for that logged transaction, the observed blocker was the purchase-status authorization gate after settlement, not failure to receive the callback or create the voucher. The access credential was withheld from the browser, so the browser could not submit the RouterOS HTTP-CHAP login.

The old request logs record only HTTP 409 and do not include the API error body or the reason for the conflict. The precise branch cannot be reconstructed from those logs. The route has three relevant conflict conditions: missing context header, expired/invalid context, and mismatch between the purchase's initiating device/router/site and the presented trusted context. The route now emits a correlation ID and safe reason-coded diagnostics for these cases. It does not log checkout IDs, device addresses, receipts, or context tokens.

## Confirmed code defect repaired

`NotificationService.notify()` caught SMS delivery errors but allowed `notifications.insert_one()` errors to propagate. `_settle_verified_success()` treated any exception from `_settle_hotspot_purchase()` as settlement failure. Therefore, an audit insertion failure after voucher creation could leave a confirmed payment marked unsettled/failed even though its voucher already existed. The voucher service already retrieves purchases by `purchase_transaction_id`, and the database startup configuration defines a unique sparse index for that association, which makes retry recovery possible.

The HotSpot settlement function now persists the voucher reference but leaves the final `settled=true` transition to the settlement owner after critical work finishes. Notification send and persistence failures are best-effort and cannot reverse voucher/payment settlement. Voucher generation remains before notification, receipt assignment remains server-side after verified provider success, and no access is returned until settlement is completed.

## Changes made

| File | Change |
|---|---|
| `app/services/mpesa_service.py` | Added safe Daraja status-query diagnostics (HTTP status and allowlisted provider code only); added a 15-second retry backoff for failed settlement claims; added a callback-confirmed HotSpot status read that retries due settlement without making a Daraja request on every browser poll; removed the premature `settled=true` write from voucher creation; made reconciliation failure logs omit raw checkout IDs and exception text. |
| `app/services/notification_service.py` | Notification SMS and audit persistence failures now remain non-fatal; logs contain only event/category and exception class, not phone numbers, provider response bodies, or exception text. |
| `app/routes/hotspot.py` | Purchase-status polling retries an eligible settlement only after the caller passes trusted-context and purchase-binding checks; adds a correlation ID and reason-coded logs for status 409 branches. |
| `hotspot/js/app.js` | On a 409 specifically identifying a missing/expired context, performs one fresh device attestation and resumes polling. Binding conflicts remain fail-closed and offer receipt recovery; stale context is cleared and the safe backend message is shown escaped. |
| `tests/test_mpesa_settlement_resilience.py` | Added tests for notification persistence failure, settlement status integrity, status-triggered settlement retry without provider re-query, retry recovery after a partial write, and sanitized Daraja HTTP diagnostics. |
| `tests/test_mpesa_callback.py` | Existing settlement-retry test now advances the retry time before requesting the retry. |
| `tests/hotspot-portal.test.js` | Covers expired-context refresh behavior; aligns the support-number assertion with the current portal branding value. |

The working tree also contains pre-existing untracked `fix_nyaururu_nas_mapping.py` and `nas_mapping_preflight.py`; these were not opened or changed as part of this repair.

No RADIUS resolver or authorization rules were weakened. The existing implementation requires both `NAS-IP-Address` and `NAS-Identifier`, when both are provided, to uniquely resolve to the same active NAS/router/site. This is the correct fail-closed behavior. Existing tests cover matching and conflicting attributes, site isolation, voucher expiry, device binding, and MikroTik reply limits.

## Payment and access state behavior

1. A callback is still only a verification trigger; `_query_provider_status()` must return a matching checkout ID and valid result code before state changes.
2. A provider-confirmed successful HotSpot payment still requires a valid receipt. Missing or conflicting receipts go to review and do not grant access.
3. Settlement remains protected by an atomic MongoDB claim. Voucher creation/retrieval is keyed by purchase transaction ID; receipt uniqueness and the existing unique voucher purchase index remain the concurrency backstops.
4. A failed critical settlement operation retains payment status `success`, marks settlement recoverable, and schedules a retry. It does not turn the provider-confirmed payment into `failed`.
5. The purchase-status route releases receipt/login values only when callback received, payment successful, settlement completed, no review flag, and the caller's trusted device/router/site binding matches.
6. On successful status, the existing frontend computes MikroTik HTTP-CHAP from the RouterOS-provided CHAP ID, voucher username/password, and challenge, then posts to `link-login-only`. It does not display “connected” merely because the form was submitted.

## RADIUS / router evidence and remaining uncertainty

Earlier production logs shared in this conversation showed a voucher Access-Request rejected as `unknown_nas_ip`. The current operator-provided mapping is NAS `6ae7ca9e59c537c1de29d770`, router `6ab587aa145e0b7ff9adcf49`, site `6aa1c1318c57af83b37a0e49`, and NAS IP `10.30.0.10`. That mapping was not read back from production during this turn. The NAS `nas_identifier` value was not provided. Before production verification, confirm that the stored NAS IP is `10.30.0.10`, the router's `nas_client_id` references that NAS, both site IDs match, the site is active, and any `NAS-Identifier` sent by FreeRADIUS exactly matches the NAS record. The MongoDB NAS `secret` placeholder must not be used as the FreeRADIUS shared secret.

The source and mock tests cannot establish an Access-Accept from the live FreeRADIUS service, a RouterOS active session, or working Internet/DNS/routing. No live router or RADIUS verification was performed.

## Tests and checks

| Check | Result |
|---|---|
| Node test suite (`node --test` over the five `*.test.js` / `*.test.mjs` files under `tests`) | **39 passed, 0 failed, 0 skipped** |
| `node --check hotspot/js/app.js` | **Passed** |
| Python compilation of changed application and test files using `.venv-1` | **Passed** |
| `git diff --check` | **Passed**; Git printed only line-ending normalization warnings for edited files. |
| Router parser regression (`python -m pytest tests/test_mikrotik_dhcp_parser.py -q`, `.venv-1`) | **2 passed** |
| Relevant pytest collection | **40 tests collected** across settlement, callback, purchase-status, NAS identity, and RADIUS site authorization. |
| Relevant/full pytest execution | **Incomplete**. Async pytest execution stalled in this Windows environment before reporting test results; no Python test is claimed as passed. `.venv` also lacks `mongomock_motor`; `.venv-1` has the dependency but the async run did not complete. No packages were installed. |

The new asynchronous regression tests are present but still require execution in a compatible Python test environment. Do not treat compilation or collection as behavioral test success.

## Deployment and rollback

These changes have not been deployed. Review and run the Python tests in the project's supported Linux/CI environment first. Then deploy the application through the existing Render process; do not change production relay, RADIUS, router, database mappings, or payment settings as part of this code deployment.

Recommended sequence after approval:

1. Run the repository's full pytest suite in CI or Linux with the existing locked dependencies; require the 40 focused tests above plus the complete suite to pass.
2. Review the diff, create the normal reviewed source-control change, and deploy to Render using the established project workflow.
3. Verify `/health/ready`, public plan retrieval, a no-payment HotSpot status check, and a staged/sandbox purchase before any live purchase.
4. For a specifically authorized live verification, use one operator-controlled test device and a low-value test purchase only after payment approval; verify callback, transaction `settlement_status=completed`, exactly one voucher by purchase transaction ID, HTTP-CHAP result, matching RADIUS NAS identity, Access-Accept, active MikroTik session, and traffic. Do not repeat a payment if status is delayed; use the receipt/reconnect flow.

Rollback: redeploy the previously active Render build through Render's deployment history. The changes add only optional transaction retry metadata and code paths; they do not require a database migration. Do not roll back by deleting transactions or vouchers. If an individual transaction remains in `review_required` or settlement failed after deployment, reconcile it from the verified provider result and existing purchase voucher under the normal support procedure.

## Current classification

**PARTIALLY REPAIRED — identified blockers remain.** The notification/settlement failure mode, recoverable status polling, safe Daraja diagnostics, and stale-context retry are implemented locally. Production status 409s were not re-observed after deployment because no deployment was authorized. The focused async Python suite did not complete in this Windows environment, and live RADIUS/RouterOS Internet access remains unverified.
