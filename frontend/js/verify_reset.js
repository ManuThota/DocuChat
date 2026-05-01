/**
 * frontend/js/verify_reset.js — Entry point for password reset verification (OTP).
 */

import { handleVerifyReset, initOTPInputs } from './auth.js';

const email = sessionStorage.getItem('docuchat_reset_email');
const resetEmailEl = document.getElementById('resetEmail');

if (!email) {
  window.location.href = 'forgot_password.html';
} else if (resetEmailEl) {
  resetEmailEl.textContent = email;
}

initOTPInputs();

const verifyResetForm = document.getElementById('verifyResetForm');
if (verifyResetForm) {
  verifyResetForm.addEventListener('submit', handleVerifyReset);
}
