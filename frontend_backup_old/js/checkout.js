import { getPortalPackages, startMpesaCheckout, attestHotspotDevice, getHotspotContext, setHotspotContext, api } from './api.js';
import { $, formatCurrency, esc } from './ui.js';

const params = new URLSearchParams(location.search);
const packageId = params.get('pkg');
const summary = $('#package-summary');
const form = $('#checkout-form');
const deviceMessage = $('#device-message');
const errorBox = $('#checkout-error');
const payButton = $('#pay-button');
const phoneInput = $('#phone');
const deviceTypeInput = $('#device-type');

// RouterOS supplies this connection context on the captive redirect. The
// backend confirms it against a live DHCP lease before accepting a purchase.
const captiveIp = params.get('ip') || params.get('client_ip') || params.get('address') || '';
const captiveMac = params.get('mac') || params.get('client_mac') || params.get('mac-address') || params.get('calling_station_id') || '';
let selectedDevice = 'this_device';
let verifiedMac = '';
let plan = null;
let trustedContextToken = getHotspotContext();
let purchaseIdempotencyKey = '';

function getOrCreatePurchaseKey(packageId) {
  try {
    const raw = sessionStorage.getItem('dz_hotspot_purchase_key');
    const saved = raw ? JSON.parse(raw) : null;
    if (saved?.packageId === packageId && /^[A-Za-z0-9._:-]{16,128}$/.test(saved.key || '')) return saved.key;
    if (!globalThis.crypto?.getRandomValues) return '';
    const bytes = new Uint8Array(24);
    globalThis.crypto.getRandomValues(bytes);
    const value = Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('');
    sessionStorage.setItem('dz_hotspot_purchase_key', JSON.stringify({ packageId, key: value }));
    return value;
  } catch {
    return '';
  }
}

async function initializeTrustedContext() {
  if (!captiveIp && !captiveMac) return trustedContextToken;
  if (!captiveIp || !captiveMac) {
    setHotspotContext('');
    trustedContextToken = '';
    return '';
  }
  try {
    const response = api.data(await attestHotspotDevice(captiveIp, captiveMac));
    if (
      response?.verified !== true
      || typeof response.context_token !== 'string'
      || !/^[A-Za-z0-9_-]{32,128}$/.test(response.context_token)
      || !Number.isInteger(response.expires_at)
      || response.expires_at <= Math.floor(Date.now() / 1000)
    ) throw new Error('The billing service returned an invalid or expired device context.');
    trustedContextToken = response.context_token;
    setHotspotContext(trustedContextToken);
    try { sessionStorage.setItem('dz_hotspot_context', trustedContextToken); } catch { /* session-only */ }
  } catch {
    trustedContextToken = '';
    setHotspotContext('');
  }
  return trustedContextToken;
}

async function identifyCurrentDevice() {
  deviceMessage.dataset.state = 'identifying';
  deviceMessage.textContent = 'Verifying this device with the trusted router attestation…';
  if (trustedContextToken && captiveIp && captiveMac) {
    verifiedMac = String(captiveMac).replaceAll('-', ':').toUpperCase();
    deviceMessage.className = 'field-help success-text';
    deviceMessage.dataset.state = 'verified';
    deviceMessage.textContent = 'This device was verified by the billing service against its approved MikroTik router.';
    return;
  }
  if (captiveIp && captiveMac) {
    trustedContextToken = await initializeTrustedContext();
    if (trustedContextToken) return identifyCurrentDevice();
  }
  verifiedMac = '';
  deviceMessage.className = 'field-help error-text';
  deviceMessage.dataset.state = 'failed';
  deviceMessage.textContent = 'Device verification is unavailable. Reopen this checkout from the MikroTik WiFi sign-in page; purchases require trusted router verification.';
}

try {
  trustedContextToken = await initializeTrustedContext();
  const response = await getPortalPackages(trustedContextToken);
  const plans = api.rows(response);
  plan = plans.find((item) => (item._id || item.id) === packageId);
  if (!plan) throw new Error('This package is no longer available. Choose a live package from the home page.');

  summary.innerHTML = `
    <div class="plan-price-large">${formatCurrency(plan.price)}</div>
    <h2>${esc(plan.name)}</h2>
    <p>${esc(plan.description || 'Internet access')}</p>
    <div class="plan-facts">
      <span>${esc(plan.duration_hours)} hours</span>
      <span>${esc(plan.rate_limit || 'Standard speed')}</span>
      <span>${plan.data_allowance_mb ? `${esc(plan.data_allowance_mb)} MB` : 'No data cap listed'}</span>
      <span>Up to ${esc(plan.max_devices || 1)} device(s)</span>
    </div>`;
  payButton.textContent = `Pay ${formatCurrency(plan.price)} with M-Pesa`;
  await identifyCurrentDevice();
} catch (error) {
  summary.textContent = error.message;
  payButton.disabled = true;
}

document.querySelectorAll('[data-device]').forEach((choice) => {
  choice.addEventListener('click', () => {
    // Until secure device pairing is supported by the backend, purchases are
    // limited to the client that was independently attested on this router.
    selectedDevice = 'this_device';
    deviceTypeInput.value = 'this_device';
    document.querySelectorAll('[data-device]').forEach((item) => {
      item.classList.toggle('active', item === choice);
      item.setAttribute('aria-pressed', String(item === choice));
    });
  });
});

phoneInput.addEventListener('input', (event) => {
  event.target.value = event.target.value.replace(/\D/g, '').slice(0, 9);
});

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  errorBox.hidden = true;
  const phone = phoneInput.value.replace(/\D/g, '');
  if (phone.length !== 9) {
    errorBox.textContent = 'Enter exactly 9 digits after +254.';
    errorBox.hidden = false;
    return;
  }
  if (!verifiedMac) {
    errorBox.textContent = 'Reconnect through the DevZen WiFi sign-in page so this device can be verified.';
    errorBox.hidden = false;
    return;
  }
  if (!trustedContextToken) {
    errorBox.textContent = 'Secure router verification is required before payment.';
    errorBox.hidden = false;
    return;
  }

  payButton.disabled = true;
  payButton.innerHTML = '<span class="spinner-border spinner-border-sm" aria-hidden="true"></span> Sending STK prompt…';
  try {
    if (!purchaseIdempotencyKey) purchaseIdempotencyKey = getOrCreatePurchaseKey(packageId);
    if (!purchaseIdempotencyKey) throw new Error('Secure checkout is unavailable in this browser.');
    const response = api.data(await startMpesaCheckout(packageId, `254${phone}`, selectedDevice, verifiedMac, captiveIp, trustedContextToken, purchaseIdempotencyKey));
    const next = new URLSearchParams(location.search);
    next.set('ref', response.checkout_request_id);
    location.href = `/payment-status.html?${next}`;
  } catch (error) {
    errorBox.textContent = error.message;
    errorBox.hidden = false;
    payButton.disabled = false;
    payButton.textContent = `Pay ${formatCurrency(plan.price)} with M-Pesa`;
  }
});
