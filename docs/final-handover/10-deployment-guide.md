# 10 — Deployment guide (prepared, not executed)

## Deployment surfaces

- Render uses the repository `Dockerfile` and `render.yaml`; image copies the repository (`COPY . .`) and runs Uvicorn on `$PORT`. Health check is `/health/ready`.
- FastAPI mounts `/hotspot/`, `/admin/`, `/portal/`; root redirects to `/hotspot/`.
- Self-hosted Compose/Nginx has separate static mounts and routes API traffic to FastAPI. Validate the exact compose file/config selected for the target environment.
- Relay copy under `phase-j-relay-source/` is not deployed and is not the live source checkout. Do not copy it over the VPS service without review/approval.

## Staging procedure

1. Create isolated staging API, database, relay, FreeRADIUS and test-router setup; use separate credentials and sandbox payment configuration.
2. Back up staging source/config/database using `11-backup-and-recovery.md`; never print secrets.
3. Verify required environment variable names against `render.yaml` and `app/core/config.py`; populate through secret manager only. Do not use example values as production facts.
4. Resolve one approved test router/site mapping and provision relay-side allowlist settings; confirm both FastAPI and relay use the same staging bearer token without displaying it.
5. Build image from reviewed commit, run tests, deploy to staging, check `/health/ready`, app pages/static assets, API auth, logs, and rollback readiness.
6. Run mocked HMAC and provider tests; then controlled router/RADIUS integration without customer accounts or real payment.
7. Record exact commit/image digest, environment names (not values), results and approver. Production deployment requires separate approval.

## Production procedure (future authorized change only)

1. Reconcile production router/site inventory, Render hostname/allowed-hosts, callback reachability, Mongo backups/indexes, RADIUS endpoint/secret coordination and relay source revision.
2. Review security blockers in `08-security-audit.md`; stop if unresolved critical/high items affect target service.
3. Take verified backups; deploy an immutable reviewed image with a staged rollout/health gate; retain previous image and database recovery point.
4. Smoke-test `/health/ready`, `/hotspot/`, `/admin/`, `/portal/`, authenticated API, no-secret static paths, and observability. Do not initiate a real STK without separate explicit authorization.
5. Monitor errors, database health, callback reconciliation and RADIUS. Confirm actual controlled customer-like device login only under an approved test plan.

No deployment, config modification, or infrastructure restart was performed for this handover. Exact production commands should be generated only after confirming the currently used Render/Compose/VPS deployment mechanism; the repository alone cannot establish current live configuration.
