const TABS = [
  { path: '#/dashboard', label: 'Home', icon: 'home' },
  { path: '#/subscription', label: 'Plan', icon: 'subscription' },
  { path: '#/billing', label: 'Invoices', icon: 'billing' },
  { path: '#/payments', label: 'Payments', icon: 'payments' },
  { path: '#/usage', label: 'Usage', icon: 'usage' },
  { path: '#/support', label: 'Support', icon: 'support' },
];

const Router = (() => {
  const routes = {};
  function register(path, fn) { routes[path] = fn; }
  function currentPath() { return location.hash || '#/dashboard'; }
  function go(path) { location.hash = path; }

  function buildShell(activeBase) {
    const profile = Api.getProfile();
    const tabsHtml = TABS.map(t => `<a class="${activeBase === t.path ? 'active' : ''}" href="${t.path}">${Icons[t.icon]}<span>${t.label}</span></a>`).join('');
    return `
      <header class="topbar">
        <div class="brand"><div class="mark">${Icons.wifi}</div>DEVZEN CREATIONS</div>
        <div class="topbar-right">
          <span class="topbar-name">${escapeHtml(profile?.full_name || '')}</span>
          <button class="icon-btn" id="portal-logout" style="background:rgba(255,255,255,.1);color:#fff;" title="Sign out">${Icons.logout}</button>
        </div>
      </header>
      <nav class="tabbar">${tabsHtml}</nav>
      <main class="shell-body" id="page-content"></main>`;
  }

  async function render() {
    document.querySelectorAll('.sheet-overlay').forEach(n => n.remove());
    const path = currentPath();
    const base = '#/' + path.replace('#/', '').split('/')[0];

    if (base === '#/login' || base === '#/register' || !Api.isAuthed()) {
      document.getElementById('app-root').innerHTML = '';
      if (base === '#/register') Pages.register(document.getElementById('app-root'));
      else Pages.login(document.getElementById('app-root'));
      return;
    }

    const root = document.getElementById('app-root');
    root.innerHTML = buildShell(base);
    document.getElementById('portal-logout').onclick = () => { Api.clearTokens(); go('#/login'); };

    const target = document.getElementById('page-content');
    target.innerHTML = '<div class="center-loading"><div class="spinner"></div></div>';
    const fn = routes[base];
    if (!fn) { target.innerHTML = `<div class="empty-state">Page not found</div>`; return; }
    try { await fn(target, path); }
    catch (err) {
      console.error(err);
      target.innerHTML = `<div class="card"><div class="empty-state"><div class="big">Couldn't load this page</div><div>${escapeHtml(err.message || '')}</div></div></div>`;
    }
  }

  window.addEventListener('hashchange', render);
  return { register, go, render };
})();
