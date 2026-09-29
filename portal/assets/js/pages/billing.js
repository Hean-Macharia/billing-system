Pages.billing = async function (root) {
  root.innerHTML = `
    <div class="card card-flush">
      <div class="card-head" style="padding:16px 18px 0;"><h2>Your invoices</h2></div>
      <div id="inv-list"><div class="center-loading"><div class="spinner"></div></div></div>
    </div>`;

  const res = await Api.get('/api/v1/portal/invoices', { limit: 50 });
  const invoices = res.data;
  root.querySelector('#inv-list').innerHTML = renderList({
    rows: invoices, emptyTitle: 'No invoices yet',
    renderRow: inv => `
      <div class="list-row" data-id="${inv._id}" style="cursor:pointer;">
        <div class="main">
          <div class="title mono">${escapeHtml(inv.invoice_number)}</div>
          <div class="sub">Due ${fmtDate(inv.due_date)}</div>
        </div>
        <div class="right">
          <div class="mono" style="font-weight:700;">${fmtMoney(inv.total_kes)}</div>
          <div style="margin-top:2px;">${statusBadge(inv.status)}</div>
        </div>
      </div>`,
  });

  root.querySelectorAll('[data-id]').forEach(row => row.onclick = () => viewInvoice(invoices.find(i => i._id === row.dataset.id)));

  function viewInvoice(inv) {
    const itemsHtml = (inv.line_items || []).map(li => `
      <div style="display:flex;justify-content:space-between;font-size:13px;padding:6px 0;">
        <span>${escapeHtml(li.description)} ${li.quantity > 1 ? `× ${li.quantity}` : ''}</span>
        <span class="mono">${fmtMoney(li.total_kes)}</span>
      </div>`).join('');

    const bodyHtml = `
      <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:16px;">
        <div><div class="mono" style="font-weight:700;font-size:15px;">${escapeHtml(inv.invoice_number)}</div><div style="font-size:12px;color:var(--muted);">Issued ${fmtDate(inv.invoice_date)}</div></div>
        ${statusBadge(inv.status)}
      </div>
      ${itemsHtml}
      <div class="divider"></div>
      <div style="display:flex;flex-direction:column;gap:5px;font-size:13px;">
        <div style="display:flex;justify-content:space-between;"><span>Subtotal</span><span class="mono">${fmtMoney(inv.subtotal_kes)}</span></div>
        <div style="display:flex;justify-content:space-between;"><span>Tax</span><span class="mono">${fmtMoney(inv.tax_amount_kes)}</span></div>
        <div style="display:flex;justify-content:space-between;font-weight:700;font-size:15px;"><span>Total</span><span class="mono">${fmtMoney(inv.total_kes)}</span></div>
        <div style="display:flex;justify-content:space-between;color:#12894A;"><span>Paid</span><span class="mono">${fmtMoney(inv.amount_paid_kes)}</span></div>
        ${inv.balance_due_kes > 0 ? `<div style="display:flex;justify-content:space-between;color:#B4293A;font-weight:700;"><span>Balance due</span><span class="mono">${fmtMoney(inv.balance_due_kes)}</span></div>` : ''}
      </div>`;

    const { close, overlay } = openSheet({
      title: 'Invoice', bodyHtml,
      footerHtml: inv.balance_due_kes > 0 ? `<button class="btn btn-primary btn-block" id="inv-pay">${Icons.bolt} Pay ${fmtMoney(inv.balance_due_kes)}</button>` : '',
    });
    if (inv.balance_due_kes > 0) {
      overlay.querySelector('#inv-pay').onclick = () => { close(); Pages._openPaySheet(inv); };
    }
  }
};
