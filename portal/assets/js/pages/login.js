Pages.login = function (root) {
  root.innerHTML = `
    <div style="min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px;background:linear-gradient(180deg,#10192F,#16213A 40%,#F6F8FC 40%);">
      <div style="width:100%;max-width:380px;">
        <div style="display:flex;align-items:center;gap:9px;margin-bottom:22px;justify-content:center;color:#fff;">
          <div style="width:34px;height:34px;border-radius:9px;background:linear-gradient(135deg,#2DD4BF,#1a8f82);display:flex;align-items:center;justify-content:center;color:#063B36;">${Icons.wifi}</div>
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
            First time here? <a href="#/register" style="color:#0E8578;font-weight:700;">Activate your account</a>
          </p>
          <details style="margin-top:14px;font-size:12px;color:var(--muted);">
            <summary style="cursor:pointer;">Backend connection</summary>
            <div style="margin-top:8px;">
              <input type="text" id="api-base-input" value="${Api.getBaseUrl()}" placeholder="http://localhost:8000"/>
            </div>
          </details>
        </div>
      </div>
    </div>`;

  root.querySelector('#api-base-input').addEventListener('change', e => { Api.setBaseUrl(e.target.value.trim()); toast('Saved', 'success'); });

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
          <div style="width:34px;height:34px;border-radius:9px;background:linear-gradient(135deg,#2DD4BF,#1a8f82);display:flex;align-items:center;justify-content:center;color:#063B36;">${Icons.wifi}</div>
          <div style="font-weight:700;font-size:16px;">DEVZEN CREATIONS</div>
        </div>
        <div class="card" style="box-shadow:0 20px 40px -18px rgba(16,25,47,.35);">
          <h2 style="margin-bottom:4px;">Activate your account</h2>
          <p style="color:var(--muted);font-size:13px;margin:0 0 18px;">Use the customer code and phone number your installer gave you.</p>
          <form id="reg-form">
            <div class="field-row">
              <label class="field-label">Customer code</label>
              <input type="text" name="customer_code" required placeholder="CUST-0001"/>
            </div>
            <div class="field-row">
              <label class="field-label">Phone number on file</label>
              <input type="text" name="phone" required placeholder="254712345678"/>
            </div>
            <div class="field-row">
              <label class="field-label">Email address</label>
              <input type="email" name="email" required placeholder="you@example.com"/>
              <div class="field-hint">This becomes your login.</div>
            </div>
            <div class="field-row">
              <label class="field-label">Create a password</label>
              <input type="password" name="password" required minlength="8" placeholder="At least 8 characters"/>
            </div>
            <div id="reg-error" style="display:none;background:#FCEAEC;color:#B4293A;font-size:12.5px;padding:9px 12px;border-radius:8px;margin-bottom:14px;"></div>
            <button class="btn btn-primary btn-block" type="submit" id="reg-submit">Activate account</button>
          </form>
          <div class="divider"></div>
          <p style="text-align:center;font-size:13px;color:var(--muted);margin:0;">
            Already activated? <a href="#/login" style="color:#0E8578;font-weight:700;">Sign in</a>
          </p>
        </div>
      </div>
    </div>`;

  root.querySelector('#reg-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = root.querySelector('#reg-submit');
    const errBox = root.querySelector('#reg-error');
    errBox.style.display = 'none';
    const raw = formToObject(e.target);
    btn.disabled = true; btn.innerHTML = '<span class="spinner light"></span> Activating…';
    try {
      const res = await Api.post('/api/v1/portal/auth/register', raw);
      Api.setTokens(res.data.tokens);
      Api.setProfile(res.data.user);
      toast('Account activated — welcome!', 'success');
      Router.go('#/dashboard'); Router.render();
    } catch (err) {
      errBox.textContent = err.message || 'Could not activate your account';
      errBox.style.display = 'block';
    } finally { btn.disabled = false; btn.textContent = 'Activate account'; }
  });
};
