import { API } from './api.config.js';
import { api } from './api.js';
import { mountShell } from './app-shell.js';
import { $, esc, currency, statusBadge, toast, empty, modal } from './ui.js';

const user = await mountShell('catalog-packages');
const root = $('#main-content');
if (!user || !root) throw new Error('Staff session is required.');
const permissions = new Set(user.permissions || []);
const canCreate = ['admin', 'super_admin'].includes(user.role) || permissions.has('services.create');
const canUpdate = ['admin', 'super_admin'].includes(user.role) || permissions.has('services.update');
root.innerHTML = `<section class="page-head"><div><h2>Packages</h2><p>Manage the standalone package catalog. Recurring billing uses Service plans; HotSpot vouchers use HotSpot plans.</p></div><div class="page-actions"><button class="btn" id="refresh-packages">Refresh</button>${canCreate ? '<button class="btn btn-primary" id="create-package">Add package</button>' : ''}</div></section><section class="panel"><div class="table-tools"><select class="search-input" id="package-type" aria-label="Filter package type"><option value="">All package types</option><option value="home">Home</option><option value="hotspot">HotSpot</option></select><span class="muted-small" id="package-count"></span></div><div id="package-list"></div></section>`;

let records = [];
async function load() {
  $('#package-list').innerHTML = '<div class="panel-body"><div class="skeleton"></div><div class="skeleton" style="margin-top:12px"></div></div>';
  try {
    const params = { active_only: false };
    if ($('#package-type').value) params.package_type = $('#package-type').value;
    records = api.rows(await api.get(API.catalogPackages, params));
    $('#package-count').textContent = `${records.length} package${records.length === 1 ? '' : 's'} returned`;
    draw();
  } catch (error) { $('#package-list').innerHTML = `<div class="error-state" role="alert">${esc(error.message)}</div>`; }
}
function draw() {
  $('#package-list').innerHTML = records.length ? `<div class="table-wrap"><table class="data-table"><thead><tr><th>Package</th><th>Type</th><th>Speed</th><th>Price</th><th>Validity</th><th>Devices</th><th>Router profile</th><th>Status</th>${canUpdate ? '<th>Action</th>' : ''}</tr></thead><tbody>${records.map((record) => { const speeds = [record.download_speed, record.upload_speed].map(Number).filter((value) => Number.isFinite(value) && value > 0); const speed = speeds.length ? `Up to ${Math.max(...speeds)} Mbps` : '—'; return `<tr><td><strong>${esc(record.name)}</strong><br><span class="muted-small">${esc(record.package_id || '')}</span></td><td>${esc(record.package_type || '—')}</td><td>${speed}</td><td>${currency(record.price)}</td><td>${esc(record.validity_days ?? record.duration_days ?? '—')} days</td><td>${esc(record.max_devices ?? '—')}</td><td>${esc(record.mikrotik_profile || '—')}</td><td>${statusBadge(record.status || (record.is_active ? 'active' : 'inactive'))}</td>${canUpdate ? `<td><button class="btn btn-quiet" data-edit="${esc(record.package_id)}">Edit</button></td>` : ''}</tr>`; }).join('')}</tbody></table></div>` : empty('No packages found');
  $('#package-list').querySelectorAll('[data-edit]').forEach((button) => button.addEventListener('click', () => openForm(records.find((item) => item.package_id === button.dataset.edit))));
}
function openForm(record) {
  const val = (key, fallback = '') => esc(record?.[key] ?? fallback);
  const validity = record?.validity_days ?? record?.duration_days ?? '';
  const body = `<form id="catalog-form"><div class="grid-2"><div class="field"><label for="package-name">Package name</label><input id="package-name" name="name" value="${val('name')}" required></div><div class="field"><label for="package-type-field">Type</label><select id="package-type-field" name="package_type"><option value="home">Home</option><option value="hotspot">HotSpot</option></select></div><div class="field"><label for="package-download">Download Mbps <span class="muted-small">(optional)</span></label><input id="package-download" name="download_speed" type="number" min="1" step="1" value="${val('download_speed')}" placeholder="Optional"></div><div class="field"><label for="package-upload">Upload Mbps <span class="muted-small">(optional)</span></label><input id="package-upload" name="upload_speed" type="number" min="1" step="1" value="${val('upload_speed')}" placeholder="Optional"></div><div class="field"><label for="package-price">Price (KES)</label><input id="package-price" name="price" type="number" min="0.01" step="0.01" value="${val('price')}" required></div><div class="field"><label for="package-validity">Validity (days)</label><input id="package-validity" name="validity_days" type="number" min="1" step="1" value="${esc(validity)}" required></div><div class="field"><label for="package-max-devices">Maximum devices</label><input id="package-max-devices" name="max_devices" type="number" min="1" step="1" value="${val('max_devices', 1)}" required></div><div class="field"><label for="package-profile">MikroTik profile</label><input id="package-profile" name="mikrotik_profile" value="${val('mikrotik_profile')}"></div>${record ? `<div class="field"><label for="package-status">Status</label><select id="package-status" name="status"><option value="active">Active</option><option value="inactive">Inactive</option></select></div>` : ''}</div><div class="notice" id="catalog-error" hidden role="alert"></div><button class="btn btn-primary" type="submit">${record ? 'Save package' : 'Create package'}</button></form>`;
  const dialog = modal(record ? 'Edit package' : 'Create package', body);
  $('#package-type-field', dialog.host).value = record?.package_type || 'home';
  if (record) $('#package-status', dialog.host).value = record.status || 'active';
  $('#catalog-form', dialog.host).addEventListener('submit', async (event) => {
    event.preventDefault(); const form = Object.fromEntries(new FormData(event.currentTarget));
    const payload = {
      name: form.name.trim(), package_type: form.package_type,
      download_speed: form.download_speed ? Number(form.download_speed) : null,
      upload_speed: form.upload_speed ? Number(form.upload_speed) : null,
      price: Number(form.price), validity_days: Number(form.validity_days),
      max_devices: Number(form.max_devices), mikrotik_profile: form.mikrotik_profile.trim() || null,
    };
    if (record) payload.status = form.status;
    try {
      if (record) await api.patch(`${API.catalogPackages}/${encodeURIComponent(record.package_id)}`, payload);
      else await api.post(API.catalogPackages, payload);
      dialog.close(); toast(record ? 'Package updated' : 'Package created'); await load();
    } catch (error) { const message = $('#catalog-error', dialog.host); message.hidden = false; message.textContent = error.message; }
  });
}
$('#refresh-packages').addEventListener('click', load);
$('#package-type').addEventListener('change', load);
$('#create-package')?.addEventListener('click', () => openForm(null));
await load();
