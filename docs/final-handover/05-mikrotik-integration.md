# 05 — MikroTik integration

## Source architecture

FastAPI routes call `RouterService`, which selects the configured router integration/relay. The retrieved relay copy is a Python `BaseHTTPRequestHandler` / `ThreadingHTTPServer`, bound in its source to localhost port 8765, with bearer auth, rate limits, JSON/body-size validation, predefined RouterOS actions, and a RouterOS binary API socket adapter. Existing management endpoint: `POST /api/v1/router/relay`; health: `GET /health`. Additive attestation is in the un-deployed local copy at `phase-j-relay-source/`.

## Attestation boundary

The relay mock implementation reads DHCP leases and HotSpot hosts from the same configured router, checks bound/current lease and matching IP/MAC, then signs the complete claims object using the Phase 4 HMAC contract. FastAPI verifies issuer, audience, router/site/device/nonce and freshness, consumes a nonce once, and issues an opaque short-lived context. Mock cross-component tests pass.

The relay requires explicit router ID/site ID and enable/active flags. Those IDs have not been verified against approved live records. The copied RouterOS adapter contains one management target only; it does not establish Nyaururu/Nakuru mapping. No production relay source/configuration was changed and no live RouterOS query was run. Consequently attestation is **not live-ready** and site-specific package availability cannot be claimed operational.

## RouterOS operations and cautions

Management calls are allowlisted actions rather than arbitrary commands. Attestation reads only DHCP lease and HotSpot host tables. RouterOS API reachability, credentials, actual record semantics, L2TP path, and RouterOS 6.49.21 compatibility still require a controlled staging test. DHCP/HotSpot observations identify matching records but do not cryptographically prevent local MAC spoofing.

## Required staging proof

With an approved test router/device only: API reachability through the intended VPN, read-only DHCP/HotSpot query, signed positive and negative evidence, FastAPI acceptance/rejection/replay handling, correct site catalog, re-attestation before purchase using a mocked payment provider, then RouterOS/RADIUS login and confirmed Internet path. Do not use live customers or payment during initial verification.
