# DevZen Creations frontend

The canonical public screens are the top-level HTML files (`index.html`, `checkout.html`, and the remaining named pages). Shared public assets use the root `css/`, `js/`, and `assets/` folders. FastAPI's root static handler allowlists those pages and public asset folders so it does not expose backend files such as `.env`. `frontend/` is a local preview copy. The app is plain HTML, CSS, and ES modules; there is no build step or npm dependency.

## Run

Use the project's normal backend setup from the repository root. After MongoDB and `.env` are configured, run `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`. Open `http://localhost:8000/` for the public hotspot portal, `http://localhost:8000/admin-login.html` for staff, or `http://localhost:8000/checkout.html?pkg=<plan-id>` for a direct package checkout. FastAPI allowlists the public HTML pages and mounts the public `css/`, `js/`, and `assets/` folders. The existing account portal and hotspot compatibility URLs remain `/portal/` and `/hotspot/`.

For VS Code Live Server, open the repository's top-level `index.html`. The API client maps common Live Server ports to port 8000. If the backend is elsewhere, set `dz_api_base` in local storage or use the existing hotspot backend connection control. Opening an ES module page via `file://` is blocked by browser module security; use FastAPI or Live Server.

## API configuration

All root frontend routes and base URL detection are in `js/api.config.js`. `js/api.js` implements JSON requests, optional JWT auth, one token refresh on 401, one network retry, and normalized errors. Portal requests are public and use only routes found in this backend:

- `GET /api/v1/hotspot/plans/public`
- `POST /api/v1/hotspot/devices/lookup`
- `POST /api/v1/hotspot/purchase`
- `GET /api/v1/hotspot/purchase/status/{checkout_request_id}`
- `GET /api/v1/vouchers/public/check/{code}`
- `POST /api/v1/hotspot/free-trial`

The supplied prompt's `/portal/packages`, `/portal/checkout/mpesa`, `/portal/checkout/status`, and `/portal/voucher/verify` routes are not implemented by this backend. Advertising submission, independent voucher balance lookup, and captive session-info routes are also absent. `api.config.js` marks those as TODO; the UI uses email/contact fallback or explains the missing capability rather than issuing fake API calls. Purchase requires a verified device MAC and a Kenyan phone normalized to `2547XXXXXXXX` or `2541XXXXXXXX`.

Staff pages are the existing protected admin application under `/admin/`; top-level admin URLs redirect there. It authenticates with the existing `/api/v1/auth/login`, `/api/v1/auth/refresh`, and `/api/v1/auth/me` routes using `dz_token` and `dz_refresh_token`.

## Styling and libraries

Tokens are in `css/variables.css`. Shared admin styles and captive portal styles are separated under `css/`; reduced-motion rules are included. Bootstrap 5.3, Bootstrap Icons, AOS, GSAP, Chart.js (admin), and Google Fonts use CDN links. Brand red is `--primary`; gold, teal, violet, green, and neutral tokens support status and chart accents.

## Integration checklist

- [ ] `GET /health/ready` confirms database readiness.
- [ ] Public hotspot packages return active plans with IDs.
- [ ] Device lookup can verify the client MAC from the captive request or MikroTik DHCP leases.
- [ ] M-Pesa hotspot purchase sends STK push; callback updates transaction; public status returns voucher on success.
- [ ] Voucher validity check and MikroTik/FreeRADIUS voucher authentication succeed.
- [ ] Admin login, refresh, `/auth/me`, and protected resources work.
- [ ] Set up a RADIUS NAS client/shared secret separately from RouterOS API credentials.
- [ ] Add backend routes before enabling advertising enquiries, voucher balance, or portal-session info.
