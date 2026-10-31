import { API } from './api.config.js';
import { api } from './api.js';
import { mountShell } from './app-shell.js';
import { $, esc, formatDate, statusBadge, toast, empty, modal } from './ui.js';

const user = await mountShell('staff');
const canCreate = ['admin', 'super_admin'].includes(user?.role);
const canChangeStatus = ['admin', 'super_admin'].includes(user?.role);
const root = $('#main-content');
const roles = ['super_admin', 'admin', 'billing_manager', 'network_admin', 'technician', 'sales_agent', 'support_agent', 'reseller'];
root.innerHTML = `<section class="page-head"><div><h2>Staff access</h2><p>Manage staff identities and account status through the permission-protected API.</p></div><div class="page-actions"><button class="btn" id="refresh-staff">Refresh</button>${canCreate ? '<button class="btn btn-primary" id="new-staff">Create staff account</button>' : ''}</div></section><section class="panel"><div class="table-tools"><input class="search-input" id="staff-search" type="search" placeholder="Search staff" aria-label="Search staff"><select class="search-input" id="staff-role" aria-label="Filter role"><option value="">All roles (first page)</option>${roles.map((role) => `<option value="${role}">${role.replaceAll('_', ' ')}</option>`).join('')}</select><select class="search-input" id="staff-status" aria-label="Filter status"><option value="">All statuses</option><option value="active">Active</option><option value="inactive">Inactive</option><option value="suspended">Suspended</option><option value="pending">Pending</option></select><span class="muted-small" id="staff-count"></span></div><div id="staff-list"></div></section><p class="muted-small" style="margin-top:12px">Role assignment and activation are validated by FastAPI. This screen cannot edit permissions directly or reset passwords.</p>`;

let users = [];
let page = 1;
async function load() {
  $('#staff-list').innerHTML = '<div class="panel-body"><div class="skeleton"></div><div class="skeleton" style="margin-top:12px"></div></div>';
  try {
    const params = { page, limit: 50, role: $('#staff-role').value || undefined, status: $('#staff-status').value || undefined, search: $('#staff-search').value.trim() || undefined };
    const response = await api.get(API.users, params);
    users = api.rows(response).filter((user) => user.role !== 'customer');
    $('#staff-count').textContent = `Showing ${users.length} staff account${users.length === 1 ? '' : 's'} · page ${page}`;
    draw(response?.meta?.total ?? response?.total ?? users.length);
  } catch (error) { $('#staff-list').innerHTML = `<div class="error-state" role="alert">${esc(error.message)}</div>`; }
}
function draw(total) {
  $('#staff-list').innerHTML = users.length ? `<div class="table-wrap"><table class="data-table"><thead><tr><th>Staff member</th><th>Username</th><th>Role</th><th>Status</th><th>Last sign-in</th><th>Created</th>${canChangeStatus ? '<th>Action</th>' : ''}</tr></thead><tbody>${users.map((user) => `<tr><td><strong>${esc(user.full_name)}</strong><br><span class="muted-small">${esc(user.email)}</span></td><td>${esc(user.username)}</td><td>${esc(String(user.role).replaceAll('_', ' '))}</td><td>${statusBadge(user.status)}</td><td>${formatDate(user.last_login)}</td><td>${formatDate(user.created_at)}</td>${canChangeStatus ? `<td><button class="btn btn-quiet" data-toggle-user="${esc(user._id || user.id)}" data-next="${user.status === 'active' ? 'inactive' : 'active'}">${user.status === 'active' ? 'Deactivate' : 'Activate'}</button></td>` : ''}</tr>`).join('')}</tbody></table></div>` : empty('No staff accounts match these filters');
  $('#staff-list').querySelectorAll('[data-toggle-user]').forEach((button) => button.addEventListener('click', async () => {
    const user = users.find((item) => String(item._id || item.id) === button.dataset.toggleUser);
    if (!user || !confirm(`${button.dataset.next === 'active' ? 'Activate' : 'Deactivate'} ${user.full_name}?`)) return;
    try { await api.request(`${API.users}/${encodeURIComponent(button.dataset.toggleUser)}/status`, { method: 'PATCH', params: { status: button.dataset.next } }); toast(`Staff status set to ${button.dataset.next}`); await load(); }
    catch (error) { toast(error.message, 'error'); }
  }));
  const previous = $('#staff-pagination');
  if (previous) previous.remove();
  const pagination = document.createElement('div'); pagination.id = 'staff-pagination'; pagination.className = 'table-tools';
  pagination.innerHTML = `<span class="muted-small">${total} matching accounts</span><div style="margin-left:auto;display:flex;gap:8px"><button class="btn" id="staff-prev" ${page <= 1 ? 'disabled' : ''}>Previous</button><button class="btn" id="staff-next" ${users.length < 50 ? 'disabled' : ''}>Next</button></div>`;
  $('#staff-list').append(pagination);
  $('#staff-prev').onclick = () => { if (page > 1) { page -= 1; load(); } };
  $('#staff-next').onclick = () => { if (users.length === 50) { page += 1; load(); } };
}
function openCreate() {
  const body = `<form id="staff-form"><div class="grid-2"><div class="field"><label for="staff-name">Full name</label><input id="staff-name" name="full_name" maxlength="100" required></div><div class="field"><label for="staff-email">Email</label><input id="staff-email" name="email" type="email" autocomplete="email" required></div><div class="field"><label for="staff-username">Username</label><input id="staff-username" name="username" minlength="3" maxlength="50" autocomplete="username" required></div><div class="field"><label for="staff-phone">Phone</label><input id="staff-phone" name="phone" inputmode="tel"></div><div class="field"><label for="staff-role-field">Role</label><select id="staff-role-field" name="role" required>${roles.filter((role) => role !== 'super_admin').map((role) => `<option value="${role}">${role.replaceAll('_', ' ')}</option>`).join('')}</select></div><div class="field"><label for="staff-password">Initial password</label><input id="staff-password" name="password" type="password" minlength="8" autocomplete="new-password" required><small class="muted-small">Use at least 8 characters with uppercase, lowercase and a number.</small></div></div><div class="notice" id="staff-form-error" hidden role="alert"></div><button class="btn btn-primary" type="submit">Create account</button></form>`;
  const dialog = modal('Create staff account', body);
  $('#staff-form', dialog.host).addEventListener('submit', async (event) => {
    event.preventDefault(); const fields = Object.fromEntries(new FormData(event.currentTarget));
    if (!/[A-Z]/.test(fields.password) || !/[a-z]/.test(fields.password) || !/[0-9]/.test(fields.password)) {
      const error = $('#staff-form-error', dialog.host); error.hidden = false; error.textContent = 'Password must include an uppercase letter, lowercase letter and number.'; return;
    }
    fields.phone ||= null;
    try { await api.post(API.auth.register, fields); dialog.close(); toast('Staff account created'); page = 1; await load(); }
    catch (error) { const box = $('#staff-form-error', dialog.host); box.hidden = false; box.textContent = error.message; }
  });
}
$('#new-staff')?.addEventListener('click', openCreate);
$('#refresh-staff').addEventListener('click', load);
$('#staff-role').addEventListener('change', () => { page = 1; load(); });
$('#staff-status').addEventListener('change', () => { page = 1; load(); });
$('#staff-search').addEventListener('input', () => { clearTimeout(window.staffSearchTimer); window.staffSearchTimer = setTimeout(() => { page = 1; load(); }, 250); });
await load();
