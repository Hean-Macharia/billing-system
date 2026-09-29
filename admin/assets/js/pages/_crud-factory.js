/*
  Simple CRUD page factory
  ------------------------
  For modules that are just "list + create/edit drawer + delete", with no
  bespoke workflow (packages, services, sites). Config describes the
  endpoint, table columns, and form fields; this renders the rest.

  config = {
    title, endpoint, idKey='_id', listPath=null (if list response is a
    bare array instead of paginated), permCreate, permUpdate, permDelete,
    columns: [{label, render(row)}],
    formFields(existing) -> html string (inside <form id="crud-form">),
    toCreatePayload(rawFormValues),
    toUpdatePayload(rawFormValues, existing),
    newButtonLabel, emptyTitle, emptyBody, paginated=true,
  }
*/
function makeSimpleCrudPage(config) {
  return async function (root) {
    const state = { page: 1, limit: 20 };

    root.innerHTML = `
      <div class="panel">
        <div class="panel-head">
          <div class="panel-toolbar"></div>
          <button class="btn btn-primary" id="crud-new">${Icons.plus} ${config.newButtonLabel}</button>
        </div>
        <div id="crud-table-wrap"></div>
        <div id="crud-pager-wrap"></div>
      </div>`;

    async function load() {
      const wrap = root.querySelector('#crud-table-wrap');
      wrap.innerHTML = '<div class="center-loading"><div class="spinner dark"></div></div>';
      const res = await Api.get(config.endpoint, config.paginated === false ? {} : { page: state.page, limit: state.limit });
      const rows = config.paginated === false ? res.data : res.data;

      wrap.innerHTML = renderTable({
        emptyTitle: config.emptyTitle || 'Nothing here yet',
        emptyBody: config.emptyBody || '',
        columns: [...config.columns, {
          label: '', render: r => `
            <div class="row-actions">
              <button class="btn btn-ghost btn-sm" data-act="edit" data-id="${r[config.idKey || '_id']}">${Icons.edit}</button>
              <button class="btn btn-danger btn-sm" data-act="delete" data-id="${r[config.idKey || '_id']}">${Icons.trash}</button>
            </div>`,
        }],
        rows,
      });

      wrap.querySelectorAll('[data-act=edit]').forEach(b => b.onclick = () => openForm(rows.find(r => String(r[config.idKey || '_id']) === b.dataset.id)));
      wrap.querySelectorAll('[data-act=delete]').forEach(b => b.onclick = () => doDelete(b.dataset.id));

      const pagerWrap = root.querySelector('#crud-pager-wrap');
      pagerWrap.innerHTML = '';
      if (config.paginated !== false && res.meta) {
        pagerWrap.appendChild(renderPager({ page: state.page, limit: state.limit, total: res.meta.total }, (p) => { state.page = p; load(); }));
      }
    }

    async function doDelete(id) {
      const ok = await confirmDialog({ title: `Delete this ${config.title.toLowerCase()}?`, body: 'This cannot be undone.', confirmLabel: 'Delete', danger: true });
      if (!ok) return;
      try {
        await Api.delete(`${config.endpoint}/${id}`);
        toast(`${config.title} deleted`, 'success');
        load();
      } catch (e) { toastError(e); }
    }

    function openForm(existing) {
      const isEdit = !!existing;
      const { close, overlay } = openDrawer({
        title: isEdit ? `Edit ${config.title.toLowerCase()}` : `New ${config.title.toLowerCase()}`,
        bodyHtml: `<form id="crud-form">${config.formFields(existing)}</form>`,
        footerHtml: `<button class="btn btn-ghost" data-act="cancel">Cancel</button><button class="btn btn-primary" data-act="save">${isEdit ? 'Save changes' : 'Create'}</button>`,
      });
      overlay.querySelector('[data-act=cancel]').onclick = close;
      overlay.querySelector('[data-act=save]').onclick = async () => {
        const form = overlay.querySelector('#crud-form');
        if (!form.reportValidity()) return;
        const raw = formToObject(form);
        const btn = overlay.querySelector('[data-act=save]');
        btn.disabled = true;
        try {
          if (isEdit) {
            await Api.patch(`${config.endpoint}/${existing[config.idKey || '_id']}`, config.toUpdatePayload(raw, existing));
            toast(`${config.title} updated`, 'success');
          } else {
            await Api.post(config.endpoint, config.toCreatePayload(raw));
            toast(`${config.title} created`, 'success');
          }
          close(); load();
        } catch (e) { toastError(e); }
        finally { btn.disabled = false; }
      };
    }

    root.querySelector('#crud-new').onclick = () => openForm(null);
    load();
  };
}
