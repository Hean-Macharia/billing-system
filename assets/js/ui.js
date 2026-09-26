/*
  UI toolkit
  ----------
  Small, dependency-free builders reused by every page so the app has
  one table style, one drawer style, one status vocabulary — not a
  bespoke widget per module.
*/

// Declared once, here, because every page/*.js file is a classic
// (non-module) <script> tag sharing one global scope. A top-level
// `const Pages = ...` repeated in a second script tag throws
// "Identifier 'Pages' has already been declared" and takes the whole
// app down — so every page file below just does `Pages.xxx = ...`
// against this single global object instead of redeclaring it.
window.Pages = window.Pages || {};

const Icons = {
  dashboard: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/></svg>',
  customers: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c0-3.6 2.9-6.5 6.5-6.5s6.5 2.9 6.5 6.5"/><circle cx="17.5" cy="8.5" r="2.5"/><path d="M15.5 13.2c2.9.4 5 2.9 5 6.3"/></svg>',
  package: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 8l-9-5-9 5 9 5 9-5z"/><path d="M3 8v8l9 5 9-5V8"/><path d="M12 13v8"/></svg>',
  service: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 17l6-6-4-4 6-6"/><path d="M13 21l7-7-3-3"/><path d="M14 8l2 2"/></svg>',
  subscriptions: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18"/><path d="M8 14h4"/></svg>',
  billing: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 2h9l5 5v13a2 2 0 01-2 2H6a2 2 0 01-2-2V4a2 2 0 012-2z"/><path d="M14 2v5h5"/><path d="M8 13h8M8 17h5"/></svg>',
  payments: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="6" width="20" height="13" rx="2"/><path d="M2 10h20"/><path d="M6 15h4"/></svg>',
  vouchers: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 8a2 2 0 012-2h14a2 2 0 012 2v2a2 2 0 000 4v2a2 2 0 01-2 2H5a2 2 0 01-2-2v-2a2 2 0 000-4V8z"/><path d="M10 6v12" stroke-dasharray="2 2"/></svg>',
  sites: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s7-6.3 7-12a7 7 0 10-14 0c0 5.7 7 12 7 12z"/><circle cx="12" cy="10" r="2.5"/></svg>',
  routers: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="15" width="18" height="6" rx="1.5"/><circle cx="8" cy="18" r=".8" fill="currentColor"/><circle cx="12" cy="18" r=".8" fill="currentColor"/><path d="M7 15V9a5 5 0 0110 0v6"/></svg>',
  sessions: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>',
  reports: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 20V10M12 20V4M20 20v-7"/></svg>',
  plus: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M12 5v14M5 12h14"/></svg>',
  search: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></svg>',
  close: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg>',
  logout: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4"/><path d="M16 17l5-5-5-5"/><path d="M21 12H9"/></svg>',
  edit: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 013 3L7 19l-4 1 1-4z"/></svg>',
  trash: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18"/><path d="M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2"/><path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6"/></svg>',
  more: '<svg viewBox="0 0 24 24" fill="currentColor"><circle cx="5" cy="12" r="1.8"/><circle cx="12" cy="12" r="1.8"/><circle cx="19" cy="12" r="1.8"/></svg>',
  download: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3v13"/><path d="M7 11l5 5 5-5"/><path d="M4 20h16"/></svg>',
  print: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 9V3h12v6"/><rect x="4" y="9" width="16" height="8" rx="1.5"/><path d="M6 17v4h12v-4"/></svg>',
  bolt: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M13 2L3 14h7l-1 8 10-12h-7z"/></svg>',
  check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4"><path d="M20 6L9 17l-5-5"/></svg>',
  ban: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="M5.5 5.5l13 13"/></svg>',
  refresh: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 11-3-6.7"/><path d="M21 3v6h-6"/></svg>',
  copy: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15V5a2 2 0 012-2h10"/></svg>',
  menu: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 7h16M4 12h16M4 17h16"/></svg>',
  wifi: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M2 8.5a17 17 0 0120 0"/><path d="M5.5 12.5a11.5 11.5 0 0113 0"/><path d="M9 16.5a6 6 0 016 0"/><circle cx="12" cy="20" r="1" fill="currentColor"/></svg>',
};

function el(html) {
  const t = document.createElement('template');
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
}

function fmtMoney(v, currency = 'KES') {
  if (v === null || v === undefined || v === '') return '—';
  const n = Number(v);
  return `${currency} ${n.toLocaleString('en-KE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}
function fmtNum(v) {
  if (v === null || v === undefined || v === '') return '—';
  return Number(v).toLocaleString('en-US');
}
function fmtDate(v) {
  if (!v) return '—';
  const d = new Date(v);
  if (isNaN(d)) return '—';
  return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
}
function fmtDateTime(v) {
  if (!v) return '—';
  const d = new Date(v);
  if (isNaN(d)) return '—';
  return d.toLocaleString('en-GB', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}
function timeAgo(v) {
  if (!v) return '—';
  const d = new Date(v);
  if (isNaN(d)) return '—';
  const s = Math.floor((Date.now() - d.getTime()) / 1000);
  if (s < 60) return 'just now';
  if (s < 3600) return Math.floor(s / 60) + 'm ago';
  if (s < 86400) return Math.floor(s / 3600) + 'h ago';
  return Math.floor(s / 86400) + 'd ago';
}
function escapeHtml(s) {
  if (s === null || s === undefined) return '';
  return String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

/* Fixed status → badge class vocabulary, reused everywhere */
const STATUS_MAP = {
  active: 'good', online: 'good', paid: 'good', completed: 'good', confirmed: 'good', installed: 'good',
  pending: 'amber', partially_paid: 'amber', unpaid: 'amber', generated: 'amber', pending_disconnect: 'amber', pending_installation: 'amber',
  overdue: 'bad', expired: 'bad', disabled: 'bad', failed: 'bad', suspended: 'bad', cancelled: 'bad', offline: 'bad', inactive: 'muted',
  draft: 'muted', sent: 'signal', reversed: 'bad', refunded: 'muted', used: 'muted',
};
function statusBadge(status) {
  if (!status) return '<span class="badge badge-muted">—</span>';
  const cls = STATUS_MAP[status] || 'muted';
  const label = String(status).replace(/_/g, ' ');
  return `<span class="badge badge-${cls}">${escapeHtml(label)}</span>`;
}

/* Toasts */
function ensureToastStack() {
  let s = document.querySelector('.toast-stack');
  if (!s) { s = el('<div class="toast-stack"></div>'); document.body.appendChild(s); }
  return s;
}
function toast(message, type = 'default') {
  const stack = ensureToastStack();
  const node = el(`<div class="toast ${type}">${escapeHtml(message)}</div>`);
  stack.appendChild(node);
  setTimeout(() => { node.style.opacity = '0'; node.style.transition = 'opacity .2s'; setTimeout(() => node.remove(), 220); }, 3400);
}
function toastError(err) {
  toast(err?.message || 'Something went wrong', 'error');
}

/* Confirm dialog (promise-based) */
function confirmDialog({ title = 'Are you sure?', body = '', confirmLabel = 'Confirm', danger = false }) {
  return new Promise((resolve) => {
    const overlay = el(`
      <div class="modal-center">
        <div class="modal-box">
          <div class="drawer-head"><h3>${escapeHtml(title)}</h3></div>
          <div class="drawer-body"><p style="color:#5A6B8C;font-size:13.5px;margin:0">${body}</p></div>
          <div class="drawer-foot">
            <button class="btn btn-ghost" data-act="cancel">Cancel</button>
            <button class="btn ${danger ? 'btn-danger' : 'btn-primary'}" data-act="ok">${escapeHtml(confirmLabel)}</button>
          </div>
        </div>
      </div>`);
    overlay.addEventListener('click', (e) => { if (e.target === overlay) { overlay.remove(); resolve(false); } });
    overlay.querySelector('[data-act=cancel]').onclick = () => { overlay.remove(); resolve(false); };
    overlay.querySelector('[data-act=ok]').onclick = () => { overlay.remove(); resolve(true); };
    document.body.appendChild(overlay);
  });
}

/* Drawer (side panel for create/edit forms) */
function openDrawer({ title, wide = false, bodyHtml, onMount, footerHtml }) {
  const overlay = el(`
    <div class="overlay">
      <div class="drawer ${wide ? 'wide' : ''}">
        <div class="drawer-head">
          <h3>${escapeHtml(title)}</h3>
          <button class="icon-btn" data-act="close">${Icons.close}</button>
        </div>
        <div class="drawer-body">${bodyHtml}</div>
        <div class="drawer-foot">${footerHtml || ''}</div>
      </div>
    </div>`);
  function close() { overlay.remove(); document.removeEventListener('keydown', onEsc); }
  function onEsc(e) { if (e.key === 'Escape') close(); }
  overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });
  overlay.querySelector('[data-act=close]').onclick = close;
  document.addEventListener('keydown', onEsc);
  document.body.appendChild(overlay);
  if (onMount) onMount(overlay, close);
  return { close, overlay };
}

/* Form field builders — return HTML strings, kept simple on purpose */
const Field = {
  text: (name, label, value = '', opts = {}) => `
    <div class="field-row">
      <label class="field-label">${escapeHtml(label)}${opts.required ? ' *' : ''}</label>
      <input type="${opts.type || 'text'}" name="${name}" value="${escapeHtml(value)}" placeholder="${escapeHtml(opts.placeholder || '')}" ${opts.required ? 'required' : ''} ${opts.disabled ? 'disabled' : ''} ${opts.step ? `step="${opts.step}"` : ''} ${opts.min !== undefined ? `min="${opts.min}"` : ''}/>
      ${opts.hint ? `<div class="field-hint">${opts.hint}</div>` : ''}
    </div>`,
  textarea: (name, label, value = '', opts = {}) => `
    <div class="field-row">
      <label class="field-label">${escapeHtml(label)}${opts.required ? ' *' : ''}</label>
      <textarea name="${name}" placeholder="${escapeHtml(opts.placeholder || '')}" ${opts.required ? 'required' : ''}>${escapeHtml(value)}</textarea>
    </div>`,
  select: (name, label, options, value = '', opts = {}) => `
    <div class="field-row">
      <label class="field-label">${escapeHtml(label)}${opts.required ? ' *' : ''}</label>
      <select name="${name}" ${opts.required ? 'required' : ''}>
        ${opts.placeholder ? `<option value="">${escapeHtml(opts.placeholder)}</option>` : ''}
        ${options.map(o => {
          const v = typeof o === 'object' ? o.value : o;
          const l = typeof o === 'object' ? o.label : o;
          return `<option value="${escapeHtml(v)}" ${String(v) === String(value) ? 'selected' : ''}>${escapeHtml(l)}</option>`;
        }).join('')}
      </select>
    </div>`,
  checkbox: (name, label, checked = false) => `
    <div class="field-row" style="display:flex;align-items:center;gap:8px;">
      <input type="checkbox" name="${name}" ${checked ? 'checked' : ''} style="width:auto;"/>
      <label class="field-label" style="margin:0;">${escapeHtml(label)}</label>
    </div>`,
  row2: (a, b) => `<div class="field-grid">${a}${b}</div>`,
};

function formToObject(form) {
  const data = {};
  new FormData(form).forEach((v, k) => { data[k] = v; });
  form.querySelectorAll('input[type=checkbox]').forEach((cb) => { data[cb.name] = cb.checked; });
  return data;
}

/* Data table */
function renderTable({ columns, rows, emptyTitle = 'Nothing here yet', emptyBody = '' }) {
  if (!rows.length) {
    return `<div class="table-empty"><div class="big">${escapeHtml(emptyTitle)}</div><div>${escapeHtml(emptyBody)}</div></div>`;
  }
  const thead = columns.map(c => `<th class="${c.num ? 'num' : ''}">${escapeHtml(c.label)}</th>`).join('');
  const tbody = rows.map(row => {
    const tds = columns.map(c => `<td class="${c.num ? 'num' : ''}">${c.render(row)}</td>`).join('');
    return `<tr>${tds}</tr>`;
  }).join('');
  return `<div class="table-wrap"><table class="data"><thead><tr>${thead}</tr></thead><tbody>${tbody}</tbody></table></div>`;
}

function renderPager({ page, limit, total }, onPage) {
  const pages = Math.max(1, Math.ceil(total / limit));
  const wrap = el(`
    <div class="pager">
      <div class="info">${total === 0 ? '0 results' : `${(page - 1) * limit + 1}–${Math.min(page * limit, total)} of ${fmtNum(total)}`}</div>
      <div class="btns">
        <button class="btn btn-ghost btn-sm" data-act="prev" ${page <= 1 ? 'disabled' : ''}>Previous</button>
        <button class="btn btn-ghost btn-sm" data-act="next" ${page >= pages ? 'disabled' : ''}>Next</button>
      </div>
    </div>`);
  wrap.querySelector('[data-act=prev]').onclick = () => onPage(page - 1);
  wrap.querySelector('[data-act=next]').onclick = () => onPage(page + 1);
  return wrap;
}

function statCard({ label, value, sub, accent = '' }) {
  return `
    <div class="stat-card ${accent ? 'a-' + accent : ''}">
      <div class="stat-label">${escapeHtml(label)}</div>
      <div class="stat-value">${value}</div>
      ${sub ? `<div class="stat-sub">${sub}</div>` : ''}
    </div>`;
}

function copyChip(text) {
  return `<span class="copy-code" onclick="navigator.clipboard.writeText('${escapeHtml(text)}');toast('Copied','success')">${escapeHtml(text)}${Icons.copy}</span>`;
}
