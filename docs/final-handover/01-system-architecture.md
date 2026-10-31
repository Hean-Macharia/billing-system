# 01 — System architecture

## Scope and evidence

This handover describes the local repository at `main` on 2026-10-31. It reflects source inspection and automated local tests. No live Render, MongoDB, Daraja, VPS, FreeRADIUS host, or MikroTik was contacted.

## Components

- **API:** Python 3.12 / FastAPI, Pydantic, async MongoDB access through Motor. Route modules live in `app/routes/`; domain logic in `app/services/`; persistence records in `app/models/`.
- **Database:** MongoDB collections for users, customers, services/packages, subscriptions, invoices, payments, vouchers, sites, routers, RADIUS records, M-Pesa transactions, and trusted HotSpot contexts/nonces. Startup creates declared indexes.
- **Browser applications:** `hotspot/` is the documented captive portal; `admin/` is staff login/management; `portal/` is customer self-service. FastAPI also serves a retained root captive/checkout flow. `frontend/` and `admin/assets/`/`portal/assets/` include preview or legacy implementations and are not the authoritative mounted app entry points.
- **Network:** RouterService uses configured RouterOS integrations/relay; FreeRADIUS REST calls the API's secret-gated RADIUS endpoints. Relay source copy and mocked tests are in `phase-j-relay-source/`; no deploy took place.
- **Payments:** Daraja STK push and query. Provider verification, idempotent settlement, voucher issuance, and reconciliation are backend responsibilities. No live payment test was performed. No Pesapal implementation was found.

## Serving paths

FastAPI mounts `/hotspot/`, `/admin/`, `/portal/` and selected root assets; `/` redirects to `/hotspot/`. Production Compose also defines Nginx routing and read-only app mounts. Render builds through `Dockerfile`; `render.yaml` is a blueprint, not proof of live service configuration. See `docs/frontend-rebuild-audit.md`, `docs/frontend-endpoint-inventory.md`, and `10-deployment-guide.md`.

## Critical boundaries

Source-level endpoint tests do not prove router reachability, RADIUS exchange, successful HotSpot login, or Internet routing. Current relay attestation has a single-router code path but awaits verified router/site IDs; Nyaururu/Nakuru mapping is not established in available records. Treat site-restricted HotSpot operations and live authentication as blocked pending staging verification.
