# 14 — Known limitations and external dependencies

## Blocking for customer-facing site-specific service

1. Verify actual router IDs, site IDs, active status and management target for Nyaururu and Nakuru. Existing local relay attestation uses one fixed RouterOS target and static mapping flags; do not map it to both sites without evidence.
2. Deploy and stage-test the relay endpoint with approved router allowlisting. Current tests are mocked/cross-component only.
3. Test RouterOS DHCP and HotSpot table semantics, API connectivity over VPN, FastAPI relay connectivity, and the complete captive login/RADIUS/Internet path on a controlled test setup.

## Functional/backend gaps

- PPPoE CHAP/MS-CHAP verification not established; protocol-correct auth needed before service commitments.
- FreeRADIUS disconnect is queued-only; CoA/actual disconnect not implemented/proven.
- Public customer registration is deliberately disabled; password reset absent.
- No Pesapal, advertising, voucher balance, dedicated reports, reseller, or general outbound SMS API found.
- Dashboard/report coverage is bounded by existing endpoints; don't present fabricated KPIs or unsupported exports.
- There is no load-test proof for 10,000 customers or simultaneous sessions.
- 27 database-dependent tests were skipped in the current environment due to unavailable local MongoDB.
- `.env.radius` must be created securely for deployment; no values should be copied from example without validation.
- No live Daraja callback, Render integration, Mongo index state, VPS relay service, FreeRADIUS, or MikroTik operation was verified.

## Security/reliability follow-up

- Add distributed rate limiting to login/public purchase endpoints.
- Review XSS exposure and localStorage bearer-token threat; backend-supported cookie/session design requires a separate architecture change.
- Review app-specific CSP and production allowed-host/CORS values.
- Validate production DB uniqueness/indexes and restore-tested backups.
- Perform controlled performance/load testing and observability review.
