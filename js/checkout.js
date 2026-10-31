import { API } from './api.config.js';
import { getPortalPackages, startMpesaCheckout, attestHotspotDevice, getHotspotContext, setHotspotContext, api } from './api.js';
import { $, formatCurrency, esc } from './ui.js';

const params = new URLSearchParams(location.search);
const packageId = params.get('pkg');
const summary = $('#package-summary');
const form = $('#checkout-form');
const targetFields = $('#target-device-fields');
const macInput = $('#mac');
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
let verifiedDevice = null;
let deviceLookupSequence = 0;
let plan = null;
let trustedContextToken = getHotspotContext();

async function initializeTrustedContext() {
  if (!captiveIp && !captiveMac) return trustedContextToken;
  if (!captiveIp || !captiveMac) {
    setHotspotContext('');
    trustedContextToken = '';
    return '';
  }
  try {
    const response = api.data(await attestHotspotDevice(captiveIp, captiveMac));
    trustedContextToken = response?.context_token || '';
    setHotspotContext(trustedContextToken);
  } catch {
    trustedContextToken = '';
    setHotspotContext('');
  }
  return trustedContextToken;
}

async function verifyDevice(payload) {
  const sequence = ++deviceLookupSequence;
  verifiedMac = '';
  verifiedDevice = null;
  deviceMessage.className = 'field-help';
  deviceMessage.dataset.state = 'verifying';
  deviceMessage.textContent = 'Verifying device against the MikroTik DHCP lease…';
  try {
    const response = api.data(await api.post(API.portal.deviceLookup, payload, { auth: false }));
    if (sequence !== deviceLookupSequence) return;
    if (response.verification_status !== 'verified' || !response.router_id || !response.mac_address) {
      throw new Error('The router did not return a complete DHCP verification result.');
    }
    verifiedDevice = response;
    verifiedMac = String(response.mac_address).replaceAll('-', ':').toUpperCase();
    if (selectedDevice !== 'this_device') macInput.value = verifiedMac;
    deviceMessage.className = 'field-help success-text';
    deviceMessage.dataset.state = 'verified';
    deviceMessage.textContent = `Device verified on ${response.router_name || 'this Wi-Fi network'}${response.site_id ? ` · site ${response.site_id}` : ''}.`;
  } catch (error) {
    if (sequence !== deviceLookupSequence) return;
    verifiedDevice = null;
    verifiedMac = '';
    deviceMessage.className = 'field-help error-text';
    deviceMessage.dataset.state = 'failed';
    deviceMessage.textContent = `Device verification failed: ${error.message}`;
  }
}

function identifyCurrentDevice() {
  deviceLookupSequence += 1;
  targetFields.hidden = true;
  macInput.required = false;
  deviceMessage.dataset.state = 'identifying';
  deviceMessage.textContent = 'Identifying this device from the MikroTik captive redirect…';
  if (captiveIp && captiveMac) return verifyDevice({ ip_address: captiveIp, mac_address: captiveMac });
  if (captiveIp) return verifyDevice({ ip_address: captiveIp });
  if (captiveMac) return verifyDevice({ mac_address: captiveMac });
  verifiedMac = '';
  verifiedDevice = null;
  deviceMessage.className = 'field-help error-text';
  deviceMessage.dataset.state = 'failed';
  deviceMessage.textContent = 'Device details were not provided by the hotspot. Reconnect to DevZen Wi-Fi and reopen its sign-in page to continue.';
}

function identifyOtherDevice() {
  deviceLookupSequence += 1;
  targetFields.hidden = false;
  macInput.required = true;
  macInput.value = '';
  verifiedMac = '';
  verifiedDevice = null;
  deviceMessage.className = 'field-help';
  deviceMessage.textContent = 'Connect the selected device to this Wi-Fi, enter its MAC address, then verify it.';
}

macInput.addEventListener('input', () => {
  deviceLookupSequence += 1;
  verifiedMac = '';
  verifiedDevice = null;
  deviceMessage.dataset.state = 'identifying';
});

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
  identifyCurrentDevice();
} catch (error) {
  summary.textContent = error.message;
  payButton.disabled = true;
}

document.querySelectorAll('[data-device]').forEach((choice) => {
  choice.addEventListener('click', () => {
    selectedDevice = choice.dataset.device;
    deviceTypeInput.value = selectedDevice;
    document.querySelectorAll('[data-device]').forEach((item) => {
      item.classList.toggle('active', item === choice);
      item.setAttribute('aria-pressed', String(item === choice));
    });
    if (selectedDevice === 'this_device') identifyCurrentDevice();
    else identifyOtherDevice();
  });
});

$('#verify-device').addEventListener('click', () => {
  const mac = macInput.value.trim();
  if (!mac) {
    deviceMessage.className = 'field-help error-text';
    deviceMessage.textContent = 'Enter the connected target device’s MAC address.';
    return;
  }
  verifyDevice({ mac_address: mac });
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
    errorBox.textContent = selectedDevice === 'this_device'
      ? 'Reconnect through the DevZen Wi-Fi sign-in page so this device can be verified.'
      : 'Verify the connected target device before continuing.';
    errorBox.hidden = false;
    return;
  }

  payButton.disabled = true;
  payButton.innerHTML = '<span class="spinner-border spinner-border-sm" aria-hidden="true"></span> Sending STK prompt…';
  try {
    const response = api.data(await startMpesaCheckout(packageId, `254${phone}`, selectedDevice, verifiedMac, verifiedDevice?.ip_address, trustedContextToken));
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
