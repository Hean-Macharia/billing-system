Pages.vouchers = async function (root) {
  const state = { tab: 'batches' };

  root.innerHTML = `
    <div class="tabs">
      <div class="tab active" data-tab="batches">Voucher batches</div>
      <div class="tab" data-tab="plans">HotSpot plans</div>
    </div>
    <div id="v-content"></div>`;

  root.querySelectorAll('.tab').forEach(t => t.onclick = () => {
    root.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
    t.classList.add('active');
    state.tab = t.dataset.tab;
    renderTab();
  });

  function renderTab() {
    if (state.tab === 'batches') renderBatches();
    else renderPlans();
  }

  async function renderBatches() {
    const content = root.querySelector('#v-content');
    content.innerHTML = `
      <div class="panel">
        <div class="panel-head">
          <div class="panel-toolbar"></div>
          <button class="btn btn-primary" id="b-new">${Icons.plus} Generate batch</button>
        </div>
        <div id="b-table-wrap"></div>
        <div id="b-pager-wrap"></div>
      </div>`;

    const bstate = { page: 1, limit: 20 };
    async function loadBatches() {
      const wrap = content.querySelector('#b-table-wrap');
      wrap.innerHTML = '<div class="center-loading"><div class="spinner dark"></div></div>';
      const res = await Api.get('/api/v1/vouchers/batches', { page: bstate.page, limit: bstate.limit });
      const rows = res.data;
      wrap.innerHTML = renderTable({
        emptyTitle: 'No voucher batches yet',
        emptyBody: 'Generate a batch to start printing HotSpot access codes.',
        columns: [
          { label: 'Batch', render: r => `<div class="row-title">${escapeHtml(r.batch_name)}</div><div class="row-sub">${fmtDate(r.created_at)}</div>` },
          { label: 'Package', render: r => `${r.duration_hours ? r.duration_hours + 'h' : '—'} ${r.data_allowance_mb ? '/ ' + r.data_allowance_mb + 'MB' : '/ unlimited'}<div class="row-sub">${fmtMoney(r.price, r.currency)} each</div>` },
          { label: 'Generated', num: true, render: r => fmtNum(r.generated_count) },
          { label: 'Activated', num: true, render: r => fmtNum(r.activated_count) },
          { label: 'Used', num: true, render: r => fmtNum(r.used_count) },
          { label: '', render: r => `
            <div class="row-actions">
              <button class="btn btn-ghost btn-sm" data-act="view" data-id="${r._id}">View codes</button>
              <button class="btn btn-ghost btn-sm" data-act="activate" data-id="${r._id}" title="Activate all pending">${Icons.bolt}</button>
              <a class="btn btn-ghost btn-sm" href="${Api.downloadUrl('/api/v1/vouchers/batches/' + r._id + '/export')}" target="_blank" title="Export CSV">${Icons.download}</a>
              <a class="btn btn-ghost btn-sm" href="${Api.downloadUrl('/api/v1/vouchers/batches/' + r._id + '/print')}" target="_blank" title="Print PDF">${Icons.print}</a>
            </div>` },
        ],
        rows,
      });
      wrap.querySelectorAll('[data-act=view]').forEach(b => b.onclick = () => viewBatchVouchers(rows.find(r => r._id === b.dataset.id)));
      wrap.querySelectorAll('[data-act=activate]').forEach(b => b.onclick = () => activateBatch(b.dataset.id));

      const pagerWrap = content.querySelector('#b-pager-wrap');
      pagerWrap.innerHTML = '';
      pagerWrap.appendChild(renderPager({ page: bstate.page, limit: bstate.limit, total: res.meta.total }, (p) => { bstate.page = p; loadBatches(); }));
    }

    async function activateBatch(id) {
      const ok = await confirmDialog({ title: 'Activate all pending vouchers?', body: 'Every voucher in this batch still marked "generated" will become usable immediately — its expiry clock starts now.', confirmLabel: 'Activate all' });
      if (!ok) return;
      try {
        const res = await Api.post(`/api/v1/vouchers/batches/${id}/activate`, {});
        toast(`Activated ${res.data.activated} voucher(s)`, 'success');
        loadBatches();
      } catch (e) { toastError(e); }
    }

    async function viewBatchVouchers(batch) {
      const bodyHtml = `<div id="voucher-list-body"><div class="center-loading"><div class="spinner dark"></div></div></div>`;
      const { overlay } = openDrawer({ title: batch.batch_name, wide: true, bodyHtml, footerHtml: '' });
      const vres = await Api.get('/api/v1/vouchers', { batch_id: batch._id, limit: 200 });
      const vrows = vres.data;
      const listBody = overlay.querySelector('#voucher-list-body');
      listBody.innerHTML = renderTable({
        emptyTitle: 'No vouchers found',
        columns: [
          { label: 'Code', render: v => copyChip(v.voucher_code) },
          { label: 'Status', render: v => statusBadge(v.status) },
          { label: 'Expiry', render: v => fmtDate(v.expiry_date) },
          { label: '', render: v => `
            <div class="row-actions">
              ${v.status === 'generated' ? `<button class="btn btn-ghost btn-sm" data-vact="activate" data-vid="${v._id}">Activate</button>` : ''}
              ${v.status !== 'used' && v.status !== 'disabled' ? `<button class="btn btn-danger btn-sm" data-vact="disable" data-vid="${v._id}">Disable</button>` : ''}
            </div>` },
        ],
        rows: vrows,
      });
      listBody.querySelectorAll('[data-vact=activate]').forEach(b => b.onclick = async () => {
        try { await Api.post(`/api/v1/vouchers/${b.dataset.vid}/activate`); toast('Voucher activated', 'success'); viewBatchVouchers(batch); }
        catch (e) { toastError(e); }
      });
      listBody.querySelectorAll('[data-vact=disable]').forEach(b => b.onclick = async () => {
        const ok = await confirmDialog({ title: 'Disable this voucher?', confirmLabel: 'Disable', danger: true });
        if (!ok) return;
        try { await Api.post(`/api/v1/vouchers/${b.dataset.vid}/disable`, {}); toast('Voucher disabled', 'success'); viewBatchVouchers(batch); }
        catch (e) { toastError(e); }
      });
    }

    async function openBatchForm() {
      const plansRes = await Api.get('/api/v1/hotspot/plans');
      const planOpts = plansRes.data.map(p => ({ value: p._id, label: `${p.name} — ${fmtMoney(p.price, p.currency)}` }));

      const bodyHtml = `
        <form id="batch-form">
          ${Field.text('batch_name', 'Batch name', '', { required: true, placeholder: 'e.g. Front Desk - March' })}
          ${Field.row2(
            Field.text('quantity', 'Quantity', 20, { type: 'number', required: true, min: 1 }),
            Field.text('code_length', 'Code length', 8, { type: 'number', min: 6, max: 20 })
          )}
          ${planOpts.length ? Field.select('plan_id', 'Use a HotSpot plan (optional)', planOpts, '', { placeholder: 'Set fields manually instead…' }) : ''}
          ${Field.row2(
            Field.text('duration_hours', 'Duration (hours)', 1, { type: 'number', min: 0.1, step: '0.1' }),
            Field.text('data_allowance_mb', 'Data cap (MB, blank = unlimited)', '', { type: 'number', min: 1 })
          )}
          ${Field.row2(
            Field.text('price', 'Price (KES)', 0, { type: 'number', min: 0, step: '0.01' }),
            Field.text('rate_limit', 'Rate limit (up/down)', '', { placeholder: 'e.g. 2M/5M' })
          )}
          ${Field.checkbox('activate_on_generation', 'Activate immediately (skip the sell-later step)', false)}
        </form>`;

      const { close, overlay } = openDrawer({
        title: 'Generate voucher batch', wide: true, bodyHtml,
        footerHtml: `<button class="btn btn-ghost" data-act="cancel">Cancel</button><button class="btn btn-primary" data-act="save">Generate</button>`,
      });

      const planSelect = overlay.querySelector('select[name=plan_id]');
      if (planSelect) planSelect.addEventListener('change', () => {
        const plan = plansRes.data.find(p => p._id === planSelect.value);
        if (plan) {
          overlay.querySelector('input[name=duration_hours]').value = plan.duration_hours;
          overlay.querySelector('input[name=data_allowance_mb]').value = plan.data_allowance_mb || '';
          overlay.querySelector('input[name=price]').value = plan.price;
          overlay.querySelector('input[name=rate_limit]').value = plan.rate_limit || '';
        }
      });

      overlay.querySelector('[data-act=cancel]').onclick = close;
      overlay.querySelector('[data-act=save]').onclick = async () => {
        const form = overlay.querySelector('#batch-form');
        if (!form.reportValidity()) return;
        const raw = formToObject(form);
        const btn = overlay.querySelector('[data-act=save]');
        btn.disabled = true;
        try {
          await Api.post('/api/v1/vouchers/batches', {
            batch_name: raw.batch_name, quantity: Number(raw.quantity), code_length: Number(raw.code_length) || 10,
            plan_id: raw.plan_id || undefined,
            duration_hours: raw.duration_hours ? Number(raw.duration_hours) : undefined,
            data_allowance_mb: raw.data_allowance_mb ? Number(raw.data_allowance_mb) : undefined,
            price: Number(raw.price) || 0, rate_limit: raw.rate_limit || undefined,
            activate_on_generation: !!raw.activate_on_generation,
          });
          toast('Voucher batch generated', 'success');
          close(); loadBatches();
        } catch (e) { toastError(e); }
        finally { btn.disabled = false; }
      };
    }

    content.querySelector('#b-new').onclick = () => openBatchForm().catch(toastError);
    loadBatches();
  }

  Pages._hotspotPlansAsCrud = Pages._hotspotPlansAsCrud || makeSimpleCrudPage({
    title: 'HotSpot plan',
    endpoint: '/api/v1/hotspot/plans',
    paginated: false,
    newButtonLabel: 'New plan',
    emptyTitle: 'No HotSpot plans yet',
    emptyBody: 'Plans are reusable templates you can pick when generating a voucher batch.',
    columns: [
      { label: 'Plan', render: r => `<div class="row-title">${escapeHtml(r.name)}</div><div class="row-sub">${escapeHtml(r.description || '')}</div>` },
      { label: 'Duration', render: r => `${r.duration_hours}h` },
      { label: 'Data', render: r => r.data_allowance_mb ? `${fmtNum(r.data_allowance_mb)} MB` : 'Unlimited' },
      { label: 'Price', num: true, render: r => fmtMoney(r.price, r.currency) },
      { label: 'Status', render: r => statusBadge(r.is_active ? 'active' : 'inactive') },
    ],
    formFields: (existing) => `
      ${Field.text('name', 'Plan name', existing?.name || '', { required: true })}
      ${Field.row2(
        Field.text('duration_hours', 'Duration (hours)', existing?.duration_hours || 1, { type: 'number', required: true, min: 0.1, step: '0.1' }),
        Field.text('data_allowance_mb', 'Data cap (MB, blank = unlimited)', existing?.data_allowance_mb ?? '', { type: 'number', min: 1 })
      )}
      ${Field.row2(
        Field.text('price', 'Price (KES)', existing?.price ?? 0, { type: 'number', min: 0, step: '0.01' }),
        Field.text('rate_limit', 'Rate limit (up/down)', existing?.rate_limit || '', { placeholder: 'e.g. 2M/5M' })
      )}
      ${Field.textarea('description', 'Description', existing?.description || '')}
      ${Field.checkbox('is_active', 'Active', existing ? existing.is_active : true)}`,
    toCreatePayload: (raw) => ({
      name: raw.name, duration_hours: Number(raw.duration_hours),
      data_allowance_mb: raw.data_allowance_mb ? Number(raw.data_allowance_mb) : undefined,
      price: Number(raw.price) || 0, rate_limit: raw.rate_limit || undefined,
      description: raw.description || undefined, is_active: !!raw.is_active,
    }),
    toUpdatePayload: (raw) => ({
      name: raw.name, duration_hours: Number(raw.duration_hours),
      data_allowance_mb: raw.data_allowance_mb ? Number(raw.data_allowance_mb) : undefined,
      price: Number(raw.price) || 0, rate_limit: raw.rate_limit || undefined,
      description: raw.description || undefined, is_active: !!raw.is_active,
    }),
  });

  async function renderPlans() {
    const content = root.querySelector('#v-content');
    await Pages._hotspotPlansAsCrud(content);
  }

  renderTab();
};
