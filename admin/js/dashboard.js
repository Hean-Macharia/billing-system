import { API } from './api.config.js';
import { api } from './api.js';
import { mountShell } from './app-shell.js';
import { currency, esc, formatDate, statusBadge, empty } from './ui.js';
import { countUp } from './animations.js';

await mountShell('dashboard');
const root = document.querySelector('#main-content');
root.innerHTML = `
  <section class="page-head">
    <div><h2>Powering connections.</h2><p>Your network and billing performance at a glance.</p></div>
    <div class="page-actions">
      <a class="btn" href="./customers.html">＋ Add customer</a>
      <a class="btn" href="./payments.html">↗ Record payment</a>
      <a class="btn" href="./vouchers.html">◈ Create voucher</a>
      <a class="btn btn-primary" href="./invoices.html">＋ Create invoice</a>
    </div>
  </section>
  <section id="stats" class="stat-grid" aria-label="Business summary">
    ${Array.from({ length: 4 }, () => '<div class="card stat"><div class="skeleton" style="width:50%"></div><div class="skeleton" style="width:70%;height:28px;margin-top:15px"></div></div>').join('')}
  </section>
  <section class="content-grid">
    <article class="panel"><header class="panel-head"><div><h3>Revenue snapshot</h3><span class="muted-small">Completed payments, up to 100 latest records</span></div><span class="badge active">KES</span></header><div class="panel-body"><canvas id="revenue-chart" height="125" aria-label="Revenue by month"></canvas></div></article>
    <article class="panel"><header class="panel-head"><h3>Network health</h3><a class="muted-small" href="./network.html">Manage routers →</a></header><div class="panel-body" id="router-summary"><div class="skeleton"></div></div></article>
  </section>
  <section class="content-grid" style="margin-top:18px">
    <article class="panel"><header class="panel-head"><h3>Expiring within 7 days</h3><a class="muted-small" href="./sessions.html">View live sessions →</a></header><div class="panel-body" id="expiring-list"><div class="skeleton"></div></div></article>
    <article class="panel"><header class="panel-head"><h3>Recent payments</h3><a class="muted-small" href="./payments.html">All payments →</a></header><div class="panel-body" id="recent-payments"><div class="skeleton"></div></div></article>
  </section>`;

const settled = await Promise.allSettled([
  api.get(API.dashboard),
  api.get(API.payments, { page: 1, limit: 100 }),
  api.get(API.routers, { page: 1, limit: 20 }),
  api.get(API.subscriptions, { page: 1, limit: 100 }),
]);
const [summaryResult, paymentsResult, routersResult, subscriptionsResult] = settled;
const summary = summaryResult.status === 'fulfilled' ? api.data(summaryResult.value) : null;
const payments = paymentsResult.status === 'fulfilled' ? api.rows(paymentsResult.value) : [];
const routers = routersResult.status === 'fulfilled' ? api.rows(routersResult.value) : [];
const subscriptions = subscriptionsResult.status === 'fulfilled' ? api.rows(subscriptionsResult.value) : [];

const stats = [
  ['Active subscribers', summary?.customers?.active, 'Customer accounts currently active', '♙', false],
  ['Active subscriptions', summary?.subscriptions_active, 'Service connections in billing', '⌁', false],
  ['Revenue this month', summary?.revenue?.this_month_kes, 'Completed payments recorded', '↗', true],
  ['Overdue invoices', summary?.invoices?.overdue, `${summary?.invoices?.unpaid ?? '—'} unpaid invoices`, '▤', false],
];
document.querySelector('#stats').innerHTML = stats.map(([label, value, note, icon, money]) => `
  <article class="card stat"><span class="stat-icon">${icon}</span><div class="stat-label">${label}</div>
    <div class="kpi-value" data-value="${Number(value) || 0}" data-money="${money}">${money ? currency(value || 0) : Number(value || 0).toLocaleString()}</div>
    <div class="stat-meta">${esc(note)}</div></article>`).join('');
document.querySelectorAll('.kpi-value').forEach(el => {
  const n = Number(el.dataset.value);
  countUp(el, n);
  if (el.dataset.money === 'true') setTimeout(() => { el.textContent = currency(n); }, 700);
});
if (!summary) document.querySelector('#stats').insertAdjacentHTML('beforeend', `<div class="notice" style="grid-column:1/-1">Summary metrics are unavailable: ${esc(summaryResult.reason?.message || 'permission denied')}</div>`);

document.querySelector('#router-summary').innerHTML = routers.length ? `<div class="mini-list">${routers.map(router => `
  <div class="mini-row"><div style="display:flex;align-items:center;gap:10px"><span class="avatar">⌁</span><span><strong>${esc(router.name || 'Router')}</strong><br><small class="muted-small">${esc(router.ip_address || router.location || 'No address')}</small></span></div>${statusBadge(router.status || 'unknown')}</div>`).join('')}</div>` : empty(routersResult.status === 'rejected' ? 'Router status is unavailable' : 'No routers registered', '⌁');

const now = Date.now();
const expiring = subscriptions.filter(s => s.end_date && new Date(s.end_date).getTime() >= now && new Date(s.end_date).getTime() <= now + 7 * 86400000);
document.querySelector('#expiring-list').innerHTML = expiring.length ? `<div class="mini-list">${expiring.map(s => {
  const days = Math.max(0, Math.ceil((new Date(s.end_date).getTime() - now) / 86400000));
  return `<div class="mini-row"><span><strong>${esc(s.customer_name || s.customer_code || 'Subscriber')}</strong><br><small class="muted-small">${esc(s.plan_name || 'Plan')} · ends ${formatDate(s.end_date)}</small></span><span class="badge warning">${days} day${days === 1 ? '' : 's'}</span></div>`;
}).join('')}</div>` : empty(subscriptionsResult.status === 'rejected' ? 'Subscription dates are unavailable' : 'No subscriptions ending this week', '◷');
if (subscriptionsResult.status === 'fulfilled' && expiring.length) {
  document.querySelector('#expiring-list').insertAdjacentHTML('beforeend', '<p class="muted-small" style="margin:12px 0 0">Reminder sending is not exposed by the current backend.</p>');
}

const recent = payments.slice(0, 5);
document.querySelector('#recent-payments').innerHTML = recent.length ? `<div class="mini-list">${recent.map(p => `
  <div class="mini-row"><span><strong>${esc(p.customer_name || p.customer_code || 'Customer')}</strong><br><small class="muted-small">${esc(p.payment_method || 'Payment')} · ${formatDate(p.payment_date || p.created_at)}</small></span><span style="text-align:right"><strong>${currency(p.amount_kes)}</strong><br>${statusBadge(p.status)}</span></div>`).join('')}</div>` : empty(paymentsResult.status === 'rejected' ? 'Payments are unavailable' : 'No payments recorded', '↗');

if (window.Chart) {
  const recentMonths = Array.from({ length: 12 }, (_, i) => {
    const d = new Date(); d.setDate(1); d.setMonth(d.getMonth() - 11 + i); return d;
  });
  const completed = payments.filter(p => p.status === 'completed');
  const totals = recentMonths.map(month => completed.filter(p => {
    const date = new Date(p.payment_date || p.created_at);
    return date.getMonth() === month.getMonth() && date.getFullYear() === month.getFullYear();
  }).reduce((sum, p) => sum + Number(p.amount_kes || 0), 0));
  new Chart(document.querySelector('#revenue-chart'), {
    type: 'line',
    data: { labels: recentMonths.map(d => d.toLocaleString('en', { month: 'short' })), datasets: [{ data: totals, borderColor: '#E11D2E', backgroundColor: 'rgba(225,29,46,.12)', fill: true, tension: .38, pointRadius: 3 }] },
    options: { responsive: true, plugins: { legend: { display: false }, tooltip: { callbacks: { label: ctx => currency(ctx.raw) } } }, scales: { y: { beginAtZero: true, grid: { color: 'rgba(148,163,184,.12)' }, ticks: { callback: v => currency(v) } }, x: { grid: { display: false } } }, animation: { duration: 800, easing: 'easeOutQuart' } },
  });
}
