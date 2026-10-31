# 07 — Payment integration

## Daraja flow

`DarajaClient` obtains OAuth credentials server-side, sends STK Push/query requests with timeouts, and never runs in browser code. `MpesaService` creates a pending transaction, links the provider checkout request, processes callbacks by querying the provider, checks transaction matching, uses idempotent settlement, and reconciles pending/settlement failures. HotSpot voucher creation is backend-controlled and tied to the settled transaction. UI must treat STK acceptance as pending, not paid; voucher delivery is only allowed when the backend status confirms settlement and provides the voucher.

All payment tests in this environment use mocks. No real STK request or callback was sent. Production callback URL, Daraja app settings and provider connectivity remain unverified. `render.yaml` declares Daraja variables as externally configured (`sync: false`); values were not inspected.

## Logging fix

The STK initiation log previously included the complete customer phone. It now logs only a masked suffix (`***` plus last four digits). `tests/test_daraja_client_logging.py` verifies full-number absence. No payment behavior changed.

## Pesapal

No Pesapal implementation, configuration, or tests were found. It is not supported by this codebase.

## Operational controls

Do not log callback secrets or full payment payloads. Keep provider query verification as settlement authority. Test duplicate callback, mismatched amount/phone/reference, timeout/reconciliation, voucher idempotency, and receipt behavior in staging with provider mocks/sandbox only. Real payment testing requires separate explicit approval and a controlled test account.
