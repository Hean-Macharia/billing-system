Pages.login = function (root) {
  root.innerHTML = `
    <div style="min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px;background:linear-gradient(180deg,#991B1B,#DC2626 40%,#F7F8FA 40%);">
      <div style="width:100%;max-width:380px;">
        <div style="display:flex;align-items:center;gap:9px;margin-bottom:22px;justify-content:center;color:#fff;">
          <div style="width:34px;height:34px;border-radius:9px;background:linear-gradient(135deg,#EF4444,#991B1B);display:flex;align-items:center;justify-content:center;color:#FFFFFF;">${Icons.wifi}</div>
          <div style="font-weight:700;font-size:16px;">DEVZEN CREATIONS</div>
        </div>
        <div class="card" style="box-shadow:0 20px 40px -18px rgba(16,25,47,.35);">
          <h2 style="margin-bottom:4px;">Welcome back</h2>
          <p style="color:var(--muted);font-size:13px;margin:0 0 18px;">Sign in to view your account, pay your bill, and check your usage.</p>
          <form id="login-form">
            <div class="field-row">
              <label class="field-label">Email</label>
              <input type="email" name="email" required placeholder="you@example.com" autofocus/>
            </div>
            <div class="field-row">
              <label class="field-label">Password</label>
              <input type="password" name="password" required placeholder="••••••••"/>
            </div>
            <div id="login-error" style="display:none;background:#FCEAEC;color:#B4293A;font-size:12.5px;padding:9px 12px;border-radius:8px;margin-bottom:14px;"></div>
            <button class="btn btn-primary btn-block" type="submit" id="login-submit">Sign in</button>
          </form>
          <div class="divider"></div>
          <p style="text-align:center;font-size:13px;color:var(--muted);margin:0;">
            First time here? <a href="#/register" style="color:#B91C1C;font-weight:700;">Activate your account</a>
          </p>
          <details style="margin-top:14px;font-size:12px;color:var(--muted);">
            <summary style="cursor:pointer;">Backend connection</summary>
            <div style="margin-top:8px;">
              <input type="text" id="api-base-input" value="${Api.getBaseUrl()}" placeholder="http://localhost:8000"/>
              <button class="btn btn-ghost btn-sm" type="button" id="api-test" style="margin-top:8px;">Test backend connection</button>
              <div id="api-test-result" class="field-hint" role="status" aria-live="polite" style="margin-top:6px;"></div>
            </div>
          </details>
        </div>
      </div>
    </div>`;

  root.querySelector('#api-base-input').addEventListener('change', e => {
    try { Api.setBaseUrl(e.target.value.trim()); e.target.value = Api.getBaseUrl(); toast('API address saved', 'success'); }
    catch (err) { toast(err.message, 'error'); }
  });
  root.querySelector('#api-test').onclick = async (event) => {
    const button = event.currentTarget;
    const result = root.querySelector('#api-test-result');
    try {
      Api.setBaseUrl(root.querySelector('#api-base-input').value.trim());
      button.disabled = true;
      result.textContent = 'Checking backend…';
      await Api.testConnection();
      result.textContent = 'Backend is ready.';
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
    btn.disabled = true; btn.innerHTML = '<span class="spinner light"></span> Signing in…';
    try {
      const res = await Api.post('/api/v1/auth/login', { email, password });
      Api.setTokens(res.data.tokens || res.data);
      const me = await Api.get('/api/v1/portal/me');
      Api.setProfile(me.data);
      Router.go('#/dashboard'); Router.render();
    } catch (err) {
      Api.clearTokens();
      errBox.textContent = err.message || 'Invalid email or password';
      errBox.style.display = 'block';
    } finally { btn.disabled = false; btn.textContent = 'Sign in'; }
  });
};

Pages.register = function (root) {
  root.innerHTML = `
    <div style="min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px;background:linear-gradient(180deg,#10192F,#16213A 40%,#F6F8FC 40%);">
      <div style="width:100%;max-width:400px;">
        <div style="display:flex;align-items:center;gap:9px;margin-bottom:22px;justify-content:center;color:#fff;">
          <div style="width:34px;height:34px;border-radius:9px;background:linear-gradient(135deg,#EF4444,#991B1B);display:flex;align-items:center;justify-content:center;color:#FFFFFF;">${Icons.wifi}</div>
          <div style="font-weight:700;font-size:16px;">DEVZEN CREATIONS</div>
        </div>
        <div class="card" style="box-shadow:0 20px 40px -18px rgba(16,25,47,.35);">
          <h2 style="margin-bottom:4px;">Activate your account</h2>
          <p style="color:var(--muted);font-size:13px;margin:0 0 18px;">
            Self-service activation is temporarily paused while secure account verification is being set up.
            Please contact support to get portal access.
          </p>
          <div class="divider"></div>
          <p style="text-align:center;font-size:13px;color:var(--muted);margin:0;">
            Already have portal access? <a href="#/login" style="color:#B91C1C;font-weight:700;">Sign in</a>
          </p>
        </div>
      </div>
    </div>`;
};
