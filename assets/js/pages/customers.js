Pages.customers = async function (root) {
  const state = { page: 1, limit: 20, search: '', status: '', customer_type: '' };

  root.innerHTML = `
    <div class="panel">
      <div class="panel-head">
        <div class="panel-toolbar">
          <div class="search-box">${Icons.search}<input type="search" id="c-search" placeholder="Search name, code, phone…"/></div>
          <select id="c-status" style="width:150px;">
            <option value="">Any status</option>
            <option value="active">Active</option>
            <option value="suspended">Suspended</option>
            <option value="pending_installation">Pending installation</option>
            <option value="cancelled">Cancelled</option>
          </select>
          <select id="c-type" style="width:150px;">
            <option value="">Any type</option>
            <option value="residential">Residential</option>
            <option value="business">Business</option>
            <option value="enterprise">Enterprise</option>
          </select>
        </div>
        <button class="btn btn-primary" id="c-new">${Icons.plus} New customer</button>
      </div>
      <div id="c-table-wrap"></div>
      <div id="c-pager-wrap"></div>
    </div>`;

  async function load() {
    const wrap = root.querySelector('#c-table-wrap');
    wrap.innerHTML = '<div class="center-loading"><div class="spinner dark"></div></div>';
    const res = await Api.get('/api/v1/customers', {
      page: state.page, limit: state.limit, search: state.search || undefined,
      status: state.status || undefined, customer_type: state.customer_type || undefined,
    });
    const rows = res.data;
    wrap.innerHTML = renderTable({
      emptyTitle: 'No customers yet',
      emptyBody: 'Add your first customer to get started.',
      columns: [
        { label: 'Customer', render: r => `<div class="row-title">${escapeHtml(r.full_name)}</div><div class="row-sub">${escapeHtml(r.customer_code)}</div>` },
        { label: 'Contact', render: r => `${escapeHtml(r.phone)}${r.email ? '<div class="row-sub">' + escapeHtml(r.email) + '</div>' : ''}` },
        { label: 'Type', render: r => `<span class="badge badge-muted">${escapeHtml(r.customer_type)}</span>` },
        { label: 'Status', render: r => statusBadge(r.status) },
        { label: 'Outstanding', num: true, render: r => fmtMoney(r.outstanding_balance || 0) },
        { label: '', render: r => `
          <div class="row-actions">
            <button class="btn btn-ghost btn-sm" data-act="edit" data-id="${r._id}">${Icons.edit}</button>
            <button class="btn btn-ghost btn-sm" data-act="status" data-id="${r._id}" data-status="${r.status}">${Icons.refresh}</button>
            <button class="btn btn-danger btn-sm" data-act="delete" data-id="${r._id}">${Icons.trash}</button>
          </div>` },
      ],
      rows,
    });

    wrap.querySelectorAll('[data-act=edit]').forEach(b => b.onclick = () => openForm(rows.find(r => r._id === b.dataset.id)));
    wrap.querySelectorAll('[data-act=delete]').forEach(b => b.onclick = () => doDelete(b.dataset.id));
    wrap.querySelectorAll('[data-act=status]').forEach(b => b.onclick = () => changeStatus(b.dataset.id, b.dataset.status));

    const pagerWrap = root.querySelector('#c-pager-wrap');
    pagerWrap.innerHTML = '';
    pagerWrap.appendChild(renderPager({ page: state.page, limit: state.limit, total: res.meta.total }, (p) => { state.page = p; load(); }));
  }

  async function doDelete(id) {
    const ok = await confirmDialog({ title: 'Deactivate customer?', body: 'This soft-deletes the customer (marks them inactive) — it does not erase their billing history.', confirmLabel: 'Deactivate', danger: true });
    if (!ok) return;
    try { await Api.delete(`/api/v1/customers/${id}`); toast('Customer deactivated', 'success'); load(); }
    catch (e) { toastError(e); }
  }

  async function changeStatus(id, current) {
    const options = ['active', 'suspended', 'pending_installation', 'cancelled'].filter(s => s !== current);
    const { close, overlay } = openDrawer({
      title: 'Change status',
      bodyHtml: Field.select('status', 'New status', options, options[0]),
      footerHtml: `<button class="btn btn-ghost" data-act="cancel">Cancel</button><button class="btn btn-primary" data-act="save">Update</button>`,
    });
    overlay.querySelector('[data-act=cancel]').onclick = close;
    overlay.querySelector('[data-act=save]').onclick = async () => {
      const sel = overlay.querySelector('select[name=status]').value;
      try {
        await Api.request(`/api/v1/customers/${id}/status`, { method: 'PATCH', params: { status: sel } });
        toast('Status updated', 'success'); close(); load();
      } catch (e) { toastError(e); }
    };
  }

  function openForm(existing) {
    const isEdit = !!existing;
    const a = existing?.address || {};
    const bodyHtml = `
      <form id="c-form">
        ${Field.row2(
          Field.text('customer_code', 'Customer code', existing?.customer_code || '', { required: !isEdit, hint: isEdit ? undefined : 'e.g. CUST-0001', ...(isEdit ? { disabled: true } : {}) }),
          Field.text('customer_number', 'Customer number', existing?.customer_code || '', { required: !isEdit })
        )}
        ${Field.text('full_name', 'Full name', existing?.full_name || '', { required: true })}
        ${Field.row2(
          Field.text('phone', 'Phone', existing?.phone || '', { required: true, placeholder: '2547XXXXXXXX' }),
          Field.text('email', 'Email', existing?.email || '', { type: 'email' })
        )}
        ${Field.select('customer_type', 'Customer type', ['residential', 'business', 'enterprise'], existing?.customer_type || 'residential')}
        <div class="divider"></div>
        ${Field.text('street', 'Street address', a.street || '', { required: true })}
        ${Field.row2(
          Field.text('city', 'City', a.city || '', { required: true }),
          Field.text('country', 'Country', a.country || 'Kenya')
        )}
        <div class="divider"></div>
        ${Field.row2(
          Field.text('billing_day', 'Billing day', existing?.billing_day || 1, { type: 'number', min: 1 }),
          Field.select('auto_billing', 'Auto billing', [{ value: 'true', label: 'Enabled' }, { value: 'false', label: 'Disabled' }], String(existing?.auto_billing ?? true))
        )}
        ${Field.textarea('notes', 'Notes', existing?.notes || '')}
      </form>`;

    const { close, overlay } = openDrawer({
      title: isEdit ? `Edit ${existing.full_name}` : 'New customer',
      wide: true,
      bodyHtml,
      footerHtml: `<button class="btn btn-ghost" data-act="cancel">Cancel</button><button class="btn btn-primary" data-act="save">${isEdit ? 'Save changes' : 'Create customer'}</button>`,
    });
    overlay.querySelector('[data-act=cancel]').onclick = close;
    overlay.querySelector('[data-act=save]').onclick = async () => {
      const form = overlay.querySelector('#c-form');
      if (!form.reportValidity()) return;
      const raw = formToObject(form);
      const btn = overlay.querySelector('[data-act=save]');
      btn.disabled = true;
      try {
        if (isEdit) {
          await Api.patch(`/api/v1/customers/${existing._id}`, {
            full_name: raw.full_name, phone: raw.phone, email: raw.email || null,
            notes: raw.notes || null, billing_day: Number(raw.billing_day),
            auto_billing: raw.auto_billing === 'true',
          });
          toast('Customer updated', 'success');
        } else {
          await Api.post('/api/v1/customers', {
            customer_number: raw.customer_number, customer_code: raw.customer_code,
            full_name: raw.full_name, phone: raw.phone, email: raw.email || undefined,
            customer_type: raw.customer_type,
            address: { street: raw.street, city: raw.city, country: raw.country || 'Kenya' },
            billing_day: Number(raw.billing_day), auto_billing: raw.auto_billing === 'true',
            notes: raw.notes || undefined,
          });
          toast('Customer created', 'success');
        }
        close(); load();
      } catch (e) { toastError(e); }
      finally { btn.disabled = false; }
    };
  }

  root.querySelector('#c-new').onclick = () => openForm(null);
  let searchTimer;
  root.querySelector('#c-search').addEventListener('input', (e) => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => { state.search = e.target.value; state.page = 1; load(); }, 350);
  });
  root.querySelector('#c-status').addEventListener('change', (e) => { state.status = e.target.value; state.page = 1; load(); });
  root.querySelector('#c-type').addEventListener('change', (e) => { state.customer_type = e.target.value; state.page = 1; load(); });

  load();
};
