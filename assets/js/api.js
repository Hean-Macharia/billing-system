/*
  API client
  ----------
  Wraps fetch() against the FastAPI backend. Every route in this app
  returns the same envelope: { success, message, data } or, for lists,
  { success, message, data, meta: { total, page, limit, pages } }.
  This module unwraps that consistently so pages never touch envelopes
  directly.
*/

const DEFAULT_BASE_URL = 'http://localhost:8000';

const Api = (() => {
  function getBaseUrl() {
    return localStorage.getItem('isp_api_base_url') || DEFAULT_BASE_URL;
  }
  function setBaseUrl(url) {
    localStorage.setItem('isp_api_base_url', url.replace(/\/$/, ''));
  }
  function getAccessToken() {
    return localStorage.getItem('isp_access_token');
  }
  function getRefreshToken() {
    return localStorage.getItem('isp_refresh_token');
  }
  function setTokens({ access_token, refresh_token }) {
    if (access_token) localStorage.setItem('isp_access_token', access_token);
    if (refresh_token) localStorage.setItem('isp_refresh_token', refresh_token);
  }
  function clearTokens() {
    localStorage.removeItem('isp_access_token');
    localStorage.removeItem('isp_refresh_token');
    localStorage.removeItem('isp_current_user');
  }
  function getCurrentUser() {
    const raw = localStorage.getItem('isp_current_user');
    return raw ? JSON.parse(raw) : null;
  }
  function setCurrentUser(user) {
    localStorage.setItem('isp_current_user', JSON.stringify(user));
  }
  function isAuthed() {
    return !!getAccessToken();
  }

  let refreshPromise = null;

  async function tryRefresh() {
    if (refreshPromise) return refreshPromise;
    const refresh_token = getRefreshToken();
    if (!refresh_token) return false;
    refreshPromise = fetch(`${getBaseUrl()}/api/v1/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token }),
    })
      .then(async (res) => {
        if (!res.ok) return false;
        const body = await res.json();
        if (body?.success && body?.data?.access_token) {
          setTokens(body.data);
          return true;
        }
        return false;
      })
      .catch(() => false)
      .finally(() => { refreshPromise = null; });
    return refreshPromise;
  }

  /**
   * @param {string} path e.g. "/api/v1/customers"
   * @param {object} opts { method, body, params, isRetry, rawResponse }
   */
  async function request(path, opts = {}) {
    const { method = 'GET', body, params, isRetry = false, rawResponse = false } = opts;

    let url = `${getBaseUrl()}${path}`;
    if (params && Object.keys(params).length) {
      const qs = new URLSearchParams();
      Object.entries(params).forEach(([k, v]) => {
        if (v !== undefined && v !== null && v !== '') qs.set(k, v);
      });
      const qsStr = qs.toString();
      if (qsStr) url += (url.includes('?') ? '&' : '?') + qsStr;
    }

    const headers = {};
    const token = getAccessToken();
    if (token) headers['Authorization'] = `Bearer ${token}`;
    if (body !== undefined && !(body instanceof FormData)) headers['Content-Type'] = 'application/json';

    let res;
    try {
      res = await fetch(url, {
        method,
        headers,
        body: body === undefined ? undefined : (body instanceof FormData ? body : JSON.stringify(body)),
      });
    } catch (networkErr) {
      throw new ApiError('Could not reach the server. Is the backend running at ' + getBaseUrl() + '?', 0, null);
    }

    if (res.status === 401 && !isRetry && getRefreshToken()) {
      const refreshed = await tryRefresh();
      if (refreshed) return request(path, { ...opts, isRetry: true });
      clearTokens();
      Router.go('#/login');
      throw new ApiError('Session expired. Please sign in again.', 401, null);
    }

    if (rawResponse) return res;

    const contentType = res.headers.get('content-type') || '';
    let payload = null;
    if (contentType.includes('application/json')) {
      payload = await res.json().catch(() => null);
    }

    if (!res.ok) {
      const message = payload?.message || payload?.detail || `Request failed (${res.status})`;
      throw new ApiError(message, res.status, payload);
    }

    return payload;
  }

  class ApiError extends Error {
    constructor(message, status, payload) {
      super(message);
      this.status = status;
      this.payload = payload;
    }
  }

  const get = (path, params) => request(path, { method: 'GET', params });
  const post = (path, body) => request(path, { method: 'POST', body: body ?? {} });
  const patch = (path, body) => request(path, { method: 'PATCH', body: body ?? {} });
  const del = (path) => request(path, { method: 'DELETE' });
  const downloadUrl = (path) => `${getBaseUrl()}${path}`;

  return {
    getBaseUrl, setBaseUrl,
    getAccessToken, getRefreshToken, setTokens, clearTokens,
    getCurrentUser, setCurrentUser, isAuthed,
    request, get, post, patch, delete: del, downloadUrl,
    ApiError,
  };
})();
