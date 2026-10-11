/*
  Portal API client. Same envelope-unwrapping approach as the admin
  console's api.js, but with its own localStorage key prefix
  (isp_portal_*) so a staff member testing both apps in the same
  browser never gets their sessions mixed up.
*/
function getDefaultBaseUrl() {
  if (typeof window === 'undefined') return 'http://localhost:8000';
  const { protocol, hostname, port } = window.location;
  const localHosts = ['localhost', '127.0.0.1', '0.0.0.0'];
  if (localHosts.includes(hostname) && port && port !== '8080') return 'http://localhost:8000';
  if (protocol === 'file:') return 'http://localhost:8000';
  return `${protocol}//${hostname}${port ? `:${port}` : ''}`;
}

const DEFAULT_BASE_URL = getDefaultBaseUrl();

const Api = (() => {
  function getBaseUrl() { return localStorage.getItem('isp_portal_api_base_url') || DEFAULT_BASE_URL; }
  function setBaseUrl(url) { localStorage.setItem('isp_portal_api_base_url', url.replace(/\/$/, '')); }
  function getAccessToken() { return localStorage.getItem('isp_portal_access_token'); }
  function getRefreshToken() { return localStorage.getItem('isp_portal_refresh_token'); }
  function setTokens({ access_token, refresh_token }) {
    if (access_token) localStorage.setItem('isp_portal_access_token', access_token);
    if (refresh_token) localStorage.setItem('isp_portal_refresh_token', refresh_token);
  }
  function clearTokens() {
    localStorage.removeItem('isp_portal_access_token');
    localStorage.removeItem('isp_portal_refresh_token');
    localStorage.removeItem('isp_portal_profile');
  }
  function getProfile() { const raw = localStorage.getItem('isp_portal_profile'); return raw ? JSON.parse(raw) : null; }
  function setProfile(p) { localStorage.setItem('isp_portal_profile', JSON.stringify(p)); }
  function isAuthed() { return !!getAccessToken(); }

  let refreshPromise = null;
  async function tryRefresh() {
    if (refreshPromise) return refreshPromise;
    const refresh_token = getRefreshToken();
    if (!refresh_token) return false;
    refreshPromise = fetch(`${getBaseUrl()}/api/v1/auth/refresh`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ refresh_token }),
    }).then(async (res) => {
      if (!res.ok) return false;
      const body = await res.json();
      if (body?.success && body?.data?.access_token) { setTokens(body.data); return true; }
      return false;
    }).catch(() => false).finally(() => { refreshPromise = null; });
    return refreshPromise;
  }

  async function request(path, opts = {}) {
    const { method = 'GET', body, params, isRetry = false } = opts;
    let url = `${getBaseUrl()}${path}`;
    if (params && Object.keys(params).length) {
      const qs = new URLSearchParams();
      Object.entries(params).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== '') qs.set(k, v); });
      const qsStr = qs.toString();
      if (qsStr) url += (url.includes('?') ? '&' : '?') + qsStr;
    }
    const headers = {};
    const token = getAccessToken();
    if (token) headers['Authorization'] = `Bearer ${token}`;
    if (body !== undefined) headers['Content-Type'] = 'application/json';

    let res;
    try {
      res = await fetch(url, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
    } catch (e) {
      throw new ApiError(`Could not reach the server at ${getBaseUrl()}. Please try again.`, 0, null);
    }

    if (res.status === 401 && !isRetry && getRefreshToken()) {
      const refreshed = await tryRefresh();
      if (refreshed) return request(path, { ...opts, isRetry: true });
      clearTokens();
      Router.go('#/login');
      throw new ApiError('Your session expired. Please sign in again.', 401, null);
    }

    const contentType = res.headers.get('content-type') || '';
    let payload = null;
    if (contentType.includes('application/json')) payload = await res.json().catch(() => null);

    if (!res.ok) {
      const message = payload?.message || payload?.detail || `Something went wrong (${res.status})`;
      throw new ApiError(message, res.status, payload);
    }
    return payload;
  }

  class ApiError extends Error {
    constructor(message, status, payload) { super(message); this.status = status; this.payload = payload; }
  }

  async function fetchBlob(path) {
    const token = getAccessToken();
    const headers = {};
    if (token) headers['Authorization'] = `Bearer ${token}`;
    const res = await fetch(`${getBaseUrl()}${path}`, { headers });
    if (res.status === 401) {
      const refreshed = await tryRefresh();
      if (refreshed) return fetchBlob(path);
      clearTokens();
      Router.go('#/login');
      throw new ApiError('Your session expired. Please sign in again.', 401, null);
    }
    if (!res.ok) {
      let message = `Download failed (${res.status})`;
      try { const body = await res.json(); message = body?.message || message; } catch (_) {}
      throw new ApiError(message, res.status, null);
    }
    return res.blob();
  }

  return {
    getBaseUrl, setBaseUrl, getAccessToken, getRefreshToken, setTokens, clearTokens, getProfile, setProfile, isAuthed,
    get: (p, params) => request(p, { method: 'GET', params }),
    post: (p, body) => request(p, { method: 'POST', body: body ?? {} }),
    patch: (p, body) => request(p, { method: 'PATCH', body: body ?? {} }),
    downloadUrl: (p) => `${getBaseUrl()}${p}`,
    fetchBlob,
    ApiError,
  };
})();
