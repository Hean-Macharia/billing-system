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

    function formatSpeed(plan) {
      const rate = String(plan?.rate_limit || '').trim().split(/\s+/)[0];
      const candidates = rate ? rate.split('/') : [plan?.download_speed, plan?.upload_speed].filter((value) => value != null).map(String);
      const mbps = candidates.map((value) => {
        const match = String(value).trim().match(/^(\d+(?:\.\d+)?)\s*([kmg]?)$/i);
        if (!match) return NaN;
        const scale = { k: 0.001, m: 1, g: 1000 }[match[2].toLowerCase()] || 1;
        return Number(match[1]) * scale;
      }).filter((value) => Number.isFinite(value) && value > 0);
      if (!mbps.length) return '';
      const max = Math.max(...mbps);
      return `Up to ${Number(max.toFixed(3))} Mbps`;
    }

    const api = PortalApiRequest.createApiRequest(() => API_BASE_URL);

    let deviceAttestationRequest = null;

    async function attestCurrentHotspotDevice(signal) {
      if (deviceAttestationRequest) return deviceAttestationRequest;
      const pending = attestCurrentHotspotDeviceOnce(signal);
      deviceAttestationRequest = pending;
      try {
        return await pending;
      } finally {
        if (deviceAttestationRequest === pending) deviceAttestationRequest = null;
      }
    }

    async function attestCurrentHotspotDeviceOnce(signal) {
      const status = document.getElementById('device-identification-status');
      if (!CLIENT_IP || !CLIENT_MAC) {
        saveHotspotContext('');
        if (status) { status.textContent = ''; status.hidden = true; }
        return '';
      }
      if (status) { status.textContent = ''; status.hidden = true; }
      try {
        const result = await api('/api/v1/hotspot/devices/attest', {
          method: 'POST',
          body: { ip_address: CLIENT_IP, mac_address: CLIENT_MAC },
          timeoutMs: 30000,
          signal,
          timeoutMessage: 'Secure device verification timed out while checking the router. Please reconnect to WiFi and retry.',
        });
        const token = PortalApiRequest.getTrustedContextToken(result);
        saveHotspotContext(token);
        if (status) status.hidden = true;
        return token;
      } catch (error) {
        saveHotspotContext('');
        if (status) { status.textContent = ''; status.hidden = true; }
        return '';
      }
    }

    async function checkBackend() {
      const status = document.getElementById('api-status');
      status.className = 'service-pill api-status api-status-checking';
      status.innerHTML = '<i></i> Checking service';
      try {
        await api('/health/ready');
        status.className = 'service-pill api-status api-status-online';
        status.innerHTML = '<i></i> Service online';
        status.title = `Connected to ${API_BASE_URL}`;
        return true;
      } catch (error) {
        status.className = 'service-pill api-status api-status-offline';
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

    function createPurchaseKey() {
      if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
      if (!globalThis.crypto?.getRandomValues) throw new Error('Secure checkout is unavailable in this browser.');
      const bytes = new Uint8Array(24);
      globalThis.crypto.getRandomValues(bytes);
      return Array.from(bytes, (value) => value.toString(16).padStart(2, '0')).join('');
    }

    function normalizeKenyanPhone(raw) {
      let phone = String(raw || '').replace(/\D/g, '');
      if (phone.startsWith('0')) phone = `254${phone.slice(1)}`;
      else if (phone.startsWith('7') || phone.startsWith('1')) phone = `254${phone}`;
      return /^254(7|1)\d{8}$/.test(phone) ? phone : '';
    }

    async function openReceiptReconnect() {
      const overlay = showResourceDialog('Already paid? Reconnect', `
        <p>Enter the M-Pesa receipt from your confirmed payment. This will not start another payment.</p>
        <form id="receipt-reconnect-form">
          <label for="receipt-input">M-Pesa receipt / access token</label>
          <input id="receipt-input" name="receipt" autocomplete="off" maxlength="32" required>
          <label for="receipt-phone">Phone number (optional)</label>
          <input id="receipt-phone" name="phone" type="tel" inputmode="numeric" placeholder="0712345678">
          <div class="error-text" id="receipt-reconnect-result" role="status" aria-live="polite"></div>
          <button class="btn btn-primary" type="submit" id="receipt-reconnect-submit">Verify and connect</button>
        </form>`);
      const form = overlay.querySelector('#receipt-reconnect-form');
      const errorBox = overlay.querySelector('#receipt-reconnect-result');
      const button = overlay.querySelector('#receipt-reconnect-submit');
      form.addEventListener('submit', async (event) => {
        event.preventDefault();
        if (!CAPTIVE_REDIRECT.ok) {
          errorBox.textContent = CAPTIVE_REDIRECT.message || 'Open this page from the MikroTik WiFi sign-in screen before reconnecting.';
          return;
        }
        const receipt = form.elements.receipt.value.trim().toUpperCase();
        const rawPhone = form.elements.phone.value.trim();
        const phone = rawPhone ? normalizeKenyanPhone(rawPhone) : '';
        if (!/^[A-Z0-9]{4,32}$/.test(receipt)) {
          errorBox.textContent = 'Enter the receipt exactly as shown in the M-Pesa confirmation.';
          return;
        }
        if (rawPhone && !phone) {
          errorBox.textContent = 'Enter a valid Kenyan mobile number.';
          return;
        }
        button.disabled = true;
        button.textContent = 'Verifying device and receipt…';
        errorBox.textContent = '';
        try {
          let context = readHotspotContext();
          if (!context) context = await attestCurrentHotspotDevice();
          if (!context) throw new Error('This device could not be verified on the WiFi router. Reopen the WiFi sign-in page and retry.');
          const result = await api('/api/v1/hotspot/reconnect', {
            method: 'POST',
            body: { receipt, ...(phone ? { phone_number: phone } : {}) },
            headers: { 'X-Hotspot-Context': context },
            timeoutMs: 30000,
            timeoutMessage: 'Receipt verification timed out. No new payment was started; you can retry safely.',
          });
          if (result?.data?.verified !== true || typeof result.data.login_username !== 'string') {
            throw new Error('The billing service returned an incomplete reconnect authorization.');
          }
          overlay.querySelector('.sheet-body').innerHTML = `
            <div class="status-screen">
              <h3>Receipt verified</h3>
              <p>Your paid access is being submitted to MikroTik. Do not pay again.</p>
              <div class="voucher-box"><div class="code">${escapeHtml(result.data.access_token)}</div><div class="tap">M-Pesa receipt</div></div>
              <p id="reconnect-login-progress" role="status" aria-live="polite">Submitting the HTTP-CHAP login…</p>
              ${voucherLoginMarkup(result.data.login_username, { autoSubmit: true })}
            </div>`;
          const loginForm = overlay.querySelector('#paid-router-login-form');
          loginForm?.addEventListener('submit', () => {
            const progress = overlay.querySelector('#reconnect-login-progress');
            if (progress) progress.textContent = 'MikroTik is processing your login. The router will return you to the requested destination after acceptance.';
          }, { once: true });
          if (loginForm) window.setTimeout(() => loginForm.isConnected && loginForm.requestSubmit(), 500);
        } catch (error) {
          errorBox.textContent = error.message || 'The receipt could not be verified. No new payment was started.';
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

    function formatDataAllowance(plan) {
      if (plan.data_allowance_mb == null) return 'Unlimited data';
      const mb = Number(plan.data_allowance_mb);
      const cap = `${new Intl.NumberFormat().format(mb)} MB total`;
      const bonus = String(plan.description || '').match(/(?:\+\s*[\d.]+\s*(?:GB|MB)\s*BONUS|BONUS\s*[\d.]+\s*(?:GB|MB))/i);
      return bonus ? `${cap} · ${bonus[0]}` : cap;
    }

    let plansRequest = null;
    let plansRequestController = null;
    let plansRequestGeneration = 0;

    function loadPlans() {
      if (plansRequest) return plansRequest;
      const generation = ++plansRequestGeneration;
      plansRequestController = new AbortController();
      plansRequest = loadPlansOnce(generation, plansRequestController.signal)
        .finally(() => {
          if (generation === plansRequestGeneration) {
            plansRequest = null;
            plansRequestController = null;
          }
        });
      return plansRequest;
    }

    async function loadPlansOnce(generation, signal) {
      const listEl = document.getElementById('plan-list');
      listEl.setAttribute('aria-busy', 'true');
      try {
        const contextToken = await attestCurrentHotspotDevice(signal);
        if (generation !== plansRequestGeneration || signal.aborted) return;
        let res;
        for (let attempt = 0; ; attempt += 1) {
          try {
            res = await api('/api/v1/hotspot/plans/public', {
              headers: contextToken ? { 'X-Hotspot-Context': contextToken } : {},
              signal,
            });
            break;
          } catch (error) {
            const canRetry = [502, 503, 504].includes(error.status) && attempt < 2;
            if (!canRetry) throw error;
            await new Promise((resolve) => setTimeout(resolve, 500 * (attempt + 1)));
          }
        }
        if (generation !== plansRequestGeneration || signal.aborted) return;
        const plans = (res.data || []).slice().sort((a, b) => Number(a.price) - Number(b.price));

        if (!plans.length) {
          listEl.innerHTML = '<div class="error-box">No plans are available right now. Please try again shortly.</div>';
          return;
        }

        listEl.innerHTML = plans.map((plan, index) => {
          const title = plan.name || plan.description || 'Internet bundle';
          const duration = fmtDuration(Number(plan.duration_hours || 1));
          const rate = formatSpeed(plan);
          const devices = plan.max_devices || 1;
          const price = new Intl.NumberFormat('en-KE', { minimumFractionDigits: 0, maximumFractionDigits: 2 }).format(Number(plan.price || 0));
          const badge = ['HOT_DEAL', 'LIMITED'].includes(String(plan.badge || '').toUpperCase())
            ? `<span class="plan-ribbon ${String(plan.badge).toLowerCase() === 'hot_deal' ? 'hot-deal' : 'limited'}">${String(plan.badge).toUpperCase() === 'HOT_DEAL' ? 'HOT DEAL' : 'LIMITED'}</span>`
            : '';
          return `
            <article class="plan-card" data-plan-index="${index}" tabindex="0" role="button" aria-label="Select ${escapeHtml(title)}">
              ${badge}
              <div class="pack-visual">
                <h3>${escapeHtml(title)}</h3>
                <span class="pack-duration">◷ ${escapeHtml(duration)}</span>
                <span class="pack-devices">▯ Up to ${devices} device${devices > 1 ? 's' : ''}</span>
              </div>
              <div class="plan-body">
                <div class="plan-description">${escapeHtml(plan.description || formatDataAllowance(plan))}</div>
                <div class="sub">${escapeHtml(formatDataAllowance(plan))}</div>
                ${rate ? `<div class="sub plan-speed">${escapeHtml(rate)}</div>` : ''}
                <div class="plan-footer">
                  <div class="plan-price">${escapeHtml(plan.currency || 'KES')} ${price}</div>
                  <span class="plan-btn">View package →</span>
                </div>
              </div>
            </article>
          `;
        }).join('');

        listEl.querySelectorAll('[data-plan-index]').forEach((card) => {
          const selectCard = () => openPurchaseSheet(plans[Number(card.dataset.planIndex)]);
          card.addEventListener('click', selectCard);
          card.addEventListener('keydown', (event) => {
            if (event.key === 'Enter' || event.key === ' ') {
              event.preventDefault();
              selectCard();
            }
          });
        });
        listEl.setAttribute('aria-busy', 'false');
      } catch (error) {
        if (error.code === 'REQUEST_ABORTED' || generation !== plansRequestGeneration) return;
        listEl.innerHTML = `<div class="error-box">Couldn't load packages right now. ${escapeHtml(error.message)}<button type="button" id="retry-plans">Try again</button></div>`;
        listEl.setAttribute('aria-busy', 'false');
        const retry = listEl.querySelector('#retry-plans');
        retry.addEventListener('click', async () => {
          if (plansRequest) return;
          retry.disabled = true;
          retry.textContent = 'Retrying…';
          listEl.setAttribute('aria-busy', 'true');
          try {
            await loadPlans();
          } finally {
            if (retry.isConnected) {
              retry.disabled = false;
              retry.textContent = 'Try again';
            }
          }
        });
      }
    }

    window.addEventListener('pagehide', () => {
      if (plansRequestController) plansRequestController.abort();
      plansRequestGeneration += 1;
      saveHotspotContext('');
    }, { once: true });

    function openPurchaseSheet(plan) {
      const overlay = document.createElement('div');
      overlay.className = 'sheet-overlay';
      overlay.dataset.purchaseKey = createPurchaseKey();
      const devices = Number(plan.max_devices || 1);
      const price = new Intl.NumberFormat('en-KE', { minimumFractionDigits: 0, maximumFractionDigits: 2 }).format(Number(plan.price || 0));
      overlay.innerHTML = `
        <div class="sheet" role="dialog" aria-modal="true" aria-labelledby="purchase-title">
          <div class="sheet-header">
            <h3 id="purchase-title">Complete payment</h3>
            <button class="sheet-close" type="button" aria-label="Close">×</button>
          </div>
          <div class="sheet-body">
            <div class="pay-plan-summary">
              <div class="pay-plan-copy">
                <strong>${escapeHtml(plan.name || plan.description || 'Internet bundle')}</strong>
                <span>${escapeHtml(fmtDuration(Number(plan.duration_hours || 1)))} · Up to ${devices} device${devices === 1 ? '' : 's'}</span>
                <small>${escapeHtml(formatDataAllowance(plan))}${formatSpeed(plan) ? ` · ${escapeHtml(formatSpeed(plan))}` : ''}</small>
              </div>
              <strong class="pay-plan-price">${escapeHtml(plan.currency || 'KES')} ${price}</strong>
            </div>
            <form id="buy-form">
              <label>Purchase for</label>
              <div class="device-choice-grid" role="group" aria-label="Choose a device">
                <button class="device-choice is-selected" type="button" data-device-type="this_device" aria-pressed="true"><span aria-hidden="true">📱</span><strong>This device</strong><i aria-hidden="true">✓</i></button>
                <button class="device-choice" type="button" data-device-type="tv" aria-pressed="false"><span aria-hidden="true">📺</span><strong>TV</strong><i aria-hidden="true">•</i></button>
                <button class="device-choice" type="button" data-device-type="other" aria-pressed="false"><span aria-hidden="true">💻</span><strong>Other device</strong><i aria-hidden="true">•</i></button>
              </div>
              <p class="hint" id="device-selection-help"></p>
              <div id="target-device-fields" hidden>
                <label for="target-device-mac">Target device MAC address</label>
                <input type="text" id="target-device-mac" inputmode="text" autocomplete="off" placeholder="AA:BB:CC:DD:EE:FF" maxlength="17" aria-describedby="target-device-help" />
                <label for="target-device-ip">Target device IP address <span>(optional)</span></label>
                <input type="text" id="target-device-ip" inputmode="decimal" autocomplete="off" placeholder="192.168.89.120" />
                <p class="hint" id="target-device-help">The target device must be connected to this WiFi. Find its MAC in the device network settings; the router verifies it before payment starts.</p>
              </div>
              <label for="phone-input">M-Pesa phone number</label>
              <input type="tel" id="phone-input" inputmode="tel" autocomplete="tel" placeholder="0791196121" required />
              <div class="hint">The M-Pesa prompt will be sent to this phone.</div>
              <div class="error-text" id="buy-error"></div>
              <button type="submit" class="btn btn-primary" id="buy-submit">Complete payment · ${escapeHtml(plan.currency || 'KES')} ${price}</button>
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
      const normalizeMac = (mac) => String(mac || '').replace(/-/g, ':').toUpperCase();
      const verifiedContextAvailable = Boolean(readHotspotContext());
      const verifiedMac = verifiedContextAvailable ? normalizeMac(CLIENT_MAC) : '';
      const targetFields = overlay.querySelector('#target-device-fields');
      const targetMacInput = overlay.querySelector('#target-device-mac');
      const targetIpInput = overlay.querySelector('#target-device-ip');
      const selectionHelp = overlay.querySelector('#device-selection-help');
      overlay.querySelectorAll('[data-device-type]').forEach((choice) => {
        choice.addEventListener('click', () => {
          selectedDevice = choice.dataset.deviceType;
          overlay.querySelectorAll('[data-device-type]').forEach((button) => {
            const active = button === choice;
            button.classList.toggle('is-selected', active);
            button.setAttribute('aria-pressed', String(active));
            button.querySelector('i').textContent = active ? '✓' : '•';
          });
          const isCurrentDevice = selectedDevice === 'this_device';
          targetFields.hidden = isCurrentDevice;
          targetMacInput.required = !isCurrentDevice;
          selectionHelp.textContent = isCurrentDevice
            ? ''
            : 'Enter the target device MAC. The router must verify it before payment.';
          if (!isCurrentDevice) targetMacInput.focus();
        });
      });
      overlay.querySelector('#buy-form').addEventListener('submit', async (event) => {
        event.preventDefault();
        const phoneInput = document.getElementById('phone-input');
        const errBox = document.getElementById('buy-error');
        const submitBtn = document.getElementById('buy-submit');
        errBox.style.display = 'none';

        if (!readHotspotContext() || !verifiedMac) {
          errBox.textContent = 'Checkout is unavailable for this Wi-Fi session. Reopen the Wi-Fi sign-in page and try again.';
          errBox.style.display = 'block';
          return;
        }

        if (!readHotspotContext()) {
          errBox.textContent = 'Secure router verification is required before payment. Reconnect to the WiFi sign-in page and retry device verification.';
          errBox.style.display = 'block';
          return;
        }

        const targetMac = selectedDevice === 'this_device' ? verifiedMac : normalizeMac(targetMacInput.value);
        const targetIp = selectedDevice === 'this_device' ? CLIENT_IP : targetIpInput.value.trim();
        if (!/^(?:[0-9A-F]{2}:){5}[0-9A-F]{2}$/.test(targetMac)) {
          errBox.textContent = selectedDevice === 'this_device'
            ? 'The verified WiFi device MAC is missing. Reopen the WiFi sign-in page and retry.'
            : 'Enter the target device MAC in a format such as AA:BB:CC:DD:EE:FF.';
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
          const res = await api('/api/v1/hotspot/purchase', {
            method: 'POST',
            body: {
              plan_id: plan._id,
              phone_number: phone,
              device_type: selectedDevice,
              device_mac: targetMac,
              idempotency_key: overlay.dataset.purchaseKey,
              ...(targetIp ? { ip_address: targetIp } : {})
            },
            headers: readHotspotContext() ? { 'X-Hotspot-Context': readHotspotContext() } : {},
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

    function showWaitingScreen(overlay, checkoutRequestId, contextRecoveryAttempt = 0) {
      if (!overlay?.isConnected) return;
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
          if (error.status === 409) {
            clearInterval(poll);
            // Refresh only when the server explicitly says this context is
            // absent or expired. A purchase/device binding conflict must not
            // be retried as though it were an expired session.
            const contextExpired = /context.{0,40}(missing|expired|required)/i.test(error.message || '');
            if (contextExpired && contextRecoveryAttempt === 0 && CAPTIVE_REDIRECT.ok) {
              saveHotspotContext('');
              const freshContext = await attestCurrentHotspotDevice();
              if (freshContext && overlay.isConnected) {
                showWaitingScreen(overlay, checkoutRequestId, 1);
                return;
              }
            }
            saveHotspotContext('');
            showReceiptRecoveryScreen(sheet, error.message);
            return;
          }
          if (attempts >= 30) {
            clearInterval(poll);
            showStillPendingScreen(sheet, checkoutRequestId, error.message);
          }
        } finally {
          polling = false;
        }
      }, 3000);
    }

    function showReceiptRecoveryScreen(sheet, reason = '') {
      if (!sheet?.isConnected) return;
      sheet.innerHTML = `
        <div class="status-screen">
          <div class="status-icon waiting">${Icons.clock}</div>
          <h3>Payment sent — finish connecting</h3>
          <p>We could not continue checking this purchase for the current WiFi session. Do not pay again. Use the receipt from your M-Pesa confirmation to verify the completed payment and connect.</p>
          ${reason ? `<p class="device-status">${escapeHtml(reason)}</p>` : ''}
          <button class="btn btn-primary" id="recover-with-receipt" type="button">Connect with M-Pesa receipt</button>
          <p class="device-status">The receipt is checked by the billing service; it does not start another payment.</p>
        </div>`;
      sheet.querySelector('#recover-with-receipt')?.addEventListener('click', openReceiptReconnect);
    }

    function showSuccessScreen(sheet, purchase) {
      const { accessToken, loginUsername, result } = purchase;
      const isCurrentDevice = !result.device_type || result.device_type === 'this_device';
      if (!isCurrentDevice) {
        sheet.innerHTML = `
          <div class="status-screen">
            <div class="status-icon success">${Icons.check}</div>
            <h3>Payment confirmed</h3>
            <p>${escapeHtml(result.package_name || 'Your internet package')} is ready for the selected device.</p>
            <div class="voucher-box" id="voucher-copy"><div class="code">${escapeHtml(accessToken)}</div><div class="tap">M-Pesa receipt · Tap to copy</div></div>
            <p>On the target device, connect to DEVZEN CREATIONS WiFi and enter this M-Pesa receipt on the sign-in page. The router will verify the device and connect it without another payment.</p>
            <p class="device-status">This purchase is bound to the target MAC you entered. Keep the receipt for reconnecting that device.</p>
          </div>`;
        sheet.querySelector('#voucher-copy').onclick = () => {
          navigator.clipboard?.writeText(accessToken);
          const tap = sheet.querySelector('.voucher-box .tap');
          if (tap) tap.textContent = 'Copied!';
        };
        return;
      }
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
          <p class="device-status">If automatic sign-in does not finish, tap “Connect now”. Do not pay again.</p>
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
        if (progress) progress.textContent = 'MikroTik is processing your login. The router will open your original destination after acceptance.';
      }, { once: true });
      if (loginForm && CAPTIVE_REDIRECT.ok) {
        window.setTimeout(() => loginForm.isConnected && loginForm.requestSubmit(), 700);
      } else {
        const progress = document.getElementById('router-login-progress');
        if (progress) progress.textContent = 'Payment is confirmed. Reopen this page from the WiFi sign-in screen to submit the router login.';
      }
    }

    function showStillPendingScreen(sheet, checkoutRequestId, detail = '') {
      sheet.innerHTML = `
        <div class="status-screen">
          <div class="status-icon waiting">${Icons.clock}</div>
          <h3>Payment confirmation is still pending</h3>
          <p>${escapeHtml(detail || 'Do not pay again. Safaricom may still be processing the payment callback.')}</p>
          <button class="btn btn-primary" id="continue-status-check">Continue checking</button>
          <button class="btn btn-ghost" id="close-pending">Close</button>
        </div>`;
      sheet.querySelector('#close-pending').onclick = () => document.querySelector('.sheet-overlay')?.remove();
      sheet.querySelector('#continue-status-check').onclick = () => showWaitingScreen(document.querySelector('.sheet-overlay'), checkoutRequestId);
    }

    function showPendingReviewScreen(sheet, detail) {
      sheet.innerHTML = `<div class="status-screen"><div class="status-icon waiting">${Icons.clock}</div><h3>Payment received</h3><p>${escapeHtml(detail)}</p><p>Contact ${escapeHtml(SUPPORT_PHONE)} with your M-Pesa message. Do not pay again.</p></div>`;
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
    document.getElementById('check-balance').addEventListener('click', openBalanceCheck);
    document.getElementById('connect-receipt').addEventListener('click', openReceiptReconnect);
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
