# 02 — Feature completion matrix

Status labels are evidence-based: **Verified locally** means covered by current source/tests, not live operation.

| Feature | Status | Evidence / boundary |
|---|---|---|
| FastAPI route groups and OpenAPI inventory | Implemented and verified locally | 146 operations / 112 paths, plus internal secret-gated RADIUS routes; see endpoint inventory. |
| Admin login and bearer authorization | Implemented, locally tested | JWT auth, permission checks, DB-backed active-user validation. Browser token storage remains localStorage. |
| Customer self-service login/read flows | Partially implemented | Existing portal APIs; self-registration intentionally returns 503 until identity proof exists. Password reset absent. |
| Customer, services/packages, subscriptions, invoices, payments | Implemented, locally tested | CRUD/service contracts and business services exist; no production-data verification. |
| Voucher batch, issuance and RADIUS binding | Implemented, locally tested | Unique indexes and atomic device claim logic; router-side login not proven live. |
| M-Pesa STK/callback/reconciliation | Implemented, mock-tested | Callback is provider queried and settlement idempotent; real Daraja callback/configuration unverified. Customer phone log masking fixed and tested. |
| Pesapal | Missing | No integration/configuration found in source or requirements. |
| HotSpot portal purchase and status | Implemented, mock-tested | Existing flow; payment success depends on backend settlement. User Internet access is not inferred from purchase status. |
| Trusted router attestation | Partially implemented, cross-component mock-tested | FastAPI HMAC/nonce/context and copied relay endpoint tests pass; actual router/site registry values and staging router observation absent. |
| Nyaururu/Nakuru multi-site mapping | Blocked by external configuration | No verified inventory for both sites/routers available. Do not assign the one observed VPN target to both. |
| Router management | Implemented, locally tested | Configured operations exist; live router API health not checked. |
| PPPoE CHAP/MS-CHAP | Incomplete / high-risk gap | Current RADIUS service verifies regular password but CHAP/MS-CHAP response support is not established. |
| FreeRADIUS auth/accounting | Implemented, locally tested | REST route and accounting tests exist; actual FreeRADIUS deployment/runtime unavailable. Compose requires operator-created `.env.radius`. |
| Session disconnect / CoA | Partially implemented | API marks a pending disconnect; does not demonstrate a live MikroTik disconnect. UI must describe queued state accurately. |
| Reports | Partial | Dashboard summary exists; dedicated revenue/churn/report endpoints are absent. Avoid fabricated or unbounded aggregation. |
| Advertising, voucher balance | Missing backend endpoints | Do not expose as functional actions. |
| Customer registration/password reset | Blocked by missing identity-proof workflow | Public portal registration disabled; reset endpoint absent. |
| Full frontend flows | Partially implemented | Pages and JS are present; feature/API coverage varies. Use endpoint inventory and app-specific existing tests. |
| 10,000-customer capacity | Not established | No load-test evidence. Pool size/configuration alone is not a capacity test. |
| Backup/restore | Operationally undocumented before handover | Local procedure in `11-backup-and-recovery.md`; no production backup was run or verified. |

No feature in this table is classified as live-verified.
