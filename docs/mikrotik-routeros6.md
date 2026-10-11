# MikroTik RouterOS 6 and FreeRADIUS setup

This connects a RouterOS 6 HotSpot to the DEVZEN CREATIONS portal and this application's FreeRADIUS-backed voucher authentication. Replace every example value with your own. The laptop URL `127.0.0.1` is not reachable by WiFi guests.

## Render deployment: split web/API and RADIUS

Render hosts the HTTPS web app, but the MikroTik sends RADIUS over UDP. Render web services receive public HTTP(S), not public inbound UDP. Therefore deploy the API and portal on Render and run FreeRADIUS on a small Linux VPS with a static address. Prefer an IPsec/WireGuard tunnel from the router to the VPS, and bind RADIUS only to the VPS tunnel interface.

### Deploy the app to Render

1. Push this repository to GitHub, then in Render choose **New → Blueprint** and select the repository. Render reads [`render.yaml`](../render.yaml), builds the root Dockerfile, and serves `/hotspot/`, `/admin/`, `/portal/`, and `/api/` from one web service. The root redirects to `/hotspot/`.
2. At the Blueprint prompt, provide:
   - `MONGODB_URL`: a MongoDB Atlas SRV connection string with an application-specific database user.
   - `JWT_SECRET_KEY`: a unique random secret of at least 32 characters.
   - `RADIUS_SECRET`: 64 random hexadecimal characters; share this only with FreeRADIUS and the MikroTik.
   - `RADIUS_API_SECRET`: a *different* 64 random hexadecimal characters; share this only with the Render app and FreeRADIUS.
   - `ROUTER_ENCRYPTION_KEY`: a unique random secret of at least 32 characters. Keep it stable or stored router credentials will no longer decrypt.
3. In Atlas Network Access, allow the Render service's outbound IP range. For a durable allowlist, use a Render dedicated outbound IP feature if available; don't leave MongoDB open to `0.0.0.0/0`.
4. After deployment, test `https://<service>.onrender.com/health/ready` and `https://<service>.onrender.com/`. The first should be ready and the second should redirect to `/hotspot/`.
5. Buy the domain and add it to the Render web service under **Settings → Custom Domains**. Add the DNS records Render shows, remove conflicting `AAAA` records, and wait for domain verification/TLS issuance. Render provisions and renews the HTTPS certificate. In the service's environment, set `ALLOWED_HOSTS` to the purchased hostname (for example `wifi.example.com`); the app also allows its runtime Render hostname. Set `MPESA_CALLBACK_URL` to `https://<your-domain>/api/v1/mpesa/callback`.
6. Keep the service on an always-on paid plan for a captive-portal production workload; sleeping/cold starts can make guests wait. The database and M-Pesa production credentials must also be configured before taking payments.

### Deploy FreeRADIUS on the VPS

1. Install Docker Engine and the Docker Compose plugin on a Linux VPS. Create a private VPN link between the MikroTik and this VPS where possible. The VPS needs HTTPS egress to the Render domain.
2. Clone the same repository on the VPS, then copy `.env.radius.example` to `.env.radius`.
3. Set:
   - `RADIUS_SECRET`: exactly the same 64-hex secret configured on Render; this is also the MikroTik RADIUS secret.
   - `RADIUS_API_SECRET`: exactly the separate 64-hex API secret configured on Render.
   - `RADIUS_API_BASE_URL`: `https://<your-domain>` (no trailing slash), or the Render hostname until the domain is ready.
   - `MIKROTIK_NAS_CIDR`: the single stable router VPN/source address as a `/32`.
   - `RADIUS_BIND_IP`: the VPS VPN interface address. The sample `10.20.0.1` is a placeholder.
4. Start and check FreeRADIUS (pass `.env.radius` to Compose for both port binding and container environment):

   ```bash
   docker compose --env-file .env.radius -f docker-compose.radius.yml up -d --build
   docker compose --env-file .env.radius -f docker-compose.radius.yml ps
   docker compose --env-file .env.radius -f docker-compose.radius.yml logs --tail=100 radius
   ```

5. Permit UDP 1812 and 1813 in the VPS firewall only from the MikroTik VPN/source IP. Do not publish these ports to all interfaces or leave them open to the public Internet. RADIUS/UDP does not encrypt credentials; if you cannot create a VPN, restrict firewall access to the router's fixed public IP and understand the remaining risk.

The Render FastAPI service exposes the internal RADIUS REST endpoints on its HTTPS web host, protected by the separate `RADIUS_API_SECRET`. FreeRADIUS sends those HTTPS requests outbound, so it does not need private access to Render.

### Router management API reachability limitation

The admin app's DHCP lease lookup calls the MikroTik management API from the FastAPI server. A Render service cannot automatically reach a router's private LAN. If you need automatic lease lookup (used by device verification), provide a private routed VPN path from the Render service to the router, or use a dedicated Render static outbound IP and allow only that source on the router's TLS API port 8729. Never expose RouterOS API 8728/8729 to all Internet addresses. Without this separate management path, captive pages and RADIUS may work while DHCP-based device verification returns unavailable.

## 1. Prepare a self-hosted server (alternative to Render)

If you host the whole production stack on your own Linux server instead, point public DNS to that server and use the existing Docker Compose production deployment.

1. Copy `.env.production.example` to `.env.production`.
2. Set unique production secrets. Generate two independent secrets on the server, for example by running `openssl rand -hex 32` twice. Use the first as `RADIUS_SECRET` in `.env.production` and in the MikroTik RADIUS client entry. Use the second as `RADIUS_API_SECRET`; never put this internal API secret on the MikroTik.
3. Set `MIKROTIK_NAS_CIDR` to the source IP/CIDR from which the router's RADIUS packets will arrive at FreeRADIUS. Prefer the router's static VPN address (or a fixed private address on the same routed network), usually as a `/32`. Do not use a broad public range.
4. Set `RADIUS_BIND_IP` to the server interface that receives the VPN/private RADIUS traffic. The `10.8.0.1` in the example env file is only a placeholder; it must be assigned to the server. Restrict UDP 1812 and 1813 in the server firewall to the MikroTik source IP/CIDR.
5. Replace the example hostnames in `CORS_ORIGINS`, `ALLOWED_HOSTS`, and `MPESA_CALLBACK_URL`.
6. Obtain a valid TLS certificate for the public portal hostname and copy its full chain and private key to `docker/nginx/certs/fullchain.pem` and `docker/nginx/certs/privkey.pem`. Protect the private key and keep both certificate files out of version control. The production Nginx config listens on HTTPS 443 and redirects HTTP to HTTPS; it will not start without these files.
7. Start the services:

   ```bash
   docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build
   ```

   The RADIUS service waits for the API health check and talks to it over the private Compose network. The public-facing RADIUS ports are UDP 1812 (authentication) and UDP 1813 (accounting). Do not expose TCP 8000 or MongoDB 27017 to the Internet.

Check startup and configuration:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml ps
docker compose --env-file .env.production -f docker-compose.prod.yml logs --tail=100 api radius
docker compose --env-file .env.production -f docker-compose.prod.yml exec radius radiusd -C
```

Do not forward RADIUS over the open Internet without a VPN or IPsec tunnel. RADIUS/UDP is not a transport-security protocol. A shared secret is not a substitute for a private network and source-IP firewall rules.

## 2. Create the RouterOS 6 HotSpot

In WinBox, use **IP → Hotspot → Hotspot Setup** and select the client-facing bridge/WiFi interface. Complete the wizard with the correct LAN address, DHCP pool, and DNS settings. Do not select the WAN interface. Back up the router before changing its HotSpot files.

In the examples below:

- `RADIUS_SERVER_IP` is the FreeRADIUS server's VPN/private address reachable from the router.
- `RADIUS_SECRET` is the same strong value as `.env.production`.
- `hsprof1` is the profile created by the HotSpot wizard; check `/ip hotspot profile print` if its name differs.
- `MIKROTIK_VPN_IP` is the stable private/VPN source address that the server's firewall allows and that matches `MIKROTIK_NAS_CIDR`.

Run in the MikroTik terminal:

```routeros
/radius add address=RADIUS_SERVER_IP src-address=MIKROTIK_VPN_IP service=hotspot secret="RADIUS_SECRET" authentication-port=1812 accounting-port=1813
/ip hotspot profile set [find name="hsprof1"] use-radius=yes radius-accounting=yes login-by=https dns-name=wifi.example.com ssl-certificate=wifi-cert
/radius print detail
/ip hotspot profile print detail
```

Make sure `/radius print detail` shows the correct destination, ports, and secret and that the HotSpot profile says `use-radius=yes`. If the server firewall or `MIKROTIK_NAS_CIDR` is wrong, FreeRADIUS will discard the router's packets even when the portal page itself loads.

## 3. Send unauthenticated guests to the hosted portal

Allow the portal's web host in the HotSpot walled garden so guests can load the page and call its same-origin `/api/` endpoints before authentication. Replace the domain:

```routeros
/ip hotspot walled-garden add dst-host="hotspot.example.com" action=allow
```

Keep the router's existing HotSpot `login.html` as a backup, then replace it with a redirect page like this. Configure the HotSpot `dns-name` to a name such as `wifi.lan`, install a matching TLS certificate, and set that certificate on the HotSpot profile before enabling `login-by=https`. The `login_url` value is used by the portal's optional **Connect to WiFi** action; it must point to a private IPv4 address or a local `.lan`, `.local`, or `.hotspot` name and must be HTTPS when the portal is HTTPS. Otherwise browsers block the cross-origin sign-in and guests can still enter the voucher on the router's login page.

For a test-only setup without a router certificate, the fallback is `login-by=http-pap` and `http://` for the portal and router login. Do not use that mode for real voucher traffic: the voucher is submitted without transport encryption.

```html
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>DEVZEN CREATIONS WiFi</title>
</head>
<body>
  <form id="portal" action="https://hotspot.example.com/hotspot/" method="get">
    <input type="hidden" name="mac" value="$(mac-esc)">
    <input type="hidden" name="ip" value="$(ip-esc)">
    <input type="hidden" name="login_url" value="$(link-login-only-esc)">
    <input type="hidden" name="dst" value="$(link-orig-esc)">
  </form>
  <p>Opening the DEVZEN CREATIONS WiFi portal…</p>
  <script>document.getElementById('portal').submit();</script>
</body>
</html>
```

Upload that file to the HotSpot file directory for the profile (`html-directory`, shown by `/ip hotspot profile print detail`). Use your real HTTPS portal URL. The portal page should be reachable from a not-yet-authenticated test phone at `https://hotspot.example.com/hotspot/`; its APIs must load from the same host.

## 4. Voucher login flow and limits

After M-Pesa confirms payment, the portal displays the voucher. If the RouterOS redirect supplied a safe `login_url` and the browser can use its scheme, **Connect to WiFi** posts the voucher to the MikroTik login endpoint. Otherwise, return to the RouterOS login screen and enter the voucher as the username (and as the password too if the login form requires one). The voucher is a secret; do not share it.

FreeRADIUS calls the API's internal `/api/v1/radius/auth` and `/api/v1/radius/accounting` routes with the separate `RADIUS_API_SECRET`. Nginx blocks public access to those internal routes. The API validates the RADIUS payload, checks voucher status, expiry, device binding and applicable plan limits, and records accounting events. It supplies the remaining duration and data quota, rather than restarting them on a same-device retry. A repeat auth request for the same device is allowed so normal RADIUS retries do not consume a voucher twice; a different device is rejected for an already-claimed voucher.

The HotSpot redirects to the web portal; RADIUS does not deliver the portal HTML. RouterOS still owns the captive interception and final login. M-Pesa live credentials/callback delivery and a real router/client are required to verify the entire paid flow.

## 5. Test in order

1. From a device not yet signed in, confirm the router opens the DEVZEN portal and that package loading works.
2. In the admin app, add the router using its management IP, API type **legacy**, port **8728** (or **8729** with API-SSL), and a dedicated RouterOS API account. Permit API access from the application server only.
3. Confirm the router source address matches `MIKROTIK_NAS_CIDR`, and test RADIUS reachability over the VPN/private network.
4. Test with a paid voucher and then with a trial voucher. Check `docker compose ... logs radius api` and RouterOS `/log print` when authentication fails.
5. Confirm the voucher is accepted at the router, an active HotSpot session appears in `/ip hotspot active print`, and accounting rows/sessions appear in the admin/API.

If the portal works but login fails, check in this order: RADIUS UDP firewall/VPN, NAS source CIDR and shared secret, `/radius` settings, `use-radius=yes`, voucher username, and the router's Calling-Station-Id/device MAC. A captive page loading successfully does not prove RADIUS is reachable.
