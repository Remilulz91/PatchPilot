/* PatchPilot — login page */
"use strict";

const form = document.getElementById('login-form');
const totpBlock = document.getElementById('totp-block');
const errEl = document.getElementById('error');
const totpInput = document.getElementById('totp');

// Toggle between 6-digit TOTP and a longer recovery code.
let recoveryMode = false;
document.getElementById('use-recovery').addEventListener('click', (e) => {
  e.preventDefault();
  recoveryMode = !recoveryMode;
  if (recoveryMode) {
    totpInput.removeAttribute('maxlength');
    totpInput.setAttribute('inputmode', 'text');
    totpInput.value = '';
    totpInput.placeholder = 'xxxx-xxxx';
    document.getElementById('totp-label').textContent = t('recovery_code');
    document.getElementById('use-recovery').textContent = t('use_totp');
  } else {
    totpInput.setAttribute('maxlength', '6');
    totpInput.setAttribute('inputmode', 'numeric');
    totpInput.value = '';
    totpInput.placeholder = '';
    document.getElementById('totp-label').textContent = t('mfa_code');
    document.getElementById('use-recovery').textContent = t('use_recovery');
  }
  totpInput.focus();
});

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
