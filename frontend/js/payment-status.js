import { pollCheckoutStatus } from './api.js';
import { $, esc } from './ui.js';

const reference = new URLSearchParams(location.search).get('ref');
const host = $('#payment-state');
const statusMessage = $('#status-message');
let alive = true;
let attempts = 0;
let running = false;

function renderConfirmed(data) {
  const receipt = String(data.access_token || '');
  const username = String(data.login_username || '');
  host.innerHTML = `
    <div class="success-check">✓</div>
    <div class="eyebrow">PAYMENT CONFIRMED</div>
    <h1>Your WiFi access is ready</h1>
    <p>Use this M-Pesa receipt as your access token:</p>
    <button class="voucher-code" id="copy-receipt" type="button">${esc(receipt)}</button>
    <p id="router-login-progress" role="status" aria-live="polite">Submitting your paid login to MikroTik…</p>
    <div id="router-login-form-host"></div>
    <p class="muted-small">The payment is confirmed. Internet access starts only after MikroTik accepts the login through RADIUS. If the automatic login does not complete, tap Connect now. Do not pay again.</p>
    <a class="back-link" href="/index.html">Back to packages</a>`;
  $('#copy-receipt').onclick = () => navigator.clipboard?.writeText(receipt);

  const redirect = window.MikrotikLogin?.parseRedirectParameters(location.search);
  const formHost = $('#router-login-form-host');
  if (!redirect?.ok || !username) {
    $('#router-login-progress').textContent = redirect?.message || 'Payment confirmed. Reopen the WiFi sign-in page to submit the router login.';
    return;
  }
  try {
    const submission = window.MikrotikLogin.createLoginSubmission(redirect, username);
    const form = document.createElement('form');
    form.id = 'paid-router-login-form';
    form.method = submission.method;
    form.action = submission.action;
    for (const [name, value] of Object.entries(submission.fields)) {
      const input = document.createElement('input');
      input.type = 'hidden';
      input.name = name;
      input.value = value;
      form.appendChild(input);
    }
    const button = document.createElement('button');
    button.type = 'submit';
    button.className = 'btn btn-primary';
    button.textContent = 'Connect now';
    form.appendChild(button);
    form.addEventListener('submit', () => {
      $('#router-login-progress').textContent = 'MikroTik is processing your login and will open the original destination after acceptance.';
    }, { once: true });
    formHost.appendChild(form);
    window.setTimeout(() => form.isConnected && form.requestSubmit(), 500);
  } catch (error) {
    $('#router-login-progress').textContent = `Payment confirmed. Router login could not be prepared: ${error.message}`;
  }
}

function renderPendingReview(message) {
  host.innerHTML = `
    <div class="eyebrow">PAYMENT RECEIVED</div>
    <h1>Access is being reviewed</h1>
    <p>${esc(message || 'Your payment was confirmed but the access details require support review.')}</p>
    <p>Do not pay again. Contact support and provide the M-Pesa message.</p>
    <a class="back-link" href="/index.html">Back to packages</a>`;
}

function renderFailed(data) {
  host.innerHTML = `
    <div class="status-fail">!</div>
    <div class="eyebrow">PAYMENT ${esc(data.status)}</div>
    <h1>Payment not completed</h1>
    <p>${esc(data.result_desc || 'The payment was not completed. You can try again.')}</p>
    <a class="btn btn-primary" href="/index.html">Try another package</a>`;
}

async function poll() {
  if (!reference || running || !alive) return;
  running = true;
  while (alive && attempts < 45) {
    attempts += 1;
    try {
      let context = '';
      try { context = sessionStorage.getItem('dz_hotspot_context') || ''; } catch { /* session-only storage may be unavailable */ }
      const data = (await pollCheckoutStatus(reference, context))?.data || {};
      if (data.status === 'success' && data.settled === true && data.access_token && data.login_username) {
        try { sessionStorage.removeItem('dz_hotspot_purchase_key'); } catch { /* optional */ }
        renderConfirmed(data);
        return;
      }
      if (data.status === 'success' && data.settlement_review_required) {
        renderPendingReview(data.result_desc);
        return;
      }
      if (['failed', 'cancelled', 'timeout'].includes(data.status)) {
        try { sessionStorage.removeItem('dz_hotspot_purchase_key'); } catch { /* optional */ }
        renderFailed(data);
        return;
      }
      statusMessage.textContent = 'Waiting for Safaricom confirmation and secure access activation…';
    } catch (error) {
      statusMessage.textContent = error.message || 'Payment status could not be checked. No additional payment was started.';
    }
    await new Promise((resolve) => setTimeout(resolve, 3000));
  }
  if (alive) {
    statusMessage.textContent = 'Payment confirmation is still pending. Do not pay again; you can keep checking safely.';
    const retry = document.createElement('button');
    retry.className = 'btn';
    retry.textContent = 'Continue checking';
    retry.onclick = () => { attempts = 0; running = false; poll(); };
    host.appendChild(retry);
  }
  running = false;
}

if (!reference) {
  host.innerHTML = '<div class="eyebrow">CHECKOUT</div><h1>Reference not found</h1><p>Return to packages and start checkout again.</p><a class="btn btn-primary" href="/index.html">Browse packages</a>';
} else {
  poll();
}

window.addEventListener('pagehide', () => { alive = false; });
