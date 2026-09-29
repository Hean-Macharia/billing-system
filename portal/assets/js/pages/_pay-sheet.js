Pages._openPaySheet = function (invoice) {
  const bodyHtml = `
    <div style="text-align:center;margin-bottom:18px;">
      <div style="font-size:12.5px;color:var(--muted);">Paying invoice</div>
      <div class="mono" style="font-weight:700;">${escapeHtml(invoice.invoice_number)}</div>
      <div style="font-size:26px;font-weight:800;margin-top:6px;">${fmtMoney(invoice.balance_due_kes || invoice.total_kes)}</div>
    </div>
    <form id="pay-form">
      <div class="field-row">
        <label class="field-label">M-Pesa phone number</label>
        <input type="text" name="phone_number" required pattern="254[0-9]{9}" placeholder="2547XXXXXXXX"/>
        <div class="field-hint">You'll get an STK push prompt on this number.</div>
      </div>
    </form>
    <div id="pay-status" style="display:none;text-align:center;padding:20px 0;">
      <div class="spinner" style="margin:0 auto 12px;"></div>
      <div style="font-weight:600;">Check your phone</div>
      <div style="font-size:12.5px;color:var(--muted);margin-top:4px;">Enter your M-Pesa PIN to complete the payment.</div>
    </div>`;

  const { close, overlay } = openSheet({
    title: 'Pay with M-Pesa', bodyHtml,
    footerHtml: `<button class="btn btn-primary btn-block" id="pay-submit">${Icons.bolt} Send payment request</button>`,
  });

  overlay.querySelector('#pay-submit').onclick = async () => {
    const form = overlay.querySelector('#pay-form');
    if (!form.reportValidity()) return;
    const { phone_number } = formToObject(form);
    const btn = overlay.querySelector('#pay-submit');
    btn.disabled = true;
    overlay.querySelector('#pay-form').style.display = 'none';
    overlay.querySelector('#pay-status').style.display = 'block';
    try {
      await Api.post('/api/v1/portal/payments/stk-push', { invoice_id: invoice._id, phone_number });
      overlay.querySelector('#pay-status').innerHTML = `
        <div style="width:44px;height:44px;border-radius:50%;background:var(--signal-soft);color:#0E8578;display:flex;align-items:center;justify-content:center;margin:0 auto 12px;">${Icons.check}</div>
        <div style="font-weight:700;">Request sent</div>
        <div style="font-size:12.5px;color:var(--muted);margin-top:4px;">Complete it on your phone, then check back here shortly — your balance updates automatically once M-Pesa confirms.</div>`;
      btn.textContent = 'Done'; btn.disabled = false;
      btn.onclick = () => { close(); Router.render(); };
    } catch (e) {
      overlay.querySelector('#pay-form').style.display = 'block';
      overlay.querySelector('#pay-status').style.display = 'none';
      btn.disabled = false;
      toastError(e);
    }
  };
};
