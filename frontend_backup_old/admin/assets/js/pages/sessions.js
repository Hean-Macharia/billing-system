Pages.sessions = async function (root) {
  const state = { page: 1, limit: 25, nas_ip: '' };

  root.innerHTML = `
    <div class="panel">
      <div class="panel-head">
        <div class="panel-toolbar">
          <div class="search-box">${Icons.search}<input type="search" id="sess-nas" placeholder="Filter by NAS IP…"/></div>
        </div>
        <button class="btn btn-ghost btn-sm" id="sess-refresh">${Icons.refresh} Refresh</button>
      </div>
      <div id="sess-table-wrap"></div>
      <div id="sess-pager-wrap"></div>
    </div>`;

  async function load() {
    const wrap = root.querySelector('#sess-table-wrap');
    wrap.innerHTML = '<div class="center-loading"><div class="spinner dark"></div></div>';
    const res = await Api.get('/api/v1/radius/sessions', { page: state.page, limit: state.limit, nas_ip: state.nas_ip || undefined });
    const rows = res.data;
    wrap.innerHTML = renderTable({
      emptyTitle: 'No sessions online right now',
      emptyBody: 'Sessions appear here the moment a PPPoE or HotSpot user authenticates via RADIUS.',
      columns: [
        { label: 'User', render: s => `<div class="row-title mono">${escapeHtml(s.username || s.user_name || '—')}</div><div class="row-sub mono">${escapeHtml(s.framed_ip_address || s.ip_address || '')}</div>` },
        { label: 'NAS', render: s => escapeHtml(s.nas_ip_address || s.nas_ip || '—') },
        { label: 'MAC', render: s => escapeHtml(s.calling_station_id || '—') },
        { label: 'Started', render: s => fmtDateTime(s.start_time || s.acct_start_time) },
        { label: 'Data used', num: true, render: s => {
          const inB = s.input_octets || s.acct_input_octets || 0, outB = s.output_octets || s.acct_output_octets || 0;
          const mb = (Number(inB) + Number(outB)) / (1024 * 1024);
          return mb ? mb.toFixed(1) + ' MB' : '—';
        } },
        { label: '', render: s => `<div class="row-actions"><button class="btn btn-danger btn-sm" data-act="terminate" data-id="${s.acct_session_id || s._id}">${Icons.ban} Disconnect</button></div>` },
      ],
      rows,
    });
    wrap.querySelectorAll('[data-act=terminate]').forEach(b => b.onclick = () => doTerminate(b.dataset.id));

    const pagerWrap = root.querySelector('#sess-pager-wrap');
    pagerWrap.innerHTML = '';
    pagerWrap.appendChild(renderPager({ page: state.page, limit: state.limit, total: res.meta.total }, (p) => { state.page = p; load(); }));
  }

  async function doTerminate(sessionId) {
    const ok = await confirmDialog({ title: 'Disconnect this session?', body: 'The user will be dropped from the network and will need to reconnect.', confirmLabel: 'Disconnect', danger: true });
    if (!ok) return;
    try {
      const res = await Api.post(`/api/v1/radius/sessions/${sessionId}/terminate`);
      toast(res.data.disconnected ? 'Session disconnected' : 'Session not found', res.data.disconnected ? 'success' : 'error');
      load();
    } catch (e) { toastError(e); }
  }

  root.querySelector('#sess-refresh').onclick = load;
  let t;
  root.querySelector('#sess-nas').addEventListener('input', (e) => {
    clearTimeout(t);
    t = setTimeout(() => { state.nas_ip = e.target.value; state.page = 1; load(); }, 350);
  });

  load();
};
