# DEVZEN CREATIONS WiFi — Architecture and Integration Audit

**Date:** 2026-10-31  
**Scope:** repository source and configuration in `app/`, `radius/`, `docker-compose.radius.yml`, portal/admin/hotspot frontend trees, tests, deployment examples, and the attached architecture prompt. No production server, router, Render, MongoDB, or VPS relay was contacted or changed. Environment values and secrets are intentionally excluded.

## Executive summary

The repository contains a real FastAPI/MongoDB billing application, three separate browser-facing frontend trees, an M-Pesa Daraja integration, RouterOS API/relay clients, and a FreeRADIUS REST integration. The captive hotspot flow is implemented in code from plan listing through payment, voucher creation, portal voucher submission, RADIUS authorization, and accounting. An HTTP success at any one stage does not prove a customer's internet session is working.

The strongest locally confirmed hard blocker is the FreeRADIUS Compose deployment: `docker-compose.radius.yml` requires a root `.env.radius`, but only `.env.radius.example` exists. The API also refuses all RADIUS internal requests with 503 when `RADIUS_API_SECRET` is unset. The repository's example RADIUS config uses a different backend hostname and VPN addresses from the attached architecture. Production runtime values therefore need to be checked against Render/VPS/MikroTik before claiming end-to-end service.

There is also frontend drift. Root `js/api.config.js` advertises a few explicitly unavailable portal endpoints (`voucherBalance`, `advertise`, and `session`); helper functions for these features reject with a clear unavailable message. The customer self-service portal tree calls `/api/v1/portal/*` routes that are implemented in `app/routes/portal.py`; self-registration is intentionally disabled until secure proof-of-control is available. The root captive portal uses the implemented `/hotspot` and `/vouchers` public routes. One standalone checkout implementation exposed a MAC input for “this device”; it now resolves the current device from RouterOS redirect context and asks the backend to validate the corresponding DHCP lease.

## Dependency map

```text
Documented RouterOS captive portal (/hotspot/)
  ├─ uses hotspot/js/app.js
  └─ secondary captive implementation remains directly available at /index.html

Secondary captive portal (/index.html / js/portal.js)
  ├─ GET /api/v1/hotspot/plans/public ─────────────┐
  ├─ POST /api/v1/hotspot/devices/lookup           │
  ├─ POST /api/v1/hotspot/purchase ──> Daraja STK │
  ├─ GET /api/v1/hotspot/purchase/status/{id}      │
  └─ GET /api/v1/vouchers/public/check/{code}      │
                                                    v
FastAPI routes -> domain services -> MongoDB collections
  ├─ hotspot_plans, mpesa_transactions, vouchers
  ├─ payments, invoices, customers, subscriptions
  └─ radius_users, radius_sessions, radius_accounting, routers, sites, ...

MikroTik HotSpot -> RADIUS UDP 1812/1813 -> FreeRADIUS rlm_rest
  ├─ POST /api/v1/radius/auth        -> voucher / RADIUS user decision in MongoDB
  └─ POST /api/v1/radius/accounting  -> session/counter updates in MongoDB

FastAPI RouterService -> RouterOS API (legacy/API) OR configured relay client -> MikroTik
  └─ DHCP lease lookup / health / active sessions / selected PPPoE operations
```

`app/services/router_service.py` selects RouterOS API or relay based on each saved router record. The relay client exists in source; the attached `isp-relay.service` is an external production service and was not inspected or touched. FreeRADIUS does not connect to that relay in this source configuration; it calls the FastAPI REST endpoints directly.

## Trace: one hotspot package purchase to RADIUS acceptance

1. `GET /api/v1/hotspot/plans/public` returns active global plans by default; a valid short-lived relay-attested context also allows plans for that site. The documented `/hotspot/` portal and the directly accessible `/index.html` portal render these live records.
2. The browser identifies the current hotspot client using MikroTik redirect query parameters when available. Otherwise it can submit a private IP or MAC to `POST /api/v1/hotspot/devices/lookup`. The backend checks that value against DHCP leases read from configured MikroTik routers; it does not accept an arbitrary MAC for a purchase without resolving it to a lease. Every saved router may be queried before a lease is found, so unreachable router API/relay credentials or routes can prevent resolution.
3. `POST /api/v1/hotspot/purchase` validates plan ID, Kenyan phone format, device type and MAC; re-resolves the MAC against DHCP leases; stores a pending M-Pesa transaction in MongoDB; then asks Daraja to initiate the STK push. The browser receives a `checkout_request_id` and polls the public status route.
4. Safaricom calls `POST /api/v1/mpesa/callback`. The backend queries the provider to verify the result before settling a success. A verified successful hotspot transaction calls `VoucherService.create_hotspot_purchase_voucher`, creates/reuses the voucher, binds it to the verified MAC, stores its code on the transaction and returns it from the purchase status endpoint. A provider callback by itself is not evidence that settlement or voucher creation succeeded.
5. The portal checks the code with `GET /api/v1/vouchers/public/check/{code}` and submits the voucher through the RouterOS captive login form (`hotspot/` templates and `js/mikrotik-login.js`). This is the point where browser success should not be shown as internet connectivity.
6. MikroTik sends an Access-Request to FreeRADIUS. FreeRADIUS forwards request attributes to `POST /api/v1/radius/auth` with `X-RADIUS-API-Secret`. The backend finds an active/used voucher, compares `Calling-Station-Id` to the voucher's bound MAC, checks expiry and data allowance, then returns Accept plus applicable rate/device/session limits. FreeRADIUS translates this JSON response to Access-Accept/Reject; MikroTik must have compatible RADIUS settings and receive the response.
7. Accounting Start/Interim/Stop goes through `POST /api/v1/radius/accounting`; the service upserts session records and updates voucher usage. Accounting is a later event and cannot establish that the initial login succeeded.

### Where this exact transaction can fail

- No matching/current DHCP lease, the RouterOS API/relay is unreachable, or saved router API credentials are invalid: device lookup/purchase fails before payment.
- Daraja credentials/environment/callback URL/provider connectivity mismatch: STK push or verified callback/settlement fails. Source supports reconciliation, but only live provider logs can confirm callback delivery.
- MongoDB connection/index/data mismatch: pending transaction, voucher or accounting writes fail.
- FreeRADIUS container cannot start without `.env.radius`; bad shared secrets or backend URL then block REST calls even if the API endpoints themselves work.
- MikroTik NAS address/secret/service configuration or VPN firewall/routing mismatch: request never reaches RADIUS or reply never returns.
- RouterOS login page is not actually serving the portal/login markup or does not preserve `link-login-only`, `chap-id`/`chap-challenge`, `mac`, and client IP context: voucher purchase may work while router login does not.
- RADIUS rejects because username/code casing or calling MAC differs, voucher is not active, or plan attributes/configuration are incompatible.
- Access-Accept may still not mean a usable Internet path if HotSpot profile, DNS, firewall, NAT, queues, or WAN routing is wrong.

## Confirmed from repository source

- FastAPI mounts auth, customers, service plans, subscriptions, invoices, payments, M-Pesa, RADIUS admin/internal, routers, vouchers, hotspot, portal, support, automation, packages, dashboard, sites, and system routes.
- Backend response helpers use `{success, message, data}`; list routes additionally expose pagination fields. Error handlers normalize API errors and validation errors.
- MongoDB is the backend's authoritative datastore; startup connects, builds indexes, starts scheduled billing/expiry/suspension/restoration/payment-reconciliation jobs, and shuts down cleanly.
- M-Pesa settlement is provider-query-verified and idempotency/reconciliation logic exists. A hotspot purchase is represented as a distinct transaction type from invoice/customer payments.
- Voucher RADIUS responses include speed, simultaneous-use, session timeout, data cap, accounting interval, and a `Class` linkage attribute.
- Router integrations include legacy RouterOS API, RouterOS REST, and relay clients. Router credentials/secrets are encrypted by the router service before storage.
- Existing tests cover hotspot verification/purchase, M-Pesa callback and idempotency, RADIUS REST payload and accounting idempotency, router API compatibility, auth, and related domain behavior.

## Confirmed integration gaps / defects

| Area | Finding | Effect |
|---|---|---|
| FreeRADIUS deployment | `docker-compose.radius.yml` names `.env.radius` as a required `env_file`; that file is absent in the repository. | Compose cannot start the RADIUS service until an operator creates it from the example with matching deployment values. |
| RADIUS API auth | `verify_radius_secret` returns HTTP 503 if the API's `RADIUS_API_SECRET` is blank. The local configured environment has no RADIUS API secret (presence only checked; value not read). | FreeRADIUS REST auth/accounting cannot succeed in that environment. A production environment may differ and needs a runtime check. |
| RADIUS example drift | `.env.radius.example` points to a different host and VPN private address range than the attached architecture. `.env.example`/production examples also contain illustrative rather than deployed addresses. | Copying examples unchanged will route to the wrong host/NAS and fail. Treat the attached network details as claims to verify on each live host, not as proof of current configuration. |
| Render blueprint identity | `render.yaml` names the service `devzen-creations`, while the attached deployment document names the hosted service `billing-system-5ckp.onrender.com`. | The repository cannot prove which Render hostname currently serves production. Reconcile the current Render dashboard, allowed-host and callback settings before deployment. |
| Render payment settings | `render.yaml` did not declare Daraja credentials, callback URL or environment even though settings support them. The blueprint now declares the environment, credentials and callback URL as Render-managed variables (`sync: false`), so the existing sandbox/production choice is explicit and is not guessed in code. | Render still needs actual values set in its environment; this repository change does not deploy or verify live STK/callback behavior. |
| Second-device limit | Voucher purchase now seeds a normalized `authorized_macs` list and remaining device slots. RADIUS claims each new MAC atomically up to the plan's `max_devices` cap; the public voucher check allows an already-used voucher to proceed to this authoritative RADIUS decision. FreeRADIUS has no configured session lookup for `Simultaneous-Use`. | Distinct-device allowance is enforced in MongoDB, including concurrent first logins. A maximum simultaneous session count is still not enforced; device allowance and simultaneous online-session count are separate policies. RouterOS behavior and pairing must be verified live. |
| PPPoE authentication | RADIUS accepts regular `User-Password` by string comparison, but CHAP/MS-CHAP fields are parsed without credential verification. | Home PPPoE credentials using CHAP/MS-CHAP are likely rejected (or need an explicit supported protocol path); validate against the actual RouterOS PPP profile. |
| Captive portal contracts | Root `js/api.config.js` lists `voucherBalance`, `advertise`, and `session` endpoints under `/api/v1/portal/*`; no matching backend routes exist. | Those links/forms cannot work as currently configured. Use an implemented endpoint or remove/label unavailable features; do not invent backend behavior. |
| Customer portal contracts | `app/routes/portal.py` implements `/me`, `/dashboard`, `/subscriptions`, `/usage`, `/notifications`, `/invoices`, `/payments`, M-Pesa invoice push, receipts, and support tickets. Customer login reuses role-aware `/api/v1/auth/login`; self-registration intentionally returns 503 pending identity verification. | The signed-in customer screens have corresponding routes. Public activation/registration is unavailable by design; show the support route instead of offering a broken signup flow. |
| Admin session action | `POST /api/v1/radius/sessions/{acct_session_id}/terminate` is the permission-gated admin route and matches the UI. Its service only marks `pending_disconnect`; it does not send a CoA command to MikroTik. | The UI can enqueue the marker, but a live session remains connected until a real CoA/disconnect transport is implemented and tested. |
| Frontend duplication | Root `js/`, `admin/js/`, `portal/js/`, `portal/assets/js/`, and `hotspot/js/` are separate implementations; root portal/hotspot pages and admin app are not the same as customer self-service portal. | Fixes can land in the wrong UI tree. Establish one deployed entry point and remove or clearly label stale app surfaces. |
| HotSpot success signal | Purchase status indicates payment/voucher settlement; it does not query active HotSpot session state. | UI must say payment confirmed/voucher ready unless an actual router session is observed. |
| Session disconnect | RADIUS disconnect endpoint is a database state update only, marked for future CoA. | UI must not claim the user was disconnected. |
| PPPoE credential auth | RADIUS schema receives CHAP/MS-CHAP fields, but `RadiusAuthService.authenticate` verifies regular `User-Password` by clear-text equality and does not validate CHAP/MS-CHAP response fields. | PPPoE users using MS-CHAP/CHAP may be rejected; this needs protocol-correct implementation or FreeRADIUS module-side validation before rollout. |

## Security and reliability observations

- The RADIUS internal endpoints are secret-gated, but their availability depends on a configured matching API secret, and they should additionally be network-restricted to the relay/RADIUS host where the deployment allows it.
- FreeRADIUS `Simultaneous-Use` requires configured session/accounting lookups; the checked-in `default.template` has no `session` section. See the [FreeRADIUS 3.2.9 simultaneous-use guide](https://www.freeradius.org/documentation/freeradius-server/3.2.9/howto/simultaneous_use.html).
- The public purchase status endpoint is keyed by opaque M-Pesa CheckoutRequestID. Limit/rate protect it at the edge and avoid exposing payment phone or other personal data (the current status response only returns status, voucher code, result description).
- DHCP-based verification is better than trusting a browser MAC, but an authenticated/observed captive request context should be correlated to the router lease. A user-supplied MAC that matches some other current lease is not cryptographic proof that the purchaser controls that device.
- The callback itself is public by necessity; source performs provider status querying before success settlement, which is the important control. Live callback URL reachability/provider credentials remain unverified.
- Do not expose `.env`, router credentials, RADIUS secrets, M-Pesa secrets, or callback payloads containing customer data in logs or audit reports.

## Work order

1. Fix/verify each active frontend's real API paths, request fields, response envelopes, auth/refresh behavior, and clear unsupported pages/actions.
2. Verify automatic client IP/MAC correlation through the actual RouterOS login redirect and DHCP lease lookup.
3. Verify M-Pesa initiation, provider verification, idempotent settlement and voucher entitlement as one transaction.
4. Make FreeRADIUS deployable/configured and validate Access-Request to Accept/Reject over the VPN.
5. Verify RouterOS captive redirect, hosted page, CHAP flow and post-login Internet path.
6. Validate Start/Interim/Stop accounting and usage totals.
7. Confirm second-device policy and pairing behavior against actual RouterOS constraints.
8. Correct CHAP/MS-CHAP and subscription synchronization for PPPoE.
9. Implement customer/admin pages only for real backend capabilities and state.
10. Complete visual transformation after the integrations above work.

## Repairs applied during this audit

- Dedicated checkout no longer asks for the current device MAC. It uses the RouterOS-provided IP first (or router-provided MAC), verifies it through the backend DHCP lease lookup, and only shows a MAC field for TV/other-device targeting.
- Free-trial requests now accept hotspot IP or MAC context, resolve that context against configured router DHCP leases, and issue the voucher only for the resolved MAC. Both the current root captive portal and the compatibility `/hotspot/` page send the IP when it is available.
- Daraja HTTP calls now run outside FastAPI's async event loop so a slow provider response does not block unrelated API requests.
- The Render blueprint now declares M-Pesa environment and externally supplied credentials/callback URL; values remain unverified until checked in the Render dashboard.
- Automatic network retry is now limited to GET/HEAD requests in the root and admin API clients. Retrying a timed-out purchase/payment POST could create a second STK request or duplicate an admin write without backend idempotency keys.
- Paid vouchers now track authorized station MACs and remaining device slots. The RADIUS auth path atomically claims one slot per new device; same-device reauth and paired devices remain allowed, and devices over the plan cap are rejected. Free-trial vouchers stay pinned to their originating device. Purchase retry/race recovery also applies the device binding before returning the existing voucher.
## Runtime verification still required

This source audit did not connect to Render, live MongoDB, Daraja, FreeRADIUS, the relay, VPN or RB951 router. To call the system end-to-end working, run one low-value controlled voucher purchase and correlate the same checkout ID/voucher code/MAC across backend logs and MongoDB, then capture the corresponding RADIUS Access-Request/Accept and Accounting Start/Interim/Stop plus MikroTik active-session/byte counters. None of those production actions were performed by this audit.





