Pages.support = async function (root) {
  root.innerHTML = `
    <button class="btn btn-primary btn-block" id="new-ticket" style="margin-bottom:14px;">${Icons.plus} New support request</button>
    <div class="card card-flush">
      <div class="card-head" style="padding:16px 18px 0;"><h2>Your tickets</h2></div>
      <div id="ticket-list"><div class="center-loading"><div class="spinner"></div></div></div>
    </div>`;

  async function load() {
    const res = await Api.get('/api/v1/portal/support/tickets', { limit: 50 });
    const tickets = res.data;
    root.querySelector('#ticket-list').innerHTML = renderList({
      rows: tickets, emptyTitle: 'No support requests yet', emptyBody: 'Need help? Tap "New support request" above.',
      renderRow: t => `
        <div class="list-row" data-id="${t._id}" style="cursor:pointer;">
          <div class="main">
            <div class="title">${escapeHtml(t.subject)}</div>
            <div class="sub">${escapeHtml(t.ticket_number)} · ${fmtDate(t.updated_at)}</div>
          </div>
          <div class="right">${statusBadge(t.status)}</div>
        </div>`,
    });
    root.querySelectorAll('[data-id]').forEach(row => row.onclick = () => viewTicket(row.dataset.id));
  }

  function viewTicket(id) {
    const bodyHtml = `<div id="thread-body"><div class="center-loading"><div class="spinner"></div></div></div>`;
    const { overlay } = openSheet({
      title: 'Support request', bodyHtml,
      footerHtml: `
        <form id="reply-form" style="display:flex;gap:8px;">
          <input type="text" name="message" placeholder="Type a reply…" required style="flex:1;"/>
          <button class="btn btn-primary" type="submit">${Icons.send}</button>
        </form>`,
    });

    async function loadThread() {
      const res = await Api.get(`/api/v1/portal/support/tickets/${id}`);
      const t = res.data;
      overlay.querySelector('.sheet-head h3').textContent = t.subject;
      overlay.querySelector('#thread-body').innerHTML = `
        <div style="margin-bottom:12px;">${statusBadge(t.status)} <span class="mono" style="font-size:11.5px;color:var(--muted);margin-left:6px;">${escapeHtml(t.ticket_number)}</span></div>
        <div class="thread">
          ${t.messages.map(m => `
            <div class="msg ${m.sender_role === 'customer' ? 'customer' : 'staff'}">
              ${escapeHtml(m.body)}
              <div class="meta">${escapeHtml(m.sender_role === 'customer' ? 'You' : m.sender_name)} · ${fmtDateTime(m.created_at)}</div>
            </div>`).join('')}
        </div>`;
      overlay.querySelector('#thread-body').scrollTop = overlay.querySelector('#thread-body').scrollHeight;
    }

    overlay.querySelector('#reply-form').addEventListener('submit', async (e) => {
      e.preventDefault();
      const { message } = formToObject(e.target);
      if (!message.trim()) return;
      e.target.reset();
      try {
        await Api.post(`/api/v1/portal/support/tickets/${id}/reply`, { message });
        loadThread(); load();
      } catch (err) { toastError(err); }
    });

    loadThread();
  }

  root.querySelector('#new-ticket').onclick = () => {
    const bodyHtml = `
      <form id="new-ticket-form">
        <div class="field-row">
          <label class="field-label">What's this about?</label>
          <select name="category">
            <option value="connectivity">My internet isn't working</option>
            <option value="billing">Billing question</option>
            <option value="installation">Installation request</option>
            <option value="account">Account details</option>
            <option value="other">Something else</option>
          </select>
        </div>
        <div class="field-row">
          <label class="field-label">Subject</label>
          <input type="text" name="subject" required placeholder="Short summary"/>
        </div>
        <div class="field-row">
          <label class="field-label">Message</label>
          <textarea name="message" required placeholder="Describe the issue…"></textarea>
        </div>
      </form>`;
    const { close, overlay } = openSheet({
      title: 'New support request', bodyHtml,
      footerHtml: `<button class="btn btn-primary btn-block" id="ticket-submit">Submit request</button>`,
    });
    overlay.querySelector('#ticket-submit').onclick = async () => {
      const form = overlay.querySelector('#new-ticket-form');
      if (!form.reportValidity()) return;
      const raw = formToObject(form);
      const btn = overlay.querySelector('#ticket-submit');
      btn.disabled = true;
      try {
        await Api.post('/api/v1/portal/support/tickets', raw);
        toast('Support request submitted', 'success');
        close(); load();
      } catch (e) { toastError(e); }
      finally { btn.disabled = false; }
    };
  };

  load();
};
