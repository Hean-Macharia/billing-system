# PPPoE controlled staging preparation

## Scope and review outcome

This preparation is for an isolated staging environment only. No database was
connected to, no migration was run, and no Render service, FreeRADIUS host, or
MikroTik router was changed.

The existing PPPoE implementation reuses the current subscription, service
plan, RADIUS user/session/accounting, NAS/site/router, invoice, and M-Pesa
settlement services. It does not replace the working HotSpot voucher path.
PPPoE credentials are encrypted at rest with `ROUTER_ENCRYPTION_KEY`; PAP
compares the decrypted value in memory, while CHAP-MD5 verifies the digest in
memory. Passwords must not be sent to FastAPI over public plain HTTP.

## Findings and controls

### Credentials and RADIUS

- FastAPI accepts `User-Password` for PAP and the pair `CHAP-Password` plus
  `CHAP-Challenge` for CHAP-MD5. It does not implement MS-CHAP/MS-CHAPv2.
- The FreeRADIUS site template previously contained an `Auth-Type MS-CHAP`
  block. That unsupported method has been removed from
  `radius/sites-enabled/default.template`; only PAP and CHAP handlers remain.
- The REST `authorize` request sends RADIUS attributes as JSON to
  `/api/v1/radius/auth`; accounting goes to `/api/v1/radius/accounting`. Both
  calls add `X-RADIUS-API-Secret` from the FreeRADIUS environment. RADIUS
  shared-secret client authentication is separately configured in
  `clients.conf`; it is not the NAS document's placeholder value.
- The checked-in `radius/Dockerfile` is based on FreeRADIUS 3.2.7. The running
  production daemon's version/configuration was not inspected in this
  staging-only task; verify the staging image with `radiusd -XC` and an
  attribute capture before assuming identical behavior.
- The FastAPI schema accepts the expected request attributes:
  `User-Name`, `User-Password`, `CHAP-Password`, `CHAP-Challenge`,
  `NAS-Identifier`, `NAS-IP-Address`, `Service-Type`, `Framed-Protocol`, and
  `Acct-Session-Id`. PPP request classification accepts RouterOS `Framed`,
  FreeRADIUS `Framed-User`, or numeric enum `2`; the response maps
  `Framed-User`, `PPP`, optional
  `Framed-Pool`/`Framed-IP-Address`, package `Mikrotik-Rate-Limit`, a bounded
  `Session-Timeout`, `Class`, and `Acct-Interim-Interval=300` through the REST
  response aliases. Confirm actual FreeRADIUS 3.2.7 JSON-to-RADIUS mapping in
  the isolated staging server before a client trial.
- Both `NAS-IP-Address` and `NAS-Identifier`, when supplied, are resolved by
  the same NAS identity service and conflicting identities fail closed.
  PPPoE account, subscription, router, NAS, and site bindings are compared
  before acceptance. HotSpot vouchers remain separated by service-type and
  RADIUS user type checks.
- Configure FreeRADIUS REST to use HTTPS for the FastAPI URL, with certificate
  verification enabled in the deployment's REST module settings. If staging
  is private-network only, document and verify that network boundary rather
  than sending PAP credentials across public HTTP.

### Accounting index migration

Application index definitions require unique compound keys on
`(acct_session_id, nas_ip_address)` for `radius_sessions` and
`radius_accounting`. An older unique `radius_sessions.acct_session_id` index
may exist in a database that was initialized by an earlier version. The
preflight reports this legacy global uniqueness separately: reuse of one
Acct-Session-Id at different NAS addresses is valid under the compound key,
but a duplicate compound key or missing/empty component blocks migration.

The new scripts use only `STAGING_MONGODB_URL` and never read `.env`,
`MONGODB_URL`, or application settings:

- `scripts/radius_index_preflight.py` performs reads only: ping, index listing,
  duplicate aggregation, and record counts. It never prints record keys.
- `scripts/migrate_radius_indexes.py` requires explicit database confirmation,
  `--execute`, and operator confirmation/reference for a verified staging
  backup. It refuses malformed or duplicate compound keys. It creates or
  verifies the two compound unique indexes first, then removes only an exact
  legacy single-field unique session index. It never deletes records.

Do not point either script at a production cluster. Use a separate staging
cluster or a separately verified staging database/credential with least
privilege. A database name containing `staging` and an exact hostname match
are required guards, not substitutes for verifying the staging cluster in
your cloud console.

### Expiry scheduler

`app.main` starts the APScheduler `AsyncIOScheduler` from FastAPI lifespan.
The current Docker command starts Uvicorn without `--workers`, so it starts one
worker per container. The scheduler has no distributed lock and starts in
every app process where `SCHEDULER_ENABLED=true`. Some state transitions use
conditional MongoDB updates and are idempotent, but that does not provide a
global lock around all notifications, reconciliation, or router operations.

For the first staging deployment, run exactly one application instance and
one Uvicorn worker with `SCHEDULER_ENABLED=true`. Do not scale that service.
If API scaling becomes necessary, run the scaled API service with
`SCHEDULER_ENABLED=false` and keep exactly one dedicated scheduler-enabled
instance; this repository does not yet provide a standalone scheduler entry
point or distributed lease. No scheduler code change is needed for the
single-worker staging arrangement.

### RouterOS 6.49.21

`docs/routeros6-pppoe-staging-template.rsc` is a reviewed proposal. Its setup
commands are comments and placeholders, not an executable script. It provides
the RouterOS 6 syntax shape for a dedicated PPPoE pool/profile/server, PPP-only
RADIUS with accounting/interim updates, a forward rule, scoped DNS examples,
and source NAT. It deliberately does not invent the access VLAN/interface,
IP pool, gateway, DNS, WAN, firewall rule position, RADIUS address, or NAS
identity. These are required inputs from the staging network plan.

The RADIUS package rate is returned through the MikroTik vendor
`Mikrotik-Rate-Limit` attribute. Confirm upload/download direction and actual
throughput on RouterOS 6.49.21. Keep the PPPoE access interface/VLAN and client
pool separate from HotSpot, LAN, and L2TP ranges. Review firewall ordering and
existing NAT before adding the examples. The RB951 is a small edge router;
capacity depends on enabled features, packet sizes, and traffic mix, so the
pilot must measure real throughput and CPU rather than extrapolating from
mock tests.

RouterOS `service=ppp` can cover multiple PPP services on one router, not only
PPPoE. Do not apply this entry to a shared router until its existing L2TP/PPTP
RADIUS behavior is reviewed. Prefer an isolated staging router; otherwise
confirm existing PPP authentication and RADIUS entries in a change review.

## Staging environment variable names

Configure these in a dedicated staging service/secret store. Do not copy any
production values or commit values to Git.

Application:

- `APP_ENV` (staging value supported by deployment policy)
- `DEBUG=false`
- `MONGODB_URL` (staging-only cluster/credential)
- `DATABASE_NAME` (a distinct database name containing `staging`)
- `JWT_SECRET_KEY`
- `ROUTER_ENCRYPTION_KEY` (stable staging key; preserve it across deploys)
- `SCHEDULER_ENABLED=true` only on the single staging worker
- `RADIUS_API_SECRET`
- Existing router adapter settings needed for the approved staging router
- `MPESA_ENVIRONMENT=sandbox` and the required sandbox credentials/callback
  URL only if sandbox payment flow is being tested

FreeRADIUS staging container:

- `RADIUS_SECRET` (staging router/client shared secret)
- `RADIUS_API_SECRET` (same staging-only API secret as the staging backend)
- `MIKROTIK_NAS_CIDR` (staging NAS source address/CIDR)
- `RADIUS_API_BASE_URL` (HTTPS staging API base URL)

Migration tools require these additional process environment variables and
will not fall back to the app variables:

- `STAGING_MONGODB_URL`
- `STAGING_DATABASE_NAME`
- `STAGING_MONGODB_HOST` (must exactly match the URI hostname)

## Exact PowerShell preparation commands

From a staging clone of the repository:

```powershell
Set-Location C:\path\to\staging\billing-system
$env:PYTHONPATH = "."
& ".\.venv\Scripts\python.exe" -m compileall -q app scripts tests
& ".\.venv\Scripts\python.exe" -m pytest -q tests\test_radius_index_migration_safety.py tests\test_pppoe_lifecycle.py tests\test_pppoe_portal_scope.py tests\test_radius_subscription_sync.py tests\test_radius_accounting_idempotency.py
```

Only after staging credentials are provisioned, set the three
`STAGING_MONGODB_*` variables in the current shell from the secret manager (do
not paste them into a command history) and run the read-only preflight:

```powershell
& ".\.venv\Scripts\python.exe" scripts\radius_index_preflight.py --confirm-staging-database $env:STAGING_DATABASE_NAME
```

Do not run the migration as part of deployment. If and only if staging
preflight is clean, a verified backup exists, and the change is approved, the
separate migration command is:

```powershell
& ".\.venv\Scripts\python.exe" scripts\migrate_radius_indexes.py --execute --confirm-staging-database $env:STAGING_DATABASE_NAME --backup-confirmation "STAGING BACKUP VERIFIED" --backup-reference "<staging-backup-id>"
```

This document prepares the command; it was not run here. The first command
can read only the explicitly configured staging URI. The migration modifies
only that explicitly confirmed target, and still requires manual execution.

## Staging end-to-end test plan

Use a dedicated staging customer, staging NAS, isolated MikroTik/VLAN, and
Safaricom sandbox. Record request IDs and timestamps, not passwords, receipt
values, or shared secrets.

1. Create a PPPoE subscriber against a verified active staging site/router/NAS
   and active package. Expect pending authorization and no internet before
   confirmed payment.
2. Initiate a Daraja sandbox STK request. Expect one pending transaction,
   correct server-side amount/package, and no active subscription yet.
3. Submit a valid sandbox callback. Expect verified receipt, one settlement,
   one subscription term, and no duplicate account. Repeat the callback and
   verify no second term or payment is created.
4. Send PAP and CHAP-MD5 requests through FreeRADIUS. Expect Access-Accept for
   the correct NAS/site/account and Access-Reject for wrong secret, unknown
   user, disabled plan, wrong site/NAS, suspended user, or expired term.
5. Connect one actual staging PPPoE client. Verify a single `/ppp active`
   session and address from the dedicated pool. Check its received speed
   profile/rate in RouterOS and measure actual throughput.
6. Verify one Accounting-Start, at least one Interim-Update, and one
   Accounting-Stop. Resend packets to test idempotency and inspect both
   `radius_sessions` and `radius_accounting` scoped to the NAS.
7. Mark/advance a test subscription into expiry through a test fixture or
   controlled staging record. Expect Access-Reject and confirmed disconnect;
   do not alter production or manually forge a payment.
8. Suspend the test subscriber and confirm new authentication rejects and
   session disconnection is confirmed. Renew through a verified sandbox
   payment; expect reactivation and a new connection without a duplicate
   subscriber.
9. Confirm assigned IP, DNS, gateway, NAT, route, and working external
   Internet traffic from the controlled staging client.
10. Run HotSpot regression tests and one controlled staging HotSpot voucher
    authentication/accounting flow. Verify PPPoE setup did not change the
    HotSpot interface, pool, RADIUS service, or voucher behavior.

Automated/mock tests can verify application logic and attribute contracts;
they cannot verify a live FreeRADIUS packet exchange, actual RouterOS PPPoE
session, speed, disconnect, or Internet egress. Those remain real staging
integration tests.

## Rollback

Keep the previous staging application and FreeRADIUS image available. To
rollback staging, redeploy the previous staging artifact, disable only the
staging PPPoE server/RADIUS PPP entry under an approved change window, and
leave HotSpot configuration untouched. Do not remove subscriber/payment
records or rotate the encryption key. Database indexes are additive except
for the exact legacy global unique session index removal; take and verify a
staging backup before running the migration, and review current indexes before
any rollback decision. Do not blindly recreate the old global unique index if
NAS-scoped duplicate session IDs exist.

## Readiness

Code-level review is suitable for controlled staging preparation after the
FreeRADIUS template update and index preflight. It is not evidence of live
PPPoE service. Remaining blockers are the verified staging database/backup,
NAS/router/site/IP/interface values, isolated RouterOS and FreeRADIUS
deployment, actual FreeRADIUS attribute mapping, PAP/CHAP exchange, payment
sandbox callback, and measured Internet access. Production remains out of
scope and requires a separate approval and change plan.

## Repository secret hygiene

The local `.env` is ignored by Git (verified without opening its contents).
The tracked `radius/clients.conf` contains environment/placeholder references
for its three secret assignments; no literal secret values were found in
those fields. Keep using the generated `clients.conf.template` in the staging
FreeRADIUS image and do not add real values to tracked files.
