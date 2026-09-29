Pages.usage = async function (root) {
  root.innerHTML = `<div class="center-loading"><div class="spinner"></div></div>`;
  const res = await Api.get('/api/v1/portal/usage', { days: 30 });
  const u = res.data;

  const maxDay = Math.max(1, ...u.daily.map(d => d.input_bytes + d.output_bytes));

  root.innerHTML = `
    <div class="stat-grid">
      <div class="stat-box"><div class="label">Downloaded</div><div class="value">${(u.totals.input_mb/1024).toFixed(2)} GB</div></div>
      <div class="stat-box"><div class="label">Uploaded</div><div class="value">${(u.totals.output_mb/1024).toFixed(2)} GB</div></div>
      <div class="stat-box"><div class="label">Status</div><div class="value" style="font-size:14px;">${u.currently_online ? statusBadge('online') : statusBadge('offline')}</div></div>
    </div>

    <div class="card">
      <div class="card-head"><h2>Last 30 days</h2></div>
      ${u.daily.length ? `
        <div style="display:flex;align-items:flex-end;gap:4px;height:120px;">
          ${u.daily.map(d => {
            const total = d.input_bytes + d.output_bytes;
            const pct = Math.max(4, (total / maxDay) * 100);
            return `<div style="flex:1;background:var(--signal);border-radius:3px 3px 0 0;height:${pct}%;" title="${d.date}: ${(total/(1024*1024)).toFixed(0)} MB"></div>`;
          }).join('')}
        </div>
        <div style="display:flex;justify-content:space-between;font-size:11px;color:var(--muted);margin-top:8px;">
          <span>${u.daily[0]?.date.slice(5) || ''}</span><span>${u.daily[u.daily.length-1]?.date.slice(5) || ''}</span>
        </div>` : `<div class="empty-state">${Icons.usage}<div>No usage recorded in this period yet.</div></div>`}
    </div>`;
};
