Pages.subscriptions = async function (root) {
  const state = { page: 1, limit: 20, status: '' };

  root.innerHTML = `
    <div class="panel">
      <div class="panel-head">
        <div class="panel-toolbar">
          <select id="s-status" style="width:170px;">
            <option value="">Any status</option>
            <option value="active">Active</option>
            <option value="pending_installation">Pending installation</option>
            <option value="suspended">Suspended</option>
            <option value="cancelled">Cancelled</option>
          </select>
        </div>
        <button class="btn btn-primary" id="s-new">${Icons.plus} New subscription</button>
      </div>
      <div id="s-table-wrap"></div>
      <div id="s-pager-wrap"></div>
    </div>`;

  async function load() {
    const wrap = root.querySelector('#s-table-wrap');
    wrap.innerHTML = '<div class="center-loading"><div class="spinner dark"></div></div>';
    const res = await Api.get('/api/v1/subscriptions', { page: state.page, limit: state.limit, status: state.status || undefined });
    const rows = res.data;
    wrap.innerHTML = renderTable({
      emptyTitle: 'No subscriptions yet',
      emptyBody: 'Create one once a customer and a service plan both exist.',
      columns: [
        { label: 'Customer', render: r => `<div class="row-title">${escapeHtml(r.customer_name || r.customer_id)}</div><div class="row-sub mono">${escapeHtml(r.customer_code || '')}</div>` },
        { label: 'Plan', render: r => `${escapeHtml(r.plan_name || r.plan_id)}<div class="row-sub">${fmtMoney(r.monthly_price_kes)}/mo</div>` },
        { label: 'Status', render: r => statusBadge(r.status) },
        { label: 'Next billing', render: r => fmtDate(r.next_billing_date) },
        { label: 'Total paid', num: true, render: r => fmtMoney(r.total_paid_kes) },
        { label: '', render: r => `
          <div class="row-actions">
            ${r.status === 'pending_installation' ? `<button class="btn btn-ghost btn-sm" data-act="install" data-id="${r._id}" title="Mark installed">${Icons.check}</button>` : ''}
            ${r.status === 'active' ? `<button class="btn btn-ghost btn-sm" data-act="invoice" data-id="${r._id}" title="Generate invoice">${Icons.billing}</button>` : ''}
            ${r.status !== 'cancelled' ? `<button class="btn btn-danger btn-sm" data-act="cancel" data-id="${r._id}" title="Cancel">${Icons.ban}</button>` : ''}
          </div>` },
      ],
      rows,
    });
    wrap.querySelectorAll('[data-act=install]').forEach(b => b.onclick = () => doAction(b.dataset.id, 'install', 'Subscription marked installed'));
    wrap.querySelectorAll('[data-act=invoice]').forEach(b => b.onclick = () => doInvoice(b.dataset.id));
    wrap.querySelectorAll('[data-act=cancel]').forEach(b => b.onclick = () => doCancel(b.dataset.id));

    const pagerWrap = root.querySelector('#s-pager-wrap');
    pagerWrap.innerHTML = '';
    pagerWrap.appendChild(renderPager({ page: state.page, limit: state.limit, total: res.meta.total }, (p) => { state.page = p; load(); }));
  }

  async function doAction(id, action, successMsg) {
    try { await Api.post(`/api/v1/subscriptions/${id}/${action}`); toast(successMsg, 'success'); load(); }
    catch (e) { toastError(e); }
  }

  async function doInvoice(id) {
    try {
      const res = await Api.post(`/api/v1/subscriptions/${id}/invoice`);
      toast(`Invoice ${res.data?.invoice_number || ''} generated`, 'success');
    } catch (e) { toastError(e); }
  }

  async function doCancel(id) {
    const ok = await confirmDialog({ title: 'Cancel subscription?', body: 'The customer will lose access once their current billing period ends (or immediately, depending on your backend policy).', confirmLabel: 'Cancel subscription', danger: true });
    if (!ok) return;
    try { await Api.post(`/api/v1/subscriptions/${id}/cancel`); toast('Subscription cancelled', 'success'); load(); }
    catch (e) { toastError(e); }
  }

  async function openForm() {
    const [customersRes, plansRes] = await Promise.all([
      Api.get('/api/v1/customers', { limit: 100, status: 'active' }),
      Api.get('/api/v1/services', { limit: 100, status: 'active' }),
    ]);
    const customerOpts = customersRes.data.map(c => ({ value: c._id, label: `${c.full_name} (${c.customer_code})` }));
    const planOpts = plansRes.data.map(p => ({ value: p._id, label: `${p.name} — ${fmtMoney(p.base_price_kes)}/mo` }));

    const bodyHtml = `
      <form id="sub-form">
        ${Field.select('customer_id', 'Customer', customerOpts, '', { required: true, placeholder: 'Select a customer…' })}
        ${Field.select('plan_id', 'Service plan', planOpts, '', { required: true, placeholder: 'Select a plan…' })}
        ${Field.row2(
          Field.text('start_date', 'Start date', new Date().toISOString().slice(0, 10), { type: 'date', required: true }),
          Field.text('contract_months', 'Contract (months)', 0, { type: 'number', min: 0 })
        )}
        ${Field.row2(
          Field.text('monthly_price_kes', 'Monthly price (KES)', '', { type: 'number', required: true, min: 0, step: '0.01', hint: 'Auto-filled from the plan; adjust for a custom rate.' }),
          Field.text('discount_kes', 'Discount (KES)', 0, { type: 'number', min: 0, step: '0.01' })
        )}
        ${Field.checkbox('auto_renew', 'Auto-renew', true)}
      </form>`;

    const { close, overlay } = openDrawer({
      title: 'New subscription', wide: true, bodyHtml,
      footerHtml: `<button class="btn btn-ghost" data-act="cancel">Cancel</button><button class="btn btn-primary" data-act="save">Create subscription</button>`,
    });

    const planSelect = overlay.querySelector('select[name=plan_id]');
    const priceInput = overlay.querySelector('input[name=monthly_price_kes]');
    planSelect.addEventListener('change', () => {
      const plan = plansRes.data.find(p => p._id === planSelect.value);
      if (plan) priceInput.value = plan.base_price_kes;
    });

    overlay.querySelector('[data-act=cancel]').onclick = close;
    overlay.querySelector('[data-act=save]').onclick = async () => {
      const form = overlay.querySelector('#sub-form');
      if (!form.reportValidity()) return;
      const raw = formToObject(form);
      const btn = overlay.querySelector('[data-act=save]');
      btn.disabled = true;
      try {
        await Api.post('/api/v1/subscriptions', {
          customer_id: raw.customer_id, plan_id: raw.plan_id,
          start_date: new Date(raw.start_date).toISOString(),
          monthly_price_kes: Number(raw.monthly_price_kes), discount_kes: Number(raw.discount_kes) || 0,
          contract_months: Number(raw.contract_months) || 0, auto_renew: !!raw.auto_renew,
        });
        toast('Subscription created', 'success');
        close(); load();
      } catch (e) { toastError(e); }
      finally { btn.disabled = false; }
    };
  }

  root.querySelector('#s-new').onclick = () => openForm().catch(toastError);
  root.querySelector('#s-status').addEventListener('change', (e) => { state.status = e.target.value; state.page = 1; load(); });

  load();
};
