# Deployment Guide

## Production checklist

- Set `APP_ENV=production`
- Configure strong secrets for `JWT_SECRET_KEY`, `RADIUS_SECRET`, and `ROUTER_ENCRYPTION_KEY`
- Use a managed MongoDB instance or a locked-down MongoDB service
- Keep router credentials and M-Pesa keys in environment variables only
- Enable HTTPS through Nginx or a reverse proxy
- Run the application behind a non-root container or service user
- Add backups, monitoring, and log retention policies

## Docker deployment

```bash
docker compose up -d --build
```

The stack is designed for:

- API service
- MongoDB persistence
- Optional reverse proxy and networking layers

## Public entry points and browser base URLs

The reverse proxy serves the apps with these default routes:

- `/` → `/hotspot/`
- `/admin/` → admin console
- `/portal/` → customer portal
- `/api/` → FastAPI backend

The browser clients should resolve their API base in this order:

1. `localStorage` override for the app-specific key
2. current browser origin in production (`https://example.com`)
3. `http://localhost:8000` for local-only development

Keys:

- admin: `isp_api_base_url`
- portal: `isp_portal_api_base_url`
- hotspot: `hotspot_api_base`

This keeps the deployed frontends working correctly when they are served behind the same domain as the API proxy without hardcoding localhost URLs.

## Hotspot guest resources

The captive portal uses this application's own voucher-check and package APIs; its resource section does not send users to a third-party hotspot domain. The free-trial flow issues one 3-minute voucher per supplied client MAC, redeemable for 10 minutes, and RADIUS checks that the voucher is used by the same MAC. Paid packages are also tied to the selected, verified MAC when the payment settles.

For trial requests to work, the MikroTik captive redirect must open `/hotspot/` with the connected station's MAC in a `mac` query parameter (and may include the assigned client IP in an `ip` parameter). Device lookup for TV/other-device purchases checks the exact private IP or MAC against DHCP leases on configured MikroTik routers. Without a configured and reachable router lease, the page requires a device that can be verified. The device-lookup endpoint is public for captive users; restrict access to the hotspot network or add trusted router-side request signing/rate limiting before exposing it directly to the internet.

The hotspot purchase page shows the plan's data total, duration, rate, supported device count, and any bonus stated in its plan description. Selecting a plan opens its full payment flow. Voucher entry validates codes against this application's voucher store; the guest then signs in through the MikroTik captive login page to establish RADIUS access.

For Render hosting, the web/API service runs on Render and FreeRADIUS runs on a separate Linux VPS because the router must reach UDP 1812/1813. Follow the [Render and RouterOS 6 setup guide](./mikrotik-routeros6.md) for secrets, NAS source IP, firewall/VPN restrictions, HotSpot profile, and captive redirect. The portal offers one-tap router login only when RouterOS supplies a safe login URL and the browser can use its scheme; manual voucher entry remains the fallback.

The self-hosted production Compose stack uses Nginx TLS and requires `docker/nginx/certs/fullchain.pem` and `docker/nginx/certs/privkey.pem`. Render terminates TLS and serves the frontend routes through FastAPI instead.

## Health checks

The application exposes health-oriented routes through the FastAPI app. Use them in external monitoring systems.

## Security warnings

- Never commit `.env` files to version control
- Use unique secrets per environment
- Rotate secrets when keys are exposed or infrastructure changes
- Keep M-Pesa callbacks behind trusted endpoints and validate payloads strictly
