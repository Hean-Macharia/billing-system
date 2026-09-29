Pages.subscription = async function (root) {
  const res = await Api.get('/api/v1/portal/subscriptions');
  const subs = res.data;
  const active = subs.find(s => s.status === 'active');

  root.innerHTML = `
    ${active ? `
      <div class="card">
        <div class="card-head"><h2>${escapeHtml(active.plan_name || 'Your plan')}</h2>${statusBadge(active.status)}</div>
        <div class="stat-grid">
          <div class="stat-box"><div class="label">Download</div><div class="value">${active.plan_download_speed_mbps || '—'} Mbps</div></div>
          <div class="stat-box"><div class="label">Upload</div><div class="value">${active.plan_upload_speed_mbps || '—'} Mbps</div></div>
          <div class="stat-box"><div class="label">Monthly price</div><div class="value">${fmtMoney(active.monthly_price_kes)}</div></div>
        </div>
        <div class="divider"></div>
        <div style="font-size:13px;color:var(--muted);">Next billing date: <b style="color:var(--text);">${fmtDate(active.next_billing_date)}</b></div>
      </div>` : `
      <div class="card"><div class="empty-state">${Icons.subscription}<div class="big">No active subscription</div><div>Contact support if you believe this is an error.</div></div></div>`}

    <div class="card card-flush">
      <div class="card-head" style="padding:16px 18px 0;"><h2>Subscription history</h2></div>
      ${renderList({
        rows: subs, emptyTitle: 'No subscriptions on file',
        renderRow: s => `
          <div class="list-row">
            <div class="main">
              <div class="title">${escapeHtml(s.plan_name || 'Plan')}</div>
              <div class="sub">Since ${fmtDate(s.created_at || s.start_date)}</div>
            </div>
            <div class="right">${statusBadge(s.status)}</div>
          </div>`,
      })}
    </div>`;
};
