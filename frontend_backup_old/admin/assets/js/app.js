/*
  App bootstrap
  -------------
  Registers every page against the router, then kicks off the first
  render. Auth guarding happens inside Router.render() itself.
*/
document.addEventListener('DOMContentLoaded', () => {
  Router.register('#/dashboard', Pages.dashboard);
  Router.register('#/customers', Pages.customers);
  Router.register('#/packages', Pages.packages);
  Router.register('#/services', Pages.services);
  Router.register('#/subscriptions', Pages.subscriptions);
  Router.register('#/billing', Pages.billing);
  Router.register('#/payments', Pages.payments);
  Router.register('#/vouchers', Pages.vouchers);
  Router.register('#/sites', Pages.sites);
  Router.register('#/routers', Pages.routers);
  Router.register('#/sessions', Pages.sessions);
  Router.register('#/reports', Pages.reports);

  if (!location.hash) location.hash = Api.isAuthed() ? '#/dashboard' : '#/login';
  Router.render();
});
