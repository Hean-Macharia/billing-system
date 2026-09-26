Pages.routers = async function (root) {
  const state = { page: 1, limit: 20 };

  root.innerHTML = `
    <div class="panel">
      <div class="panel-head">
        <div class="panel-toolbar">
          <button class="btn btn-ghost btn-sm" id="r-refresh-all">${Icons.refresh} Refresh all health</button>
        </div>
        <button class="btn btn-primary" id="r-new">${Icons.plus} Register router</button>
      </div>
      <div id="r-table-wrap"></div>
      <div id="r-pager-wrap"></div>
    </div>`;

  async function load() {
    const wrap = root.querySelector('#r-table-wrap');
    wrap.innerHTML = '<div class="center-loading"><div class="spinner dark"></div></div>';
    const res = await Api.get('/api/v1/routers', { page: state.page, limit: state.limit });
    const rows = res.data;
    wrap.innerHTML = renderTable({
      emptyTitle: 'No routers registered yet',
      emptyBody: 'Register a MikroTik router to monitor it and manage PPPoE/HotSpot from here.',
      columns: [
        { label: 'Router', render: r => `<div class="row-title">${escapeHtml(r.name)}</div><div class="row-sub mono">${escapeHtml(r.ip_address)}:${r.port}</div>` },
        { label: 'API', render: r => `<span class="badge badge-muted">${r.api_type === 'legacy' ? 'RouterOS 6 (legacy)' : 'RouterOS 7 (REST)'}</span>` },
        { label: 'Model', render: r => escapeHtml(r.model_name || '—') },
        { label: 'Status', render: r => statusBadge(r.status) },
        { label: 'Last checked', render: r => r.last_checked_at ? timeAgo(r.last_checked_at) : 'never' },
        { label: '', render: r => `
          <div class="row-actions">
            <button class="btn btn-ghost btn-sm" data-act="view" data-id="${r._id}">Details</button>
            <button class="btn btn-ghost btn-sm" data-act="edit" data-id="${r._id}">${Icons.edit}</button>
            <button class="btn btn-danger btn-sm" data-act="delete" data-id="${r._id}">${Icons.trash}</button>
          </div>` },
      ],
      rows,
    });
    wrap.querySelectorAll('[data-act=view]').forEach(b => b.onclick = () => viewRouter(rows.find(r => r._id === b.dataset.id)));
    wrap.querySelectorAll('[data-act=edit]').forEach(b => b.onclick = () => openForm(rows.find(r => r._id === b.dataset.id)));
    wrap.querySelectorAll('[data-act=delete]').forEach(b => b.onclick = () => doDelete(b.dataset.id));

    const pagerWrap = root.querySelector('#r-pager-wrap');
    pagerWrap.innerHTML = '';
    pagerWrap.appendChild(renderPager({ page: state.page, limit: state.limit, total: res.meta.total }, (p) => { state.page = p; load(); }));
  }

  async function doDelete(id) {
    const ok = await confirmDialog({ title: 'Delete this router?', body: 'This removes it from the console — it does not touch the physical device.', confirmLabel: 'Delete', danger: true });
    if (!ok) return;
    try { await Api.delete(`/api/v1/routers/${id}`); toast('Router deleted', 'success'); load(); }
    catch (e) { toastError(e); }
  }

  async function viewRouter(router) {
    const bodyHtml = `
      <div class="tabs" style="margin-bottom:14px;">
        <div class="tab active" data-rtab="health">Health</div>
        <div class="tab" data-rtab="sessions">Active sessions</div>
        <div class="tab" data-rtab="interfaces">Interfaces</div>
        <div class="tab" data-rtab="dhcp">DHCP leases</div>
        <div class="tab" data-rtab="queues">Queues</div>
      </div>
      <div id="rd-pane"><div class="center-loading"><div class="spinner dark"></div></div></div>`;
    const { overlay } = openDrawer({
      title: router.name, wide: true, bodyHtml,
      footerHtml: `<button class="btn btn-ghost" data-act="test">${Icons.bolt} Test connectivity</button><button class="btn btn-primary" data-act="health">${Icons.refresh} Refresh health</button>`,
    });

    overlay.querySelector('[data-act=test]').onclick = async (e) => {
      e.target.disabled = true;
      try {
        const res = await Api.post(`/api/v1/routers/${router._id}/test`);
        toast(res.data.reachable ? 'Router is reachable' : 'Router did not respond', res.data.reachable ? 'success' : 'error');
      } catch (err) { toastError(err); }
      finally { e.target.disabled = false; }
    };
    overlay.querySelector('[data-act=health]').onclick = async (e) => {
      e.target.disabled = true;
      try { await Api.post(`/api/v1/routers/${router._id}/health`); toast('Health refreshed', 'success'); loadPane('health'); }
      catch (err) { toastError(err); }
      finally { e.target.disabled = false; }
    };

    async function loadPane(tab) {
      const pane = overlay.querySelector('#rd-pane');
      pane.innerHTML = '<div class="center-loading"><div class="spinner dark"></div></div>';
      try {
        if (tab === 'health') {
          const res = await Api.get(`/api/v1/routers/${router._id}/health`);
          const h = res.data.health;
          if (!h) { pane.innerHTML = '<div class="table-empty">No health data yet — click "Refresh health".</div>'; return; }
          pane.innerHTML = `
            <div class="stat-row" style="grid-template-columns:repeat(3,1fr);">
              ${statCard({ label: 'Reachable', value: h.reachable ? 'Yes' : 'No', accent: h.reachable ? 'good' : 'bad' })}
              ${statCard({ label: 'CPU load', value: h.cpu_load_percent !== undefined ? h.cpu_load_percent + '%' : '—' })}
              ${statCard({ label: 'Uptime', value: h.uptime_seconds ? Math.floor(h.uptime_seconds / 86400) + 'd' : '—' })}
            </div>
            <div class="field-hint">Board: ${escapeHtml(h.board_name || '—')} · RouterOS ${escapeHtml(h.version || '—')} · Checked ${timeAgo(res.data.last_checked_at)}</div>`;
        } else if (tab === 'sessions') {
          const res = await Api.get(`/api/v1/routers/${router._id}/active-users`);
          const pppoe = res.data.pppoe || [], hotspot = res.data.hotspot || [];
          pane.innerHTML = `
            <div class="stat-label" style="margin-bottom:8px;">PPPoE (${pppoe.length})</div>
            ${renderTable({ columns: [{ label: 'User', render: s => escapeHtml(s.username) }, { label: 'Address', render: s => escapeHtml(s.address || '—') }, { label: 'Uptime', render: s => s.uptime_seconds ? Math.floor(s.uptime_seconds / 60) + 'm' : '—' }], rows: pppoe, emptyTitle: 'No active PPPoE sessions' })}
            <div class="divider"></div>
            <div class="stat-label" style="margin-bottom:8px;">HotSpot (${hotspot.length})</div>
            ${renderTable({ columns: [{ label: 'User', render: s => escapeHtml(s.user) }, { label: 'MAC', render: s => escapeHtml(s.mac_address || '—') }, { label: 'Uptime', render: s => s.uptime_seconds ? Math.floor(s.uptime_seconds / 60) + 'm' : '—' }], rows: hotspot, emptyTitle: 'No active HotSpot sessions' })}`;
        } else if (tab === 'interfaces') {
          const res = await Api.get(`/api/v1/routers/${router._id}/interfaces`);
          pane.innerHTML = renderTable({
            columns: [{ label: 'Name', render: i => escapeHtml(i.name) }, { label: 'Type', render: i => escapeHtml(i.type || '—') }, { label: 'Running', render: i => i.running ? statusBadge('active') : statusBadge('inactive') }],
            rows: res.data, emptyTitle: 'No interfaces returned',
          });
        } else if (tab === 'dhcp') {
          const res = await Api.get(`/api/v1/routers/${router._id}/dhcp-leases`);
          pane.innerHTML = renderTable({
            columns: [{ label: 'Address', render: l => escapeHtml(l.address) }, { label: 'MAC', render: l => escapeHtml(l.mac_address || '—') }, { label: 'Hostname', render: l => escapeHtml(l.hostname || '—') }],
            rows: res.data, emptyTitle: 'No DHCP leases returned',
          });
        } else if (tab === 'queues') {
          const res = await Api.get(`/api/v1/routers/${router._id}/queues`);
          pane.innerHTML = renderTable({
            columns: [{ label: 'Name', render: q => escapeHtml(q.name) }, { label: 'Upload limit', render: q => escapeHtml(q.max_limit_upload || '—') }, { label: 'Download limit', render: q => escapeHtml(q.max_limit_download || '—') }],
            rows: res.data, emptyTitle: 'No queues returned',
          });
        }
      } catch (err) {
        pane.innerHTML = `<div class="table-empty"><div class="big">Couldn't reach the router</div><div>${escapeHtml(err.message)}</div></div>`;
      }
    }

    overlay.querySelectorAll('[data-rtab]').forEach(t => t.onclick = () => {
      overlay.querySelectorAll('[data-rtab]').forEach(x => x.classList.remove('active'));
      t.classList.add('active');
      loadPane(t.dataset.rtab);
    });
    loadPane('health');
  }

  function openForm(existing) {
    const isEdit = !!existing;
    const bodyHtml = `
      <form id="rt-form">
        ${Field.text('name', 'Router name', existing?.name || '', { required: true })}
        ${Field.row2(
          Field.text('ip_address', 'Management IP', existing?.ip_address || '', { required: true }),
          Field.select('api_type', 'API type', [{ value: 'legacy', label: 'RouterOS 6.x (legacy API)' }, { value: 'rest', label: 'RouterOS 7+ (REST API)' }], existing?.api_type || 'legacy')
        )}
        ${Field.row2(
          Field.text('username', 'Username', existing?.username || '', { required: !isEdit }),
          Field.text('password', 'Password', '', { type: 'password', required: !isEdit, hint: isEdit ? 'Leave blank to keep the current password' : undefined })
        )}
        ${Field.row2(
          Field.text('port', 'Port (blank = auto)', existing?.port || '', { type: 'number' }),
          Field.text('model_name', 'Model', existing?.model_name || '', { placeholder: 'e.g. RB951Ui-2HnD' })
        )}
        ${Field.checkbox('use_ssl', 'Use SSL/HTTPS', existing?.use_ssl || false)}
        <div class="divider"></div>
        ${Field.row2(
          Field.text('wan_interface', 'WAN interface', existing?.wan_interface || ''),
          Field.text('lan_interface', 'LAN interface', existing?.lan_interface || '')
        )}
        ${Field.row2(
          Field.text('pppoe_server_interface', 'PPPoE interface', existing?.pppoe_server_interface || ''),
          Field.text('hotspot_interface', 'HotSpot interface', existing?.hotspot_interface || '')
        )}
        ${Field.text('location', 'Physical location', existing?.location || '')}
        ${Field.textarea('notes', 'Notes', existing?.notes || '')}
      </form>`;

    const { close, overlay } = openDrawer({
      title: isEdit ? `Edit ${existing.name}` : 'Register router', wide: true, bodyHtml,
      footerHtml: `<button class="btn btn-ghost" data-act="cancel">Cancel</button><button class="btn btn-primary" data-act="save">${isEdit ? 'Save changes' : 'Register router'}</button>`,
    });
    overlay.querySelector('[data-act=cancel]').onclick = close;
    overlay.querySelector('[data-act=save]').onclick = async () => {
      const form = overlay.querySelector('#rt-form');
      if (!form.reportValidity()) return;
      const raw = formToObject(form);
      const btn = overlay.querySelector('[data-act=save]');
      btn.disabled = true;
      try {
        const payload = {
          name: raw.name, ip_address: raw.ip_address, api_type: raw.api_type,
          port: raw.port ? Number(raw.port) : undefined, model_name: raw.model_name || undefined,
          use_ssl: !!raw.use_ssl, wan_interface: raw.wan_interface || undefined, lan_interface: raw.lan_interface || undefined,
          pppoe_server_interface: raw.pppoe_server_interface || undefined, hotspot_interface: raw.hotspot_interface || undefined,
          location: raw.location || undefined, notes: raw.notes || undefined,
        };
        if (raw.username) payload.username = raw.username;
        if (raw.password) payload.password = raw.password;
        if (isEdit) {
          await Api.patch(`/api/v1/routers/${existing._id}`, payload);
          toast('Router updated', 'success');
        } else {
          await Api.post('/api/v1/routers', payload);
          toast('Router registered', 'success');
        }
        close(); load();
      } catch (e) { toastError(e); }
      finally { btn.disabled = false; }
    };
  }

  root.querySelector('#r-new').onclick = () => openForm(null);
  root.querySelector('#r-refresh-all').onclick = async (e) => {
    e.target.disabled = true;
    try { const res = await Api.post('/api/v1/routers/health/refresh-all'); toast(`Checked ${res.data.checked}, ${res.data.online} online`, 'success'); load(); }
    catch (err) { toastError(err); }
    finally { e.target.disabled = false; }
  };

  load();
};
