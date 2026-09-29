/*
  Router + app shell
  -------------------
  Hash-based routing (no build step, works from a plain file:// or any
  static server). Renders the sidebar/topbar once, then swaps only the
  <main class="page"> content per route.
*/

const NAV = [
  { group: 'Overview', items: [
    { path: '#/dashboard', label: 'Dashboard', icon: 'dashboard', perm: null },
  ]},
  { group: 'Customers & Billing', items: [
    { path: '#/customers', label: 'Customers', icon: 'customers', perm: 'customers.read' },
    { path: '#/packages', label: 'Packages', icon: 'package', perm: 'services.read' },
    { path: '#/services', label: 'Services', icon: 'service', perm: 'services.read' },
    { path: '#/subscriptions', label: 'Subscriptions', icon: 'subscriptions', perm: 'subscriptions.read' },
    { path: '#/billing', label: 'Billing', icon: 'billing', perm: 'billing.read' },
    { path: '#/payments', label: 'Payments', icon: 'payments', perm: 'payments.read' },
    { path: '#/vouchers', label: 'Vouchers', icon: 'vouchers', perm: 'vouchers.read' },
  ]},
  { group: 'Network', items: [
    { path: '#/sites', label: 'Sites', icon: 'sites', perm: 'routers.read' },
    { path: '#/routers', label: 'Routers', icon: 'routers', perm: 'routers.read' },
    { path: '#/sessions', label: 'Sessions', icon: 'sessions', perm: 'radius.read' },
  ]},
  { group: 'Insight', items: [
    { path: '#/reports', label: 'Reports', icon: 'reports', perm: 'reports.read' },
  ]},
];

const Router = (() => {
  const routes = {};
  function register(path, renderFn) { routes[path] = renderFn; }

  function currentPath() {
    return location.hash || '#/dashboard';
  }

  function go(path) { location.hash = path; }

  function hasPerm(perm) {
    if (!perm) return true;
    const user = Api.getCurrentUser();
    if (!user) return false;
    if (user.role === 'super_admin' || user.role === 'admin') return true;
    return (user.permissions || []).includes(perm);
  }

  function buildSidebar(activePath) {
    const user = Api.getCurrentUser();
    const initials = (user?.full_name || user?.email || '?').split(' ').map(s => s[0]).slice(0, 2).join('').toUpperCase();
    const groupsHtml = NAV.map(g => {
      const items = g.items.filter(i => hasPerm(i.perm));
      if (!items.length) return '';
      const itemsHtml = items.map(i => `
        <a class="nav-item ${activePath.startsWith(i.path) ? 'active' : ''}" href="${i.path}">
          ${Icons[i.icon] || ''}<span>${i.label}</span>
        </a>`).join('');
      return `<div class="nav-group"><div class="nav-group-label">${g.group}</div>${itemsHtml}</div>`;
    }).join('');

    return `
      <aside class="sidebar" id="sidebar">
        <div class="sidebar-brand">
          <div class="mark">${Icons.wifi}</div>
          <div>
            <div class="name">Nyaururu Net</div>
            <div class="sub">Ops Console</div>
          </div>
        </div>
        <nav class="nav-scroll">${groupsHtml}</nav>
        <div class="sidebar-foot">
          <div class="avatar">${initials}</div>
          <div class="who">
            <div class="name">${escapeHtml(user?.full_name || user?.email || 'User')}</div>
            <div class="role">${escapeHtml((user?.role || '').replace(/_/g, ' '))}</div>
          </div>
          <button class="icon-btn" id="logout-btn" title="Sign out">${Icons.logout}</button>
        </div>
      </aside>`;
  }

  function ensureShell() {
    let shell = document.getElementById('app-shell');
    if (shell) return shell;
    document.getElementById('app-root').innerHTML = `
      <div class="app-shell" id="app-shell">
        <div id="sidebar-slot"></div>
        <div class="main-col">
          <header class="topbar">
            <div>
              <div class="crumb" id="crumb"></div>
              <h1 id="page-title">—</h1>
            </div>
            <div class="topbar-right">
              <button class="icon-btn" id="menu-toggle" style="display:none;">${Icons.menu}</button>
            </div>
          </header>
          <main class="page"><div class="page-inner" id="page-content"></div></main>
        </div>
      </div>`;
    return document.getElementById('app-shell');
  }

  async function render() {
    // Close any open drawer/modal before switching routes — they're appended
    // to document.body, not #page-content, so re-rendering the page content
    // alone would otherwise leave them stuck on top of the new page,
    // permanently blocking clicks (this is exactly what happens if a user
    // opens a form and then clicks a sidebar link, or navigates back).
    document.querySelectorAll('.overlay, .modal-center').forEach(n => n.remove());

    const path = currentPath();
    const base = '#/' + path.replace('#/', '').split('/')[0];

    if (base === '#/login' || !Api.isAuthed()) {
      document.getElementById('app-root').innerHTML = '';
      Pages.login(document.getElementById('app-root'));
      return;
    }

    ensureShell();
    document.getElementById('sidebar-slot').innerHTML = buildSidebar(base);
    document.getElementById('logout-btn').onclick = () => {
      Api.clearTokens();
      go('#/login');
    };
    document.getElementById('menu-toggle').onclick = () => {
      document.getElementById('sidebar')?.classList.toggle('open');
    };

    const matchedNav = NAV.flatMap(g => g.items).find(i => base.startsWith(i.path));
    document.getElementById('page-title').textContent = matchedNav?.label || 'Not found';
    document.getElementById('crumb').textContent = matchedNav ? (NAV.find(g => g.items.includes(matchedNav))?.group || '') : '';

    const target = document.getElementById('page-content');
    target.innerHTML = '<div class="center-loading"><div class="spinner dark"></div></div>';

    const renderFn = routes[base];
    if (!renderFn) {
      target.innerHTML = `<div class="table-empty"><div class="big">Page not found</div></div>`;
      return;
    }
    try {
      await renderFn(target, path);
    } catch (err) {
      console.error(err);
      target.innerHTML = `<div class="table-empty"><div class="big">Couldn't load this page</div><div>${escapeHtml(err.message || '')}</div></div>`;
    }
  }

  window.addEventListener('hashchange', render);

  return { register, go, render, hasPerm };
})();
