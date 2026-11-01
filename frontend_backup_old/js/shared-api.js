/** Shared fetch client used by the mounted admin, customer and captive apps. */
export class HttpError extends Error {
  constructor(message, status = 0, fieldErrors = {}, payload = null) {
    super(message);
    this.name = 'HttpError';
    this.status = status;
    this.fieldErrors = fieldErrors;
    this.payload = payload;
  }
}

function normalizeError(payload, status) {
  const detail = payload?.detail;
  const errors = payload?.errors || {};
  const message = Array.isArray(detail)
    ? detail.map((item) => item.msg || String(item)).join(', ')
    : payload?.message || (typeof detail === 'string' ? detail : `Request failed (${status})`);
  const fieldErrors = Array.isArray(detail)
    ? Object.fromEntries(detail.filter((item) => item.loc?.length).map((item) => [item.loc.at(-1), item.msg]))
    : errors;
  return new HttpError(message, status, fieldErrors, payload);
}

export function createApiClient({ baseUrl, getToken, refresh, onUnauthorized } = {}) {
  async function request(path, options = {}) {
    const {
      method = 'GET', body, params, headers = {}, signal, timeoutMs = 18000,
      auth = true, responseType = 'json', _retried = false, _networkRetried = false,
    } = options;
    const origin = typeof baseUrl === 'function' ? baseUrl() : baseUrl;
    const url = new URL(path, `${String(origin || '').replace(/\/$/, '')}/`);
    if (params) {
      for (const [key, value] of Object.entries(params)) {
        if (value !== undefined && value !== null && value !== '') url.searchParams.set(key, String(value));
      }
    }

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    const abortFromCaller = () => controller.abort();
    signal?.addEventListener('abort', abortFromCaller, { once: true });
    const isFormData = typeof FormData !== 'undefined' && body instanceof FormData;
    const token = auth ? getToken?.() : null;

    try {
      const response = await fetch(url, {
        method,
        headers: {
          ...((body !== undefined && !isFormData) ? { 'Content-Type': 'application/json' } : {}),
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
          ...headers,
        },
        body: body === undefined ? undefined : (isFormData ? body : JSON.stringify(body)),
        signal: controller.signal,
        cache: 'no-store',
      });

      if (!response.ok) {
        const payload = await response.clone().json().catch(() => null);
        const error = normalizeError(payload, response.status);
        if (response.status === 401 && auth && !_retried && refresh && await refresh()) {
          return request(path, { ...options, _retried: true });
        }
        if (response.status === 401 && auth) onUnauthorized?.();
        throw error;
      }

      if (responseType === 'response') return response;
      if (responseType === 'blob') return response.blob();
      if (responseType === 'text') return response.text();
      if (response.status === 204) return null;
      return response.json().catch(() => null);
    } catch (error) {
      if (error instanceof HttpError) throw error;
      if (error?.name === 'AbortError') throw new HttpError('The server took too long to respond.', 0);
      const networkError = new HttpError('Connection lost. Check your connection and try again.', 0);
      const safeMethod = ['GET', 'HEAD'].includes(String(method).toUpperCase());
      if (safeMethod && !_networkRetried && error?.name !== 'AbortError') {
        await new Promise((resolve) => setTimeout(resolve, 350));
        return request(path, { ...options, _networkRetried: true });
      }
      throw networkError;
    } finally {
      clearTimeout(timer);
      signal?.removeEventListener('abort', abortFromCaller);
    }
  }

  return { request };
}
