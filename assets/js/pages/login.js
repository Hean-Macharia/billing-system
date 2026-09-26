Pages.login = function (root) {
  root.innerHTML = `
    <div style="min-height:100vh;display:flex;align-items:center;justify-content:center;background:radial-gradient(circle at 20% 20%, #1B2A4A, #10192F 60%);padding:20px;">
      <div style="width:100%;max-width:380px;">
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:28px;justify-content:center;">
          <div class="mark" style="width:38px;height:38px;border-radius:10px;background:linear-gradient(135deg,#2DD4BF,#1a8f82);display:flex;align-items:center;justify-content:center;color:#063B36;">${Icons.wifi}</div>
          <div>
            <div style="font-weight:700;font-size:16px;color:#E8ECF7;">Nyaururu Net</div>
            <div style="font-size:12px;color:#93A2C4;">Ops Console</div>
          </div>
        </div>
        <div style="background:#1B2A4A;border:1px solid #2A3C63;border-radius:14px;padding:26px 24px;">
          <h2 style="color:#E8ECF7;font-size:18px;margin-bottom:4px;">Sign in</h2>
          <p style="color:#93A2C4;font-size:12.5px;margin:0 0 20px;">Use your admin, billing, network or support account.</p>
          <form id="login-form">
            <div class="field-row">
              <label class="field-label" style="color:#C6D0E8;">Email</label>
              <input type="email" name="email" required placeholder="you@nyaururunet.co.ke" autofocus/>
            </div>
            <div class="field-row">
              <label class="field-label" style="color:#C6D0E8;">Password</label>
              <input type="password" name="password" required placeholder="••••••••"/>
            </div>
            <div id="login-error" style="display:none;background:#4A1015;color:#FCA5AC;font-size:12.5px;padding:9px 12px;border-radius:8px;margin-bottom:14px;"></div>
            <button class="btn btn-signal" type="submit" style="width:100%;justify-content:center;padding:10px;" id="login-submit">Sign in</button>
          </form>
          <div class="divider" style="background:#2A3C63;"></div>
          <details style="color:#93A2C4;font-size:12px;">
            <summary style="cursor:pointer;">Backend connection</summary>
            <div style="margin-top:10px;">
              <label class="field-label" style="color:#C6D0E8;">API base URL</label>
              <input type="text" id="api-base-input" value="${Api.getBaseUrl()}" placeholder="http://localhost:8000"/>
              <div class="field-hint" style="color:#7284AC;">Where your FastAPI backend is running. Saved locally in this browser.</div>
            </div>
          </details>
        </div>
      </div>
    </div>`;

  root.querySelector('#api-base-input').addEventListener('change', (e) => {
    Api.setBaseUrl(e.target.value.trim());
    toast('API base URL saved', 'success');
  });

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
      Api.setCurrentUser(me.data);
      toast(`Welcome back, ${me.data.full_name || me.data.email}`, 'success');
      Router.go('#/dashboard');
      Router.render();
    } catch (err) {
      errBox.textContent = err.message || 'Invalid email or password';
      errBox.style.display = 'block';
    } finally {
      btn.disabled = false;
      btn.textContent = 'Sign in';
    }
  });
};
