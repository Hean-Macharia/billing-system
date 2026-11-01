# DevZen Creations frontend

This is a plain HTML, CSS, and JavaScript module frontend served from FastAPI at `/admin/`. It does not require a build step or npm install. Bootstrap 5.3, Bootstrap Icons, Google Fonts, AOS, GSAP, and Chart.js load from CDNs.

## Run

Start the backend and MongoDB using the project instructions, then open `http://localhost:8000/admin/`. When using VS Code Live Server, open `index.html` on port 5500; the API client will target the same host on port 8000. If the API is hosted elsewhere, set its origin under **Backend connection** on the login page. The backend must allow the frontend origin through CORS. Opening ES modules with `file://` is blocked by many browsers; use FastAPI or Live Server.

## Authentication

Staff login calls `POST /api/v1/auth/login`, then `GET /api/v1/auth/me`. Access and refresh tokens use `dz_token` and `dz_refresh_token` in localStorage. Requests use Bearer authentication and attempt one refresh after a 401. The login screen's **Test API and database** button checks `/health/ready`.

## API mapping

Endpoint constants live in `js/api.config.js`. They map to this project's implemented FastAPI resources: dashboard summary, customers, service plans, subscriptions, invoices, payments, M-Pesa STK push/query, vouchers and voucher batches, hotspot plans, routers, RADIUS NAS clients and sessions, support tickets, and auth/profile. API responses use the backend's `{success,message,data,meta}` envelope.

The uploaded backend does not currently implement reseller management, standalone SMS sending, expense tracking, churn reports, or business preference persistence. The UI marks these limitations instead of showing invented records. Reports summarize payment and customer records currently loaded from the API. Router API configuration does not configure MikroTik's separate RADIUS client settings; the router and FreeRADIUS still need matching addresses/shared secrets and network reachability.

## Design tokens

Colors and dark-mode overrides are in `css/variables.css`; base typography, layout, components, motion, and responsive behavior are split into the remaining files under `css/`. Brand red is reserved for actions and focus, with gold, teal, violet, and green supporting statuses and charts.

## Endpoint checklist

- [ ] `GET /health/ready` reports database ready.
- [ ] Staff `POST /api/v1/auth/login`, `GET /api/v1/auth/me`, refresh and logout.
- [ ] `GET /api/v1/dashboard/summary`.
- [ ] List/create/update customers, plans, invoices, payments, vouchers, and routers.
- [ ] `POST /api/v1/mpesa/stk-push` and `/query` with working Daraja credentials/callback URL.
- [ ] Router test and health refresh succeed from the backend host.
- [ ] RADIUS sessions are returned; test authentication/accounting from MikroTik.
- [ ] Support ticket list/status/reply endpoints succeed.

No staff admin bootstrap is exposed through public registration; provision the first staff account through the secure backend/database setup process.
