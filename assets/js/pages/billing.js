Pages.billing = async function (root) {
  const state = { page: 1, limit: 20, status: '', view: 'all' };

  root.innerHTML = `
    <div class="tabs">
      <div class="tab active" data-view="all">All invoices</div>
      <div class="tab" data-view="overdue">Overdue</div>
    </div>
    <div class="panel">
      <div class="panel-head">
        <div class="panel-toolbar">
          <select id="i-status" style="width:170px;">
            <option value="">Any status</option>
            <option value="unpaid">Unpaid</option>
            <option value="partially_paid">Partially paid</option>
            <option value="paid">Paid</option>
            <option value="overdue">Overdue</option>
            <option value="draft">Draft</option>
          </select>
        </div>
        <button class="btn btn-primary" id="i-new">${Icons.plus} New invoice</button>
      </div>
      <div id="i-table-wrap"></div>
      <div id="i-pager-wrap"></div>
    </div>`;

  root.querySelectorAll('.tab').forEach(t => t.onclick = () => {
    root.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
    t.classList.add('active');
    state.view = t.dataset.view;
    root.querySelector('#i-status').closest('.panel-toolbar').style.display = state.view === 'all' ? 'flex' : 'none';
    load();
  });

  function rowCols() {
    return [
      { label: 'Invoice', render: r => `<div class="row-title mono">${escapeHtml(r.invoice_number)}</div><div class="row-sub">${escapeHtml(r.customer_name || r.customer_id)}</div>` },
      { label: 'Issued', render: r => fmtDate(r.invoice_date) },
      { label: 'Due', render: r => fmtDate(r.due_date) },
      { label: 'Total', num: true, render: r => fmtMoney(r.total_kes) },
      { label: 'Balance due', num: true, render: r => fmtMoney(r.balance_due_kes) },
      { label: 'Status', render: r => statusBadge(r.status) },
      { label: '', render: r => `
        <div class="row-actions">
          <button class="btn btn-ghost btn-sm" data-act="view" data-id="${r._id}">View</button>
          ${r.status === 'draft' ? `<button class="btn btn-ghost btn-sm" data-act="send" data-id="${r._id}">${Icons.check} Send</button>` : ''}
        </div>` },
    ];
  }

  async function load() {
    const wrap = root.querySelector('#i-table-wrap');
    wrap.innerHTML = '<div class="center-loading"><div class="spinner dark"></div></div>';
    let rows, meta = null;
    if (state.view === 'overdue') {
      const res = await Api.get('/api/v1/invoices/overdue');
      rows = res.data;
    } else {
      const res = await Api.get('/api/v1/invoices', { page: state.page, limit: state.limit, status: state.status || undefined });
      rows = res.data; meta = res.meta;
    }
    wrap.innerHTML = renderTable({ columns: rowCols(), rows, emptyTitle: 'No invoices found' });
    wrap.querySelectorAll('[data-act=view]').forEach(b => b.onclick = () => viewInvoice(rows.find(r => r._id === b.dataset.id)));
    wrap.querySelectorAll('[data-act=send]').forEach(b => b.onclick = () => doSend(b.dataset.id));

    const pagerWrap = root.querySelector('#i-pager-wrap');
    pagerWrap.innerHTML = '';
    if (meta) pagerWrap.appendChild(renderPager({ page: state.page, limit: state.limit, total: meta.total }, (p) => { state.page = p; load(); }));
  }

  async function doSend(id) {
    try { await Api.post(`/api/v1/invoices/${id}/send`); toast('Invoice marked as sent', 'success'); load(); }
    catch (e) { toastError(e); }
  }

  function viewInvoice(inv) {
    const itemsRows = (inv.line_items || []).map(li => `
      <tr><td>${escapeHtml(li.description)}</td><td class="num">${li.quantity}</td><td class="num">${fmtMoney(li.unit_price_kes)}</td><td class="num">${fmtMoney(li.total_kes)}</td></tr>
    `).join('');
    const bodyHtml = `
      <div style="display:flex;justify-content:space-between;margin-bottom:18px;">
        <div><div class="stat-label">Invoice</div><div class="mono" style="font-weight:700;font-size:15px;">${escapeHtml(inv.invoice_number)}</div></div>
        <div>${statusBadge(inv.status)}</div>
      </div>
      <div class="field-grid" style="margin-bottom:18px;">
        <div><div class="stat-label">Customer</div><div>${escapeHtml(inv.customer_name || inv.customer_id)}</div></div>
        <div><div class="stat-label">Due date</div><div>${fmtDate(inv.due_date)}</div></div>
      </div>
      <table class="data" style="width:100%;margin-bottom:16px;">
        <thead><tr><th>Item</th><th class="num">Qty</th><th class="num">Unit</th><th class="num">Total</th></tr></thead>
        <tbody>${itemsRows || '<tr><td colspan="4" style="color:#8792AC;">No line items</td></tr>'}</tbody>
      </table>
      <div style="display:flex;flex-direction:column;gap:6px;align-items:flex-end;font-size:13px;">
        <div>Subtotal: <b class="mono">${fmtMoney(inv.subtotal_kes)}</b></div>
        <div>Tax (${inv.tax_rate_percent}%): <b class="mono">${fmtMoney(inv.tax_amount_kes)}</b></div>
        <div>Discount: <b class="mono">-${fmtMoney(inv.discount_kes)}</b></div>
        <div style="font-size:16px;">Total: <b class="mono">${fmtMoney(inv.total_kes)}</b></div>
        <div style="color:#12894A;">Paid: <b class="mono">${fmtMoney(inv.amount_paid_kes)}</b></div>
        <div style="color:#B4293A;">Balance due: <b class="mono">${fmtMoney(inv.balance_due_kes)}</b></div>
      </div>
      ${inv.notes ? `<div class="divider"></div><div class="stat-label">Notes</div><div style="font-size:13px;">${escapeHtml(inv.notes)}</div>` : ''}`;
    openDrawer({ title: 'Invoice details', wide: true, bodyHtml, footerHtml: '' });
  }

  async function openForm() {
    const customersRes = await Api.get('/api/v1/customers', { limit: 100, status: 'active' });
    const customerOpts = customersRes.data.map(c => ({ value: c._id, label: `${c.full_name} (${c.customer_code})` }));

    let items = [{ description: '', quantity: 1, unit_price_kes: 0 }];

    function itemsHtml() {
      return items.map((it, idx) => `
        <div style="display:grid;grid-template-columns:1fr 60px 90px 28px;gap:8px;margin-bottom:8px;align-items:center;" data-item-row="${idx}">
          <input type="text" placeholder="Description" value="${escapeHtml(it.description)}" data-item="description" data-idx="${idx}"/>
          <input type="number" min="0" step="1" value="${it.quantity}" data-item="quantity" data-idx="${idx}"/>
          <input type="number" min="0" step="0.01" value="${it.unit_price_kes}" data-item="unit_price_kes" data-idx="${idx}"/>
          <button type="button" class="icon-btn" data-remove-item="${idx}">${Icons.close}</button>
        </div>`).join('');
    }

    const bodyHtml = `
      <form id="inv-form">
        ${Field.select('customer_id', 'Customer', customerOpts, '', { required: true, placeholder: 'Select a customer…' })}
        ${Field.row2(
          Field.text('invoice_date', 'Invoice date', new Date().toISOString().slice(0, 10), { type: 'date', required: true }),
          Field.text('due_date', 'Due date', new Date(Date.now() + 7 * 86400000).toISOString().slice(0, 10), { type: 'date', required: true })
        )}
        <div class="divider"></div>
        <label class="field-label">Line items</label>
        <div id="items-list">${itemsHtml()}</div>
        <button type="button" class="btn btn-ghost btn-sm" id="add-item">${Icons.plus} Add line item</button>
        <div class="divider"></div>
        ${Field.row2(
          Field.text('tax_rate_percent', 'Tax rate (%)', 0, { type: 'number', min: 0, step: '0.01' }),
          Field.text('discount_kes', 'Discount (KES)', 0, { type: 'number', min: 0, step: '0.01' })
        )}
        ${Field.textarea('notes', 'Notes', '')}
      </form>`;

    const { close, overlay } = openDrawer({
      title: 'New invoice', wide: true, bodyHtml,
      footerHtml: `<button class="btn btn-ghost" data-act="cancel">Cancel</button><button class="btn btn-primary" data-act="save">Create invoice</button>`,
    });

    function bindItemInputs() {
      overlay.querySelectorAll('[data-item]').forEach(inp => {
        inp.addEventListener('input', () => {
          const idx = Number(inp.dataset.idx);
          const key = inp.dataset.item;
          items[idx][key] = key === 'description' ? inp.value : Number(inp.value);
        });
      });
      overlay.querySelectorAll('[data-remove-item]').forEach(btn => {
        btn.onclick = () => { items.splice(Number(btn.dataset.removeItem), 1); refreshItems(); };
      });
    }
    function refreshItems() {
      overlay.querySelector('#items-list').innerHTML = itemsHtml();
      bindItemInputs();
    }
    bindItemInputs();
    overlay.querySelector('#add-item').onclick = () => { items.push({ description: '', quantity: 1, unit_price_kes: 0 }); refreshItems(); };

    overlay.querySelector('[data-act=cancel]').onclick = close;
    overlay.querySelector('[data-act=save]').onclick = async () => {
      const form = overlay.querySelector('#inv-form');
      if (!form.reportValidity()) return;
      const raw = formToObject(form);
      const validItems = items.filter(it => it.description && it.unit_price_kes >= 0);
      if (!validItems.length) { toast('Add at least one line item', 'error'); return; }
      const btn = overlay.querySelector('[data-act=save]');
      btn.disabled = true;
      try {
        await Api.post('/api/v1/invoices', {
          customer_id: raw.customer_id,
          invoice_date: new Date(raw.invoice_date).toISOString(),
          due_date: new Date(raw.due_date).toISOString(),
          line_items: validItems.map(it => ({ ...it, total_kes: it.quantity * it.unit_price_kes, item_type: 'service' })),
          tax_rate_percent: Number(raw.tax_rate_percent) || 0,
          discount_kes: Number(raw.discount_kes) || 0,
          notes: raw.notes || undefined,
        });
        toast('Invoice created', 'success');
        close(); load();
      } catch (e) { toastError(e); }
      finally { btn.disabled = false; }
    };
  }

  root.querySelector('#i-new').onclick = () => openForm().catch(toastError);
  root.querySelector('#i-status').addEventListener('change', (e) => { state.status = e.target.value; state.page = 1; load(); });

  load();
};
