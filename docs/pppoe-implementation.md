# PPPoE implementation and staging runbook

## Scope and existing architecture

PPPoE reuses the existing `subscriptions`, `service_plans`, `radius_users`, `radius_sessions`, `radius_accounting`, `nas_clients`, `routers`, `sites`, invoices, and M-Pesa settlement paths. It does not create a parallel subscriber or payment database. HotSpot voucher authentication remains on its existing `Login-User`/voucher path; PPPoE accounts are identified by `RadiusUser.user_type=pppoe` and are checked against an active subscription and the request's configured NAS/router/site binding.

Provisioning creates a **pending** subscription and RADIUS account. It grants no service. Only the existing verified invoice payment/settlement path should activate the subscription and synchronize the RADIUS account. PPPoE packages use service-plan download/upload speeds and can restrict availability with `available_site_ids`; an empty list retains the existing global-plan behavior.

## Implemented local capabilities

- Staff API under `/api/v1/pppoe`: list, create pending subscriber, get, update package/IP/pool, suspend, billing-guarded restore, reset secret, and list accounting sessions.
- Customer portal subscription response uses an explicit safe projection. Customers see their own PPPoE username and can change the password through an ownership-checked route; the API never returns the password.
- PPPoE credentials are encrypted at rest in `radius_users`. New PPPoE provisioning does not copy the plaintext password into the subscription. Existing legacy credential fields remain supported by the old sync path during a controlled migration.
- RADIUS accepts PAP and CHAP-MD5 for an assigned PPPoE account, checks account, subscription, package, expiry, and NAS/router/site association, and returns PPP framing, interim accounting, optional pool/address, session expiry, and MikroTik rate-limit attributes.
- PPPoE accounting validates NAS identity and subscriber assignment before Start/Stop/Interim processing. Start is upserted by session ID; Stop is conditional and repeated Stops do not double-increment usage. Site/router IDs are recorded with accounting.
- Verified payment settlement extends an existing PPPoE term from the later of now or its current expiry and synchronizes the RADIUS account. Expiry sweep expires RADIUS authorization and attempts disconnection through the existing RouterOS adapter. Scheduler is hourly and must be enabled on only one application worker unless distributed job locking is added.
- Admin navigation and a PPPoE subscriber page are present. Service-plan forms include optional site availability.

## Current API contracts

Staff routes are authenticated and permission-gated:

```text
GET    /api/v1/pppoe/subscribers?page=1&limit=50&site_id=...&status=...
POST   /api/v1/pppoe/subscribers
GET    /api/v1/pppoe/subscribers/{subscription_id}
PATCH  /api/v1/pppoe/subscribers/{subscription_id}
POST   /api/v1/pppoe/subscribers/{subscription_id}/suspend
POST   /api/v1/pppoe/subscribers/{subscription_id}/reactivate
POST   /api/v1/pppoe/subscribers/{subscription_id}/reset-password
GET    /api/v1/pppoe/subscribers/{subscription_id}/sessions
```

The create request has customer, package, site, router, NAS, username, initial password, and optional framed IP/pool. The account remains pending. Payment is not initiated from this administrative provisioning endpoint. Staff can use the existing `POST /api/v1/subscriptions/{subscription_id}/invoice` route to create the initial invoice; the customer then pays through the authenticated portal invoice flow. Do not mark a payment as settled manually to activate a subscription.

Customer self-service password reset:

```text
POST /api/v1/portal/pppoe/subscriptions/{subscription_id}/reset-password
```

It requires a customer access token and an owned PPPoE subscription.

## Configuration prerequisites

Use the existing secret manager/environment settings. Do not copy production values into files or scripts.

- `APP_ENV=production` for the deployed service.
- `MONGODB_URL` and `DATABASE_NAME` for the existing database.
- `JWT_SECRET_KEY` for API sessions.
- `RADIUS_API_SECRET` shared only by FreeRADIUS REST configuration and FastAPI.
- `RADIUS_SECRET` shared only by MikroTik and FreeRADIUS; do not confuse it with a NAS document placeholder.
- `ROUTER_ENCRYPTION_KEY`, stable across restarts and deployments, to decrypt stored PPPoE credentials. Rotating it without re-encrypting data makes saved credentials unusable.
- Existing `MPESA_*` credentials/callback configuration for verified billing. No new payment secret is introduced here.
- `SCHEDULER_ENABLED=true` on exactly one application worker for hourly expiry and billing jobs; otherwise configure an external single-runner scheduler.

Before deploying, verify the production secret manager already contains the encryption key used for stored router/RADIUS credentials. Do not regenerate it.

## MongoDB compatibility and indexes

No collection or record migration is required for new subscribers; existing RADIUS username uniqueness is reused. The local code adds two non-unique `subscriptions` indexes for PPPoE expiry scans and site/status listings. It also adds unique compound `(acct_session_id, nas_ip_address)` indexes to both RADIUS accounting collections. This is required because a RADIUS Acct-Session-Id is scoped to a NAS, and a single-field key incorrectly collides across routers. `radius_sessions` currently has a legacy unique single-field Acct-Session-Id index, so a staged index migration is required: inspect duplicates, then replace that old unique index with the compound key. Startup index creation treats these compound uniqueness indexes as critical and fails closed if existing duplicates prevent creation. Do not deploy before this preflight and migration is planned. The existing unique `radius_users.username` index is the username uniqueness guarantee. Confirm it exists before provisioning. No unique index was added to `subscriptions.pppoe_username`, avoiding a migration that could fail on legacy duplicates.

Read-only preflight in `mongosh` (select the configured database first):

```javascript
db.radius_sessions.aggregate([
  { $group: { _id: "$acct_session_id", count: { $sum: 1 } } },
  { $match: { count: { $gt: 1 } } }, { $limit: 100 }
])
db.radius_accounting.aggregate([
  { $group: { _id: { session: "$acct_session_id", nas: "$nas_ip_address" }, count: { $sum: 1 } } },
  { $match: { count: { $gt: 1 } } }, { $limit: 100 }
])
db.radius_sessions.getIndexes()
db.radius_accounting.getIndexes()
```

Only after an approved backup and duplicate reconciliation in staging, remove `radius_sessions`' legacy `acct_session_id_1` index and allow the application to build its compound unique index. Do not delete records automatically. Production migration requires separate approval.

Legacy plaintext credentials in existing `subscriptions.pppoe_password` or RADIUS records are not automatically migrated. Plan a controlled migration and credential rotation if needed. Never print these fields during audit.

## FreeRADIUS compatibility

The existing REST-backed auth/accounting integration is reused. Stage PAP first. CHAP-MD5 is supported by the FastAPI verifier when FreeRADIUS sends `CHAP-Password` and `CHAP-Challenge`. MS-CHAP/MS-CHAPv2 verification is **not implemented in FastAPI**; do not enable those PPP authentication methods unless the active FreeRADIUS configuration verifies MS-CHAP independently and the REST policy is reviewed. Confirm `Service-Type=Framed-User` and/or `Framed-Protocol=PPP` reaches the API for PPPoE, and confirm the REST response maps `reply:Mikrotik-Rate-Limit`, `reply:Framed-Pool`, `reply:Session-Timeout`, `reply:Service-Type`, `reply:Framed-Protocol`, and `reply:Acct-Interim-Interval` correctly.

Rate string direction is formatted as `uploadM/downloadM` for MikroTik `Mikrotik-Rate-Limit`. Confirm the exact attribute behavior on RouterOS 6.49.21 in staging. CoA/Disconnect-Request is not added; explicit staff/expiry disconnection uses the existing authenticated RouterOS management adapter. An account is considered disconnected only when that adapter confirms it.

## RouterOS 6.49.21 staging checklist

Do not paste or run these examples on production without a separately reviewed change window. The router-specific values below are placeholders; configure a dedicated PPPoE VLAN/interface, pool, profile and RADIUS client from the actual site plan. Keep HotSpot interfaces and pools separate.

1. Review `/ppp/aaa`, `/ppp/profile`, `/ppp/secret`, `/interface pppoe-server server`, `/ip pool`, `/radius`, and `/ppp active print` in read-only staging checks.
2. Create a dedicated PPPoE address pool and PPP profile with the selected pool and no static credentials in scripts.
3. Enable PPP authentication only for PAP/CHAP methods verified by FreeRADIUS policy; keep MS-CHAP disabled unless separately proven.
4. Enable RADIUS for PPP and accounting, configure interim updates (300 seconds), and set the exact NAS identifier/IP to the configured `nas_clients` record.
5. Bind the PPPoE server to the dedicated interface/VLAN; do not bind it to the HotSpot bridge by accident.
6. Review address routing, NAT, DNS, and firewall policies for the PPPoE pool independently from HotSpot.
7. Test one staging subscriber: Access-Accept, correct framed pool/rate, one accounting Start, interim counters, Stop, expiration rejection, and confirmed disconnect.
8. Verify a HotSpot voucher still authenticates and accounts as before.

The accompanying `docs/routeros6-pppoe-staging-template.rsc` contains read-only preflight commands and commented configuration examples. It is not an auto-applied script. Interface/VLAN, pool, gateway, NAT, firewall, and actual site/NAS values must be reviewed against each router.

## Tests and limits

`tests/test_pppoe_lifecycle.py` covers encrypted credential auth, CHAP, expiry, inactive package, NAS binding, HotSpot namespace isolation, pending provisioning, retry/partial-row recovery, conflicting assignments, and idempotent accounting Start. `tests/test_radius_subscription_sync.py` covers encrypted sync behavior.

Mock tests cannot verify live FreeRADIUS module configuration, MikroTik attribute interpretation, PPPoE server setup, actual disconnection, or internet routing. Complete those in an isolated staging router and FreeRADIUS environment before production.

## Local commands (PowerShell)

From the repository root:

```powershell
Set-Location C:\Users\ADMIN\Documents\isp-billing
$env:PYTHONPATH = "."
& ".\.venv-1\Scripts\python.exe" -m compileall -q app tests
& ".\.venv-1\Scripts\python.exe" -m pytest -q tests\test_pppoe_lifecycle.py tests\test_pppoe_portal_scope.py tests\test_radius_subscription_sync.py
& ".\.venv-1\Scripts\python.exe" -m pytest -q
git diff --check
git status --short
```

If the selected virtual environment lacks `mongomock_motor`, use the project environment that has the test dependencies installed. This change does not call production services.

## Deployment and rollback

1. Create an isolated staging database and staging RouterOS/FreeRADIUS NAS records with non-production credentials.
2. Set the staging variables above, especially the stable staging encryption key and RADIUS API secret.
3. Deploy the application to a staging service; do not point staging at production MongoDB or live M-Pesa.
4. Validate staff authorization, pending creation, successful sandbox payment settlement, access Accept/Reject, accounting and expiry/disconnect behavior. Check HotSpot regression tests and a controlled HotSpot staging login.
5. Review the new non-unique subscription indexes and the compound unique accounting indexes; preflight and reconcile duplicates before the required RADIUS session index migration.
6. For rollback, redeploy the prior application artifact and disable the PPPoE RADIUS policy on the staging NAS. Do not delete subscriber/payment records or rotate encryption keys. Existing HotSpot should remain on its unchanged authentication route.
7. Production rollout requires separate approval, database backup/index review, one-router pilot, financial callback test with sandbox before live switch, and operator confirmation of successful PPPoE session and traffic. No production action was performed by this implementation.

## Production readiness

Local code is prepared for isolated testing. It is not production verified. Remaining external validation includes the real FreeRADIUS request/response mapping, PAP/CHAP mode, RADIUS secrets, actual router/NAS/site assignments for each site, RouterOS 6.49.21 attribute direction and PPPoE server behavior, single-runner scheduler configuration, session disconnect confirmation, accounting counters, and internet egress. Nakuru must be configured from verified infrastructure records; no Nakuru router/site values are inferred here.
