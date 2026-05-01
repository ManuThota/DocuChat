/**
 * frontend/js/forgot_password.js — Entry point for forgot password page.
 */

import { handleForgotPassword } from './auth.js';

const forgotForm = document.getElementById('forgotForm');
if (forgotForm) {
  forgotForm.addEventListener('submit', handleForgotPassword);
}
