import { API } from './api.config.js';
import { createApiClient, HttpError } from './shared-api.js';

const TOKEN = 'dz_token';
const REFRESH = 'dz_refresh_token';
const HOTSPOT_CONTEXT_KEY = 'dz_hotspot_context';
let refreshJob = null;
let client;

export class ApiError extends HttpError {}

client = createApiClient({
  baseUrl: API.baseUrl,
  getToken: () => localStorage.getItem(TOKEN),
  refresh: async () => {
    if (refreshJob) return refreshJob;
    const refreshToken = localStorage.getItem(REFRESH);
    if (!refreshToken) return false;
    refreshJob = client.request(API.auth.refresh, {
      method: 'POST', body: { refresh_token: refreshToken }, auth: false, timeoutMs: 12000,
    }).then((response) => {
      const data = response?.data ?? response;
      if (!data?.access_token) return false;
      localStorage.setItem(TOKEN, data.access_token);
      localStorage.setItem(REFRESH, data.refresh_token || refreshToken);
      return true;
    }).catch(() => false).finally(() => { refreshJob = null; });
    return refreshJob;
  },
  onUnauthorized: () => {
    localStorage.removeItem(TOKEN);
    localStorage.removeItem(REFRESH);
    if (!location.pathname.endsWith('/admin-login.html')) location.replace('/admin-login.html');
  },
});

export const request = (path, options = {}) => client.request(path, options);
export const api = {
  request,
  get: (path, params, options = {}) => request(path, { ...options, params }),
  post: (path, body, options = {}) => request(path, { ...options, method: 'POST', body }),
  put: (path, body, options = {}) => request(path, { ...options, method: 'PUT', body }),
  patch: (path, body, options = {}) => request(path, { ...options, method: 'PATCH', body }),
  delete: (path, options = {}) => request(path, { ...options, method: 'DELETE' }),
  data: (response) => response?.data ?? response,
  rows: (response) => Array.isArray(response?.data) ? response.data : Array.isArray(response?.items) ? response.items : [],
};

export const getHotspotContext = () => {
  try { return sessionStorage.getItem(HOTSPOT_CONTEXT_KEY) || ''; } catch { return ''; }
};
export const setHotspotContext = (value) => {
  try {
    if (value) sessionStorage.setItem(HOTSPOT_CONTEXT_KEY, value);
    else sessionStorage.removeItem(HOTSPOT_CONTEXT_KEY);
  } catch { /* Private browsing may disable session storage; the portal then remains global-only. */ }
};

export const attestHotspotDevice = (ipAddress, macAddress) => api.post(
  API.portal.deviceAttest,
  { ip_address: ipAddress, mac_address: macAddress },
  { auth: false, timeoutMs: 25000 },
);

export const getPortalPackages = (contextToken = getHotspotContext()) => api.get(
  API.portal.plans,
  {},
  { auth: false, headers: contextToken ? { 'X-Hotspot-Context': contextToken } : {} },
);

export const startMpesaCheckout = (packageId, phone, deviceType, deviceMac, ipAddress, contextToken = getHotspotContext()) => api.post(
  API.portal.purchase,
  {
    plan_id: packageId,
    phone_number: phone,
    device_type: deviceType,
    device_mac: deviceMac,
    ...(ipAddress ? { ip_address: ipAddress } : {}),
  },
  { auth: false, timeoutMs: 70000, headers: contextToken ? { 'X-Hotspot-Context': contextToken } : {} },
);

export const pollCheckoutStatus = (ref) => api.get(`${API.portal.status}/${encodeURIComponent(ref)}`, {}, { auth: false });
export const verifyVoucher = (code) => api.get(`${API.portal.voucherCheck}/${encodeURIComponent(code)}`, {}, { auth: false });
export const checkVoucherBalance = async () => { throw new Error('Voucher balance details are not available in the current billing API.'); };
export const sendAdvertiseEnquiry = async () => { throw new Error('Advertising enquiries are not available online yet. Please contact support.'); };

export const getCustomers = (params) => api.get(API.customers, params);
export const createCustomer = (data) => api.post(API.customers, data);
export const getPackages = (params) => api.get(API.catalogPackages, params);
export const getServicePlans = (params) => api.get(API.servicePlans, params);
export const getInvoices = (params) => api.get(API.invoices, params);
export const recordPayment = (data) => api.post(API.payments, data);
export const getVouchers = (params) => api.get(API.vouchers, params);
export const getDevices = (params) => api.get(API.devices, params);
export const getTickets = (params) => api.get(API.tickets, params);
