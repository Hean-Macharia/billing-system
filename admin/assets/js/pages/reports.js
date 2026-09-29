/*
  There's no dedicated /api/v1/reports backend module in this codebase
  yet (despite reports.read/reports.create permissions existing on
  users) - only /api/v1/dashboard/summary and /api/v1/invoices/overdue.
  This page composes those plus a recent-payments sample into something
  genuinely useful rather than fabricating data. A proper reports
  service (revenue-by-date-range, customer growth, churn) would be a
  natural next backend addition.
*/
Pages.reports = async function (root) {
  root.innerHTML = `<div class="center-loading"><div class="spinner dark"></div></div>`;

  const [summaryRes, overdueRes, paymentsRes] = await Promise.all([
    Api.get('/api/v1/dashboard/summary'),
    Api.get('/api/v1/invoices/overdue'),
    Api.get('/api/v1/payments', { limit: 200, status: 'completed' }),
  ]);
  const d = summaryRes.data;
  const overdue = overdueRes.data;
  const payments = paymentsRes.data;

  const overdueTotal = overdue.reduce((s, i) => s + (i.balance_due_kes || 0), 0);

  const byMethod = {};
  payments.forEach(p => { byMethod[p.payment_method] = (byMethod[p.payment_method] || 0) + p.amount_kes; });

  const byDay = {};
  payments.forEach(p => {
    const day = (p.payment_date || p.created_at || '').slice(0, 10);
    if (day) byDay[day] = (byDay[day] || 0) + p.amount_kes;
  });
  const days = Object.keys(byDay).sort().slice(-14);

  root.innerHTML = `
    <div class="stat-row">
      ${statCard({ label: 'Revenue this month', value: fmtMoney(d.revenue.this_month_kes), accent: 'good' })}
      ${statCard({ label: 'Revenue (30 days)', value: fmtMoney(d.revenue.last_30_days_kes), accent: 'signal' })}
      ${statCard({ label: 'Overdue balance', value: fmtMoney(overdueTotal), sub: `${overdue.length} invoice(s)`, accent: overdueTotal > 0 ? 'bad' : 'good' })}
      ${statCard({ label: 'Payments sampled', value: fmtNum(payments.length), sub: 'most recent completed', accent: 'amber' })}
    </div>

    <div class="stat-row" style="grid-template-columns: 2fr 1fr;">
      <div class="panel">
        <div class="panel-head"><h2>Payments by day (last 14 active days)</h2></div>
        <div class="panel-body"><canvas id="rep-chart" height="90"></canvas></div>
      </div>
      <div class="panel">
        <div class="panel-head"><h2>By payment method</h2></div>
        <div class="panel-body" style="display:flex;flex-direction:column;gap:10px;">
          ${Object.entries(byMethod).sort((a, b) => b[1] - a[1]).map(([method, amt]) => `
            <div>
              <div style="display:flex;justify-content:space-between;font-size:12.5px;margin-bottom:4px;">
                <span style="text-transform:capitalize;color:#3C4A6B;">${escapeHtml(method)}</span>
                <span class="mono">${fmtMoney(amt)}</span>
              </div>
              <div style="height:6px;background:#EEF1F8;border-radius:100px;overflow:hidden;">
                <div style="height:100%;width:${Math.max(4, (amt / Math.max(...Object.values(byMethod))) * 100)}%;background:#2DD4BF;border-radius:100px;"></div>
              </div>
            </div>`).join('') || '<div style="color:#8792AC;font-size:13px;">No completed payments in the recent sample.</div>'}
        </div>
      </div>
    </div>

    <div class="panel">
      <div class="panel-head"><h2>Overdue invoices</h2></div>
      ${renderTable({
        emptyTitle: 'Nothing overdue',
        emptyBody: 'Every invoice is within its due date.',
        columns: [
          { label: 'Invoice', render: r => `<div class="row-title mono">${escapeHtml(r.invoice_number)}</div><div class="row-sub">${escapeHtml(r.customer_name || r.customer_id)}</div>` },
          { label: 'Due date', render: r => fmtDate(r.due_date) },
          { label: 'Balance due', num: true, render: r => fmtMoney(r.balance_due_kes) },
        ],
        rows: overdue,
      })}
    </div>`;

  if (days.length && window.Chart) {
    const ctx = document.getElementById('rep-chart').getContext('2d');
    new Chart(ctx, {
      type: 'bar',
      data: {
        labels: days.map(d2 => d2.slice(5)),
        datasets: [{ label: 'Revenue (KES)', data: days.map(d2 => byDay[d2]), backgroundColor: '#2DD4BF', borderRadius: 4 }],
      },
      options: {
        plugins: { legend: { display: false } },
        scales: { y: { beginAtZero: true, ticks: { callback: (v) => v.toLocaleString() } } },
      },
    });
  } else if (!days.length) {
    document.getElementById('rep-chart')?.closest('.panel-body').insertAdjacentHTML('beforeend', '<div style="color:#8792AC;font-size:13px;">No payment activity in the recent sample to chart.</div>');
  }
};
