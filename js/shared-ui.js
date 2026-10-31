/** Small, dependency-free helpers shared by the mounted browser applications. */
export const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
}[char]));

export function formatKes(value) {
  const amount = Number(value);
  return Number.isFinite(amount) ? `KES ${new Intl.NumberFormat('en-KE', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(amount)}` : '—';
}

export function formatDate(value, options = { dateStyle: 'medium' }) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '—' : new Intl.DateTimeFormat('en-KE', options).format(date);
}

export function debounce(callback, wait = 250) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => callback(...args), wait);
  };
}

export function announce(message, type = 'info') {
  window.dispatchEvent(new CustomEvent('dz:toast', { detail: { message: String(message), type } }));
}

export function setBusy(button, busy, label = 'Working…') {
  if (!button) return;
  if (busy) {
    button.dataset.idleLabel = button.textContent;
    button.disabled = true;
    button.setAttribute('aria-busy', 'true');
    button.textContent = label;
  } else {
    button.disabled = false;
    button.removeAttribute('aria-busy');
    if (button.dataset.idleLabel !== undefined) button.textContent = button.dataset.idleLabel;
    delete button.dataset.idleLabel;
  }
}
