# 12 — Administrator guide

## Access

Open `/admin/` (or `/admin/index.html`) on the configured deployment. Sign in with an authorized staff account created through the provider's controlled process. No default credentials are provided. A customer account must not be used as an administrator.

## Routine operation

- Use dashboard and paginated resource views to inspect customers, plans, vouchers, billing, routers, sites, RADIUS users/sessions and support tickets where exposed by current permissions.
- Confirm a payment through backend transaction status; an initiated STK prompt is pending, not paid.
- Generate/activate/revoke vouchers only through authorized backend operations. Share credentials only with the intended recipient.
- Site and router actions require verified server-side associations. Do not infer a location from an IP address alone.
- Session disconnect currently queues a pending marker; confirm actual network state separately.
- Use reports only where the backend provides source data. Dedicated reports are absent; do not treat improvised aggregates as audited financial reports.

## Safe administration

Use unique staff accounts and least privilege. Avoid shared administrator logins. Do not export personal data unless necessary; do not paste credentials, payment callbacks, or customer data into logs/issues. Log out on shared devices. Escalate account lockout or suspected compromise through the approved operator procedure.

The UI may hide controls, but backend permission checks are authoritative. Contact support for customer portal activation because public identity-proof registration is disabled. This guide documents source behavior, not live-tested screen-by-screen operation.
