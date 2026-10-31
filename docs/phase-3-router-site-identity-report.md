# Phase 3 — Router and Site Identity Report

**Date:** 2026-10-31  
**Scope:** repository source and isolated local tests only. No production Render, MongoDB, payment provider, router, FreeRADIUS host, or VPS relay was contacted or changed.

## 1. Executive summary

This phase implements server-side RADIUS NAS-to-router-to-site resolution, site-restricted voucher enforcement, accounting identity persistence, server-owned plan/site snapshots, and global-only public package listing. New fields are optional and backward-compatible. Site-restricted vouchers now fail closed if the NAS cannot be resolved unambiguously to the permitted active site.

The requested trusted captive router context is **not implemented**. The repository's existing authenticated relay is a FastAPI-to-VPS management client and has no captive DHCP-attestation endpoint here. RouterOS captive redirect values are browser-visible and mutable; DHCP lookup from those hints is not proof of router identity. Thus the public catalog returns only global plans and purchase initiation rejects a site-specific plan until a trusted relay context is available. This keeps the browser from choosing an arbitrary site but means Phase 3 is not fully complete against the acceptance criteria.

## 2. Python import stall: cause and repair

Before the change, `app.routes.__init__`, `app.services.__init__`, and `app.integrations.__init__` eagerly imported every route/service/integration when importing one module. That increased cold import work, but source inspection found no Mongo connection, network request, router discovery, relay request, scheduler startup, or background job during ordinary route import. Mongo connect and scheduler startup occur in `app.main.lifespan`.

The actual pytest hang occurred before the test body: pytest-asyncio initialized a Windows event loop, Python fell back to a TCP localhost socket pair, and the sandbox blocked `accept()` in `socket._fallback_socketpair`. It was not a circular import or router/database wait. Package initializers are now import-light docstrings; explicit application imports and lifespan behavior remain intact. Local loopback permission was granted solely for isolated tests. No arbitrary timeout was added.

## 3. Existing router/site/NAS architecture

- `Site` has an ID and active/inactive/planned status.
- `Router` has optional `site_id`, optional `nas_client_id`, management `ip_address`, and online/offline/unknown/disabled status.
- `NasClient` has a unique configured RADIUS `ip_address`, optional `site_id`, status, and secret. This phase adds optional `nas_identifier`.
- RADIUS request schemas accept NAS-IP-Address and NAS-Identifier. Those attributes arrive at the internal, secret-gated FreeRADIUS API; browser router/site IDs are never used for RADIUS mapping.
- Router mapping prefers the explicit `Router.nas_client_id` relationship. Legacy fallback requires one exact NAS IP == Router management IP match. It does not choose an arbitrary first record. Both NAS attributes, when present, must resolve to the same NAS client. Router and NAS site IDs must agree if both exist; the resulting site must exist and be active.
- The relay client in this repository authenticates FastAPI-to-VPS management operations with the existing relay token. No router-originated captive attestation or lease observation API appears in repository source. The external `isp-relay.service` was not accessed or modified.

The resolver rejects unknown/duplicate NAS identities, conflicting IP and Identifier, missing/multiple routers, disabled NAS/router, conflicting or missing site, and missing/inactive site. Accounting may retain an unresolved event for compatibility, but unresolved identity cannot authorize a site-restricted voucher.

## 4. Trusted captive router-context design

Captive IP, MAC, router identity, original URL, and login parameters are visible to the browser and are only lookup hints. RouterOS v6.49.21 support for creating a secure signed assertion within HotSpot templates was not established from the version-specific primary material available. We therefore did not put signing credentials in HTML/JavaScript or assume RouterOS signing support. References: [MikroTik Scripting](https://help.mikrotik.com/docs/spaces/ROS/pages/47579229/Scripting), [HotSpot customisation](https://help.mikrotik.com/docs/spaces/ROS/pages/87162881/Hotspot%2Bcustomisation).

Recommended follow-up: extend the **existing authenticated relay** to query a configured router for a current DHCP/host observation and issue an attestation to FastAPI over the existing server-to-server authenticated relay channel. Include issuer, audience, configured router ID, configured site ID, client IP/MAC, issued/expiry times (short lifetime), and one-time nonce. FastAPI must validate active configured records, exact IP/MAC binding, expiry/audience/issuer, and consume nonce atomically. Reject replay, mismatch, unknown/disabled router/site, missing site mapping, and relay unavailability. The relay must select only from configured router records, not trust an arbitrary browser router ID. No browser-held signing key or relay credential.

This is **designed, not implemented** because the needed relay API is absent from the repository and the relay is external. Even a current DHCP attestation proves what the router observed, not cryptographic possession against a local MAC-spoofing attacker.

## 5. Lifecycle identity changes implemented

1. **Captive request/device lookup:** browser IP/MAC remains untrusted; existing DHCP verification cannot mint trusted site context.
2. **Public packages:** `/hotspot/plans/public` accepts `site_id` for compatibility but ignores it and returns active global plans only. It cannot expose another site's catalog through query manipulation.
3. **Purchase:** the backend reads the plan's `site_id`; a site-specific plan is rejected before STK initiation while trusted router context is absent. Global purchase follows the existing payment flow. Pending transactions store the plan's server-side `site_id`; `router_id` remains unset.
4. **Settlement/voucher:** no provider settlement/reconciliation semantics were intentionally changed. After verified settlement, the transaction site snapshot flows to the voucher batch. Plan-based voucher batches inherit the plan site, and incompatible explicit overrides fail validation. Old transactions without a site field fall back to the existing plan lookup. Global/legacy vouchers retain `site_id=None`.
5. **RADIUS authentication:** NAS identity resolves from received NAS-IP/Identifier. A restricted voucher is rejected before device MAC-slot claim unless the NAS resolves to the voucher's exact active site. Unknown NAS does not bypass site restrictions. Unrestricted legacy vouchers keep prior behavior. No additional-device pairing was added.
6. **Accounting:** Start stores received NAS-IP/Identifier plus resolved router/site IDs. Start writes identity once; duplicate Start, Interim, and Stop do not replace it. Session records retain the same identity. Unresolved Start can still be recorded without router/site attribution.

## 6. Model, index, and API changes

Added optional fields: `NasClient.nas_identifier`; RADIUS accounting/session `nas_identifier` and `router_id`; transaction `site_id` and `router_id`; voucher last-seen router/site/NAS-Identifier. Existing records with missing fields remain readable. Index definitions include NAS-Identifier (non-unique so legacy duplicates do not break startup), router-to-NAS lookup, and accounting/session router/site lookups. No destructive migration or production index operation occurred.

Admin resource UI includes NAS Identifier/site fields and displays router/site/NAS identity in sessions. Public plan output remains compatible and now returns only global plans. No endpoint for trusted captive context was added. No payment provider settlement logic, RADIUS secret check, relay authentication, router credentials, FreeRADIUS deployment, or production configuration was changed.

## 7. Verification results

- Direct imports `app.routes.hotspot`, `app.services.router_service`, `app.services.nas_identity_service`: **passed**.
- `python -m compileall -q app tests`: **passed**.
- Focused Phase 2 and Phase 3 tests plus isolated database reconnect: **31 passed**, 1 third-party deprecation warning.
- Full `python -m pytest -q`: **112 passed, 27 skipped, 2 failed**, 3 warnings. Failures are existing assertions in `tests/test_health.py`: root redirect expects `/hotspot/` while current app redirects to `/index.html`; static frontend assertion expects `DEVZEN CREATIONS` in `/hotspot/`, `/admin/`, `/portal/` HTML. These route/branding expectations are unrelated to router/site work and were not altered.
- `node --check admin/js/resource-page.js`: **passed**.
- `node --test tests/hotspot-portal.test.js`: **7 passed**.
- `git diff --check`: **passed**; Git emitted only LF-to-CRLF working-copy notices.
- An initial full-suite attempt exposed `tests/test_database_reconnect.py` reading the machine's configured Mongo URI and attempting SRV DNS resolution. It failed before connecting to any database. The test now uses an explicitly local mock URI and a stub client; isolated rerun passed. No production URI/value was printed or contacted.
- Automated fixtures use mock MongoDB. No production API, Render deployment, router, relay, FreeRADIUS host, or M-Pesa request was made.

## 8. Files changed in Phase 3

- `app/routes/__init__.py`, `app/services/__init__.py`, `app/integrations/__init__.py` — stop eager package-wide imports.
- `app/services/nas_identity_service.py` — deterministic NAS-to-router-to-site resolver.
- `app/models/radius.py`, `app/schemas/radius.py`, `app/routes/radius.py` — NAS Identifier and router identity fields/wiring.
- `app/core/database.py` — lookup indexes.
- `app/models/voucher.py`, `app/models/mpesa_transaction.py` — optional identity/site snapshots.
- `app/services/radius_auth_service.py` — restricted voucher site authorization and accounting identity persistence.
- `app/services/hotspot_service.py`, `app/routes/hotspot.py` — global-only public package selection and fail-closed site-specific initiation behavior.
- `app/services/mpesa_service.py`, `app/services/voucher_service.py` — transaction/plan site snapshot propagation without changing provider settlement semantics.
- `admin/js/resource-page.js` — NAS/site/router/session identity fields.
- `tests/test_nas_identity.py`, `tests/test_radius_site_authorization.py`, `tests/test_radius_site_accounting.py`, `tests/test_hotspot_site_package_selection.py` — isolated coverage.
- `tests/test_database_reconnect.py` — prevent test from reading environment Mongo configuration.
- `docs/phase-3-router-site-identity-report.md` — this report.

The working tree already contained many Phase 1/2 modified and untracked files before Phase 3; they were not reset. In particular, existing portal JavaScript, RouterOS parser changes, `render.yaml`, and Phase 2 tests are not listed as Phase 3 edits. Inspect `git status` before staging.

## 9. Status against completion criteria

**Implemented and tested:** import diagnosis/repair; Phase 2 device and DHCP parser regressions; deterministic NAS mapping; site-restricted voucher checks; Start/Interim/Stop identity retention; server-owned plan-site snapshots; public site spoofing prevention; regression tests.

**Not complete:** trusted relay-attested captive router context and nonce/replay protection; site-specific public catalog after trusted context; proving router-originated device identity. Those require a reviewed and implemented contract in the external relay and corresponding FastAPI endpoint/tests. Thus router/site identity is authoritative for authenticated RADIUS requests, but not yet for captive browsing/purchase selection.

**Not established live:** exact deployed NAS attributes and records; deployed Router↔NAS↔Site links; customer payment-to-entitlement-to-RADIUS-to-Internet flow. No live connectivity claim is made.

## 10. Remaining live verification

Only under separately authorized supervised verification: confirm deployed NAS-IP/Identifier values against configured NAS clients; inspect router/NAS/site mapping; confirm restricted voucher allowed/rejected across intended sites; inspect accounting Start/Interim/Stop identity; verify relay attestation once implemented; then verify a real customer device authenticates through RouterOS/RADIUS and can reach the Internet. This phase did none of those live checks.

## 11. Rollback considerations

Package initializer edits can be reverted independently if an external consumer requires re-exported classes; repository-local code imports explicit submodules. Added model fields and indexes are additive and require no destructive migration. Before deployment, check that active routers and NAS clients are mapped to the same active site; restricted vouchers will now reject when that map is unknown or ambiguous. Public site-specific package access stays fail-closed until trusted relay context is implemented. No production setting or service was changed.
