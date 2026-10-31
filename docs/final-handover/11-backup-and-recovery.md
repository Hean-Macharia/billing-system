# 11 — Backup and recovery

This is a procedure proposal; no production backup or restore was executed.

## Before a release

- Record source commit, built image digest, deployment manifest version, and secret *names* only.
- Take a consistent MongoDB backup using the organization's approved MongoDB backup tooling. Encrypt it, restrict access, and store it separately from the database. Never put credentials or connection strings in command logs or tickets.
- Preserve previous deployable image/source and non-secret configuration. Back up relay source/config only through approved secret-safe process; secret files must remain in secret storage and must not be attached to code reports.
- Verify backup timestamp, size/checksum and retention metadata without printing customer records.

## Restore drill

1. Restore to an isolated database, never over production initially.
2. Verify collection counts and indexes, then run read-only health and consistency checks.
3. Test login, voucher uniqueness, payment idempotency and RADIUS session reads using sanitized fixtures.
4. Record recovery time and missing data window. Repeat periodically.

## Rollback

- Application: route traffic to the prior immutable image/release and check health/static entry points.
- Database: prefer forward-compatible application rollback. Restore a database snapshot only after assessing writes since the snapshot and obtaining explicit approval; restoring may lose valid payments/vouchers/accounting records.
- Relay/RADIUS/network: this project did not modify production. Any change to `isp-relay.service`, FreeRADIUS, VPN, firewall, or router needs a separately approved maintenance/rollback plan.

Backups must be access-controlled, encrypted at rest and in transit, retention-limited, and periodically restore-tested. A successful backup command is not proof of recoverability.
