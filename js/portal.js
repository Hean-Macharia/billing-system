import{request}from'./api.js';import{formatCurrency}from'./ui.js';
function getDefaultApiBase() {
      if (typeof window === 'undefined') return 'http://localhost:8000';
      const { protocol, hostname, port } = window.location;
      const localHosts = ['localhost', '127.0.0.1', '0.0.0.0'];
      const devPorts = ['3000', '4173', '5173', '5500', '5501', '5502'];
      if (localHosts.includes(hostname) && (devPorts.includes(port) || (port && port !== '8000' && port !== '8080'))) return 'http://localhost:8000';
      if (protocol === 'file:') return 'http://localhost:8000';
      if (devPorts.includes(port)) return `${protocol}//${hostname}:8000`;
      return `${protocol}//${hostname}${port ? `:${port}` : ''}`;
    }

    let API_BASE_URL = localStorage.getItem('hotspot_api_base') || getDefaultApiBase();
    const SUPPORT_PHONE = '+254791196121';
    const SUPPORT_EMAIL = 'heannjuki@gmail.com';
    const PORTAL_PARAMS = new URLSearchParams(window.location.search);
    document.querySelectorAll('a[href="/voucher.html"]').forEach((link) => { if (window.location.search) link.href += window.location.search; });
    const CAPTIVE_REDIRECT = MikrotikLogin.parseRedirectParameters(window.location.search);
    const CLIENT_MAC = PORTAL_PARAMS.get('mac')
      || PORTAL_PARAMS.get('client_mac')
      || PORTAL_PARAMS.get('mac-address')
      || PORTAL_PARAMS.get('calling_station_id')
      || '';
    const CLIENT_IP = PORTAL_PARAMS.get('ip')
      || PORTAL_PARAMS.get('client_ip')
      || PORTAL_PARAMS.get('address')
      || '';
    const HOTSPOT_CONTEXT_KEY = 'dz_hotspot_context';

    function saveHotspotContext(value) {
      try {
        if (value) sessionStorage.setItem(HOTSPOT_CONTEXT_KEY, value);
        else sessionStorage.removeItem(HOTSPOT_CONTEXT_KEY);
      } catch {}
    }

    function readHotspotContext() {
      try { return sessionStorage.getItem(HOTSPOT_CONTEXT_KEY) || ''; } catch { return ''; }
    }

    function voucherLoginMarkup(voucherCode, options = {}) {
      if (!CAPTIVE_REDIRECT.ok) {
        const message = CAPTIVE_REDIRECT.message
          || 'Voucher verified, but no MikroTik login URL was provided. Open the WiFi login page again to connect.';
        return `<p>${escapeHtml(message)} Voucher verification does not connect you by itself.</p>`;
      }

      const submission = MikrotikLogin.createLoginSubmission(CAPTIVE_REDIRECT, voucherCode);
      const fields = Object.entries(submission.fields)
        .map(([name, value]) => `<input type="hidden" name="${escapeHtml(name)}" value="${escapeHtml(value)}">`)
        .join('');
      const formId = options.autoSubmit ? 'paid-router-login-form' : '';
      return `
        <form ${formId ? `id="${formId}"` : ''} action="${escapeHtml(submission.action)}" method="${submission.method}">
          ${fields}
          <button class="btn btn-primary" type="submit">${options.autoSubmit ? 'Connect now' : 'Connect to WiFi'}</button>
        </form>
        <p>${options.autoSubmit ? 'Your paid login is being submitted to MikroTik. Internet access starts only after the router accepts this login through RADIUS.' : 'Your voucher is verified. Internet access starts only after MikroTik accepts this login through RADIUS.'}</p>
        ${CAPTIVE_REDIRECT.message ? `<p>${escapeHtml(CAPTIVE_REDIRECT.message)}</p>` : ''}`;
    }

    const Icons = {
      wifi: '📶',
      bolt: '⚡',
      clock: '⏱',
      device: '📱',
      check: '✓',
      x: '×'
    };

    function escapeHtml(value) {
      return String(value ?? '').replace(/[&<>"']/g, (char) => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;'
      })[char]);
    }

    function fmtDuration(hours) {
      if (hours >= 24 && hours % 24 === 0) {
        const days = hours / 24;
        return days === 1 ? '24 Hours' : `${days} Days`;
      }
      if (hours < 1) return `${Math.round(hours * 60)} Minutes`;
      return `${hours} Hours`;
    }

    async function api(path, opts = {}) {
      return request(path, { method: opts.method || 'GET', body: opts.body, headers: opts.headers || {}, auth: false });
    }

    let attestationJob = null;
    async function attestCurrentHotspotDevice() {
      if (attestationJob) return attestationJob;
      attestationJob = attestCurrentHotspotDeviceOnce();
      try { return await attestationJob; }
      finally { attestationJob = null; }
    }

    async function attestCurrentHotspotDeviceOnce() {
      if (!CLIENT_IP || !CLIENT_MAC) {
        saveHotspotContext('');
        return '';
      }
      try {
        const result = await api('/api/v1/hotspot/devices/attest', {
          method: 'POST',
          body: { ip_address: CLIENT_IP, mac_address: CLIENT_MAC },
        });
        const data = result?.data;
        const token = data?.verified === true
          && typeof data.context_token === 'string'
          && /^[A-Za-z0-9_-]{32,128}$/.test(data.context_token)
          && Number.isInteger(data.expires_at)
          && data.expires_at > Math.floor(Date.now() / 1000)
          ? data.context_token : '';
        saveHotspotContext(token);
        return token;
      } catch {
        saveHotspotContext('');
        return '';
      }
    }

    async function checkBackend() {
      const status = document.getElementById('api-status');
      status.className = 'api-status api-status-checking';
      status.innerHTML = '<i></i> Checking service';
      try {
        await api('/health/ready');
        status.className = 'api-status api-status-online';
        status.innerHTML = '<i></i> Service online';
        status.title = `Connected to ${API_BASE_URL}`;
        return true;
      } catch (error) {
        status.className = 'api-status api-status-offline';
        status.innerHTML = '<i></i> Service offline';
        status.title = error.message;
        return false;
      }
    }

    document.getElementById('backend-settings').addEventListener('click', async () => {
      const current = API_BASE_URL;
      const entered = window.prompt('Billing API address (for example, http://192.168.1.10:8000)', current);
      if (entered === null) { await checkBackend(); return; }
      try {
        const url = new URL(entered.trim());
        if (!['http:', 'https:'].includes(url.protocol)) throw new Error('Use an HTTP or HTTPS address.');
        API_BASE_URL = url.origin;
        localStorage.setItem('hotspot_api_base', API_BASE_URL);
        await checkBackend();
      } catch (error) {
        window.alert(error.message || 'Enter a valid backend address.');
      }
    });

    function showResourceDialog(title, content) {
      document.querySelector('.sheet-overlay')?.remove();
      const overlay = document.createElement('div');
      overlay.className = 'sheet-overlay';
      overlay.dataset.purchaseKey = globalThis.crypto?.randomUUID?.() || '';
      overlay.innerHTML = `
        <div class="sheet" role="dialog" aria-modal="true" aria-label="${escapeHtml(title)}">
          <div class="sheet-header">
            <h3>${escapeHtml(title)}</h3>
            <button class="sheet-close" type="button" aria-label="Close">×</button>
          </div>
          <div class="sheet-body">${content}</div>
        </div>`;
      document.body.appendChild(overlay);
      overlay.querySelector('.sheet-close').addEventListener('click', () => overlay.remove());
      overlay.addEventListener('click', (event) => {
        if (event.target === overlay) overlay.remove();
      });
      return overlay;
    }

    function normalizeKenyanPhone(value) {
      let phone = String(value || '').replace(/\D/g, '');
      if (phone.startsWith('0')) phone = `254${phone.slice(1)}`;
      else if (phone.startsWith('7') || phone.startsWith('1')) phone = `254${phone}`;
      return /^254(7|1)\d{8}$/.test(phone) ? phone : '';
    }

    async function openReceiptReconnect() {
      const overlay = showResourceDialog('Already paid? Reconnect', `
        <p>Enter the M-Pesa receipt from your confirmed payment. No new payment will be requested.</p>
        <form id="receipt-reconnect-form">
          <label for="reconnect-receipt">M-Pesa receipt / access token</label>
          <input id="reconnect-receipt" maxlength="32" autocomplete="off" required>
          <label for="reconnect-phone">Phone number (optional)</label>
          <input id="reconnect-phone" type="tel" inputmode="numeric" placeholder="0712345678">
          <div id="reconnect-error" class="error-text" role="status" aria-live="polite"></div>
          <button id="reconnect-submit" class="btn btn-primary" type="submit">Verify and connect</button>
        </form>`);
      const form = overlay.querySelector('#receipt-reconnect-form');
      const errorBox = overlay.querySelector('#reconnect-error');
      const button = overlay.querySelector('#reconnect-submit');
      form.addEventListener('submit', async (event) => {
        event.preventDefault();
        if (!CAPTIVE_REDIRECT.ok) {
          errorBox.textContent = CAPTIVE_REDIRECT.message || 'Open the portal from the MikroTik WiFi sign-in page before reconnecting.';
          return;
        }
        const receipt = form.elements['reconnect-receipt'].value.trim();
        const rawPhone = form.elements['reconnect-phone'].value.trim();
        const phone = rawPhone ? normalizeKenyanPhone(rawPhone) : '';
        if (!/^[A-Za-z0-9]{4,32}$/.test(receipt) || (rawPhone && !phone)) {
          errorBox.textContent = 'Enter a valid M-Pesa receipt and, if supplied, a valid Kenyan phone number.';
          return;
        }
        button.disabled = true;
        button.textContent = 'Verifying…';
        errorBox.textContent = '';
        try {
          let context = readHotspotContext();
          if (!context) context = await attestCurrentHotspotDevice();
          if (!context) throw new Error('This device could not be verified on the connected router. Reopen the WiFi sign-in page.');
          const response = await api('/api/v1/hotspot/reconnect', {
            method: 'POST',
            body: { receipt, ...(phone ? { phone_number: phone } : {}) },
            headers: { 'X-Hotspot-Context': context },
          });
          const data = response?.data;
          if (data?.verified !== true || typeof data.login_username !== 'string') throw new Error('The billing API returned an incomplete reconnect authorization.');
          overlay.querySelector('.sheet-body').innerHTML = `
            <div class="status-screen"><h3>Receipt verified</h3>
            <p>Your paid access is being submitted to MikroTik. Do not pay again.</p>
            <div class="voucher-box"><div class="code">${escapeHtml(data.access_token)}</div><div class="tap">M-Pesa receipt</div></div>
            <p id="reconnect-progress" role="status" aria-live="polite">Submitting the HTTP-CHAP login…</p>
            ${voucherLoginMarkup(data.login_username, { autoSubmit: true })}</div>`;
          const loginForm = overlay.querySelector('#paid-router-login-form');
          loginForm?.addEventListener('submit', () => {
            const progress = overlay.querySelector('#reconnect-progress');
            if (progress) progress.textContent = 'MikroTik is processing the login and will return you to the requested destination after acceptance.';
          }, { once: true });
          if (loginForm) window.setTimeout(() => loginForm.isConnected && loginForm.requestSubmit(), 500);
        } catch (error) {
          errorBox.textContent = error.message || 'The receipt could not be verified. No payment was initiated.';
          button.disabled = false;
          button.textContent = 'Verify and connect';
        }
      });
    }

    function openBalanceCheck() {
      const overlay = showResourceDialog('Check voucher status', `
        <p>Check whether your DEVZEN CREATIONS WiFi voucher is active and view its expiry. Remaining balance is not available through this API.</p>
        <form id="balance-form">
          <label for="voucher-code">Voucher code</label>
          <input type="text" id="voucher-code" name="voucher_code" autocomplete="off" required maxlength="32" />
          <div class="error-text" id="balance-result" role="status"></div>
          <button type="submit" class="btn btn-primary" id="balance-submit">Check status</button>
        </form>`);
      const result = overlay.querySelector('#balance-result');
      overlay.querySelector('#balance-form').addEventListener('submit', async (event) => {
        event.preventDefault();
        const code = overlay.querySelector('#voucher-code').value.trim();
        const submit = overlay.querySelector('#balance-submit');
        result.style.display = 'none';
        submit.disabled = true;
        submit.textContent = 'Checking…';
        try {
          const response = await api(`/api/v1/vouchers/public/check/${encodeURIComponent(code)}`);
          const voucher = response.data;
          const expiry = voucher.expiry_date ? new Date(voucher.expiry_date).toLocaleString() : 'Not specified';
          const allowance = voucher.data_allowance_mb == null ? 'Unlimited data' : `${voucher.data_allowance_mb} MB`;
          result.textContent = voucher.valid
            ? `${voucher.status === 'used' ? 'Voucher is ready for a paired device.' : 'Voucher is active.'} ${voucher.duration_hours ?? '—'} hours, ${allowance}. Devices: up to ${voucher.max_devices ?? 1}. Expires: ${expiry}.`
            : (voucher.reason || 'This voucher is not active.');
          result.style.display = 'block';
        } catch (error) {
          result.textContent = error.message;
          result.style.display = 'block';
        } finally {
          submit.disabled = false;
          submit.textContent = 'Check status';
        }
      });
      overlay.querySelector('#voucher-code').focus();
    }

    function openFreeTrial() {
      if (!CLIENT_MAC && !CLIENT_IP) {
        showResourceDialog('Free trial access', `
          <p>This three-minute trial is issued once per device. Open this page from the DEVZEN CREATIONS MikroTik captive portal so it can provide your device MAC address.</p>
          <p>If the hotspot opened this page but the device could not be identified, contact support:</p>
          <p><a href="tel:${SUPPORT_PHONE}">${SUPPORT_PHONE}</a><br/><a href="mailto:${SUPPORT_EMAIL}">${SUPPORT_EMAIL}</a></p>`);
        return;
      }

      const overlay = showResourceDialog('Free 3-minute trial', `
        <div id="trial-content">
          <p>Get one free 3-minute WiFi session for this device. The voucher expires if it is not used within 10 minutes.</p>
          <button type="button" class="btn btn-primary" id="request-trial">Start free trial</button>
          <div class="error-text" id="trial-result" role="status"></div>
        </div>`);
      const button = overlay.querySelector('#request-trial');
      const result = overlay.querySelector('#trial-result');
      button.addEventListener('click', async () => {
        button.disabled = true;
        button.textContent = 'Preparing trial…';
        result.style.display = 'none';
        try {
          const response = await api('/api/v1/hotspot/free-trial', {
            method: 'POST',
            body: { ...(CLIENT_IP ? { ip_address: CLIENT_IP } : {}), ...(CLIENT_MAC ? { client_mac: CLIENT_MAC } : {}) }
          });
          const trial = response.data;
          overlay.querySelector('#trial-content').innerHTML = `
            <p>Your 3-minute trial is ready. Use this voucher to sign in:</p>
            <div class="voucher-box">
              <div class="code">${escapeHtml(trial.voucher_code)}</div>
            </div>
            ${voucherLoginMarkup(trial.voucher_code)}
            <p>Use it before ${escapeHtml(new Date(trial.redeem_before).toLocaleTimeString())}. This device can claim a trial once.</p>`;
        } catch (error) {
          result.textContent = error.status === 409
            ? 'This device has already claimed its free trial.'
            : error.message;
          result.style.display = 'block';
          button.disabled = false;
          button.textContent = 'Start free trial';
        }
      });
    }

    function getPlanAccentLabel(plan) {
      const name = String(plan.name || '').toLowerCase();
      if (/unlimited\s*40\s*minutes?/.test(name) || /unlimited\s*30\s*days?/.test(name)) return 'Hot Deal';
      if (/24\s*hrs?\s*10\s*mbps/.test(name)) return 'Best Value';
      if (/500\s*mb/.test(name)) return 'Limited';
      if (/unlimited\s*2\s*hrs?/.test(name)) return 'Popular';
      return '';
    }

    function formatDataAllowance(plan) {
      if (plan.data_allowance_mb == null) return 'Unlimited data';
      const mb = Number(plan.data_allowance_mb);
      const cap = `${new Intl.NumberFormat().format(mb)} MB total`;
      const bonus = String(plan.description || '').match(/(?:\+\s*[\d.]+\s*(?:GB|MB)\s*BONUS|BONUS\s*[\d.]+\s*(?:GB|MB))/i);
      return bonus ? `${cap} · ${bonus[0]}` : cap;
    }

    function getPlanClass(plan) {
      const label = getPlanAccentLabel(plan);
      if (label === 'Hot Deal') return 'featured';
      if (label === 'Popular' || label === 'Best Value') return 'popular';
      return '';
    }

    async function loadPlans() {
      const listEl = document.getElementById('plan-list');
      try {
        const contextToken = await attestCurrentHotspotDevice();
        let res;
        for (let attempt = 0; ; attempt += 1) {
          try {
            res = await api('/api/v1/hotspot/plans/public', {
              headers: contextToken ? { 'X-Hotspot-Context': contextToken } : {},
            });
            break;
          } catch (error) {
            const canRetry = [502, 503, 504].includes(error.status) && attempt < 2;
            if (!canRetry) throw error;
            await new Promise((resolve) => setTimeout(resolve, 500 * (attempt + 1)));
          }
        }
        const plans = (res.data || []).slice().sort((a, b) => Number(a.price) - Number(b.price));

        if (!plans.length) {
          listEl.innerHTML = '<div class="error-box">No plans are available right now. Please try again shortly.</div>';
          return;
        }

        listEl.innerHTML = plans.map((plan, index) => {
          const title = plan.name || plan.description || 'Internet bundle';
          const cardClass = getPlanClass(plan);
          const label = getPlanAccentLabel(plan);
          const duration = fmtDuration(Number(plan.duration_hours || 1));
          const rate = plan.rate_limit || 'Up to 10 Mbps';
          const devices = plan.max_devices || 1;
          return `
            <article class="plan-card ${cardClass}" data-plan-index="${index}" tabindex="0" role="button" aria-label="Select ${escapeHtml(title)}">
              <div class="pack-visual">
                <div class="signal">${Icons.wifi}</div>
              </div>
              <div class="plan-body">
                <div class="plan-meta">
                  ${label ? `<span class="plan-ribbon">${label}</span>` : '<span></span>'}
                  <span>${duration}</span>
                </div>
                <h3>${escapeHtml(title)}</h3>
                <div class="sub">${escapeHtml(formatDataAllowance(plan))}</div>
                <div class="sub">${escapeHtml(rate)} · Up to ${devices} device${devices > 1 ? 's' : ''}</div>
                ${plan.description ? `<div class="sub">${escapeHtml(plan.description)}</div>` : ''}
                <div class="plan-footer">
                  <div class="plan-price">${formatCurrency(plan.price || 0)}<small>/</small></div>
                  <span class="plan-btn">View package</span>
                </div>
              </div>
            </article>
          `;
        }).join('');

        listEl.querySelectorAll('[data-plan-index]').forEach((card) => {
          const selectCard = () => { const chosen = plans[Number(card.dataset.planIndex)]; const params = new URLSearchParams(window.location.search); params.set('pkg', chosen._id || chosen.id); location.href = `/checkout.html?${params.toString()}`; };
          card.addEventListener('click', selectCard);
          card.addEventListener('keydown', (event) => {
            if (event.key === 'Enter' || event.key === ' ') {
              event.preventDefault();
              selectCard();
            }
          });
        });
      } catch (error) {
        listEl.innerHTML = `<div class="error-box">Couldn't load packages right now. ${escapeHtml(error.message)}<button type="button" id="retry-plans">Try again</button></div>`;
        listEl.querySelector('#retry-plans').addEventListener('click', loadPlans);
      }
    }

    function openPurchaseSheet(plan) {
      const overlay = document.createElement('div');
      overlay.className = 'sheet-overlay';
      const devices = Number(plan.max_devices || 1);
      overlay.innerHTML = `
        <div class="sheet">
          <div class="sheet-header">
            <h3>Complete payment</h3>
            <button class="sheet-close" type="button" aria-label="Close">×</button>
          </div>
          <div class="sheet-body">
            <div class="pay-hero">
              <div class="mini-pic">${Icons.wifi}</div>
              <div>
                <strong>${escapeHtml(plan.name || plan.description || 'Internet bundle')}</strong>
                <span>${escapeHtml(fmtDuration(Number(plan.duration_hours || 1)))}</span>
              </div>
            </div>
            <div class="price-box"><span>Data allowance</span><strong>${escapeHtml(formatDataAllowance(plan))}</strong></div>
            <div class="price-box"><span>Devices supported</span><strong>Up to ${devices}</strong></div>
            <div class="price-box"><span>Speed</span><strong>${escapeHtml(plan.rate_limit || 'Standard hotspot speed')}</strong></div>
            ${plan.description ? `<p>${escapeHtml(plan.description)}</p>` : ''}
            <div class="price-box">
              <span>You are paying for:</span>
              <strong>${formatCurrency(plan.price || 0)}</strong>
            </div>
            <form id="buy-form">
              <label>Who are you buying access for?</label>
              <div class="device-options" role="group" aria-label="Purchase device"><button class="device-choice" type="button" data-device="this_device" aria-pressed="true">This device</button></div>
              <p class="hint">Secure pairing for a different device is not available yet.</p>
              <div id="device-status" class="device-status" role="status" aria-live="polite"></div>
              <label for="phone-input">M-Pesa number</label>
              <input type="tel" id="phone-input" inputmode="numeric" placeholder="0712345678" required />
              <div class="hint">We will send an STK push to this number.</div>
              <div class="error-text" id="buy-error"></div>
              <button type="submit" class="btn btn-primary" id="buy-submit">Complete payment · ${formatCurrency(plan.price || 0)}</button>
              <button type="button" class="btn btn-ghost" id="cancel-btn">Cancel</button>
            </form>
          </div>
        </div>
      `;

      document.body.appendChild(overlay);
      const close = () => overlay.remove();
      overlay.querySelector('.sheet-close').onclick = close;
      overlay.querySelector('#cancel-btn').onclick = close;

      let selectedDevice = 'this_device';
      let verifiedMac = '';
      const deviceStatus = overlay.querySelector('#device-status');
      const normalizeMac = (mac) => String(mac || '').replace(/-/g, ':').toUpperCase();
      const context = readHotspotContext();
      const verified = Boolean(context && CLIENT_MAC);
      verifiedMac = verified ? normalizeMac(CLIENT_MAC) : '';
      deviceStatus.dataset.verified = String(verified);
      deviceStatus.dataset.state = verified ? 'verified' : 'failed';
      deviceStatus.textContent = verified
        ? 'This device has trusted router verification. Verification is repeated before purchase.'
        : 'Reopen the portal from the MikroTik captive login so the router can verify this device.';
      overlay.querySelectorAll('[data-device]').forEach((choice) => {
        choice.addEventListener('click', () => {
          selectedDevice = 'this_device';
          overlay.querySelectorAll('[data-device]').forEach((button) => button.setAttribute('aria-pressed', String(button === choice)));
        });
      });

      overlay.querySelector('#buy-form').addEventListener('submit', async (event) => {
        event.preventDefault();
        const phoneInput = overlay.querySelector('#phone-input');
        const errBox = document.getElementById('buy-error');
        const submitBtn = document.getElementById('buy-submit');
        errBox.style.display = 'none';

        if (!readHotspotContext() || !verifiedMac || deviceStatus.dataset.verified !== 'true') {
          errBox.textContent = 'Verify the device before payment.';
          errBox.style.display = 'block';
          return;
        }

        const phone = normalizeKenyanPhone(phoneInput.value.trim());
        if (!phone) {
          errBox.textContent = 'Enter a valid Safaricom number, e.g. 0712345678';
          errBox.style.display = 'block';
          return;
        }

        submitBtn.disabled = true;
        submitBtn.innerHTML = '<span class="spinner"></span>Sending request...';

        try {
          if (!overlay.dataset.purchaseKey) {
            if (!globalThis.crypto?.getRandomValues) throw new Error('Secure checkout is unavailable in this browser.');
            const bytes = new Uint8Array(24);
            globalThis.crypto.getRandomValues(bytes);
            overlay.dataset.purchaseKey = Array.from(bytes, (value) => value.toString(16).padStart(2, '0')).join('');
          }
          const res = await api('/api/v1/hotspot/purchase', {
            method: 'POST',
            body: {
              plan_id: plan._id,
              phone_number: phone,
              device_type: selectedDevice,
              device_mac: verifiedMac,
              ...(CLIENT_IP ? { ip_address: CLIENT_IP } : {}),
              idempotency_key: overlay.dataset.purchaseKey || globalThis.crypto.randomUUID(),
            },
            headers: { 'X-Hotspot-Context': readHotspotContext() },
          });
          showWaitingScreen(overlay, res.data.checkout_request_id);
        } catch (error) {
          errBox.textContent = error.message || 'Something went wrong. Please try again.';
          errBox.style.display = 'block';
          submitBtn.disabled = false;
          submitBtn.textContent = 'Pay Now';
        }
      });
    }

    function showWaitingScreen(overlay, checkoutRequestId) {
      const sheet = overlay.querySelector('.sheet-body');
      sheet.innerHTML = `
        <div class="status-screen">
          <div class="status-icon waiting">${Icons.clock}</div>
          <h3>Check your phone</h3>
          <p>Enter your M-Pesa PIN to complete the payment. This page will update automatically.</p>
        </div>
      `;

      let attempts = 0;
      let polling = false;
      const poll = setInterval(async () => {
        if (polling) return;
        polling = true;
        attempts += 1;
        try {
          const res = await api(`/api/v1/hotspot/purchase/status/${encodeURIComponent(checkoutRequestId)}`, {
            headers: { 'X-Hotspot-Context': readHotspotContext() },
          });
          const { status, settled, settlement_review_required, access_token, login_username, result_desc } = res.data || {};

          if (status === 'success' && settled === true && access_token && login_username) {
            clearInterval(poll);
            showSuccessScreen(sheet, { accessToken: access_token, loginUsername: login_username, result: res.data });
          } else if (status === 'success' && settlement_review_required) {
            clearInterval(poll);
            showPendingReviewScreen(sheet, result_desc || 'Your payment was confirmed, but the receipt needs support review. Do not pay again.');
          } else if (['failed', 'cancelled', 'timeout'].includes(status)) {
            clearInterval(poll);
            showFailScreen(sheet, result_desc || 'The payment was not completed.');
          } else if (attempts >= 30) {
            clearInterval(poll);
            showStillPendingScreen(sheet, checkoutRequestId);
          }
        } catch (error) {
          if (attempts >= 30) {
            clearInterval(poll);
            showStillPendingScreen(sheet, checkoutRequestId, error.message);
          }
        } finally {
          polling = false;
        }
      }, 3000);
    }

    function showSuccessScreen(sheet, purchase) {
      const { accessToken, loginUsername, result } = purchase;
      sheet.innerHTML = `
        <div class="status-screen">
          <div class="status-icon success">${Icons.check}</div>
          <h3>Payment confirmed</h3>
          <p>${escapeHtml(result.package_name || 'Your internet package')} is ready. M-Pesa receipt and access token:</p>
          <div class="voucher-box" id="voucher-copy">
            <div class="code">${escapeHtml(accessToken)}</div>
            <div class="tap">Tap to copy</div>
          </div>
          <p id="router-login-progress" role="status" aria-live="polite">Submitting your paid login to MikroTik…</p>
          ${voucherLoginMarkup(loginUsername, { autoSubmit: true })}
          <p>If automatic sign-in does not finish, tap “Connect now”. Do not pay again.</p>
        </div>
      `;

      document.getElementById('voucher-copy').onclick = () => {
        navigator.clipboard?.writeText(accessToken);
        const tap = document.querySelector('.voucher-box .tap');
        if (tap) tap.textContent = 'Copied!';
      };
      const loginForm = document.getElementById('paid-router-login-form');
      loginForm?.addEventListener('submit', () => {
        const progress = document.getElementById('router-login-progress');
        if (progress) progress.textContent = 'MikroTik is processing the login. The router will open your original destination after acceptance.';
      }, { once: true });
      if (loginForm && CAPTIVE_REDIRECT.ok) window.setTimeout(() => loginForm.isConnected && loginForm.requestSubmit(), 700);
      else {
        const progress = document.getElementById('router-login-progress');
        if (progress) progress.textContent = 'Payment is confirmed. Reopen this page from the WiFi sign-in screen to submit the router login.';
      }
    }

    function showStillPendingScreen(sheet, checkoutRequestId, detail = '') {
      sheet.innerHTML = `<div class="status-screen"><h3>Payment confirmation is still pending</h3><p>${escapeHtml(detail || 'Do not pay again. Safaricom may still be processing the payment callback.')}</p><button class="btn btn-primary" id="continue-status-check">Continue checking</button><button class="btn btn-ghost" id="close-pending">Close</button></div>`;
      sheet.querySelector('#close-pending').onclick = () => document.querySelector('.sheet-overlay')?.remove();
      sheet.querySelector('#continue-status-check').onclick = () => showWaitingScreen(document.querySelector('.sheet-overlay'), checkoutRequestId);
    }

    function showPendingReviewScreen(sheet, detail) {
      sheet.innerHTML = `<div class="status-screen"><h3>Payment received</h3><p>${escapeHtml(detail)}</p><p>Contact ${escapeHtml(SUPPORT_PHONE)}. Do not pay again.</p></div>`;
    }

    function showFailScreen(sheet, message) {
      sheet.innerHTML = `
        <div class="status-screen">
          <div class="status-icon fail">${Icons.x}</div>
          <h3>Payment not completed</h3>
          <p>${escapeHtml(message)}</p>
          <button class="btn btn-primary" id="retry-btn" style="margin-top: 18px;">Try again</button>
        </div>
      `;
      document.getElementById('retry-btn').onclick = () => document.querySelector('.sheet-overlay')?.remove();
    }

    // Verify an existing voucher and offer MikroTik login.
    document.getElementById('voucher-login-form').addEventListener('submit', async (event) => {
      event.preventDefault();

      const input = document.getElementById('voucher-login-code');
      const button = document.getElementById('voucher-login-submit');
      const result = document.getElementById('voucher-login-result');
      const code = input.value.trim();

      if (!code) {
        result.textContent = 'Please enter your WiFi voucher code.';
        return;
      }

      button.disabled = true;
      button.textContent = 'Verifying...';
      result.textContent = 'Checking your voucher...';

      try {
        const response = await api(
          `/api/v1/vouchers/public/check/${encodeURIComponent(code)}`
        );

        const voucher = response.data;

        if (!voucher || voucher.valid !== true) {
          result.textContent =
            voucher?.reason || 'This voucher is invalid, inactive, or expired.';
          return;
        }

        result.textContent = '';

        const connect = document.createElement('div');
        connect.innerHTML = voucherLoginMarkup(code);
        result.appendChild(connect);

      } catch (error) {
        result.textContent =
          error.message || 'Unable to verify the voucher. Please try again.';
      } finally {
        button.disabled = false;
        button.textContent = 'Verify voucher';
      }
    });

    checkBackend();
    loadPlans();
    document.getElementById('connect-receipt')?.addEventListener('click', openReceiptReconnect);
    document.getElementById('free-trial').addEventListener('click', openFreeTrial);
    if (CAPTIVE_REDIRECT.state === 'invalid') {
      document.getElementById('router-login-notice').textContent = CAPTIVE_REDIRECT.message;
    }
    const routerLoginError = PORTAL_PARAMS.get('router_error') || PORTAL_PARAMS.get('error') || '';
    if (routerLoginError) {
      document.getElementById('router-login-notice').textContent = `MikroTik login was not accepted: ${routerLoginError}`;
    }
    const clientIp = CLIENT_IP;
    if (clientIp) document.getElementById('client-ip').textContent = clientIp;
