# HotSpot captive redirect regression investigation

**Date:** 2026-10-31  
**Scope:** local source, supplied failing URL, mocked HTTP/static route tests. No router/RADIUS/VPN/relay/Render configuration or payment was changed.

## Supplied URL analysis

The failing address was:

```text
https://billing-system-5ckp.onrender.com/hotspot/?link-login-only=http%3A%2F%2Flogin.hean.local%2Flogin&link-orig=http%253A%252F%252Fconnectivitycheck.gstatic.com%252Fgenerate%255F204&chap-id=%5C213&chap-challenge=%5C277%5C154%5C110%5C145%5C127%5C347%5C223%5C373%5C157%5C252%5C232%5C270%5C110%5C011%5C006%5C314
```

After one standard query decode:

- `link-login-only` is `http://login.hean.local/login`, an acceptable RouterOS HTTP login target under the current parser.
- `link-orig` is still percent-encoded (`http%3A%2F%2F...`) because RouterOS supplied an escaped value and the outer redirect encoded it again. The previous parser passed this to `new URL()` as though it were an absolute URL. It rejected the destination, but left the captive redirect itself in `ready` state.
- `chap-id` becomes the literal RouterOS octal string `\213`; the challenge likewise becomes octal escapes. These are not hexadecimal values. The current `routerOsBytes()` correctly decodes each `\ooo` escape into a byte before MD5.
- The parser constructs a normal form POST to the private RouterOS login URL, with voucher username and HTTP-CHAP digest. No browser-supplied router identity is used.

## Failure point and limits of source diagnosis

The reported `net::ERR_CONNECTION_CLOSED` is observed while loading the HTTPS portal URL. The FastAPI page route is a static-file mount; the supplied query does not select an API route. The hosted JavaScript and its CHAP/destination parsing only execute after the browser receives `/hotspot/index.html`, so that JavaScript defect cannot by itself explain a connection closure before the HTML response.

Local ASGI testing confirms both `/hotspot/` and `/hotspot/` with the exact supplied query return the same static HTML with HTTP 200. This proves the local FastAPI route accepts the path/query; it does not prove Render's edge, TLS path, captive browser, or router walled-garden path returns that response. A read-only request to the hosted URL was not successfully completed from this environment, and no Render edge/request logs or router-side `login.html` were available. Therefore the precise live network component that closed the connection remains unverified. Do not treat this as a confirmed fix for the TCP/TLS error.

`hotspot/login.html` is absent from the checkout. The repository's RouterOS setup guide contains only a sample template. The RouterOS-served `login.html` is a file on the router and is not served by FastAPI's `/hotspot/` static mount. Its actual installed contents and the configured HotSpot profile were not inspected or modified.

## Local fix

`hotspot/mikrotik-login.js` now recognizes an already-percent-escaped HTTP(S) scheme in the destination, decodes exactly one additional encoding layer, then applies the existing HTTP/HTTPS destination validation. Other destination values are not repeatedly decoded. The exact supplied URL now produces:

- action: `http://login.hean.local/login`
- destination: `http://connectivitycheck.gstatic.com/generate_204`
- decoded CHAP bytes from the octal strings
- a digest matching an independent Python `hashlib.md5` calculation for the regression voucher fixture.

The public page path, RouterOS HTTP-CHAP submission, RADIUS, and payment flows were not otherwise changed.

## Tests

- `node --test tests/hotspot-portal.test.js` — **8 passed, 0 failed, 0 skipped**.
- `python -m pytest -q tests/test_health.py` — **14 passed, 0 failed, 0 skipped**; includes direct and exact-query static page requests.
- `node --check hotspot/mikrotik-login.js` — passed.

The exact query fixture was supplied by the user. Client IP/MAC are not present in it. No real voucher or identity was used. No live browser-to-Render request, MikroTik authentication, RADIUS exchange, or Internet access was verified.

## Changed files

- `hotspot/mikrotik-login.js`
- `tests/hotspot-portal.test.js`
- `tests/test_health.py`
- `docs/hotspot-redirect-regression-report.md`

## Remaining live diagnosis

To locate the `ERR_CONNECTION_CLOSED` layer, an operator must correlate one captured attempt with Render edge/application request logs and inspect the router-installed `login.html`/HotSpot profile in a separately approved read-only session. If Render records no request, investigate the phone-to-router/walled-garden/TLS path. If Render records the request, inspect its status and edge rejection details. Keep the HTTPS public portal and RADIUS enabled; do not switch to PAP or weaken login security. No router or production setting should be changed based on the parser fix alone.
