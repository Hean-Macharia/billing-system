import { API } from './api.config.js';
import { createApiClient, HttpError } from '../../js/shared-api.js';

const TOKEN = 'dz_token';
const REFRESH = 'dz_refresh_token';
let refreshJob = null;
let client;

export const token = {
  get: () => localStorage.getItem(TOKEN),
  set: (value) => localStorage.setItem(TOKEN, value),
  clear: () => { localStorage.removeItem(TOKEN); localStorage.removeItem(REFRESH); },
};

export function setRefreshToken(value) { if (value) localStorage.setItem(REFRESH, value); }
export function getRefreshToken() { return localStorage.getItem(REFRESH); }
export const ApiError = HttpError;

client = createApiClient({
  baseUrl: API.baseUrl,
  getToken: token.get,
  refresh: async () => {
    if (refreshJob) return refreshJob;
    const refreshToken = getRefreshToken();
    if (!refreshToken) return false;
    refreshJob = client.request(API.auth.refresh, {
      method: 'POST', body: { refresh_token: refreshToken }, auth: false, timeoutMs: 12000,
    }).then((response) => {
      const data = response?.data ?? response;
      if (!data?.access_token) return false;
      token.set(data.access_token);
      setRefreshToken(data.refresh_token || refreshToken);
      return true;
    }).catch(() => false).finally(() => { refreshJob = null; });
    return refreshJob;
  },
  onUnauthorized: () => {
    token.clear();
    if (!location.pathname.endsWith('/index.html') && !location.pathname.endsWith('/')) {
      location.replace('./index.html');
    }
  },
});

export const request = (path, options = {}) => client.request(path, options);
export const api = {
  request,
  get: (path, params, options = {}) => request(path, { ...options, params }),
  post: (path, body, options = {}) => request(path, { ...options, method: 'POST', body }),
  patch: (path, body, options = {}) => request(path, { method: 'PATCH', body }),
  put: (path, body, options = {}) => request(path, { ...options, method: 'PUT', body }),
  delete: (path, options = {}) => request(path, { ...options, method: 'DELETE' }),
  data: (response) => response?.data ?? response,
  rows: (response) => {
    const data = response?.data ?? response;
    return Array.isArray(data) ? data : Array.isArray(response?.items) ? response.items : [];
  },
  meta: (response) => response?.meta ?? {
    total: response?.total ?? (Array.isArray(response?.data) ? response.data.length : 0),
    page: response?.page ?? 1,
    limit: response?.limit ?? 20,
  },
  health: () => request(API.health, { auth: false }),
};
