# DEVZEN CREATIONS ISP Billing System

A production-oriented ISP billing, AAA, customer, subscription, hotspot, voucher, billing, and MikroTik management platform built with FastAPI and MongoDB.

## Overview

This project is designed for a Kenyan ISP serving multiple sites and supporting:

- PPPoE and HotSpot access
- multi-site operations
- recurring billing and subscriptions
- M-Pesa payment flows
- RADIUS-based authorization and accounting
- FreeRADIUS service for MikroTik HotSpot voucher authentication
- customer portal and admin workflows
- router monitoring and session tracking

## Key stack

- Python 3.12+
- FastAPI
- Uvicorn
- MongoDB with Motor
- Pydantic and Pydantic Settings
- JWT authentication
- Docker and Docker Compose

## Project layout

- `app/` - application source code
- `docs/` - setup, deployment, and architecture guides
- `tests/` - automated tests
- `docker/` - deployment support files
- `radius/` - RADIUS-related configuration assets
- `admin/` and `portal/` - admin/customer web assets

## Web interfaces

The static interfaces are served directly by FastAPI; no frontend build or npm install is required. Start the API with the command above, then open:

- Staff console: `http://localhost:8000/admin/`
- Customer account: `http://localhost:8000/portal/`
- MikroTik hotspot captive portal: `http://localhost:8000/hotspot/`

The staff and customer screens use the API already in this repository. Staff API paths and browser configuration live in `admin/js/api.config.js`; customer portal paths live in `portal/js/api.config.js`. Each can store an API origin in browser local storage from its sign-in page. The hotspot uses `hotspot_api_base` and retains the RouterOS redirect/CHAP login flow. For LAN preview, use the server machine's LAN IP and allow the frontend origin through the API CORS settings.

Staff and customer sign-in use the existing JWT endpoints. The customer portal registration endpoint currently returns HTTP 503, so staff must create/link customer portal credentials before a customer can sign in. The backend does not implement reseller, SMS sending, churn, or expense reports; the admin screens label these unavailable rather than returning sample data.

Frontend styling tokens and setup notes: `admin/README.md`. The shared red/white theme uses the `--primary`/`--surface`/`--bg` tokens in `admin/css/variables.css`; the portal imports the same theme. Third-party UI assets use Bootstrap 5.3, Bootstrap Icons, AOS, GSAP, Chart.js, and Google Fonts via CDN where applicable.

## Quick start

1. Create a virtual environment.
2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Create a local environment file:

   ```bash
   copy .env.example .env
   ```

4. Update the required secret and connection values.
5. Run the API:

   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

For Render hosting with MikroTik RouterOS 6, follow the [Render and FreeRADIUS setup guide](docs/mikrotik-routeros6.md). Render hosts the web/API app; run FreeRADIUS on a Linux VPS because the router-to-RADIUS connection uses inbound UDP 1812/1813.

## Default app entry points

When the app is served through the production reverse proxy, the public root is the hotspot portal:

- `/` → `/hotspot/`
- `/admin/` → admin console
- `/portal/` → customer portal
- `/api/` → FastAPI API

When the backend is started directly without Nginx, the root response is the FastAPI JSON health/root payload from `app.main`, not the static hotspot landing page.

## Browser-side API base configuration

The static frontends automatically prefer the current origin in production and fall back to `http://localhost:8000` only for local development. If you need to override the backend URL manually, set these browser values:

- admin: `isp_api_base_url`
- portal: `isp_portal_api_base_url`
- hotspot: `hotspot_api_base`

Example:

```javascript
localStorage.setItem('hotspot_api_base', 'https://api.example.com');
localStorage.setItem('isp_api_base_url', 'https://api.example.com');
localStorage.setItem('isp_portal_api_base_url', 'https://api.example.com');
```

## Production security

Production deployments must set strong values for:

- `JWT_SECRET_KEY`
- `RADIUS_SECRET`
- `RADIUS_API_SECRET`
- `ROUTER_ENCRYPTION_KEY`

These are enforced in `app/core/config.py` when `APP_ENV=production`.

## Render to VPS relay architecture

The application supports a secure `vps_relay` router connection mode for Render deployments when direct access to the private MikroTik VPN address is not possible.

Use these variables in Render:

- `ROUTER_CONNECTION_MODE=vps_relay`
- `ROUTER_RELAY_URL=https://<vps-public-host>:<https-port>`
- `ROUTER_RELAY_TOKEN=<shared-token>`
- `ROUTER_HOST=10.30.0.10`
- `ROUTER_PORT=8728`
- `ROUTER_USERNAME=isp-billing-api`

The relay should live on the Oracle VPS, validate the token, restrict allowed RouterOS operations, and never expose the router's raw TCP 8728/8729 port to the public Internet. Direct router access remains the fallback when the relay is not configured.

## Documentation

- [docs/architecture.md](docs/architecture.md)
- [docs/installation.md](docs/installation.md)
- [docs/deployment.md](docs/deployment.md)
- [docs/mikrotik-routeros6.md](docs/mikrotik-routeros6.md)

## New admin frontend

The rebuilt multi-page admin interface is under `admin/` and is served at `/admin/`. See [admin/README.md](admin/README.md) for API mapping, startup instructions, current backend limitations, and the integration checklist. The frontend uses the actual endpoints implemented under `app/routes/`; it does not provide fabricated reseller or analytics APIs.

## Testing

```bash
pytest -q
```

Some tests are database-dependent and are skipped automatically when MongoDB is unavailable.
