/**
 * frontend/js/verify.js — Entry point for signup verification (OTP).
 */

import { handleVerify, handleResend, initOTPInputs, startCountdown } from './auth.js';

// Must arrive here from signup form only
const email = sessionStorage.getItem('docuchat_pending_email');
const pendingEmailEl = document.getElementById('pendingEmail');

if (!email) {
  window.location.href = 'signup.html';
} else if (pendingEmailEl) {
  pendingEmailEl.textContent = email;
}

const verifyForm = document.getElementById('verifyForm');
if (verifyForm) {
  verifyForm.addEventListener('submit', handleVerify);
}

const resendBtn = document.getElementById('resendBtn');
if (resendBtn) {
  resendBtn.addEventListener('click', handleResend);
}

initOTPInputs();
startCountdown(60);
