(function (root, factory) {
  const client = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = client;
  root.PortalApiRequest = client;
})(globalThis, function () {
  function createApiRequest(getBaseUrl, fetchRequest = (...args) => fetch(...args)) {
    return async function api(path, options = {}) {
      const timeoutMs = Number.isFinite(options.timeoutMs) ? options.timeoutMs : 15000;
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), timeoutMs);
      let response;

      try {
        response = await fetchRequest(`${getBaseUrl()}${path}`, {
          method: options.method || 'GET',
          headers: {
            ...(options.body ? { 'Content-Type': 'application/json' } : {}),
            ...(options.headers || {}),
          },
          body: options.body ? JSON.stringify(options.body) : undefined,
          signal: controller.signal,
        });
      } catch (cause) {
        const timedOut = cause?.name === 'AbortError';
        const error = new Error(timedOut
          ? (options.timeoutMessage || `The billing API request timed out after ${Math.ceil(timeoutMs / 1000)} seconds. Please retry.`)
          : `Cannot reach the billing API at ${getBaseUrl()}. Check your connection and try again.`);
        error.code = timedOut ? 'REQUEST_TIMEOUT' : 'NETWORK_ERROR';
        error.cause = cause;
        throw error;
      } finally {
        clearTimeout(timeout);
      }

      const body = await response.json().catch(() => null);
      if (!response.ok) {
        const backendMessage = typeof body?.message === 'string' ? body.message : '';
        const labels = {
          401: 'Your session is no longer valid',
          403: 'This request is not authorized',
          404: 'The requested service was not found',
          422: 'Some submitted information is invalid',
          429: 'Too many requests. Please wait and try again',
        };
        const label = labels[response.status]
          || (response.status >= 500 ? 'The billing service encountered an error' : `Request failed (${response.status})`);
        const error = new Error(backendMessage ? `${label}: ${backendMessage}` : label);
        error.status = response.status;
        error.code = response.status === 401 || response.status === 403
          ? 'HTTP_AUTH_ERROR'
          : response.status === 422
            ? 'HTTP_VALIDATION_ERROR'
            : response.status === 429
              ? 'HTTP_RATE_LIMIT'
              : response.status >= 500
                ? 'HTTP_SERVER_ERROR'
                : 'HTTP_ERROR';
        throw error;
      }
      return body;
    };
  }

  function getTrustedContextToken(response, nowSeconds = Math.floor(Date.now() / 1000)) {
    const data = response?.data;
    if (
      response?.success !== true
      || data?.verified !== true
      || typeof data.context_token !== 'string'
      || !/^[A-Za-z0-9_-]{32,128}$/.test(data.context_token)
      || !Number.isInteger(data.expires_at)
      || data.expires_at <= nowSeconds
    ) {
      throw new Error('The billing API returned an incomplete or expired trusted-device response.');
    }
    return data.context_token;
  }

  return { createApiRequest, getTrustedContextToken };
});
