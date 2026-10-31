# DEVZEN CREATIONS Frontend Rebuild — Phase A Repository Audit

**Audit date:** 2026-10-31  
**Scope:** checked-in repository source only. No Render service, production MongoDB, M-Pesa, MikroTik, FreeRADIUS host, VPS, or relay was contacted. No frontend/backend implementation files were changed during Phase A.

## Executive summary

The repository already contains three distinct frontend applications configured to be served, but it also contains duplicate and preview implementations that make it easy to edit the wrong files:

- `/hotspot/` is the documented MikroTik captive portal and is mounted from `hotspot/`.
- `/admin/` is the staff application and is mounted from `admin/`; its index is the login page, while resource screens are separate HTML files.
- `/portal/` is customer self-service and is mounted from `portal/`.
- The root URL redirects to `/hotspot/`. A second public captive/checkout implementation remains directly served from root HTML/`js/` files.
- `frontend/` is documented as a preview copy and is not mounted by FastAPI. `admin/assets/` and `portal/assets/` contain an older parallel SPA implementation; deployed page script tags use `admin/js/` and `portal/js/` instead.

FastAPI exposes **146 OpenAPI operations across 112 paths**. Four additional secret-gated FreeRADIUS routes are intentionally omitted from OpenAPI. The full method/path/request-schema/query/path-input/response inventory is in [frontend-endpoint-inventory.md](frontend-endpoint-inventory.md).

The backend has working contracts for core authentication, staff resources, HotSpot plans/purchases/vouchers, customer self-service, sites/routers, and RADIUS records. It intentionally disables customer self-registration (HTTP 503) until identity proof is added. No password-reset endpoint, customer-visible package catalog/renewal endpoint, advertising endpoint, voucher balance endpoint, dedicated reports endpoint, reseller endpoint, or general SMS send endpoint is present. Those must be shown as unavailable or treated as backend dependencies; a frontend must not fabricate them.

**Phase A is complete.** No redesign or frontend replacement has started. The next safe step is the shared foundation, using only the contracts in the endpoint inventory and preserving unsupported feature states.

## 1. Repository and change-safety baseline

The repository contains Python FastAPI/MongoDB backend code, multiple browser applications, Docker/Render configuration, a FreeRADIUS configuration tree, tests, and Phase 1–5 audit documents. The working tree already has numerous Phase 1–4 modifications and untracked reports/tests. These changes were observed and preserved; this audit did not reset, stage, commit, or overwrite them.

Relevant source groups:

- Backend: `app/routes/`, `app/schemas/`, `app/models/`, `app/services/`, `app/integrations/`.
- Deployed frontends: `hotspot/`, `admin/`, `portal/`, plus root `index.html`, checkout/status/voucher pages and root `js/`, `css/`, `assets/`.
- Preview/parallel code: `frontend/`, `admin/assets/`, `portal/assets/`.
- Deployment: `app/main.py`, `Dockerfile`, `render.yaml`, `docker-compose.prod.yml`, `docker/nginx/production.conf`, and `docker/nginx/snippets/apps-locations.conf`.

## 2. Static routing and actual entry points

### FastAPI / Render path

`app/main.py` mounts `admin/`, `portal/`, `hotspot/`, root `css/`, `js/`, and `assets/`. At `/`, `PublicFrontendFiles` serves only allowlisted root pages and safe asset types; it rejects `/api/` paths and path traversal. The root endpoint redirects to `/hotspot/`. `/admin-login.html` is an allowlisted root page which redirects to `/admin/index.html`.

| URL | Source / role | Page code loaded |
|---|---|---|
| `/hotspot/` | `hotspot/index.html`; documented captive entry | `hotspot/mikrotik-login.js`, `hotspot/js/app.js`; CSS in `hotspot/css/` |
| `/` | Redirects to `/hotspot/` | — |
| `/index.html` | Secondary captive marketing/package portal | root `js/mikrotik-login.js`, `js/portal.js`, `js/animations.js` |
| `/checkout.html` | Secondary portal checkout | root `js/checkout.js` |
| `/payment-status.html` | Standalone purchase-status screen | root `js/payment-status.js` |
| `/voucher.html` | Voucher validation/login compatibility screen | root `js/mikrotik-login.js`, root `js/voucher.js` |
| `/admin/` and `/admin/index.html` | Staff login | `admin/js/login-page.js` |
| `/admin/dashboard.html`, `/admin/customers.html`, etc. | Staff application screens | matching `admin/js/*.js` modules and `admin/js/app-shell.js` |
| `/admin-login.html` | Compatibility entry | redirects to `/admin/index.html` |
| `/portal/` and `/portal/index.html` | Customer login | `portal/js/auth.js` inline module import |
| `/portal/dashboard.html`, `/portal/subscription.html`, etc. | Customer self-service | `portal/js/pages.js` and `portal/js/auth.js` |

The exact served frontend depends on which URL an operator/MikroTik configures. Documentation names `/hotspot/` as the captive portal; the second root captive flow is intentionally retained. Do not remove either during the redesign.

### Docker/Nginx path

The production Compose definition mounts `admin/`, `portal/`, and `hotspot/` as read-only Nginx directories. Nginx routes `/api/` to FastAPI, sends `/` to `/hotspot/`, and aliases the three app paths. The config hides the internal RADIUS auth/accounting URLs from public HTTP at the proxy. Render instead uses the Dockerized FastAPI application and its static mounts. This audit did not inspect Render's live deployed artifact or settings.

### Duplicate/stale implementations to manage carefully

- `frontend/` is a preview copy; `frontend/README.md` says root canonical pages/assets are served by FastAPI. It is not among the FastAPI static mounts.
- `admin/assets/js/` includes a hash-routed SPA and page modules, but the mounted `admin/*.html` pages load `admin/js/*.js`; treat `admin/assets/` as legacy until a later comparison confirms otherwise.
- `portal/assets/js/` includes a separate hash-routed app; mounted portal pages use `portal/js/`.
- Root `js/` is a secondary public captive flow, not the mounted `/hotspot/` implementation.
- Admin shared styles/scripts coexist with legacy assets. Refactor planning must identify exact imports before moving or removing any file.

## 3. Authentication and authorization contracts

- Admin/staff login is `POST /api/v1/auth/login` with `UserLogin {email, password}`. It returns token data consumed by the deployed admin client. The admin client stores access and refresh tokens in localStorage (`dz_token`, `dz_refresh_token`), sends Bearer auth, attempts one refresh after 401, then logs out/redirects. The backend is bearer/JWT-based; the inspected routes do not implement an HttpOnly cookie auth session. Do not assume cookie auth without a backend change.
- The customer portal reuses `/api/v1/auth/login`; it does not have a separate customer login endpoint. It stores its own bearer/refresh values in localStorage (`dz_portal_token`, `dz_portal_refresh_token`) and loads identity through `GET /api/v1/portal/me`.
- Token storage in localStorage has XSS exposure. The Phase A rebuild should retain backend compatibility and minimize injection risk (safe DOM rendering, strict escaping/CSP review); switching to HttpOnly cookies requires a deliberate backend/auth design, not a frontend-only change.
- `GET/PATCH /api/v1/auth/me`, `POST /api/v1/auth/change-password`, refresh, and logout exist. Staff list/read/status endpoints are under `/api/v1/auth/users` and permission-gated.
- `POST /api/v1/auth/register` is a staff/user registration route with a role field; it must not be exposed as an unrestricted public staff signup flow.
- `POST /api/v1/portal/auth/register` exists but deliberately returns 503. The generic `POST /api/v1/auth/register` can create a CUSTOMER user, but the service stores a user identity only; source does not show it verifying ownership of an existing ISP customer record or linking a subscriber/customer account. The current portal therefore tells customers to contact the provider. Do not present the disabled portal registration path as working signup, or assume generic user creation activates customer self-service.
- Backend dependencies (`require_permission`, customer identity dependency, and `X-RADIUS-API-Secret`) are authoritative. Hiding a button in the UI is not authorization.

## 4. API coverage by product area

See the endpoint inventory for all requests and fields. Main route families:

| Product area | Existing backend contract | Notes / UI constraint |
|---|---|---|
| Auth | `/api/v1/auth/*` | Bearer/refresh JWT; role and permission dependencies. |
| Admin dashboard | `GET /api/v1/dashboard/summary` | Uses live summary; no fabricated KPI values. |
| Customers | `/api/v1/customers` | CRUD/status/package assignment; backend filters/page/limit. |
| ISP service plans | `/api/v1/services` | Recurring ISP product plans; distinct from HotSpot vouchers. |
| Product packages | `/api/v1/packages` | Separate package model; staff authorization. |
| Subscriptions | `/api/v1/subscriptions` | CRUD/cancel/install/invoice operations. |
| Invoices/payments | `/api/v1/invoices`, `/api/v1/payments` | Includes manual payment records/confirm; M-Pesa callback and verification are backend-owned. |
| Daraja | `/api/v1/mpesa/stk-push`, `/query`, callback/reconcile/transactions | Never call Daraja directly from browser; no real STK in tests. |
| HotSpot plans/purchase | `/api/v1/hotspot/*` | Public catalog, device lookup/attestation, purchase/status/free trial; staff plan CRUD. |
| Vouchers | `/api/v1/vouchers/*` | Batch generation/export/print, activation/disable, public validity check. No separate voucher-balance endpoint. |
| Routers | `/api/v1/routers/*` | CRUD, test/health/interfaces/active users/DHCP/queues/PPPoE endpoints. Router credentials are not returned. |
| Sites | `/api/v1/sites/*` | CRUD/status; backend uses sites in router/NAS/package contexts. |
| RADIUS admin | `/api/v1/radius/nas`, `/users`, `/sessions` | JWT/permission-protected staff APIs. |
| FreeRADIUS internal | `/api/v1/radius/auth`, `/accounting`, `/sessions/online`, `/sessions/{id}/disconnect` | Secret-gated, excluded from OpenAPI; not browser APIs. The disconnect endpoint marks pending disconnect and does not send MikroTik CoA. |
| Customer portal | `/api/v1/portal/*` | Profile read, dashboard, subscriptions, usage, notifications, invoices, payments, STK for invoice, receipt, tickets. Registration is disabled. |
| Support | `/api/v1/support/tickets`, `/api/v1/portal/support/tickets` | Staff and customer ticket routes exist. |
| Automation | `/api/v1/automation/*` | Staff operational controls; do not surface destructive/financial triggers casually. |
| Reports | `GET /api/v1/dashboard/summary` and source records | No dedicated `/api/v1/reports/*` endpoints for date-based revenue/churn/export. A UI may report only derived values from complete fetched records and label scope; do not claim unavailable analytics. |

## 5. Frontend/API mismatches and backend dependencies

### Existing APIs with corresponding frontend use

The current primary HotSpot, root captive checkout, admin and signed-in portal clients generally use the route families present in FastAPI. Phase 1 corrected several prior mismatches and retained RouterOS HTTP-CHAP parsing/login behavior. Phase 4 added FastAPI-side attestation and opaque context use. This is source-level correspondence, not live API verification.

### Unsupported requested functionality

- No reseller API exists.
- No standalone SMS send or SMS-management endpoint exists; notification records/read endpoints do not prove SMS delivery.
- No dedicated revenue/churn/report endpoint exists.
- No advertising enquiry endpoint exists. Existing portal uses contact/email fallback.
- No voucher balance route exists; public voucher check reports validity/status/expiry, not remaining balance.
- No portal session/current client IP route exists.
- Customer portal self-registration is intentionally disabled with HTTP 503; no password reset/OTP contract was found.
- No customer-scoped package catalog or new subscription checkout endpoint exists. Customer M-Pesa payment is invoice-scoped (`POST /api/v1/portal/payments/stk-push`).
- No setting persistence API for arbitrary business branding/notification preferences was found. Do not pretend a browser-local appearance toggle updates ISP backend settings.
- PPPoE UI actions exist through router API endpoints, but current backend/RADIUS auth protocol concerns documented in prior audit remain. Do not represent unsupported CHAP/MS-CHAP paths as working.
- RADIUS termination route returns a pending/disconnect marker; no CoA transport is present in this route. UI must say queued/requested, not disconnected.

### Contract/schema observations for later integration

- Shared API responses are `{success, message, data}`; list routes commonly add pagination metadata. Some portal receipts return PDF bytes; voucher export/print may return files or structured data and must be checked from route implementation before setting download behavior.
- Pagination is endpoint-specific (`page`, `limit`); filters use names such as `status_filter`, `site_id`, `package_type`, `overdue_only`, and `customer_id`. Do not standardize client query names without matching route signatures.
- `/api/v1/routers/{router_id}/pppoe-users` accepts `username`, `password`, and `profile` as query parameters in the current route signature. This risks credential exposure through URL/proxy logs. Avoid exposing this operation in the UI until backend contract is safely changed or a secure request-body contract is added and approved.
- A package record (`/packages`) and ISP service plan (`/services`) and HotSpot plan (`/hotspot/plans`) are different resources with different schemas. The UI must present them as distinct service types or use the correct backend resource.
- Payment initiation is not payment settlement. Browser success must depend on backend transaction status after provider verification; voucher generation remains server-side.
- HotSpot site-specific catalog/purchase uses `X-Hotspot-Context`; browser-supplied router/site IDs are not authoritative. External relay attestation remains unimplemented per Phase 4/5 reports, so live site-specific flows are not verified.

## 6. Design rebuild implications

The requested blue/white direction differs from existing red branding. The design refresh can be implemented in CSS/HTML after Phase A without touching backend models. Preserve consistent DEVZEN CREATIONS identity while applying blue as the new visual accent; do not modify payment, RouterOS, RADIUS, relay, or auth behavior during visual work.

Recommended shared foundation:

1. Define shared CSS tokens and accessible components that can be consumed by all three existing mount roots without moving their entry files.
2. Consolidate duplicated API handling only after compatibility tests confirm the three applications' base-URL and auth differences. Keep captive requests public and context-bearing; keep admin/customer JWT scopes distinct.
3. Build HotSpot mobile screens using live plan/catalog responses, automatic RouterOS context, `X-Hotspot-Context`, current purchase/status endpoints, and voucher/CHAP contracts.
4. Build staff screens on existing permission-gated routes; label missing capabilities and ensure service plans, product packages and HotSpot plans are not conflated.
5. Build customer self-service on `/api/v1/portal/*`; present registration/password-reset as unavailable until backend identity proof exists.
6. Add frontend tests/mocks for the actual endpoints and ensure payment tests cannot contact Daraja.

## 7. Test and verification scope

Phase A used source inspection and generated the endpoint inventory from `create_app().openapi()`. No frontend files were changed and no test suite was run as part of this audit.

The existing Phase 1–4 reports list previously executed regression results. Those results are not repeated here as Phase A tests. Before implementation merges, run JavaScript syntax/portal tests, relevant backend contract tests, static routing tests, and `git diff --check`. Live authentication, M-Pesa, RouterOS, RADIUS, relay, and Internet-access tests remain separate controlled deployment tasks.

## 8. Phase A completion and next gate

**Completed:** repository/static deployment audit, actual frontend entry point and duplicate tree identification, authentication flow inspection, OpenAPI route/schema inventory, hidden RADIUS route inventory, and backend-gap list.

**Not started:** shared CSS/JS replacement, HotSpot redesign, admin redesign, customer portal redesign, endpoint wiring changes, backend modifications, deployment, or production testing.

The frontend rebuild can now proceed with existing routes as the source of truth. Any feature marked unsupported above must remain clearly unavailable until a backend endpoint is implemented in a separately approved backend phase.
