/* PatchPilot — login page */
"use strict";

const form = document.getElementById('login-form');
const totpBlock = document.getElementById('totp-block');
const errEl = document.getElementById('error');

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  errEl.textContent = '';
  const body = {
    username: document.getElementById('username').value,
    password: document.getElementById('password').value,
  };
  const totp = document.getElementById('totp').value.trim();
  if (totp) body.totp_code = totp;

  try {
    const r = await fetch('/api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await r.json();
    if (!r.ok) { errEl.textContent = tServer(data.detail) || t('error'); return; }
    if (data.mfa_code_required) {
      totpBlock.style.display = 'block';
      document.getElementById('totp').focus();
      errEl.textContent = t('enter_mfa');
      return;
    }
    window.location.href = data.redirect || '/';
  } catch {
    errEl.textContent = t('network_error');
  }
});
