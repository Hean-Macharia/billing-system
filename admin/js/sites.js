import { API } from './api.config.js';
import { api } from './api.js';
import { mountShell } from './app-shell.js';
import { $, esc, formatDate, statusBadge, toast, empty, modal } from './ui.js';

const user = await mountShell('sites');
const canUpdate = user?.role === 'super_admin' || (user?.permissions || []).includes('routers.update');
const root = $('#main-content');
root.innerHTML = `<section class="page-head"><div><h2>ISP sites</h2><p>Manage locations that routers, RADIUS clients, plans and vouchers reference.</p></div><div class="page-actions"><button class="btn" id="refresh-sites">Refresh</button>${canUpdate ? '<button class="btn btn-primary" id="new-site">Add site</button>' : ''}</div></section><section class="panel"><div class="table-tools"><input class="search-input" id="site-search" type="search" placeholder="Filter loaded sites" aria-label="Filter sites"><select class="search-input" id="site-status" aria-label="Site status"><option value="">All statuses</option><option value="active">Active</option><option value="inactive">Inactive</option><option value="planned">Planned</option></select><span class="muted-small" id="site-count"></span></div><div id="site-list"></div></section><p class="muted-small" style="margin-top:12px">Site changes can affect router identity, voucher restrictions and package availability. Use deactivation for planned maintenance; deletion is intentionally not offered here.</p>`;

let sites = [];
function draw() {
  const query = $('#site-search').value.trim().toLowerCase();
  const status = $('#site-status').value;
  const filtered = sites.filter((site) => (!status || site.status === status)
    && (!query || `${site.name} ${site.code} ${site.address || ''}`.toLowerCase().includes(query)));
  $('#site-count').textContent = `${filtered.length} site${filtered.length === 1 ? '' : 's'} in this page`;
  $('#site-list').innerHTML = filtered.length ? `<div class="table-wrap"><table class="data-table"><thead><tr><th>Site</th><th>Code</th><th>Location</th><th>Contact</th><th>Status</th><th>Updated</th>${canUpdate ? '<th>Actions</th>' : ''}</tr></thead><tbody>${filtered.map((site) => `<tr><td><strong>${esc(site.name)}</strong></td><td>${esc(site.code)}</td><td>${esc(site.address || '—')}</td><td>${esc(site.contact_person || '—')}<br><span class="muted-small">${esc(site.contact_phone || '')}</span></td><td>${statusBadge(site.status)}</td><td>${formatDate(site.updated_at)}</td>${canUpdate ? `<td><button class="btn btn-quiet" data-edit="${esc(site._id || site.id)}">Edit</button><button class="btn btn-quiet" data-status="${esc(site._id || site.id)}" data-next="${site.status === 'active' ? 'inactive' : 'active'}">${site.status === 'active' ? 'Deactivate' : 'Activate'}</button></td>` : ''}</tr>`).join('')}</tbody></table></div>` : empty(sites.length ? 'No matching sites' : 'No sites are configured');
  $('#site-list').querySelectorAll('[data-edit]').forEach((button) => button.addEventListener('click', () => openForm(sites.find((site) => String(site._id || site.id) === button.dataset.edit))));
  $('#site-list').querySelectorAll('[data-status]').forEach((button) => button.addEventListener('click', async () => {
    const site = sites.find((item) => String(item._id || item.id) === button.dataset.status);
    if (!site || !confirm(`${button.dataset.next === 'active' ? 'Activate' : 'Deactivate'} ${site.name}?`)) return;
    try { await api.patch(`${API.sites}/${encodeURIComponent(button.dataset.status)}`, { status: button.dataset.next }); toast(`Site ${button.dataset.next}`); await load(); }
    catch (error) { toast(error.message, 'error'); }
  }));
}
async function load() {
  $('#site-list').innerHTML = '<div class="panel-body"><div class="skeleton"></div><div class="skeleton" style="margin-top:12px"></div></div>';
  try { const response = await api.get(API.sites, { page: 1, limit: 100 }); sites = api.rows(response); draw(); }
  catch (error) { $('#site-list').innerHTML = `<div class="error-state" role="alert">${esc(error.message)}</div>`; }
}
function openForm(site) {
  const value = (key) => esc(site?.[key] ?? '');
  const body = `<form id="site-form"><div class="grid-2"><div class="field"><label for="site-name">Site name</label><input id="site-name" name="name" value="${value('name')}" maxlength="100" required></div><div class="field"><label for="site-code">Site code</label><input id="site-code" name="code" value="${value('code')}" maxlength="30" required></div><div class="field"><label for="site-address">Address</label><input id="site-address" name="address" value="${value('address')}"></div><div class="field"><label for="site-status-field">Status</label><select id="site-status-field" name="status"><option value="active">Active</option><option value="inactive">Inactive</option><option value="planned">Planned</option></select></div><div class="field"><label for="site-contact">Contact person</label><input id="site-contact" name="contact_person" value="${value('contact_person')}"></div><div class="field"><label for="site-phone">Contact phone</label><input id="site-phone" name="contact_phone" value="${value('contact_phone')}" inputmode="tel"></div><div class="field"><label for="site-latitude">Latitude</label><input id="site-latitude" name="latitude" type="number" step="any" value="${value('latitude')}"></div><div class="field"><label for="site-longitude">Longitude</label><input id="site-longitude" name="longitude" type="number" step="any" value="${value('longitude')}"></div><div class="field" style="grid-column:1/-1"><label for="site-notes">Notes</label><textarea id="site-notes" name="notes">${value('notes')}</textarea></div></div><div class="notice" id="site-form-error" hidden role="alert"></div><button class="btn btn-primary" type="submit">${site ? 'Save changes' : 'Create site'}</button></form>`;
  const dialog = modal(site ? 'Edit site' : 'Add site', body);
  $('#site-status-field', dialog.host).value = site?.status || 'active';
  $('#site-form', dialog.host).addEventListener('submit', async (event) => {
    event.preventDefault(); const form = new FormData(event.currentTarget);
    const data = Object.fromEntries(form.entries());
    for (const key of ['latitude', 'longitude']) data[key] = data[key] === '' ? null : Number(data[key]);
    for (const key of ['address', 'contact_person', 'contact_phone', 'notes']) data[key] ||= null;
    try {
      const id = site?._id || site?.id;
      if (id) await api.patch(`${API.sites}/${encodeURIComponent(id)}`, data);
      else await api.post(API.sites, data);
      dialog.close(); toast(site ? 'Site updated' : 'Site created'); await load();
    } catch (error) { const box = $('#site-form-error', dialog.host); box.hidden = false; box.textContent = error.message; }
  });
}
$('#new-site')?.addEventListener('click', () => openForm(null));
$('#refresh-sites').addEventListener('click', load);
$('#site-search').addEventListener('input', draw);
$('#site-status').addEventListener('change', draw);
await load();
