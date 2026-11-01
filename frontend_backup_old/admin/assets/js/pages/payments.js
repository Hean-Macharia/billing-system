Pages.payments = async function (root) {
  const state = { page: 1, limit: 20, status: '', payment_method: '' };

  root.innerHTML = `
    <div class="panel">
      <div class="panel-head">
        <div class="panel-toolbar">
          <select id="p-status" style="width:150px;">
            <option value="">Any status</option>
            <option value="pending">Pending</option>
            <option value="completed">Completed</option>
            <option value="failed">Failed</option>
            <option value="reversed">Reversed</option>
          </select>
          <select id="p-method" style="width:150px;">
            <option value="">Any method</option>
            <option value="mpesa">M-Pesa</option>
            <option value="cash">Cash</option>
            <option value="bank_transfer">Bank transfer</option>
            <option value="card">Card</option>
          </select>
        </div>
        <button class="btn btn-primary" id="p-new">${Icons.plus} Record payment</button>
      </div>
      <div id="p-table-wrap"></div>
      <div id="p-pager-wrap"></div>
    </div>`;

  async function load() {
    const wrap = root.querySelector('#p-table-wrap');
    wrap.innerHTML = '<div class="center-loading"><div class="spinner dark"></div></div>';
    const res = await Api.get('/api/v1/payments', {
      page: state.page, limit: state.limit, status: state.status || undefined, payment_method: state.payment_method || undefined,
    });
    const rows = res.data;
    wrap.innerHTML = renderTable({
      emptyTitle: 'No payments recorded yet',
      columns: [
        { label: 'Customer', render: r => `<div class="row-title">${escapeHtml(r.customer_name || r.customer_id)}</div>${r.invoice_number ? `<div class="row-sub mono">${escapeHtml(r.invoice_number)}</div>` : ''}` },
        { label: 'Method', render: r => `<span class="badge badge-muted">${escapeHtml(r.payment_method)}</span>${r.mpesa_receipt_number ? `<div class="row-sub mono">${escapeHtml(r.mpesa_receipt_number)}</div>` : ''}` },
        { label: 'Amount', num: true, render: r => fmtMoney(r.amount_kes, r.currency) },
        { label: 'Date', render: r => fmtDate(r.payment_date || r.created_at) },
        { label: 'Status', render: r => statusBadge(r.status) },
        { label: '', render: r => r.status === 'pending' ? `<div class="row-actions"><button class="btn btn-primary btn-sm" data-act="confirm" data-id="${r._id}">${Icons.check} Confirm</button></div>` : '' },
      ],
      rows,
    });
    wrap.querySelectorAll('[data-act=confirm]').forEach(b => b.onclick = () => doConfirm(b.dataset.id));

    const pagerWrap = root.querySelector('#p-pager-wrap');
    pagerWrap.innerHTML = '';
    pagerWrap.appendChild(renderPager({ page: state.page, limit: state.limit, total: res.meta.total }, (p) => { state.page = p; load(); }));
  }

  async function doConfirm(id) {
    try { await Api.post(`/api/v1/payments/${id}/confirm`); toast('Payment confirmed', 'success'); load(); }
    catch (e) { toastError(e); }
  }

  async function openForm() {
    const customersRes = await Api.get('/api/v1/customers', { limit: 100 });
    const customerOpts = customersRes.data.map(c => ({ value: c._id, label: `${c.full_name} (${c.customer_code})` }));

    const bodyHtml = `
      <form id="pay-form">
        ${Field.select('customer_id', 'Customer', customerOpts, '', { required: true, placeholder: 'Select a customer…' })}
        ${Field.text('invoice_id', 'Invoice ID (optional)', '', { hint: 'Paste an invoice _id to apply this payment against it, or leave blank for a general account payment.' })}
        ${Field.row2(
          Field.text('amount_kes', 'Amount (KES)', '', { type: 'number', required: true, min: 0.01, step: '0.01' }),
          Field.select('payment_method', 'Method', ['mpesa', 'cash', 'bank_transfer', 'card'], 'cash')
        )}
        ${Field.row2(
          Field.text('mpesa_phone_number', 'M-Pesa phone (if applicable)', ''),
          Field.text('transaction_id', 'Transaction / reference ID', '')
        )}
        ${Field.textarea('notes', 'Notes', '')}
      </form>`;

    const { close, overlay } = openDrawer({
      title: 'Record payment', wide: true, bodyHtml,
      footerHtml: `<button class="btn btn-ghost" data-act="cancel">Cancel</button><button class="btn btn-primary" data-act="save">Record payment</button>`,
    });
    overlay.querySelector('[data-act=cancel]').onclick = close;
    overlay.querySelector('[data-act=save]').onclick = async () => {
      const form = overlay.querySelector('#pay-form');
      if (!form.reportValidity()) return;
      const raw = formToObject(form);
      const btn = overlay.querySelector('[data-act=save]');
      btn.disabled = true;
      try {
        await Api.post('/api/v1/payments', {
          customer_id: raw.customer_id, invoice_id: raw.invoice_id || undefined,
          amount_kes: Number(raw.amount_kes), payment_method: raw.payment_method,
          mpesa_phone_number: raw.mpesa_phone_number || undefined,
          transaction_id: raw.transaction_id || undefined, notes: raw.notes || undefined,
        });
        toast('Payment recorded', 'success');
        close(); load();
      } catch (e) { toastError(e); }
      finally { btn.disabled = false; }
    };
  }

  root.querySelector('#p-new').onclick = () => openForm().catch(toastError);
  root.querySelector('#p-status').addEventListener('change', (e) => { state.status = e.target.value; state.page = 1; load(); });
  root.querySelector('#p-method').addEventListener('change', (e) => { state.payment_method = e.target.value; state.page = 1; load(); });

  load();
};
