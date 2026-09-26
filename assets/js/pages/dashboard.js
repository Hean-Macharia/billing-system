Pages.dashboard = async function (root) {
  const res = await Api.get('/api/v1/dashboard/summary');
  const d = res.data;

  const routerPct = d.routers.total ? Math.round((d.routers.online / d.routers.total) * 100) : 0;

  root.innerHTML = `
    <div class="stat-row">
      ${statCard({ label: 'Active customers', value: fmtNum(d.customers.active), sub: `${fmtNum(d.customers.total)} total on record`, accent: 'signal' })}
      ${statCard({ label: 'Active subscriptions', value: fmtNum(d.subscriptions_active), sub: `${fmtNum(d.service_plans_active)} service plans live`, accent: 'signal' })}
      ${statCard({ label: 'Revenue this month', value: fmtMoney(d.revenue.this_month_kes), sub: `${fmtMoney(d.revenue.last_30_days_kes)} in the last 30 days`, accent: 'good' })}
      ${statCard({ label: 'Unpaid invoices', value: fmtNum(d.invoices.unpaid), sub: `${fmtNum(d.invoices.overdue)} overdue`, accent: d.invoices.overdue > 0 ? 'bad' : 'amber' })}
    </div>

    <div class="stat-row" style="grid-template-columns: 2fr 1fr;">
      <div class="panel">
        <div class="panel-head"><h2>Network status</h2></div>
        <div class="panel-body">
          <div style="display:flex;align-items:center;gap:20px;flex-wrap:wrap;">
            <div style="flex:1;min-width:200px;">
              <div style="display:flex;justify-content:space-between;font-size:12.5px;color:#5A6B8C;margin-bottom:6px;">
                <span>Routers online</span><span class="mono">${d.routers.online} / ${d.routers.total}</span>
              </div>
              <div style="height:8px;background:#EEF1F8;border-radius:100px;overflow:hidden;">
                <div style="height:100%;width:${routerPct}%;background:${routerPct > 70 ? '#34C77A' : routerPct > 30 ? '#F2A93B' : '#F1616B'};border-radius:100px;"></div>
              </div>
            </div>
            <a href="#/routers" class="btn btn-ghost btn-sm">Manage routers</a>
          </div>
          <div class="divider"></div>
          <div style="display:flex;gap:28px;flex-wrap:wrap;">
            <div>
              <div class="stat-label">Sessions online now</div>
              <div class="stat-value" style="font-size:22px;">${fmtNum(d.sessions_online)}</div>
            </div>
            <div>
              <div class="stat-label">Active vouchers</div>
              <div class="stat-value" style="font-size:22px;">${fmtNum(d.vouchers_active)}</div>
            </div>
            <div>
              <div class="stat-label">Payments (30d)</div>
              <div class="stat-value" style="font-size:22px;">${fmtNum(d.payments_last_30_days)}</div>
            </div>
          </div>
        </div>
      </div>

      <div class="panel">
        <div class="panel-head"><h2>Quick actions</h2></div>
        <div class="panel-body" style="display:flex;flex-direction:column;gap:8px;">
          <a href="#/customers" class="btn btn-ghost" style="justify-content:flex-start;">${Icons.plus} New customer</a>
          <a href="#/billing" class="btn btn-ghost" style="justify-content:flex-start;">${Icons.billing} Create invoice</a>
          <a href="#/vouchers" class="btn btn-ghost" style="justify-content:flex-start;">${Icons.vouchers} Generate vouchers</a>
          <a href="#/sessions" class="btn btn-ghost" style="justify-content:flex-start;">${Icons.sessions} View live sessions</a>
        </div>
      </div>
    </div>`;
};
