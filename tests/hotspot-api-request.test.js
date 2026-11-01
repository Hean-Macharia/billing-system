const assert = require('node:assert/strict');
const test = require('node:test');
const { createApiRequest, getTrustedContextToken } = require('../hotspot/js/api-request.js');

test('accepts only a verified, unexpired opaque trusted context', () => {
  const token = 'A'.repeat(43);
  assert.equal(getTrustedContextToken({
    success: true,
    data: { verified: true, context_token: token, expires_at: 200 },
  }, 100), token);
});

for (const response of [
  { success: false, data: { verified: true, context_token: 'A'.repeat(43), expires_at: 200 } },
  { success: true, data: { verified: false, context_token: 'A'.repeat(43), expires_at: 200 } },
  { success: true, data: { verified: true, context_token: 'short', expires_at: 200 } },
  { success: true, data: { verified: true, context_token: 'A'.repeat(43), expires_at: 100 } },
  { success: true, data: { verified: true, context_token: 'A'.repeat(43), expires_at: '200' } },
]) {
  test('rejects incomplete, unverified, malformed, or expired trusted context', () => {
    assert.throws(() => getTrustedContextToken(response, 100), /incomplete or expired/);
  });
}

test('reports a slow router lookup as a timeout rather than API connection loss', async () => {
  const api = createApiRequest(
    () => 'https://billing.example.test',
    (_url, { signal }) => new Promise((resolve, reject) => {
      signal.addEventListener('abort', () => {
        const error = new Error('aborted');
        error.name = 'AbortError';
        reject(error);
      }, { once: true });
    }),
  );

  await assert.rejects(api('/api/v1/hotspot/devices/lookup', {
    timeoutMs: 5,
    timeoutMessage: 'Router lookup timed out.',
  }), (error) => {
    assert.equal(error.code, 'REQUEST_TIMEOUT');
    assert.equal(error.message, 'Router lookup timed out.');
    return true;
  });
});

test('keeps a real fetch failure distinct from a request timeout', async () => {
  const api = createApiRequest(
    () => 'https://billing.example.test',
    async () => { throw new TypeError('network unavailable'); },
  );

  await assert.rejects(api('/health/ready'), (error) => {
    assert.equal(error.code, 'NETWORK_ERROR');
    assert.match(error.message, /Cannot reach the billing API/);
    return true;
  });
});

test('preserves backend HTTP errors instead of converting them to network errors', async () => {
  const api = createApiRequest(
    () => 'https://billing.example.test',
    async () => ({ ok: false, status: 503, json: async () => ({ message: 'Router/site mapping is incomplete' }) }),
  );

  await assert.rejects(api('/api/v1/hotspot/devices/attest'), (error) => {
    assert.equal(error.status, 503);
    assert.equal(error.code, 'HTTP_SERVER_ERROR');
    assert.equal(error.message, 'The billing service encountered an error: Router/site mapping is incomplete');
    return true;
  });
});

for (const [status, code, label] of [
  [403, 'HTTP_AUTH_ERROR', 'This request is not authorized'],
  [422, 'HTTP_VALIDATION_ERROR', 'Some submitted information is invalid'],
  [429, 'HTTP_RATE_LIMIT', 'Too many requests. Please wait and try again'],
  [500, 'HTTP_SERVER_ERROR', 'The billing service encountered an error'],
]) {
  test(`classifies HTTP ${status} as an application response`, async () => {
    const api = createApiRequest(
      () => 'https://billing.example.test',
      async () => ({ ok: false, status, json: async () => ({ message: 'Backend detail' }) }),
    );

    await assert.rejects(api('/api/v1/hotspot/devices/attest'), (error) => {
      assert.equal(error.status, status);
      assert.equal(error.code, code);
      assert.equal(error.message, `${label}: Backend detail`);
      return true;
    });
  });
}
