import { API } from './api.config.js';
import { api } from './api.js';
import { mountShell } from './app-shell.js';
import { $, esc, formatDate, statusBadge, toast, empty, modal } from './ui.js';

const user = await mountShell('network');
const root = $('#main-content');
if (!user || !root) throw new Error('Staff session is required.');
const permissions = new Set(user.permissions || []);
const canCreate = ['admin', 'super_admin'].includes(user.role) || permissions.has('routers.create');
const canUpdate = ['admin', 'super_admin'].includes(user.role) || permissions.has('routers.update');
root.innerHTML = `<section class="page-head"><div><h2>Routers & network</h2><p>Manage approved MikroTik connections and view live information returned by the RouterService.</p></div><div class="page-actions"><a class="btn" href="./sessions.html">RADIUS sessions</a><button class="btn" id="refresh-routers">Refresh</button>${canCreate ? '<button class="btn btn-primary" id="add-router">Register router</button>' : ''}</div></section><section class="panel"><div class="table-tools"><select id="router-site-filter" class="search-input" aria-label="Filter by site"><option value="">All sites</option></select><input id="router-search" class="search-input" type="search" placeholder="Filter loaded routers" aria-label="Search routers"><span class="muted-small" id="router-count"></span></div><div id="router-list"></div><footer class="panel-head"><span id="router-page" class="muted-small"></span><div><button class="btn" id="router-prev">Previous</button><button class="btn" id="router-next">Next</button></div></footer></section><section class="page-actions" style="margin-top:14px"><a class="btn" href="./sites.html">Manage sites</a><a class="btn" href="./radius-nas.html">Manage RADIUS clients</a><a class="btn" href="./hotspot-plans.html">Manage HotSpot plans</a></section>`;

let page = 1;
let rows = [];
let sites = [];
let total = 0;
const idOf = (item) => item._id || item.id;
const siteName = (siteId) => sites.find((site) => String(idOf(site)) === String(siteId))?.name || (siteId ? String(siteId) : 'Unassigned');

async function loadSites() {
  try {
    sites = api.rows(await api.get(API.sites, { page: 1, limit: 100 }));
    $('#router-site-filter').innerHTML = `<option value="">All sites</option>${sites.map((site) => `<option value="${esc(idOf(site))}">${esc(site.name)} (${esc(site.code)})</option>`).join('')}`;
  } catch { /* The router table remains usable if site listing permission is absent. */ }
}

async function load() {
  $('#router-list').innerHTML = '<div class="panel-body"><div class="skeleton"></div><div class="skeleton" style="margin-top:12px"></div></div>';
  try {
    const params = { page, limit: 20 };
    if ($('#router-site-filter').value) params.site_id = $('#router-site-filter').value;
    const response = await api.get(API.routers, params);
    rows = api.rows(response); total = api.meta(response).total ?? rows.length;
    $('#router-count').textContent = `${total} configured router${total === 1 ? '' : 's'}`;
    $('#router-page').textContent = `Page ${page} · ${total} total`;
    draw();
    $('#router-prev').disabled = page <= 1;
    $('#router-next').disabled = rows.length < 20;
  } catch (error) { $('#router-list').innerHTML = `<div class="error-state" role="alert">${esc(error.message)}</div>`; }
}

function draw() {
  const query = $('#router-search').value.trim().toLowerCase();
  const filtered = rows.filter((router) => !query || `${router.name} ${router.ip_address} ${router.location || ''} ${router.model_name || ''} ${siteName(router.site_id)}`.toLowerCase().includes(query));
  $('#router-list').innerHTML = filtered.length ? `<div class="table-wrap"><table class="data-table"><thead><tr><th>Router</th><th>Management</th><th>Site</th><th>Model / RouterOS</th><th>API</th><th>Health</th><th>Last check</th><th>Actions</th></tr></thead><tbody>${filtered.map((router) => `<tr><td><strong>${esc(router.name)}</strong><br><span class="muted-small">${esc(router.location || 'Location not set')}</span></td><td>${esc(router.ip_address)}:${esc(router.port)}</td><td>${esc(siteName(router.site_id))}</td><td>${esc(router.model_name || '—')}<br><span class="muted-small">${esc(router.routeros_version || 'Version not reported')}</span></td><td>${esc(router.api_type || '—')} · SSL ${router.use_ssl ? 'on' : 'off'}</td><td>${statusBadge(router.status || 'unknown')}</td><td>${formatDate(router.last_checked_at)}</td><td><div class="action-row"><button class="btn btn-quiet" data-test="${esc(idOf(router))}">Test</button><button class="btn btn-quiet" data-health="${esc(idOf(router))}">Refresh health</button><button class="btn btn-quiet" data-users="${esc(idOf(router))}">Active users</button><button class="btn btn-quiet" data-leases="${esc(idOf(router))}">DHCP leases</button>${canUpdate ? `<button class="btn btn-quiet" data-edit="${esc(idOf(router))}">Edit</button>` : ''}</div></td></tr>`).join('')}</tbody></table></div>` : empty(rows.length ? 'No routers match this search' : 'No routers are registered');
  $('#router-list').querySelectorAll('[data-edit]').forEach((button) => button.addEventListener('click', () => openForm(rows.find((router) => String(idOf(router)) === button.dataset.edit))));
  for (const [selector, suffix, label] of [['[data-test]', 'test', 'Connectivity test'], ['[data-health]', 'health', 'Health refresh']]) {
    $('#router-list').querySelectorAll(selector).forEach((button) => button.addEventListener('click', async () => {
      button.disabled = true;
      try { const response = await api.post(`${API.routers}/${encodeURIComponent(button.dataset[selector === '[data-test]' ? 'test' : 'health'])}/${suffix}`, {}); const data = api.data(response); toast(data?.message || `${label} completed`, data?.reachable === false ? 'error' : 'success'); await load(); }
      catch (error) { toast(error.message, 'error'); }
      finally { button.disabled = false; }
    }));
  }
  for (const [selector, path, label] of [['[data-users]', 'active-users', 'Active router users'], ['[data-leases]', 'dhcp-leases', 'DHCP leases']]) {
    $('#router-list').querySelectorAll(selector).forEach((button) => button.addEventListener('click', () => showLiveData(button.dataset[selector === '[data-users]' ? 'users' : 'leases'], path, label)));
  }
}

async function showLiveData(routerId, endpoint, title) {
  const dialog = modal(title, '<div class="panel-body"><div class="skeleton"></div></div>');
  try {
    const data = api.data(await api.get(`${API.routers}/${encodeURIComponent(routerId)}/${endpoint}`));
    const items = Array.isArray(data) ? data : [data?.items, data?.users, data?.active_users, data?.leases].find(Array.isArray) || [];
    if (!items.length) { dialog.host.querySelector('.modal-body').innerHTML = empty(`No ${title.toLowerCase()} were returned`); return; }
    const keys = [...new Set(items.flatMap((item) => Object.keys(item || {})))].slice(0, 8);
    dialog.host.querySelector('.modal-body').innerHTML = `<div class="table-wrap"><table class="data-table"><thead><tr>${keys.map((key) => `<th>${esc(key.replaceAll('_', ' '))}</th>`).join('')}</tr></thead><tbody>${items.map((item) => `<tr>${keys.map((key) => `<td>${esc(typeof item[key] === 'object' ? JSON.stringify(item[key]) : item[key] ?? '—')}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
  } catch (error) { dialog.host.querySelector('.modal-body').innerHTML = `<div class="error-state" role="alert">${esc(error.message)}</div>`; }
}

async function openForm(router) {
  const editing = Boolean(router);
  const dialog = modal(editing ? 'Edit router configuration' : 'Register MikroTik router', '<div class="panel-body"><div class="skeleton"></div><p class="muted-small">Loading sites and RADIUS clients…</p></div>');
  try {
    const [siteResponse, nasResponse] = await Promise.all([
      api.get(API.sites, { page: 1, limit: 100 }),
      api.get(API.radiusNas, { page: 1, limit: 100 }),
    ]);
    const allSites = api.rows(siteResponse);
    const allNas = api.rows(nasResponse);
    const field = (name, label, type = 'text', value = '', extra = '') => `<div class="field"><label for="router-${name}">${esc(label)}</label><input id="router-${name}" name="${name}" type="${type}" value="${esc(value)}" ${extra}></div>`;
    const formMarkup = `<form id="router-form"><div class="grid-2">${field('name','Router name','text',router?.name || '', 'required maxlength="100"')}${field('ip_address','Management IP / hostname','text',router?.ip_address || '', 'required autocomplete="off"')}<div class="field"><label for="router-site_id">ISP site</label><select id="router-site_id" name="site_id"><option value="">No site assignment</option>${allSites.map((site) => `<option value="${esc(idOf(site))}">${esc(site.name)} (${esc(site.code)})</option>`).join('')}</select></div><div class="field"><label for="router-nas_client_id">Linked RADIUS NAS client</label><select id="router-nas_client_id" name="nas_client_id"><option value="">Not linked</option>${allNas.map((nas) => `<option value="${esc(idOf(nas))}" data-site="${esc(nas.site_id || '')}">${esc(nas.name)} · ${esc(nas.ip_address)}</option>`).join('')}</select></div><div class="field"><label for="router-api_type">RouterOS API</label><select id="router-api_type" name="api_type"><option value="legacy">RouterOS 6 legacy API</option><option value="rest">RouterOS REST API</option></select></div>${field('port','API port','number',router?.port || 8728, 'min="1" max="65535" required')}${field('username','API username','text',router?.username || '', 'required autocomplete="off"')}${!editing ? field('password','API password','password','', 'required autocomplete="new-password"') : ''}${field('radius_server_ip','RADIUS server address','text',router?.radius_server_ip || '')}${!editing ? field('radius_secret','RADIUS shared secret (optional)','password','', 'autocomplete="new-password"') : ''}${field('model_name','Model','text',router?.model_name || '')}${field('hotspot_interface','HotSpot interface','text',router?.hotspot_interface || '')}${field('pppoe_server_interface','PPPoE interface','text',router?.pppoe_server_interface || '')}${field('wan_interface','WAN interface','text',router?.wan_interface || '')}${field('lan_interface','LAN interface','text',router?.lan_interface || '')}${field('location','Location','text',router?.location || '')}${editing ? `<div class="field"><label for="router-status">Status</label><select id="router-status" name="status"><option value="unknown">Unknown</option><option value="online">Online</option><option value="offline">Offline</option><option value="disabled">Disabled</option></select></div>` : ''}<div class="field"><label><span>Transport options</span><span><input type="checkbox" name="use_ssl" ${router?.use_ssl ? 'checked' : ''}> Use SSL</span></label></div><div class="field"><label><span>Verify TLS certificate</span><span><input type="checkbox" name="ssl_verify" ${router?.ssl_verify ? 'checked' : ''}> Verify certificate</span></label></div><div class="field" style="grid-column:1/-1"><label for="router-notes">Notes</label><textarea id="router-notes" name="notes">${esc(router?.notes || '')}</textarea></div></div><div class="notice" id="router-error" hidden role="alert"></div><p class="muted-small">Router passwords and shared secrets are write-only here; the API does not return them to the browser.</p><button class="btn btn-primary" type="submit">${editing ? 'Save router' : 'Register router'}</button></form>`;
    dialog.host.querySelector('.modal-body').innerHTML = formMarkup;
    const siteField = $('#router-site_id', dialog.host); const nasField = $('#router-nas_client_id', dialog.host);
    siteField.value = router?.site_id || '';
    nasField.value = router?.nas_client_id || '';
    $('#router-api_type', dialog.host).value = router?.api_type || 'legacy';
    if (editing) $('#router-status', dialog.host).value = router.status || 'unknown';
    const filterNas = () => {
      const siteId = siteField.value;
      for (const option of nasField.options) {
        if (!option.value) continue;
        option.hidden = Boolean(siteId && option.dataset.site !== siteId);
        if (option.hidden && option.selected) nasField.value = '';
      }
    };
    siteField.addEventListener('change', filterNas); filterNas();
    $('#router-form', dialog.host).addEventListener('submit', async (event) => {
      event.preventDefault(); const form = new FormData(event.currentTarget);
      const body = {
        name: String(form.get('name')).trim(), ip_address: String(form.get('ip_address')).trim(),
        site_id: form.get('site_id') || null, nas_client_id: form.get('nas_client_id') || null,
        api_type: form.get('api_type'), port: Number(form.get('port')), username: String(form.get('username')).trim(),
        use_ssl: form.has('use_ssl'), ssl_verify: form.has('ssl_verify'), model_name: form.get('model_name') || null,
        hotspot_interface: form.get('hotspot_interface') || null, pppoe_server_interface: form.get('pppoe_server_interface') || null,
        wan_interface: form.get('wan_interface') || null, lan_interface: form.get('lan_interface') || null,
        radius_server_ip: form.get('radius_server_ip') || null, location: form.get('location') || null, notes: form.get('notes') || null,
      };
      if (!editing) { body.password = String(form.get('password')); body.radius_secret = form.get('radius_secret') || null; }
      else { body.status = form.get('status'); }
      try {
        const id = editing ? idOf(router) : null;
        await (editing ? api.patch(`${API.routers}/${encodeURIComponent(id)}`, body) : api.post(API.routers, body));
        dialog.close(); toast(editing ? 'Router configuration updated' : 'Router registered'); await load();
      } catch (error) { const box = $('#router-error', dialog.host); box.hidden = false; box.textContent = error.message; }
    });
  } catch (error) {
    dialog.host.querySelector('.modal-body').innerHTML = `<div class="error-state" role="alert">${esc(error.message)}<p>Site and RADIUS assignments require permission to read both resources.</p></div>`;
  }
}

$('#refresh-routers').addEventListener('click', load);
$('#add-router')?.addEventListener('click', () => openForm(null));
$('#router-site-filter').addEventListener('change', () => { page = 1; load(); });
$('#router-search').addEventListener('input', draw);
$('#router-prev').addEventListener('click', () => { if (page > 1) { page -= 1; load(); } });
$('#router-next').addEventListener('click', () => { if (rows.length === 20) { page += 1; load(); } });
await loadSites();
await load();
