import { API } from './api.config.js';
import { api } from './api.js';
import { mountShell } from './app-shell.js';
import { $, esc, currency, formatDate, statusBadge, toast, empty, modal } from './ui.js';

await mountShell('subscriptions');
const root = $('#main-content');
root.innerHTML = `<section class="page-head"><div><h2>Subscriptions</h2><p>Connect customers to service plans and manage their billing lifecycle.</p></div><button class="btn btn-primary" id="new-subscription">＋ Start subscription</button></section><section class="panel"><div class="table-tools"><input class="search-input" id="sub-search" placeholder="Search subscriber or plan…" aria-label="Search subscriptions"><span class="muted-small" id="sub-count"></span><button class="btn" id="sub-refresh">↻ Refresh</button></div><div id="sub-table"><div class="panel-body"><div class="skeleton"></div></div></div></section>`;
let subscriptions = [];
async function load() {
  const target = $('#sub-table'); target.innerHTML = '<div class="panel-body"><div class="skeleton"></div></div>';
  try {
    const r = await api.get(API.subscriptions, { page: 1, limit: 100 });
    subscriptions = api.rows(r); draw();
  } catch (e) { target.innerHTML = `<div class="error-state">${esc(e.message)}</div>`; }
}
function draw() {
  const q = $('#sub-search').value.trim().toLowerCase();
  const list = subscriptions.filter(s => !q || `${s.customer_name} ${s.customer_code} ${s.plan_name} ${s.status}`.toLowerCase().includes(q));
  $('#sub-count').textContent = `${list.length} subscriptions`;
  $('#sub-table').innerHTML = list.length ? `<div class="table-wrap table-responsive"><table><thead><tr><th>Subscriber</th><th>Plan</th><th>Status</th><th>Started</th><th>Expires</th><th>Days remaining</th><th>Monthly</th><th>Next bill</th><th>Actions</th></tr></thead><tbody>${list.map(s => {
    const days = s.end_date ? Math.ceil((new Date(s.end_date) - Date.now()) / 86400000) : null;
    return `<tr><td data-label="Subscriber"><strong>${esc(s.customer_name || s.customer_code || 'Customer')}</strong></td><td data-label="Plan">${esc(s.plan_name || s.plan_code || '—')}</td><td data-label="Status">${statusBadge(s.status)}</td><td data-label="Started">${formatDate(s.start_date)}</td><td data-label="Expires">${formatDate(s.end_date)}</td><td data-label="Days remaining">${days == null ? 'No end date' : `<div class="progress" style="width:100px"><span style="width:${Math.max(0,Math.min(100,days/30*100))}%"></span></div><small class="muted-small">${days} day${days===1?'':'s'}</small>`}</td><td data-label="Monthly">${currency(s.monthly_price_kes)}</td><td data-label="Next bill">${formatDate(s.next_billing_date)}</td><td data-label="Actions"><button class="btn" data-invoice="${esc(s._id)}">Invoice</button> <button class="btn" data-install="${esc(s._id)}">Installed</button> ${s.status==='active'?`<button class="btn btn-danger" data-cancel="${esc(s._id)}">Cancel</button>`:''}</td></tr>`;
  }).join('')}</tbody></table></div>` : empty('No subscriptions found','▧');
  $('#sub-table').querySelectorAll('[data-invoice]').forEach(b=>b.onclick=async()=>{try{const x=api.data(await api.post(`${API.subscriptions}/${b.dataset.invoice}/invoice`,{}));toast(`Invoice ${x.invoice_number} created`)}catch(e){toast(e.message,'error')}});
  $('#sub-table').querySelectorAll('[data-install]').forEach(b=>b.onclick=async()=>{try{await api.post(`${API.subscriptions}/${b.dataset.install}/install`,{});toast('Installation marked complete');load()}catch(e){toast(e.message,'error')}});
  $('#sub-table').querySelectorAll('[data-cancel]').forEach(b=>b.onclick=async()=>{if(!confirm('Cancel this subscription?'))return;try{await api.post(`${API.subscriptions}/${b.dataset.cancel}/cancel`,{});toast('Subscription cancelled');load()}catch(e){toast(e.message,'error')}});
}
function openCreate() {
  const m = modal('Start a service subscription', `<form id="sub-form"><div class="grid-2"><div class="field"><label>Customer</label><select name="customer_id" id="sub-customer" required><option value="">Loading customers…</option></select></div><div class="field"><label>Plan</label><select name="plan_id" id="sub-plan" required><option value="">Loading plans…</option></select></div><div class="field"><label>Start date</label><input type="date" name="start_date" required value="${new Date().toISOString().slice(0,10)}"></div><div class="field"><label>End date (optional)</label><input type="date" name="end_date"></div><div class="field"><label>Monthly price (KES)</label><input type="number" name="monthly_price_kes" min="0" step="any" required></div><div class="field"><label>Setup fee (KES)</label><input type="number" name="setup_fee_kes" min="0" step="any" value="0"></div><div class="field"><label>Equipment fee (KES)</label><input type="number" name="equipment_fee_kes" min="0" step="any" value="0"></div><div class="field"><label>Discount (KES)</label><input type="number" name="discount_kes" min="0" step="any" value="0"></div><div class="field"><label>Auto renew</label><select name="auto_renew"><option value="true">Yes</option><option value="false">No</option></select></div><div class="field" style="grid-column:1/-1"><label>Notes</label><textarea name="notes"></textarea></div></div><div class="notice" id="sub-form-error" hidden></div><button class="btn btn-primary">Create subscription</button></form>`);
  Promise.all([api.get(API.customers,{page:1,limit:100}),api.get(API.plans,{page:1,limit:100})]).then(([cr,pr])=>{
    const customers=api.rows(cr),plans=api.rows(pr),customerSelect=$('#sub-customer',m.host),planSelect=$('#sub-plan',m.host);
    customerSelect.innerHTML='<option value="">Choose a customer</option>'+customers.map(x=>`<option value="${esc(x._id)}">${esc(x.full_name)} · ${esc(x.customer_code)}</option>`).join('');
    planSelect.innerHTML='<option value="">Choose a service plan</option>'+plans.map(x=>`<option value="${esc(x._id)}" data-price="${Number(x.base_price_kes)||0}">${esc(x.name)} · ${currency(x.base_price_kes)}</option>`).join('');
    const selected=new URLSearchParams(location.search).get('plan');if(selected)planSelect.value=selected;
    planSelect.onchange=()=>{const price=planSelect.selectedOptions[0]?.dataset.price;if(price)$('#sub-form',m.host).monthly_price_kes.value=price};
  }).catch(e=>{const err=$('#sub-form-error',m.host);err.hidden=false;err.textContent=e.message});
  $('#sub-form',m.host).onsubmit=async e=>{e.preventDefault();const f=new FormData(e.target);const body={customer_id:f.get('customer_id'),plan_id:f.get('plan_id'),start_date:new Date(f.get('start_date')).toISOString(),end_date:f.get('end_date')?new Date(f.get('end_date')).toISOString():null,monthly_price_kes:+f.get('monthly_price_kes'),setup_fee_kes:+f.get('setup_fee_kes'),equipment_fee_kes:+f.get('equipment_fee_kes'),discount_kes:+f.get('discount_kes'),auto_renew:f.get('auto_renew')==='true',notes:f.get('notes')||null};try{await api.post(API.subscriptions,body);m.close();toast('Subscription created');load()}catch(x){const err=$('#sub-form-error',m.host);err.hidden=false;err.textContent=x.message}};
}
$('#new-subscription').onclick=openCreate;$('#sub-refresh').onclick=load;$('#sub-search').oninput=draw;await load();
