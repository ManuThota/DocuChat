/**
 * frontend/js/signup.js — Entry point for signup page.
 */

import { Auth } from './api.js';
import { handleSignup, togglePasswordVisibility } from './auth.js';

// Redirect if already logged in
if (Auth.isLoggedIn()) {
  window.location.href = 'dashboard.html';
}

const signupForm = document.getElementById('signupForm');
if (signupForm) {
  signupForm.addEventListener('submit', handleSignup);
}

togglePasswordVisibility('signupPassword', 'signupPwToggle');
togglePasswordVisibility('signupConfirm', 'signupConfirmToggle');
