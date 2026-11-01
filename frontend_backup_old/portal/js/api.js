import { PAPI } from './api.config.js';
import { createApiClient, HttpError } from '../../js/shared-api.js';

const ACCESS = 'dz_portal_token';
const REFRESH = 'dz_portal_refresh_token';
let refreshJob = null;
let client;

export const PortalApiError = HttpError;
export const getRefreshToken = () => localStorage.getItem(REFRESH);

client = createApiClient({
  baseUrl: PAPI.base,
  getToken: () => localStorage.getItem(ACCESS),
  refresh: async () => {
    if (refreshJob) return refreshJob;
    const refreshToken = localStorage.getItem(REFRESH);
    if (!refreshToken) return false;
    refreshJob = client.request(PAPI.refresh, {
      method: 'POST', body: { refresh_token: refreshToken }, auth: false, timeoutMs: 12000,
    }).then((response) => {
      const data = response?.data ?? response;
      if (!data?.access_token) return false;
      localStorage.setItem(ACCESS, data.access_token);
      localStorage.setItem(REFRESH, data.refresh_token || refreshToken);
      return true;
    }).catch(() => false).finally(() => { refreshJob = null; });
    return refreshJob;
  },
  onUnauthorized: () => {
    localStorage.removeItem(ACCESS);
    localStorage.removeItem(REFRESH);
    localStorage.removeItem('dz_portal_profile');
    location.replace('./index.html');
  },
});

export const request = (path, options = {}) => client.request(path, {
  ...options,
  responseType: options.raw ? 'response' : options.responseType,
});

export const portalApi = {
  get: (path, params, options = {}) => request(path, { ...options, params }),
  post: (path, body, options = {}) => request(path, { ...options, method: 'POST', body }),
  patch: (path, body, options = {}) => request(path, { ...options, method: 'PATCH', body }),
  data: (response) => response?.data ?? response,
  rows: (response) => Array.isArray(response?.data) ? response.data : [],
  receipt: (id) => request(`${PAPI.payments}/${encodeURIComponent(id)}/receipt`, { raw: true }),
};
