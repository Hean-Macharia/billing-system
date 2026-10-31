# 08 — Security review

Assessment is source-based and local-test-based, not a penetration test. Severity indicates priority for remediation or operational validation.

| Severity | Finding | Evidence / action |
|---|---|---|
| Critical blocker | Trusted relay router/site allowlist values are not verified and multi-site mapping is absent. | Do not expose site-specific purchase path as operational; establish approved per-site inventory in staging. |
| High | PPPoE CHAP/MS-CHAP verification is not established. | Confirm protocol and implement protocol-correct FreeRADIUS verification before selling PPPoE service. |
| High | No effective distributed API rate limiter was found although a limit setting exists. | Login lockout is account-based; add proxy/shared-store rate limiting before public production exposure. Per-process counters do not protect multi-worker deployment. |
| High | Browser bearer tokens use localStorage. | Existing API contract requires Bearer tokens; reduce XSS surface and consider a backend-supported HttpOnly cookie/BFF design in a separate reviewed change. |
| Medium | Public device lookup compatibility route uses browser hints and DHCP matching. | It is not trusted router attestation; restrict exposure or ensure sensitive actions require attested opaque context. |
| Medium | Configured examples/env files can drift from actual deployment. | Reconcile allowed hosts, callback, RADIUS/NAS and site/router mapping through secret-safe deployment review. |
| Medium | Existing security header CSP is omitted for app paths, where pages may use inline code/third-party resources. | Review app-specific CSP and nonce/hash strategy without breaking portal. Do not claim CSP protection for these pages. |
| Medium | Relay source copy requires static env IDs/status flags and one hardcoded target. | No dynamic verified site registry or multi-router mapping. Fail-closed behavior is tested, not deployed. |
| Low (fixed) | Full phone number was included in STK initiation info log. | Masking added and regression test passes. |
| Informational | Database index creation warnings are non-fatal. | Production index state and duplicate data are unknown; inspect before relying on unique constraints. |

Positive controls observed: password hashing uses bcrypt; production startup validates critical secrets; router credentials are encrypted in backend models/services; JWT user status is checked in DB-backed dependencies; role/permission checks are used; M-Pesa callback is not accepted as payment proof; relay bearer comparison uses constant-time comparison; relay actions are allowlisted; Mongo TTL indexes support nonce/context cleanup.

No secret values were read or included. No dynamic scan, secret scanner, external pentest, or production test was run. Review CORS/TrustedHost/proxy settings against actual hostname before deployment. Frontend authorization is never security authority; FastAPI must remain authoritative.
