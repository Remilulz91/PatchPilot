/* PatchPilot — MFA setup page */
"use strict";

const errEl = document.getElementById('error');

(async () => {
  const r = await fetch('/api/mfa/qr');
  if (!r.ok) { window.location.href = '/'; return; }
  const data = await r.json();
  document.getElementById('qr').src = data.qr;
  document.getElementById('secret').textContent = data.secret;
})();

document.getElementById('mfa-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  errEl.textContent = '';
  const csrf = (document.cookie.match(/(?:^|;\s*)pp_csrf=([^;]+)/) || [])[1];
  const r = await fetch('/api/mfa/verify', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf ? decodeURIComponent(csrf) : '' },
    body: JSON.stringify({ code: document.getElementById('code').value.trim() }),
  });
  const data = await r.json();
  if (!r.ok) { errEl.textContent = tServer(data.detail) || t('invalid_code'); return; }

  const redirect = data.redirect || '/';
  if (data.recovery_codes && data.recovery_codes.length) {
    showRecoveryCodes(data.recovery_codes, redirect);
  } else {
    window.location.href = redirect;
  }
});

function showRecoveryCodes(codes, redirect) {
  document.getElementById('mfa-form').style.display = 'none';
  const grid = document.getElementById('recovery-grid');
  grid.innerHTML = '';
  for (const c of codes) {
    const span = document.createElement('span');
    span.textContent = c;
    grid.appendChild(span);
  }
  document.getElementById('recovery-panel').style.display = 'block';
  document.getElementById('btn-copy-rc').addEventListener('click', () => {
    navigator.clipboard.writeText(codes.join('\n'));
  });
  document.getElementById('btn-rc-continue').addEventListener('click', () => {
    window.location.href = redirect;
  });
}
