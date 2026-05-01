/**
 * frontend/js/reset_password.js — Entry point for password reset page.
 */

import { handleResetPassword, togglePasswordVisibility } from './auth.js';

if (!sessionStorage.getItem('docuchat_reset_token')) {
  window.location.href = 'forgot_password.html';
}

const resetPasswordForm = document.getElementById('resetPasswordForm');
if (resetPasswordForm) {
  resetPasswordForm.addEventListener('submit', handleResetPassword);
}

togglePasswordVisibility('newPassword', 'newPwToggle');
togglePasswordVisibility('confirmNewPassword', 'confirmNewPwToggle');
