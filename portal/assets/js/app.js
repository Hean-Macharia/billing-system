document.addEventListener('DOMContentLoaded', () => {
  Router.register('#/dashboard', Pages.dashboard);
  Router.register('#/subscription', Pages.subscription);
  Router.register('#/billing', Pages.billing);
  Router.register('#/payments', Pages.payments);
  Router.register('#/usage', Pages.usage);
  Router.register('#/support', Pages.support);

  if (!location.hash) location.hash = Api.isAuthed() ? '#/dashboard' : '#/login';
  Router.render();
});
