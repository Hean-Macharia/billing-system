window.Pages = window.Pages || {};

const Icons = {
  home: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 11l9-8 9 8"/><path d="M5 10v10h14V10"/></svg>',
  subscription: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18"/></svg>',
  billing: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 2h9l5 5v13a2 2 0 01-2 2H6a2 2 0 01-2-2V4a2 2 0 012-2z"/><path d="M14 2v5h5"/></svg>',
  payments: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="6" width="20" height="13" rx="2"/><path d="M2 10h20"/></svg>',
  usage: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 20V10M12 20V4M20 20v-7"/></svg>',
  support: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 11.5a8.4 8.4 0 01-.9 3.8 8.5 8.5 0 01-7.6 4.7 8.4 8.4 0 01-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 01-.9-3.8 8.5 8.5 0 014.7-7.6 8.4 8.4 0 013.8-.9h.5a8.48 8.48 0 018 8v.5z"/></svg>',
  wifi: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M2 8.5a17 17 0 0120 0"/><path d="M5.5 12.5a11.5 11.5 0 0113 0"/><path d="M9 16.5a6 6 0 016 0"/><circle cx="12" cy="20" r="1" fill="currentColor"/></svg>',
  logout: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4"/><path d="M16 17l5-5-5-5"/><path d="M21 12H9"/></svg>',
  close: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg>',
  download: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3v13"/><path d="M7 11l5 5 5-5"/><path d="M4 20h16"/></svg>',
  send: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 2L11 13"/><path d="M22 2l-7 20-4-9-9-4 20-7z"/></svg>',
  plus: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M12 5v14M5 12h14"/></svg>',
  check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4"><path d="M20 6L9 17l-5-5"/></svg>',
  bolt: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M13 2L3 14h7l-1 8 10-12h-7z"/></svg>',
  inbox: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.5 5h13l3.5 7v6a2 2 0 01-2 2H4a2 2 0 01-2-2v-6l3.5-7z"/></svg>',
};

function el(html) { const t = document.createElement('template'); t.innerHTML = html.trim(); return t.content.firstElementChild; }
function escapeHtml(s) { if (s === null || s === undefined) return ''; return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
function fmtMoney(v, currency = 'KES') { if (v === null || v === undefined) return '—'; return `${currency} ${Number(v).toLocaleString('en-KE', {minimumFractionDigits:2, maximumFractionDigits:2})}`; }
function fmtDate(v) { if (!v) return '—'; const d = new Date(v); return isNaN(d) ? '—' : d.toLocaleDateString('en-GB', {day:'2-digit', month:'short', year:'numeric'}); }
function fmtDateTime(v) { if (!v) return '—'; const d = new Date(v); return isNaN(d) ? '—' : d.toLocaleString('en-GB', {day:'2-digit', month:'short', hour:'2-digit', minute:'2-digit'}); }

const STATUS_MAP = {
  active: 'good', online: 'good', paid: 'good', completed: 'good', open: 'signal', resolved: 'good',
  pending: 'amber', partially_paid: 'amber', unpaid: 'amber', closed: 'muted',
  sent: 'signal', viewed: 'signal', partial: 'amber',
  overdue: 'bad', expired: 'bad', failed: 'bad', suspended: 'bad', cancelled: 'bad', offline: 'muted',
};
function statusBadge(status) {
  if (!status) return '<span class="badge badge-muted">—</span>';
  const cls = STATUS_MAP[status] || 'muted';
  return `<span class="badge badge-${cls}">${escapeHtml(String(status).replace(/_/g,' '))}</span>`;
}

function ensureToastStack() { let s = document.querySelector('.toast-stack'); if (!s) { s = el('<div class="toast-stack"></div>'); document.body.appendChild(s); } return s; }
function toast(message, type = 'default') {
  const stack = ensureToastStack();
  const node = el(`<div class="toast ${type}">${escapeHtml(message)}</div>`);
  stack.appendChild(node);
  setTimeout(() => { node.style.opacity = '0'; node.style.transition = 'opacity .2s'; setTimeout(() => node.remove(), 220); }, 3200);
}
function toastError(err) { toast(err?.message || 'Something went wrong', 'error'); }

/* Bottom sheet (mobile-first modal) */
function openSheet({ title, bodyHtml, footerHtml }) {
  const overlay = el(`
    <div class="sheet-overlay">
      <div class="sheet">
        <div class="sheet-head"><h3>${escapeHtml(title)}</h3><button class="icon-btn" data-act="close">${Icons.close}</button></div>
        <div class="sheet-body">${bodyHtml}</div>
        ${footerHtml ? `<div class="sheet-foot">${footerHtml}</div>` : ''}
      </div>
    </div>`);
  function close() { overlay.remove(); document.removeEventListener('keydown', onEsc); }
  function onEsc(e) { if (e.key === 'Escape') close(); }
  overlay.addEventListener('click', e => { if (e.target === overlay) close(); });
  overlay.querySelector('[data-act=close]').onclick = close;
  document.addEventListener('keydown', onEsc);
  document.body.appendChild(overlay);
  return { close, overlay };
}

function formToObject(form) { const data = {}; new FormData(form).forEach((v,k) => data[k] = v); return data; }

/* Authenticated file download - a plain <a href> can't send the
   Authorization header, so every protected download (receipts, etc.)
   goes through here: fetch as an authed blob, then trigger a save via a
   synthetic, momentary object-URL link. */
async function downloadAuthedFile(path, filename) {
  try {
    const blob = await Api.fetchBlob(path);
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 4000);
  } catch (e) {
    toastError(e);
  }
}

function renderList({ rows, renderRow, emptyTitle = 'Nothing here yet', emptyBody = '' }) {
  if (!rows.length) return `<div class="list-empty"><div class="big">${escapeHtml(emptyTitle)}</div><div>${escapeHtml(emptyBody)}</div></div>`;
  return rows.map(renderRow).join('');
}
