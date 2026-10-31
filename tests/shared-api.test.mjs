import test from 'node:test';
import assert from 'node:assert/strict';
import { createApiClient, HttpError } from '../js/shared-api.js';

const json = (data, status = 200) => new Response(JSON.stringify(data), {
  status, headers: { 'content-type': 'application/json' },
});

test('API client serializes JSON, adds bearer auth, and encodes query parameters', async (t) => {
  const originalFetch = globalThis.fetch;
  t.after(() => { globalThis.fetch = originalFetch; });
  globalThis.fetch = async (url, options) => {
    assert.equal(new URL(url).searchParams.get('search'), 'John & Jane');
    assert.equal(options.headers.Authorization, 'Bearer access-token');
    assert.deepEqual(JSON.parse(options.body), { name: 'Amina' });
    return json({ success: true, data: { id: '1' } });
  };
  const client = createApiClient({ baseUrl: 'https://example.test', getToken: () => 'access-token' });
  assert.deepEqual(await client.request('/api/v1/customers', {
    method: 'POST', body: { name: 'Amina' }, params: { search: 'John & Jane' },
  }), { success: true, data: { id: '1' } });
});

test('API client normalizes FastAPI validation errors', async (t) => {
  const originalFetch = globalThis.fetch;
  t.after(() => { globalThis.fetch = originalFetch; });
  globalThis.fetch = async () => json({ detail: [{ loc: ['body', 'phone'], msg: 'Invalid phone' }] }, 422);
  const client = createApiClient({ baseUrl: 'https://example.test' });
  await assert.rejects(client.request('/api/v1/customers'), (error) => {
    assert.ok(error instanceof HttpError);
    assert.equal(error.status, 422);
    assert.equal(error.fieldErrors.phone, 'Invalid phone');
    return true;
  });
});

test('API client refreshes one expired request then retries once', async (t) => {
  const originalFetch = globalThis.fetch;
  t.after(() => { globalThis.fetch = originalFetch; });
  let token = 'old-token';
  let calls = 0;
  globalThis.fetch = async (_url, options) => {
    calls += 1;
    if (options.headers.Authorization === 'Bearer old-token') return json({ detail: 'Expired' }, 401);
    return json({ data: 'ok' });
  };
  const client = createApiClient({
    baseUrl: 'https://example.test', getToken: () => token,
    refresh: async () => { token = 'new-token'; return true; },
  });
  assert.deepEqual(await client.request('/api/v1/auth/me'), { data: 'ok' });
  assert.equal(calls, 2);
});

test('safe read retries one network failure and then surfaces normalized error', async (t) => {
  const originalFetch = globalThis.fetch;
  t.after(() => { globalThis.fetch = originalFetch; });
  let calls = 0;
  globalThis.fetch = async () => { calls += 1; throw new TypeError('offline'); };
  const client = createApiClient({ baseUrl: 'https://example.test' });
  await assert.rejects(client.request('/api/v1/dashboard/summary'), (error) => {
    assert.equal(error.status, 0);
    assert.match(error.message, /Connection lost/);
    return true;
  });
  assert.equal(calls, 2);
});
