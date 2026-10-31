# 04 — Database schema and persistence

## Persistence model

The code uses MongoDB with asynchronous Motor collections. Pydantic/domain models under `app/models/` cover `user`, `customer`, `service`, `package`, `subscription`, `invoice`, `payment`, `mpesa_transaction`, `voucher`, `site`, `router`, `radius`, `hotspot`, `ticket`, and `notification`. Collection names and index declarations are centralized in `app/core/database.py`.

## Indexes observed in source

Unique indexes include user email/username, customer code, service name, invoice number, payment transaction ID, voucher code and sparse purchase transaction ID, trial MAC/code, ticket number, site name, router name/IP, M-Pesa checkout ID, attestation nonce, trusted-context hash, NAS client IP, RADIUS username, and RADIUS accounting session ID. Query indexes cover status, dates, site/router, customer, package, expiry and session fields. Audit logs have a 90-day TTL; attestation nonces and trusted contexts use expiry TTL indexes.

## Operational implications

- Startup attempts to connect and creates indexes; index creation errors are logged as warnings. Production data must be checked for duplicates before relying on unique-index creation.
- TTL deletion is asynchronous MongoDB housekeeping; application validation must continue checking expiry.
- A mock in-memory Mongo fallback is allowed in development/test, not production. Current test run used no local Mongo service; DB-dependent tests were skipped.
- Mongo transactions depend on deployment topology/support. Do not assume multi-document atomicity merely because several writes occur in one service method. Inspect each purchase/settlement path and preserve idempotency keys.
- Index declarations are not a verified inventory of indexes in production. No production database was accessed.

## Safe future migration protocol

Before adding/removing an index or changing a document shape: back up the target database; test migration against a sanitized copy; scan for duplicates/nulls; run migration idempotently; verify counts and unique constraints; retain a rollback snapshot. Never run a migration against production from this handover without a separate approved change window.
