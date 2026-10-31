import { mountCustomerPage, pageTitle, PAPI, portalApi } from './shell.js';
import { $, toast } from './ui.js';

const profile = await mountCustomerPage('profile.html');
const main = $('#customer-main');
if (profile && main) {
  main.innerHTML = `${pageTitle('Profile & security', 'Keep your contact details current and protect your account.')}
    <section class="customer-columns"><article class="panel panel-body"><h3>Contact details</h3><form id="profile-form"><label class="field-label" for="profile-name">Full name</label><input class="input" id="profile-name" name="full_name" maxlength="100" required><label class="field-label" for="profile-phone">Phone number</label><input class="input" id="profile-phone" name="phone" inputmode="tel"><label class="field-label" for="profile-email">Email</label><input class="input" id="profile-email" type="email" disabled><button class="btn btn-primary" type="submit">Save profile</button><p id="profile-feedback" class="muted-small" role="status"></p></form></article>
    <article class="panel panel-body"><h3>Change password</h3><form id="password-form"><label class="field-label" for="current-password">Current password</label><input class="input" id="current-password" name="current_password" type="password" autocomplete="current-password" required><label class="field-label" for="new-password">New password</label><input class="input" id="new-password" name="new_password" type="password" minlength="8" autocomplete="new-password" required><p class="muted-small">Use at least 8 characters with uppercase, lowercase and a number.</p><button class="btn btn-primary" type="submit">Update password</button><p id="password-feedback" class="muted-small" role="status"></p></form></article></section>`;
  $('#profile-name').value = profile.full_name || '';
  $('#profile-phone').value = profile.phone || '';
  $('#profile-email').value = profile.email || '';
  $('#profile-form').addEventListener('submit', async (event) => {
    event.preventDefault(); const button = event.currentTarget.querySelector('button'); button.disabled = true;
    try {
      const response = await portalApi.patch(PAPI.authMe, {
        full_name: $('#profile-name').value.trim(), phone: $('#profile-phone').value.trim() || null,
      });
      const updated = portalApi.data(response); localStorage.setItem('dz_portal_profile', JSON.stringify(updated));
      $('#profile-feedback').textContent = 'Your contact details have been updated.'; toast('Profile saved', 'success');
    } catch (error) { $('#profile-feedback').textContent = error.message; }
    finally { button.disabled = false; }
  });
  $('#password-form').addEventListener('submit', async (event) => {
    event.preventDefault(); const form = event.currentTarget; const button = form.querySelector('button'); button.disabled = true;
    const newPassword = $('#new-password').value;
    if (!/[A-Z]/.test(newPassword) || !/[a-z]/.test(newPassword) || !/[0-9]/.test(newPassword)) {
      $('#password-feedback').textContent = 'Use an uppercase letter, lowercase letter and number.'; button.disabled = false; return;
    }
    try {
      await portalApi.post(PAPI.changePassword, {
        current_password: $('#current-password').value, new_password: newPassword,
      });
      form.reset(); $('#password-feedback').textContent = 'Password changed. Sign in again with your new password.';
      toast('Password changed. Please sign in again.', 'success');
      localStorage.removeItem('dz_portal_token');
      localStorage.removeItem('dz_portal_refresh_token');
      localStorage.removeItem('dz_portal_profile');
      setTimeout(() => location.replace('./index.html'), 1200);
    } catch (error) { $('#password-feedback').textContent = error.message; }
    finally { button.disabled = false; }
  });
}
