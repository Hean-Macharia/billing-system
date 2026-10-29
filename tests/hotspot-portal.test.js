const assert = require('node:assert/strict');
const test = require('node:test');
const { createLoginSubmission, parseRedirectParameters } = require('../hotspot/mikrotik-login.js');

const challenge = '0123456789abcdef0123456789abcdef';

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
