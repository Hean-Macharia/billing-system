# Phase 1 — Frontend and API integration report

**Date:** 2026-10-31  
**Scope:** Repository source only. No request was made to Render, MongoDB, MikroTik, FreeRADIUS, or the VPS. No production settings or secrets were read or changed.

## Summary

This repository does not have one uniquely deployed captive portal. The Docker image copies the repository, and `app/main.py` mounts the `hotspot/`, `admin/`, and `portal/` directories while also serving an allowlisted set of root pages. The RouterOS setup guide tells the router to send customers to `/hotspot/`; that is the captive entry point prescribed by the repository documentation. The site root instead redirects to `/index.html`, which is a second captive portal implementation with a separate checkout flow. Source cannot establish which URL the live MikroTik currently uses.

The API contracts used by the current HotSpot page, standalone checkout, admin app, and customer self-service app match the corresponding FastAPI routes for the traced requests. Two misleading/current-client frontend behaviors were corrected in the compatibility HotSpot page and root captive portal: the public validity check is no longer called a balance lookup, and a redirect-supplied client MAC is now checked through the backend DHCP-lease lookup before the UI labels it verified.

Payment status screens say payment is confirmed and a voucher is ready; they explain that MikroTik/RADIUS must still accept the voucher before Internet access starts. The captive pages do not claim that a paid customer is already online.

## Deployed entry points and frontend roles

| URL / files | Role | Loaded application code |
|---|---|---|
| `/` → `/index.html` | Alternate/current root captive portal | `/js/mikrotik-login.js`, `/js/portal.js` (ES module), `/js/animations.js` (ES module). Its plan purchase CTA links to `/checkout.html`. |
| `/hotspot/` | RouterOS captive portal prescribed by `docs/mikrotik-routeros6.md` | `/hotspot/mikrotik-login.js`, `/hotspot/js/app.js`; styling from `/hotspot/css/hotspot.css`. Purchase and polling are in the page modal. |
| `/checkout.html` → `/payment-status.html` → `/voucher.html` | Standalone purchase, payment status and voucher login flow used by the root portal | `/js/checkout.js`, `/js/payment-status.js`, `/js/mikrotik-login.js`, `/js/voucher.js`, and shared `/js/api.js`/`api.config.js`. |
| `/portal/` | Authenticated customer self-service (billing account, not the captive splash page) | `/portal/js/auth.js`, `/portal/js/shell.js`, `/portal/js/pages.js`, `/portal/js/api.js`, `/portal/js/api.config.js`. Page HTML imports these modules. |
| `/admin/` | Staff administrator login and management app | `/admin/js/login-page.js`, `/admin/js/auth.js`, `/admin/js/api.js`, `/admin/js/api.config.js`, `app-shell.js`, and page modules under `/admin/js/`. |

`render.yaml` selects the root `Dockerfile`; the Dockerfile copies the repository into the image and runs `uvicorn app.main:app`. `app/main.py` mounts `admin`, `portal`, `hotspot`, `css`, `js`, and `assets`, and mounts the restricted `PublicFrontendFiles` at `/`. The root mount permits its explicit page allowlist plus `css/`, `js/`, and selected `assets/` images/fonts; it does not expose the `frontend/` directory.

Root convenience pages such as `/dashboard.html` redirect into `/admin/`. `admin/index.html` is the admin sign-in page and `/admin/dashboard.html` is the dashboard. `portal/index.html` is customer sign-in; `portal/dashboard.html` is the customer account home. The attached architecture prompt is not proof of which hostname/path is currently configured on the live router.

## Frontend-to-backend dependency map

```text
RouterOS captive redirect (docs prescribe /hotspot/)
  -> /hotspot/index.html
     -> GET  /health/ready
     -> GET  /api/v1/hotspot/plans/public
     -> POST /api/v1/hotspot/devices/lookup
     -> POST /api/v1/hotspot/purchase
     -> GET  /api/v1/hotspot/purchase/status/{checkout_request_id}
     -> GET  /api/v1/vouchers/public/check/{code}
     -> POST /api/v1/hotspot/free-trial
     -> RouterOS /login (HTTP-CHAP form) -> FreeRADIUS -> /api/v1/radius/auth

Site root captive portal
  -> /index.html -> /js/portal.js
     -> same public plans/device/purchase/status/voucher/trial routes
     -> /checkout.html -> /payment-status.html -> /voucher.html

Customer self-service /portal/
  -> /api/v1/auth/login|refresh|logout
  -> /api/v1/portal/me|dashboard|subscriptions|usage|notifications
  -> /api/v1/portal/invoices|payments|payments/stk-push
  -> /api/v1/portal/payments/{id}/receipt
  -> /api/v1/portal/support/tickets[/{id}/reply]

Admin /admin/
  -> /api/v1/auth/*, dashboard, customers, services, subscriptions, invoices,
     payments, mpesa, vouchers, hotspot plans, routers, RADIUS, support,
     automation and sites routes as listed in admin/js/api.config.js.
```

## API contract comparison

### Captive HotSpot and checkout

| Frontend call | Backend route / contract | Result |
|---|---|---|
| `GET /health/ready` | `app/main.py`, GET; returns `{success,message,data}` and 503 if DB is not ready | Match. The chip indicates API/database readiness, not router Internet reachability. |
| `GET /api/v1/hotspot/plans/public` | `app/routes/hotspot.py`; optional `site_id`; returns `data` array with `_id`, `price`, `duration_hours`, data, speed and device count | Match. |
| `POST /api/v1/hotspot/devices/lookup` | `HotspotDeviceLookupRequest`; JSON `ip_address` or `mac_address`; returns resolved DHCP lease in `data` | Match. Client IP/MAC is not directly trusted as a verified device until backend lease lookup succeeds. |
| `POST /api/v1/hotspot/purchase` | `HotspotPurchaseRequest`; JSON `plan_id`, `phone_number` (`254` + 9 digits), `device_type`, `device_mac`; response `data.checkout_request_id` | Match. Backend rechecks the MAC against router leases. |
| `GET /api/v1/hotspot/purchase/status/{id}` | Returns `data.status`, `voucher_code`, `result_desc` | Match. A successful payment response with voucher does not report a live router session. |
| `GET /api/v1/vouchers/public/check/{code}` | Returns validity/status and voucher facts; no remaining-data-balance endpoint | Path and response envelope match. “Check balance” in `/hotspot/` was inaccurate; now labeled “Check voucher status.” |
| `POST /api/v1/hotspot/free-trial` | JSON `ip_address` or `client_mac`; backend resolves the lease before issuing | Match. |
| `POST /api/v1/portal/advertise`, `GET /api/v1/portal/voucher/balance`, `GET /api/v1/portal/session` | No matching FastAPI routes | Not supported. Root API helpers reject explicitly; advertising enquiry uses a prefilled mailto form instead. No customer should be told those API-backed operations succeeded. |

### Customer self-service `/portal/`

The page modules use `GET /api/v1/auth/me` for authentication, and the implemented `GET /api/v1/portal/*` resource routes for dashboard, subscriptions, usage, notifications, invoices, payments and tickets. Invoice payment submits `POST /api/v1/portal/payments/stk-push` with `invoice_id` and `phone_number`; the backend checks invoice ownership and derives the amount. Receipt download uses `GET /api/v1/portal/payments/{payment_id}/receipt`. These paths and request fields match `app/routes/portal.py` and its request schemas.

One response-field mismatch remains in the customer payment page: after STK initiation it polls `GET /api/v1/portal/payments` looking for `mpesa_checkout_request_id` on a payment. The current settlement path creates a `PaymentCreate` without that field, and the payment API response schema also omits it. Therefore that UI cannot reliably associate the new payment with the returned checkout ID; it may keep saying pending after settlement. The endpoint and POST request fields match, but this follow-up status strategy does not. Fixing it requires a payment-status contract/backend decision, so it is deliberately deferred under this phase's no-payment-changes rule.

`POST /api/v1/portal/auth/register` is intentionally a 503 response in the backend. The deployed customer login page directs users to contact the provider; it does not offer registration as working. The customer portal's “Service active” label reflects the subscription record, not a live MikroTik session indicator.

### Administrator `/admin/`

The active `admin/js/api.config.js` paths match the FastAPI router prefixes and the page modules use the backend's documented verbs for the inspected actions: GET lists, POST creates/actions, PATCH updates/status, DELETE removals. Staff report/reseller pages explicitly show unavailable capabilities where the API has no reseller, SMS, expense or churn endpoints. The available report view calculates statistics from loaded payment/customer records; it does not call nonexistent revenue/churn routes.

M-Pesa staff transaction requests use `/api/v1/mpesa/*`; hotspot checkout does not use those protected staff routes. RADIUS routes are admin-only and distinct from internal FreeRADIUS REST routes. No Phase 1 change was made to those payment or RADIUS contracts.

## Contract mismatches, unsupported behavior, and minimal changes

| Finding | Evidence / effect | Phase 1 handling |
|---|---|---|
| Repository docs disagree on captive root | `docs/installation.md`/older prose says `/` redirects to `/hotspot/`; current `app/main.py` redirects `/` to `/index.html`. MikroTik guide separately prescribes `/hotspot/`. Live configured URL cannot be inferred from source. | Reported; no routing/deployment behavior changed. Reconcile the RouterOS `login.html` destination against the URL staff intend to use. |
| Two captive portal implementations | `/hotspot/` uses `hotspot/js/app.js` and embedded purchase; `/` uses root `js/portal.js` and standalone checkout pages. They are both served but can diverge. | Both retained. Phase 1 applies the two safe UX/verification fixes in both. |
| Voucher “balance” label overstated endpoint | Public voucher check has no remaining byte/time balance field; it returns validity, status, expiry and plan limits. | Renamed the operation and copy to voucher status in both captive implementations. |
| Redirect MAC was shown as verified before lease lookup | Captive portal accepted query MAC into local verified state; only purchase later rechecked it. | Both captive JS implementations now POST the received MAC to `/hotspot/devices/lookup` before showing verification success. This remains automatic; current phone/laptop customers are never asked to type a MAC. |
| Customer invoice STK status lookup uses a field absent from API response | Customer page matches payment history by `mpesa_checkout_request_id`; settlement does not persist that field through `PaymentCreate`, and `PaymentResponse` does not return it. | Recorded for payment-phase repair. No payment or settlement code changed in Phase 1. |
| Customer Internet-connected success | Purchase status is a payment/voucher result. MikroTik login/Access-Accept and usable Internet are later stages. | Confirmed existing copy says voucher ready and access begins after router/RADIUS acceptance. No payment-success-only “You are online” message found in the captive checkout paths. |
| Unsupported captive endpoints | `/api/v1/portal/voucher/balance`, `/portal/advertise`, `/portal/session` do not exist. `js/api.config.js` marks these as unsupported; advertisement page submits email via mailto. | No endpoint guessed or added. Unsupported helper functions remain explicit failures; end-user balance wording corrected. |
| Unsupported admin analytics/services | No resellers, SMS dispatch, expenses, churn analytics or plan performance API in current FastAPI routes. | Active admin pages mark these unavailable or only calculate from loaded real data. Avoid using the old config constants as evidence that routes exist. |
| Duplicate/obsolete frontend trees | `frontend/` copies root HTML but is not mounted/allowlisted. `admin/assets/js/` and `portal/assets/js/` have no references from the active HTML. Root-level admin convenience HTML redirects to `/admin/`. | Listed as legacy/unused; not deleted. `/hotspot/` remains an active compatibility/deployment entry point per RouterOS docs. |

## Recommended minimal follow-up

1. Confirm the deployed RouterOS `login.html` points to the intended host and `/hotspot/` or `/` captive app. Keep the existing relay architecture unchanged.
2. In a local/staging environment, trace one synthetic or low-value test purchase through checkout ID → settled transaction → voucher → public voucher check → RouterOS login → RADIUS Access-Accept → accounting session. Do not infer production state from this repository.
3. Consolidate captive UI only after the owner confirms which of the two served implementations is deployed. Until then, keep both functional and test both.
4. Treat voucher check as validity/expiry only. A true remaining balance requires an existing backend contract; none is implemented here.
5. Keep unsupported resellers/SMS/advanced report controls unavailable until their APIs exist.

## Tests required for the frontend/API boundary

- Node regression test for RouterOS redirect parsing and HTTP-CHAP form creation (`tests/hotspot-portal.test.js`).
- Browser/manual request inspection for each captive entry point: plan GET, current client IP/MAC lookup, purchase payload, status polling, voucher check, and no false online state.
- Backend tests for hotspot device lookup, purchase voucher settlement, voucher public check, and free-trial schema/route.
- Customer portal route tests for JWT role scoping, invoice-owned STK request, payment list/receipt, usage, and support ticket create/reply.
- Admin route tests for list pagination, CRUD action methods, permissions and the unavailable-page controls.
- Deployment smoke checks against a non-production environment for `/`, `/hotspot/`, `/admin/`, `/portal/`, static modules and `/health/ready`.

## Phase 1 changes and constraints

Changed only `hotspot/js/app.js`, `js/portal.js`, and this report. Did not change payment settlement, RADIUS authorization/accounting, router or relay transport, Render settings, database settings, or production systems during this phase. Existing unrelated working-tree changes from earlier work were left as-is.

Source-level verification does not prove a live MikroTik-to-Internet session. A real router login and usable Internet path remain required before calling the ISP service operational.
