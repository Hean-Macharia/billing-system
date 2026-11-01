const assert = require('node:assert/strict');
const fs = require('node:fs');
const test = require('node:test');
const { createLoginSubmission, parseRedirectParameters } = require('../hotspot/mikrotik-login.js');

const challenge = '0123456789abcdef0123456789abcdef';

test('HotSpot checkout uses trusted attestation context rather than ambiguous DHCP lookup', () => {
  const app = fs.readFileSync(require.resolve('../hotspot/js/app.js'), 'utf8');
  const checkout = app.slice(app.indexOf('function openPurchaseSheet'), app.indexOf('function showWaitingScreen'));

  assert.match(checkout, /const verifiedContextAvailable = Boolean\(readHotspotContext\(\)\)/);
  assert.match(checkout, /X-Hotspot-Context/);
  assert.doesNotMatch(checkout, /\/api\/v1\/hotspot\/devices\/lookup/);
  assert.match(checkout, /Secure router verification is required before payment/);
});

test('HotSpot package verification is single-flight, cancellable, and guards stale results', () => {
  const app = fs.readFileSync(require.resolve('../hotspot/js/app.js'), 'utf8');
  assert.match(app, /if \(plansRequest\) return plansRequest/);
  assert.match(app, /new AbortController\(\)/);
  assert.match(app, /signal\.aborted/);
  assert.match(app, /generation !== plansRequestGeneration/);
  assert.match(app, /retry\.disabled = true/);
  assert.match(app, /REQUEST_ABORTED/);
});

test('paid purchase waits for completed settlement, displays the receipt, then submits HTTP-CHAP automatically', () => {
  const app = fs.readFileSync(require.resolve('../hotspot/js/app.js'), 'utf8');
  assert.match(app, /settled === true && access_token && login_username/);
  assert.match(app, /M-Pesa receipt and access token/);
  assert.match(app, /voucherLoginMarkup\(loginUsername, \{ autoSubmit: true \}\)/);
  assert.match(app, /loginForm\.requestSubmit\(\)/);
  assert.match(app, /X-Hotspot-Context': readHotspotContext\(\)/);
  assert.match(app, /router will open your original destination after acceptance/);
  assert.doesNotMatch(app, /YOU ARE CONNECTED|You’re connected/);
});

test('receipt reconnect calls the backend with opaque trusted context and never starts payment', () => {
  const app = fs.readFileSync(require.resolve('../hotspot/js/app.js'), 'utf8');
  assert.match(app, /api\('\/api\/v1\/hotspot\/reconnect'/);
  assert.match(app, /'X-Hotspot-Context': context/);
  assert.match(app, /Already paid\? Reconnect/);
  const reconnect = app.slice(app.indexOf('async function openReceiptReconnect'), app.indexOf('function openBalanceCheck'));
  assert.doesNotMatch(reconnect, /\/api\/v1\/hotspot\/purchase['"`]/);
  assert.match(reconnect, /No new payment was started/);
});

test('root checkout also requires attestation and submits its existing CHAP login after settled payment', () => {
  const portal = fs.readFileSync(require.resolve('../js/portal.js'), 'utf8');
  const html = fs.readFileSync(require.resolve('../index.html'), 'utf8');
  const purchase = portal.slice(portal.indexOf('function openPurchaseSheet'), portal.indexOf('function showWaitingScreen'));
  assert.match(portal, /\/api\/v1\/hotspot\/devices\/attest/);
  assert.match(purchase, /X-Hotspot-Context/);
  assert.doesNotMatch(purchase, /\/api\/v1\/hotspot\/devices\/lookup/);
  assert.match(portal, /settled === true && access_token && login_username/);
  assert.match(portal, /loginForm\.requestSubmit\(\)/);
  assert.match(portal, /X-Hotspot-Context': readHotspotContext\(\)/);
  assert.match(html, /id="connect-receipt"/);
  assert.doesNotMatch(portal, /You’re connected!/);
});

test('standalone payment status waits for settled backend confirmation before login', () => {
  const status = fs.readFileSync(require.resolve('../frontend/js/payment-status.js'), 'utf8');
  const api = fs.readFileSync(require.resolve('../frontend/js/api.js'), 'utf8');
  assert.match(status, /data\.settled === true && data\.access_token && data\.login_username/);
  assert.match(status, /dz_hotspot_context/);
  assert.match(status, /createLoginSubmission\(redirect, username\)/);
  assert.match(status, /form\.requestSubmit\(\)/);
  assert.match(api, /X-Hotspot-Context/);
  assert.doesNotMatch(status, /You’re connected!/);
});

test('parses MikroTik redirect parameters without hardcoding the router address', () => {
  const redirect = parseRedirectParameters(
    `?link-login-only=http%3A%2F%2F192.168.89.1%2Flogin&link-orig=https%3A%2F%2Fexample.com%2F&chap-id=00&chap-challenge=${challenge}`,
  );

  assert.equal(redirect.ok, true);
  assert.equal(redirect.action, 'http://192.168.89.1/login');
  assert.equal(redirect.destination, 'https://example.com/');
  assert.equal(redirect.chapId, '00');
  assert.equal(redirect.chapChallenge, challenge);
});

test('supports the existing login_url and dst redirect aliases', () => {
  const redirect = parseRedirectParameters(
    `?login_url=http%3A%2F%2Frouter.hotspot%2Flogin&dst=https%3A%2F%2Fexample.com&chap-id=0a&chap-challenge=${challenge}`,
  );

  assert.equal(redirect.ok, true);
  assert.equal(redirect.action, 'http://router.hotspot/login');
  assert.equal(redirect.destination, 'https://example.com/');
});

test('preserves non-hex RouterOS CHAP substitutions as their supplied text', () => {
  const redirect = parseRedirectParameters(
    '?link-login-only=http%3A%2F%2Frouter.hotspot%2Flogin&chap-id=10&chap-challenge=challenge-value',
  );
  assert.equal(redirect.ok, true);

  assert.deepEqual(createLoginSubmission(redirect, 'VOUCHER123').fields, {
    username: 'VOUCHER123',
    password: 'ae0405d21a153cd794f14373b984800a',
  });
});

test('decodes RouterOS octal-escaped CHAP bytes before hashing', () => {
  const redirect = parseRedirectParameters(
    '?link-login-only=http%3A%2F%2Frouter.hotspot%2Flogin&chap-id=%5C371&chap-challenge=%5C357%5C015%5C330%5C013%5C021%5C234%5C145%5C245%5C303%5C253%5C142%5C246%5C133%5C175%5C375%5C316',
  );
  assert.equal(redirect.ok, true);
  assert.equal(
    createLoginSubmission(redirect, 'VOUCHER123').fields.password,
    'c701397dd42d0cf9453a0fa752c59193',
  );
});

test('parses the supplied RouterOS 6 captive redirect URL including double-encoded link-orig', () => {
  const captiveUrl = 'https://billing-system-5ckp.onrender.com/hotspot/?link-login-only=http%3A%2F%2Flogin.hean.local%2Flogin&link-orig=http%253A%252F%252Fconnectivitycheck.gstatic.com%252Fgenerate%255F204&chap-id=%5C213&chap-challenge=%5C277%5C154%5C110%5C145%5C127%5C347%5C223%5C373%5C157%5C252%5C232%5C270%5C110%5C011%5C006%5C314';
  const redirect = parseRedirectParameters(new URL(captiveUrl).search);

  assert.equal(redirect.ok, true);
  assert.equal(redirect.action, 'http://login.hean.local/login');
  assert.equal(redirect.destination, 'http://connectivitycheck.gstatic.com/generate_204');
  assert.equal(redirect.chapId, '\\213');
  assert.equal(
    createLoginSubmission(redirect, 'TESTVOUCHER').fields.password,
    'c761e20a70643b0731d09c019f3996de',
  );
});

test('rejects missing and unsafe router parameters with useful feedback', () => {
  assert.equal(parseRedirectParameters('').state, 'missing');
  assert.match(parseRedirectParameters('?chap-id=00').message, /login URL/i);
  assert.match(
    parseRedirectParameters(`?link-login-only=https%3A%2F%2Fevil.example%2Flogin&chap-id=00&chap-challenge=${challenge}`).message,
    /login URL/i,
  );
  assert.match(
    parseRedirectParameters('?link-login-only=http%3A%2F%2F192.168.89.1%2Flogin&chap-id=00').message,
    /CHAP challenge/i,
  );
});

test('creates a MikroTik HTTP-CHAP form submission', () => {
  const redirect = parseRedirectParameters(
    `?link-login-only=http%3A%2F%2F192.168.89.1%2Flogin&link-orig=https%3A%2F%2Fexample.com&chap-id=00&chap-challenge=${challenge}`,
  );

  assert.deepEqual(createLoginSubmission(redirect, 'VOUCHER123'), {
    action: 'http://192.168.89.1/login',
    method: 'post',
    fields: {
      username: 'VOUCHER123',
      password: 'fa5c6e0737af215ca0dd7c2ad068e644',
      dst: 'https://example.com/',
    },
  });
});

test('rejects a login submission when redirect parameters are invalid', () => {
  const redirect = parseRedirectParameters('');
  assert.throws(() => createLoginSubmission(redirect, 'VOUCHER123'), /login URL/i);
});
