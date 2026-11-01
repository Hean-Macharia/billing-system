Pages.login = function (root) {
  root.innerHTML = `
    <div class="auth-layout" style="min-height:100vh;display:grid;grid-template-columns:minmax(0,1fr) minmax(360px,480px);background:#fff;">
      <section class="auth-story" style="display:flex;flex-direction:column;justify-content:space-between;padding:clamp(28px,6vw,76px);background:linear-gradient(145deg,#991B1B,#DC2626 62%,#F87171);color:#fff;">
        <div style="display:flex;align-items:center;gap:10px;font-weight:800;letter-spacing:.02em;"><span style="width:40px;height:40px;display:grid;place-items:center;border-radius:12px;background:rgba(255,255,255,.16);">${Icons.wifi}</span>DEVZEN CREATIONS</div>
        <div style="max-width:560px;"><div style="font-size:clamp(34px,5vw,62px);font-weight:800;line-height:1.04;letter-spacing:-.045em;">Keep your network moving.</div><p style="max-width:440px;color:#FEE2E2;font-size:16px;margin-top:18px;">A clear view of customers, billing, payments and router health, all in one place.</p></div>
        <div style="font-size:12px;color:#FECACA;">Secure operations console</div>
      </section>
      <section style="display:flex;align-items:center;justify-content:center;padding:28px;background:#fff;">
      <div style="width:100%;max-width:380px;">
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:28px;">
          <div class="mark" style="width:38px;height:38px;border-radius:10px;background:linear-gradient(135deg,#EF4444,#991B1B);display:flex;align-items:center;justify-content:center;color:#FFFFFF;">${Icons.wifi}</div>
          <div>
            <div style="font-weight:700;font-size:16px;color:#172033;">DEVZEN CREATIONS</div>
            <div style="font-size:12px;color:#6B7280;">Operations console</div>
          </div>
        </div>
        <div style="background:#fff;border:1px solid #E5E7EB;border-radius:16px;padding:26px 24px;box-shadow:0 18px 46px -28px rgba(31,41,55,.32);">
          <h2 style="color:#172033;font-size:22px;margin-bottom:4px;">Welcome back</h2>
          <p style="color:#6B7280;font-size:13px;margin:0 0 20px;">Sign in with your staff account to manage your service.</p>
          <form id="login-form">
            <div class="field-row">
              <label class="field-label">Email</label>
              <input type="email" name="email" required placeholder="admin@yourdomain.com" autofocus/>
            </div>
            <div class="field-row">
              <label class="field-label">Password</label>
              <input type="password" name="password" required placeholder="••••••••"/>
            </div>
            <div id="login-error" style="display:none;background:#FEF2F2;color:#B91C1C;font-size:12.5px;padding:9px 12px;border-radius:8px;margin-bottom:14px;"></div>
            <button class="btn btn-signal" type="submit" style="width:100%;justify-content:center;padding:10px;" id="login-submit">Sign in</button>
          </form>
          <div class="divider"></div>
          <details style="color:#6B7280;font-size:12px;">
            <summary style="cursor:pointer;">Backend connection</summary>
            <div style="margin-top:10px;">
              <label class="field-label">API base URL</label>
              <input type="text" id="api-base-input" value="${Api.getBaseUrl()}" placeholder="http://localhost:8000"/>
              <div class="field-hint">Where your FastAPI backend is running. Saved locally in this browser.</div>
              <button class="btn btn-ghost btn-sm" type="button" id="api-test" style="margin-top:10px;">Test backend connection</button>
              <div id="api-test-result" class="field-hint" role="status" aria-live="polite" style="margin-top:8px;"></div>
            </div>
          </details>
        </div>
      </div></section>
    </div>`;

  root.querySelector('#api-base-input').addEventListener('change', (e) => {
    try {
      Api.setBaseUrl(e.target.value.trim());
      e.target.value = Api.getBaseUrl();
      toast('API address saved', 'success');
    } catch (err) { toast(err.message, 'error'); }
  });
  root.querySelector('#api-test').onclick = async (event) => {
    const button = event.currentTarget;
    const result = root.querySelector('#api-test-result');
    try {
      Api.setBaseUrl(root.querySelector('#api-base-input').value.trim());
      button.disabled = true;
      result.textContent = 'Checking backend…';
      const health = await Api.testConnection();
      result.textContent = `Backend ready${health?.data?.app_name ? ` · ${health.data.app_name}` : ''}`;
      result.style.color = '#15803D';
    } catch (err) {
      result.textContent = err.message || 'Backend connection failed';
      result.style.color = '#B91C1C';
    } finally { button.disabled = false; }
  };

  root.querySelector('#login-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = root.querySelector('#login-submit');
    const errBox = root.querySelector('#login-error');
    errBox.style.display = 'none';
    const { email, password } = formToObject(e.target);
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Signing in…';
    try {
      const res = await Api.post('/api/v1/auth/login', { email, password });
      Api.setTokens(res.data.tokens || res.data);
      const me = await Api.get('/api/v1/auth/me');
      if (me.data.role === 'customer') {
        Api.clearTokens();
        throw new Error('Customer accounts should sign in through the customer portal.');
      }
      Api.setCurrentUser(me.data);
      toast(`Welcome back, ${me.data.full_name || me.data.email}`, 'success');
      Router.go('#/dashboard');
      Router.render();
    } catch (err) {
      Api.clearTokens();
      errBox.textContent = err.message || 'Invalid email or password';
      errBox.style.display = 'block';
    } finally {
      btn.disabled = false;
      btn.textContent = 'Sign in';
    }
  });
};
