# HotSpot Payment and Automatic Connection Audit

**Audit date:** 2026-11-01  
**Repository:** `C:\Users\ADMIN\Documents\isp-billing`  
**Scope:** Read-only Stage 1 audit before implementation. No production service, database, router, relay, or payment provider was contacted.

## Repository state and mounted frontends

- The checkout is on branch `main` at `4391d5d` (`worked on online routerssss`). The working tree was clean before this report was created.
- FastAPI mounts the actual HotSpot application from `hotspot/` at `/hotspot/`, the admin application from `admin/` at `/admin/`, and the customer portal from `portal/` at `/portal/` (`app/main.py`). Root-level checkout/status files and the other `frontend/` tree are separate implementations. Changes to the duplicate checkout do not automatically change the mounted HotSpot portal.
- `render.yaml` declares `APP_ENV=production`, Docker deployment, `healthCheckPath: /health/ready`, and the existing relay settings. The development default in `app/core/config.py` applies only if the deployment setting is absent; it is not the value declared in the repository's Render manifest. No Render settings were inspected remotely.

## Current payment-to-voucher contract

1. `POST /api/v1/hotspot/purchase` (`app/routes/hotspot.py`) requires `X-Hotspot-Context`, re-attests the device, and forwards the trusted router/site plus the requested package, phone, device type, and verified MAC to `MpesaService.initiate_hotspot_purchase`.
2. The service loads the plan and takes its price from MongoDB. It inserts a pending `hotspot_purchase` transaction and starts Daraja STK Push. The request schema currently accepts Kenyan international phone format `254` plus nine digits; the mounted UI normalizes `07...` and `01...` to that form. There is no purchase idempotency key in the request or service, so a repeated POST can create another transaction/STK request.
3. The public Daraja callback is handled by `POST /api/v1/payments/mpesa/callback`. A callback does not by itself establish success: the service queries Daraja and checks the returned checkout ID/result code. Provider query failure marks verification pending. Callback processing has atomic/idempotent guards and settlement claims; existing tests cover duplicate and concurrent callbacks and settlement retries.
4. On verified success, the HotSpot settlement path creates one active, transaction-linked voucher, binds it to the MAC, stores its generated random `voucher_code` on the transaction, and notifies the buyer. Voucher generation is idempotent by `purchase_transaction_id`.
5. Daraja receipt metadata is stored as `mpesa_receipt_number`, but it is optional for a success result, has no unique index in `app/core/database.py`, is not linked to the voucher lookup key, and is not returned by the HotSpot purchase status endpoint. The visible/access credential is the separate random voucher code. There is no receipt reconnect endpoint.
6. `GET /api/v1/hotspot/purchase/status/{checkout_request_id}` currently returns `status`, `voucher_code`, and `result_desc`. It does not gate voucher disclosure on `settled`/`settlement_status == completed`; the UI requires a voucher but cannot distinguish provider-confirmed success from completed settlement through this response.

## MikroTik login and automatic connection

- `hotspot/login.html` forwards `link-login-only`, escaped `link-orig`, `chap-id`, `chap-challenge`, IP, and MAC to `/hotspot/` without rewriting CHAP bytes.
- `hotspot/mikrotik-login.js` validates the RouterOS login URL and destination and computes HTTP-CHAP as MD5 of RouterOS CHAP-ID bytes, voucher username, and challenge bytes. It supports RouterOS three-digit octal byte substitutions. Existing Node tests include the supplied RouterOS 6 captive URL and verify the expected form construction.
- After payment, `hotspot/js/app.js` displays a voucher and a `Connect to WiFi` form button. It does not submit automatically, query an authenticated session, or verify a RADIUS Access-Accept/session before claiming connected. Therefore the current paid flow requires a manual click and does not meet the requested automatic login outcome.
- The root-level `frontend/js/payment-status.js` currently displays “You’re connected!” while offering another manual connection action. That wording is not supported by an observed RouterOS login/session and must be corrected if that entry point remains supported.
- The RouterOS login action in the supplied redirect is HTTP while the hosted portal is HTTPS. The implementation uses a normal top-level form POST (not `fetch`), so CORS is not the relevant mechanism. The browser/router reachability, post-login redirect, and authentication result still require an actual controlled RouterOS test. Local tests cannot prove those production properties.

## Device and site trust

- Device attestation is `POST /api/v1/hotspot/devices/attest`; the browser supplies IP/MAC hints, FastAPI asks the authenticated relay to observe them, verifies the HMAC/issuer/audience/timestamps/nonce and requires fresh DHCP plus HotSpot evidence before issuing an opaque context.
- Purchase requires the context and performs fresh re-attestation. Site-specific package listing and purchase authorization are server-side.
- The local relay source exists under `phase-j-relay-source/`, but prior production evidence says the running relay returns 404 for `POST /api/v1/router/attest`. It was not contacted in this audit. Attestation cannot be described as deployed or live-working based on repository code.
- Previously audited production records show Nyaururu's router/site mapping, a router with a dangling site reference, an unassociated NAS, and no verified Nakuru router/site configuration. No records were re-read or changed here. These external configuration gaps continue to block proof of multi-site production operation.

## RADIUS and voucher authorization

- HotSpot voucher credentials are represented by the `voucher_code` username. `RadiusAuthService` looks up the voucher, checks its status/expiry and site authorization, and binds/limits devices using the Calling-Station-Id MAC and available slots. The inspected voucher path does not compare a customer-visible password; RouterOS still requires the proper HTTP-CHAP response for the login request.
- Receipt-as-token is not implemented. Reusing receipt numbers as voucher codes would require an explicit unique-receipt policy, collision handling, migration/preflight for existing records, and strict linkage to the verified transaction/voucher/device. The receipt itself must never be treated as proof of payment.

## Confirmed findings and initial implementation targets

Confirmed software gaps:

1. Voucher issuance uses a random code rather than the verified M-Pesa receipt.
2. Receipt uniqueness and receipt-to-voucher resolution are absent.
3. A confirmed purchase status is not explicitly held until voucher settlement is complete before returning `voucher_code`.
4. The mounted HotSpot portal waits for a customer click to post the HTTP-CHAP login form.
5. No authenticated reconnect-by-receipt capability exists.
6. Repeated purchase POST requests have no idempotency key.
7. No portal-visible backend confirmation of RouterOS/RADIUS session acceptance exists.
8. The local relay implementation has not been shown to be deployed; the previously reported production attestation route is 404.

Confirmed existing protections to preserve:

- Server-side plan price lookup and site eligibility.
- Purchase-time trusted-device re-attestation.
- Provider status query and checkout-ID match before success.
- Callback idempotency and single settlement claim.
- Unique voucher code and purchase-transaction association.
- Voucher expiry/status/device-slot checks in RADIUS.
- RouterOS HTTP-CHAP calculation and preservation of octal bytes.

## Baseline test results

- Command: `node --test tests/hotspot-portal.test.js tests/hotspot-login-template.test.js tests/hotspot-api-request.test.js` — **26 passed, 0 failed, 0 skipped**.
- Command: `.\\.venv\\Scripts\\python.exe -m pytest tests/test_mpesa_callback.py tests/test_hotspot_purchase_voucher.py tests/test_hotspot_attestation.py` — **collection blocked**: all three test modules fail import with `ModuleNotFoundError: No module named 'mongomock_motor'`; 0 tests collected. This is not reported as a passing test.

## Not verified in this audit

- No production Render logs or deployment access were available in this session.
- No MongoDB connection, production payment, VPS relay request, MikroTik API query, RADIUS exchange, or end-to-end Internet access test was performed.
- No actual STK Push, callback, router login, Access-Accept, active HotSpot session, or accounting record was produced.

## Implementation boundary

The next local implementation stage should make receipt assignment and receipt uniqueness conditional on provider-verified success, keep the receipt mapped to the paid voucher and its device/site constraints, add safe idempotency for purchase initiation and receipt reconnect, gate status disclosure on completed settlement, and make the mounted portal submit its existing HTTP-CHAP form after settlement. It must not claim “connected” until a router-backed session check is available and verified. The relay 404, production router/NAS relationships, Nakuru inventory, and real browser-to-router behavior remain staging/production dependencies; they must not be papered over in frontend code.
