import { mountCustomerPage, pageTitle } from './shell.js';
import { $ } from './ui.js';

await mountCustomerPage('packages.html');
const main = $('#customer-main');
if (main) main.innerHTML = `${pageTitle('Internet packages', 'Plan changes and renewals for your account.')}
  <section class="panel panel-body"><div class="eyebrow">CUSTOMER PORTAL</div><h3>Online plan changes are not available here yet</h3>
  <p class="muted">The current API does not provide a customer-scoped package catalog or a customer subscription purchase endpoint. Your account and current subscription remain available in this portal.</p>
  <p><a class="btn btn-primary" href="./support.html">Contact support</a> <a class="btn" href="./subscription.html">View my subscription</a></p>
  <p class="muted-small">For HotSpot access vouchers, use the public <a href="/hotspot/">DEVZEN CREATIONS HotSpot portal</a>. It shows only packages allowed by its current public catalog and trusted device context.</p></section>`;
