import { API } from './api.config.js';
import { api } from './api.js';
import { mountShell } from './app-shell.js';
import { $, esc, currency, formatDate, statusBadge, toast, empty, modal } from './ui.js';

const user = await mountShell('vouchers');
const root = $('#main-content');
if (!user || !root) throw new Error('Staff session is required.');
const permissions = new Set(user.permissions || []);
const canCreate = ['admin', 'super_admin'].includes(user.role) || permissions.has('vouchers.create');
const canUpdate = ['admin', 'super_admin'].includes(user.role) || permissions.has('vouchers.update');
root.innerHTML = `<section class="page-head"><div><h2>HotSpot vouchers</h2><p>Generate vouchers from existing HotSpot plans, then manage the codes and batches returned by FastAPI.</p></div><div class="page-actions"><button class="btn" id="refresh-vouchers">Refresh</button>${canCreate ? '<button class="btn btn-primary" id="generate-vouchers">Generate batch</button>' : ''}</div></section><section class="panel"><div class="table-tools"><div class="tabs" role="tablist"><button class="btn btn-primary" id="voucher-tab" role="tab" aria-selected="true">Vouchers</button><button class="btn" id="batch-tab" role="tab" aria-selected="false">Batches</button></div><input class="search-input" id="voucher-search" type="search" placeholder="Search this page" aria-label="Search vouchers"><select id="voucher-status" class="search-input" aria-label="Filter voucher status"><option value="">All statuses</option><option value="generated">Unused</option><option value="active">Active</option><option value="used">Used</option><option value="expired">Expired</option><option value="disabled">Disabled</option></select><span class="muted-small" id="voucher-count"></span></div><div id="voucher-list"></div><footer class="panel-head"><span class="muted-small" id="voucher-page"></span><div><button class="btn" id="voucher-prev">Previous</button><button class="btn" id="voucher-next">Next</button></div></footer></section><p class="muted-small" style="margin-top:12px">Voucher credentials are generated and activated only by the backend. CSV export is available for generated batches.</p>`;

let page = 1;
let tab = 'vouchers';
let voucherRows = [];
let batchRows = [];
let total = 0;
const pathId = (row) => row._id || row.id;

async function load() {
  const list = $('#voucher-list');
  list.innerHTML = '<div class="panel-body"><div class="skeleton"></div><div class="skeleton" style="margin-top:12px"></div></div>';
  $('#voucher-prev').disabled = true; $('#voucher-next').disabled = true;
  try {
    if (tab === 'vouchers') {
      const params = { page, limit: 20 };
      if ($('#voucher-status').value) params.status_filter = $('#voucher-status').value;
      const response = await api.get(API.vouchers, params);
      voucherRows = api.rows(response); total = api.meta(response).total ?? voucherRows.length;
      $('#voucher-count').textContent = `${total} voucher${total === 1 ? '' : 's'}`;
      $('#voucher-page').textContent = `Page ${page} · ${total} total`;
      drawVouchers();
      $('#voucher-prev').disabled = page <= 1;
      $('#voucher-next').disabled = voucherRows.length < 20;
    } else {
      const response = await api.get(`${API.vouchers}/batches`, { page, limit: 20 });
      batchRows = api.rows(response); total = api.meta(response).total ?? batchRows.length;
      $('#voucher-count').textContent = `${total} batch${total === 1 ? '' : 'es'}`;
      $('#voucher-page').textContent = `Page ${page} · ${total} total`;
      drawBatches();
      $('#voucher-prev').disabled = page <= 1;
      $('#voucher-next').disabled = batchRows.length < 20;
    }
  } catch (error) {
    list.innerHTML = `<div class="error-state" role="alert">${esc(error.message)}</div>`;
    $('#voucher-count').textContent = 'Unable to load';
  }
}

function drawVouchers() {
  const query = $('#voucher-search').value.trim().toLowerCase();
  const rows = voucherRows.filter((voucher) => !query || `${voucher.voucher_code} ${voucher.batch_id || ''} ${voucher.status}`.toLowerCase().includes(query));
  $('#voucher-list').innerHTML = rows.length ? `<div class="table-wrap"><table class="data-table"><thead><tr><th>Voucher code</th><th>Batch</th><th>Plan duration</th><th>Data allowance</th><th>Price</th><th>Site</th><th>Status</th><th>Expires</th><th>Actions</th></tr></thead><tbody>${rows.map((voucher) => `<tr><td><code>${esc(voucher.voucher_code)}</code> <button class="btn btn-quiet" data-copy="${esc(voucher.voucher_code)}" aria-label="Copy voucher code">Copy</button></td><td>${esc(voucher.batch_id || '—')}</td><td>${esc(voucher.duration_hours ?? '—')} h</td><td>${voucher.data_allowance_mb == null ? 'Unlimited' : `${esc(voucher.data_allowance_mb)} MB`}</td><td>${currency(voucher.price)} ${esc(voucher.currency || 'KES')}</td><td>${esc(voucher.site_id || 'Global')}</td><td>${statusBadge(voucher.status)}</td><td>${formatDate(voucher.expiry_date)}</td><td>${canUpdate && voucher.status === 'generated' ? `<button class="btn" data-activate="${esc(pathId(voucher))}">Activate</button>` : ''}${canUpdate && voucher.status === 'active' ? `<button class="btn btn-danger" data-disable="${esc(pathId(voucher))}">Disable</button>` : '—'}</td></tr>`).join('')}</tbody></table></div>` : empty(voucherRows.length ? 'No vouchers match this search' : 'No vouchers on this page');
  wireRows();
}

function drawBatches() {
  const query = $('#voucher-search').value.trim().toLowerCase();
  const rows = batchRows.filter((batch) => !query || `${batch.batch_name} ${batch.site_id || ''} ${batch._id || ''}`.toLowerCase().includes(query));
  $('#voucher-list').innerHTML = rows.length ? `<div class="table-wrap"><table class="data-table"><thead><tr><th>Batch</th><th>Site</th><th>Quantity</th><th>Generated</th><th>Activated</th><th>Used</th><th>Price</th><th>Created</th><th>Actions</th></tr></thead><tbody>${rows.map((batch) => `<tr><td><strong>${esc(batch.batch_name)}</strong><br><span class="muted-small">${esc(pathId(batch))}</span></td><td>${esc(batch.site_id || 'Global')}</td><td>${esc(batch.quantity)}</td><td>${esc(batch.generated_count ?? 0)}</td><td>${esc(batch.activated_count ?? 0)}</td><td>${esc(batch.used_count ?? 0)}</td><td>${currency(batch.price)} ${esc(batch.currency || 'KES')}</td><td>${formatDate(batch.created_at)}</td><td><button class="btn" data-export="${esc(pathId(batch))}">Export CSV</button>${canUpdate && batch.activated_count < batch.generated_count ? `<button class="btn" data-activate-batch="${esc(pathId(batch))}">Activate unused</button>` : ''}</td></tr>`).join('')}</tbody></table></div>` : empty(batchRows.length ? 'No batches match this search' : 'No batches found');
  wireRows();
}

function wireRows() {
  $('#voucher-list').querySelectorAll('[data-copy]').forEach((button) => button.addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(button.dataset.copy); toast('Voucher code copied'); }
    catch { toast('Clipboard access is unavailable in this browser', 'error'); }
  }));
  $('#voucher-list').querySelectorAll('[data-activate]').forEach((button) => button.addEventListener('click', async () => {
    if (!confirm('Activate this generated voucher?')) return;
    try { await api.post(`${API.vouchers}/${encodeURIComponent(button.dataset.activate)}/activate`, {}); toast('Voucher activated'); await load(); }
    catch (error) { toast(error.message, 'error'); }
  }));
  $('#voucher-list').querySelectorAll('[data-disable]').forEach((button) => button.addEventListener('click', async () => {
    if (!confirm('Disable this voucher?')) return;
    try { await api.post(`${API.vouchers}/${encodeURIComponent(button.dataset.disable)}/disable`, { reason: 'Disabled by administrator' }); toast('Voucher disabled'); await load(); }
    catch (error) { toast(error.message, 'error'); }
  }));
  $('#voucher-list').querySelectorAll('[data-activate-batch]').forEach((button) => button.addEventListener('click', async () => {
    if (!confirm('Activate all generated vouchers in this batch?')) return;
    try { await api.post(`${API.vouchers}/batches/${encodeURIComponent(button.dataset.activateBatch)}/activate`, {}); toast('Unused vouchers activated'); await load(); }
    catch (error) { toast(error.message, 'error'); }
  }));
  $('#voucher-list').querySelectorAll('[data-export]').forEach((button) => button.addEventListener('click', async () => {
    try {
      const blob = await api.request(`${API.vouchers}/batches/${encodeURIComponent(button.dataset.export)}/export`, { responseType: 'blob' });
      const url = URL.createObjectURL(blob); const anchor = document.createElement('a'); anchor.href = url; anchor.download = `devzen-vouchers-${button.dataset.export}.csv`; anchor.click(); URL.revokeObjectURL(url);
    } catch (error) { toast(error.message, 'error'); }
  }));
}

async function showGenerateForm() {
  const dialog = modal('Generate voucher batch', '<div class="panel-body"><div class="skeleton"></div><p class="muted-small">Loading available sites and HotSpot plans…</p></div>');
  try {
    const [siteResponse, planResponse] = await Promise.all([
      api.get(API.sites, { page: 1, limit: 100 }),
      api.get(API.hotspotPlans, { active_only: true }),
    ]);
    const sites = api.rows(siteResponse);
    const plans = api.rows(planResponse);
    if (!plans.length) throw new Error('Create an active HotSpot plan before generating vouchers.');
    dialog.host.querySelector('.modal-body').innerHTML = `<form id="voucher-batch-form"><div class="grid-2"><div class="field"><label for="batch-name">Batch name</label><input id="batch-name" name="batch_name" maxlength="100" required></div><div class="field"><label for="batch-quantity">Number of vouchers</label><input id="batch-quantity" name="quantity" type="number" min="1" max="5000" value="20" required></div><div class="field"><label for="batch-plan">HotSpot plan</label><select id="batch-plan" name="plan_id" required><option value="">Select a plan</option>${plans.map((plan) => `<option value="${esc(pathId(plan))}" data-site="${esc(plan.site_id || '')}">${esc(plan.name)} · ${currency(plan.price)} · ${esc(plan.duration_hours)} h</option>`).join('')}</select></div><div class="field"><label for="batch-site">Site restriction</label><select id="batch-site" name="site_id"><option value="">Use plan site / global</option>${sites.map((site) => `<option value="${esc(pathId(site))}">${esc(site.name)} (${esc(site.code)})</option>`).join('')}</select><small class="muted-small">Site-specific plans retain their configured site.</small></div><div class="field"><label for="batch-prefix">Code prefix (optional)</label><input id="batch-prefix" name="code_prefix" maxlength="8"></div><div class="field"><label for="batch-length">Code length</label><input id="batch-length" name="code_length" type="number" min="6" max="20" value="10" required></div><div class="field"><label for="batch-validity">Validity after generation (days, optional)</label><input id="batch-validity" name="validity_days_after_generation" type="number" min="1"></div><label class="field"><span>Activate when generated</span><span><input type="checkbox" name="activate_on_generation"> Activate all generated codes</span></label></div><div class="notice" id="batch-error" hidden role="alert"></div><button class="btn btn-primary" type="submit">Generate vouchers</button></form>`;
    $('#batch-plan', dialog.host).addEventListener('change', (event) => {
      const siteId = event.currentTarget.selectedOptions[0]?.dataset.site || '';
      const site = $('#batch-site', dialog.host);
      if (siteId) { site.value = siteId; site.disabled = true; }
      else site.disabled = false;
    });
    $('#voucher-batch-form', dialog.host).addEventListener('submit', async (event) => {
      event.preventDefault(); const form = new FormData(event.currentTarget);
      const selectedPlan = plans.find((plan) => String(pathId(plan)) === form.get('plan_id'));
      const siteSelect = $('#batch-site', dialog.host);
      const body = {
        batch_name: String(form.get('batch_name')).trim(), quantity: Number(form.get('quantity')),
        plan_id: form.get('plan_id'), site_id: siteSelect.disabled ? undefined : (form.get('site_id') || null),
        code_prefix: String(form.get('code_prefix') || '').trim(), code_length: Number(form.get('code_length')),
        price: Number(selectedPlan?.price || 0), currency: selectedPlan?.currency || 'KES',
        activate_on_generation: form.has('activate_on_generation'),
        validity_days_after_generation: form.get('validity_days_after_generation') ? Number(form.get('validity_days_after_generation')) : null,
      };
      try {
        const result = api.data(await api.post(`${API.vouchers}/batches`, body));
        dialog.close(); toast(`Voucher batch created · ${result.generated_count ?? result.quantity} codes`); tab = 'batches'; updateTabs(); page = 1; await load();
      } catch (error) { const box = $('#batch-error', dialog.host); box.hidden = false; box.textContent = error.message; }
    });
  } catch (error) {
    dialog.host.querySelector('.modal-body').innerHTML = `<div class="error-state" role="alert">${esc(error.message)}<p>Voucher generation requires an active HotSpot plan and available backend site records.</p></div>`;
  }
}

function updateTabs() {
  $('#voucher-tab').classList.toggle('btn-primary', tab === 'vouchers');
  $('#voucher-tab').setAttribute('aria-selected', String(tab === 'vouchers'));
  $('#batch-tab').classList.toggle('btn-primary', tab === 'batches');
  $('#batch-tab').setAttribute('aria-selected', String(tab === 'batches'));
  $('#voucher-status').hidden = tab !== 'vouchers';
  $('#voucher-search').placeholder = tab === 'vouchers' ? 'Search this page' : 'Search batches on this page';
  $('#voucher-prev').disabled = true;
  $('#voucher-next').disabled = true;
}

$('#voucher-tab').addEventListener('click', () => { tab = 'vouchers'; page = 1; updateTabs(); load(); });
$('#batch-tab').addEventListener('click', () => { tab = 'batches'; page = 1; updateTabs(); load(); });
$('#generate-vouchers')?.addEventListener('click', showGenerateForm);
$('#refresh-vouchers').addEventListener('click', load);
$('#voucher-search').addEventListener('input', () => tab === 'vouchers' ? drawVouchers() : drawBatches());
$('#voucher-status').addEventListener('change', () => { page = 1; load(); });
$('#voucher-prev').addEventListener('click', () => { if (page > 1) { page -= 1; load(); } });
$('#voucher-next').addEventListener('click', () => { if (tab === 'vouchers' ? voucherRows.length === 20 : batchRows.length === 20) { page += 1; load(); } });
await load();
