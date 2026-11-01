Pages.payments = async function (root) {
  root.innerHTML = `
    <div class="card card-flush">
      <div class="card-head" style="padding:16px 18px 0;"><h2>Payment history</h2></div>
      <div id="pay-list"><div class="center-loading"><div class="spinner"></div></div></div>
    </div>`;

  const res = await Api.get('/api/v1/portal/payments', { limit: 50 });
  const payments = res.data;
  root.querySelector('#pay-list').innerHTML = renderList({
    rows: payments, emptyTitle: 'No payments yet', emptyBody: 'Your payment history will show up here.',
    renderRow: p => `
      <div class="list-row">
        <div class="main">
          <div class="title">${fmtMoney(p.amount_kes, p.currency)}</div>
          <div class="sub">${escapeHtml((p.payment_method || '').toUpperCase())}${p.mpesa_receipt_number ? ' · ' + escapeHtml(p.mpesa_receipt_number) : ''} · ${fmtDate(p.created_at)}</div>
        </div>
        <div class="right">
          ${statusBadge(p.status)}
          ${p.status === 'completed' ? `<div style="margin-top:6px;"><button class="btn btn-ghost btn-sm" data-receipt="${p._id}">${Icons.download} Receipt</button></div>` : ''}
        </div>
      </div>`,
  });

  root.querySelectorAll('[data-receipt]').forEach(btn => {
    btn.onclick = async () => {
      btn.disabled = true;
      const original = btn.innerHTML;
      btn.innerHTML = '<span class="spinner" style="width:14px;height:14px;"></span>';
      await downloadAuthedFile(`/api/v1/portal/payments/${btn.dataset.receipt}/receipt`, `receipt_${btn.dataset.receipt}.pdf`);
      btn.disabled = false; btn.innerHTML = original;
    };
  });
};
