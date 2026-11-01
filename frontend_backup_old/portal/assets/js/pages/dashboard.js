Pages.dashboard = async function (root) {
  const res = await Api.get('/api/v1/portal/dashboard');
  const d = res.data;
  Api.setProfile({ ...Api.getProfile(), full_name: d.customer.full_name });

  const hasBalance = d.balance_due_kes > 0;

  root.innerHTML = `
    <div class="hero-balance">
      <div class="label">${hasBalance ? 'Outstanding balance' : 'Account balance'}</div>
      <div class="amount">${fmtMoney(d.balance_due_kes)}</div>
      <div class="sub">${d.overdue_invoice_count > 0 ? `${d.overdue_invoice_count} invoice(s) overdue` : hasBalance ? 'Due on your next billing date' : "You're all paid up"}</div>
      ${hasBalance ? `<div class="cta"><button class="btn btn-primary" id="dash-pay">${Icons.bolt} Pay now</button></div>` : ''}
    </div>

    <div class="stat-grid">
      <div class="stat-box"><div class="label">Current plan</div><div class="value" style="font-size:14px;">${escapeHtml(d.subscription?.plan_name || 'No active plan')}</div></div>
      <div class="stat-box"><div class="label">Status</div><div class="value" style="font-size:14px;">${d.currently_online ? statusBadge('online') : statusBadge('offline')}</div></div>
      <div class="stat-box"><div class="label">Data used (30d)</div><div class="value">${d.usage_last_30_days.total_mb >= 1024 ? (d.usage_last_30_days.total_mb/1024).toFixed(1)+' GB' : d.usage_last_30_days.total_mb+' MB'}</div></div>
    </div>

    <div class="card">
      <div class="card-head"><h2>Your plan</h2><a href="#/subscription" style="font-size:12.5px;font-weight:700;color:#B91C1C;">Details</a></div>
      ${d.subscription ? `
        <div style="display:flex;justify-content:space-between;align-items:center;">
          <div>
            <div style="font-weight:700;">${escapeHtml(d.subscription.plan_name)}</div>
            <div style="font-size:12.5px;color:var(--muted);">Next billing: ${fmtDate(d.subscription.next_billing_date)}</div>
          </div>
          <div style="text-align:right;">
            <div class="mono" style="font-weight:700;">${fmtMoney(d.subscription.monthly_price_kes)}</div>
            <div style="font-size:11.5px;color:var(--muted);">per month</div>
          </div>
        </div>` : `<div class="empty-state">${Icons.subscription}<div>No active subscription on file. Contact support if this looks wrong.</div></div>`}
    </div>

    <div class="card">
      <div class="card-head"><h2>Last payment</h2><a href="#/payments" style="font-size:12.5px;font-weight:700;color:#B91C1C;">History</a></div>
      ${d.last_payment ? `
        <div style="display:flex;justify-content:space-between;align-items:center;">
          <div>
            <div style="font-weight:700;">${fmtMoney(d.last_payment.amount_kes)}</div>
            <div style="font-size:12.5px;color:var(--muted);text-transform:capitalize;">${escapeHtml(d.last_payment.method)}</div>
          </div>
          <div style="font-size:12.5px;color:var(--muted);">${fmtDate(d.last_payment.date)}</div>
        </div>` : `<div class="empty-state">${Icons.payments}<div>No payments recorded yet.</div></div>`}
    </div>

    <div style="display:flex;gap:10px;">
      <a href="#/usage" class="btn btn-ghost" style="flex:1;">${Icons.usage} Usage</a>
      <a href="#/support" class="btn btn-ghost" style="flex:1;">${Icons.support} Get help</a>
    </div>`;

  if (hasBalance) {
    root.querySelector('#dash-pay').onclick = async () => {
      const overdueRes = await Api.get('/api/v1/portal/invoices', { status_filter: 'overdue', limit: 1 });
      const invRes = await Api.get('/api/v1/portal/invoices', { status_filter: 'unpaid', limit: 1 });
      const invoice = (overdueRes.data[0] || invRes.data[0]);
      if (!invoice) { toast('No open invoice found', 'error'); return; }
      Pages._openPaySheet(invoice);
    };
  }
};
