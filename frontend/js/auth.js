/* auth.js — Login & Register Form Handling, Session Bootstrap, Password Visibility & Logout */

/* ==========================================================================
   ALERT & BANNER UTILITIES
   ========================================================================== */

function showLoginAlert(message, isSuccess = false) {
  const alertBox = document.getElementById('login-alert');
  const alertText = document.getElementById('login-alert-text');
  const alertIcon = document.getElementById('login-alert-icon');
  if (alertBox && alertText) {
    alertText.textContent = message;
    if (isSuccess) {
      alertBox.classList.add('login-alert-success');
      if (alertIcon) alertIcon.textContent = '✓';
    } else {
      alertBox.classList.remove('login-alert-success');
      if (alertIcon) alertIcon.textContent = '⚠️';
    }
    alertBox.style.display = 'flex';
  }
}

function hideLoginAlert() {
  const alertBox = document.getElementById('login-alert');
  if (alertBox) {
    alertBox.style.display = 'none';
    alertBox.classList.remove('login-alert-success');
  }
}

function showRegisterAlert(message, htmlContent = null) {
  const alertBox = document.getElementById('register-alert');
  const alertText = document.getElementById('register-alert-text');
  const alertIcon = document.getElementById('register-alert-icon');
  if (alertBox && alertText) {
    if (htmlContent) {
      alertText.innerHTML = htmlContent;
    } else {
      alertText.textContent = message;
    }
    if (alertIcon) alertIcon.textContent = '⚠️';
    alertBox.style.display = 'flex';
  }
}

function hideRegisterAlert() {
  const alertBox = document.getElementById('register-alert');
  if (alertBox) {
    alertBox.style.display = 'none';
  }
}

function showLoginInfoBanner(message) {
  const banner = document.getElementById('login-info-banner');
  const bannerText = document.getElementById('login-info-banner-text');
  if (banner && bannerText) {
    bannerText.textContent = message;
    banner.style.display = 'flex';
  }
}

function dismissLoginInfoBanner() {
  const banner = document.getElementById('login-info-banner');
  if (banner) {
    banner.style.display = 'none';
  }
}

function showFieldError(fieldId, message) {
  const errEl = document.getElementById(`${fieldId}-error`);
  const inputEl = document.getElementById(fieldId);
  if (errEl) {
    errEl.textContent = message;
    errEl.classList.add('active');
  }
  if (inputEl) {
    inputEl.classList.add('input-invalid');
  }
}

function clearFieldError(fieldId) {
  const errEl = document.getElementById(`${fieldId}-error`);
  const inputEl = document.getElementById(fieldId);
  if (errEl) {
    errEl.textContent = '';
    errEl.classList.remove('active');
  }
  if (inputEl) {
    inputEl.classList.remove('input-invalid');
  }
}

function clearAllRegisterErrors() {
  hideRegisterAlert();
  clearFieldError('register-email');
  clearFieldError('register-password');
  clearFieldError('register-confirm-password');
}

/* ==========================================================================
   PASSWORD VISIBILITY TOGGLES
   ========================================================================== */

function togglePasswordVisibility() {
  const input = document.getElementById('login-password');
  const icon = document.getElementById('toggle-password-icon');
  const btn = document.getElementById('btn-toggle-password');
  if (!input) return;

  if (input.type === 'password') {
    input.type = 'text';
    if (icon) icon.textContent = '🔒';
    if (btn) {
      btn.setAttribute('aria-label', 'Hide password');
      btn.title = 'Hide password';
    }
  } else {
    input.type = 'password';
    if (icon) icon.textContent = '👁';
    if (btn) {
      btn.setAttribute('aria-label', 'Show password');
      btn.title = 'Show password';
    }
  }
}

function toggleRegisterPasswordVisibility() {
  const input = document.getElementById('register-password');
  const icon = document.getElementById('toggle-register-password-icon');
  const btn = document.getElementById('btn-toggle-register-password');
  if (!input) return;

  if (input.type === 'password') {
    input.type = 'text';
    if (icon) icon.textContent = '🔒';
    if (btn) {
      btn.setAttribute('aria-label', 'Hide password');
      btn.title = 'Hide password';
    }
  } else {
    input.type = 'password';
    if (icon) icon.textContent = '👁';
    if (btn) {
      btn.setAttribute('aria-label', 'Show password');
      btn.title = 'Show password';
    }
  }
}

function toggleRegisterConfirmPasswordVisibility() {
  const input = document.getElementById('register-confirm-password');
  const icon = document.getElementById('toggle-register-confirm-icon');
  const btn = document.getElementById('btn-toggle-register-confirm');
  if (!input) return;

  if (input.type === 'password') {
    input.type = 'text';
    if (icon) icon.textContent = '🔒';
    if (btn) {
      btn.setAttribute('aria-label', 'Hide confirm password');
      btn.title = 'Hide confirm password';
    }
  } else {
    input.type = 'password';
    if (icon) icon.textContent = '👁';
    if (btn) {
      btn.setAttribute('aria-label', 'Show confirm password');
      btn.title = 'Show confirm password';
    }
  }
}

/* ==========================================================================
   PASSWORD STRENGTH METER (CLIENT-SIDE GUIDANCE)
   ========================================================================== */

function evaluatePasswordStrength(password) {
  if (!password || password.length === 0) {
    return { score: 0, label: '', hint: 'At least 8 characters' };
  }

  let score = 0;
  if (password.length >= 8) score += 1;
  if (password.length >= 10 && (/[A-Z]/.test(password) || /[0-9]/.test(password))) score += 1;
  if (password.length >= 12 && /[A-Z]/.test(password) && /[0-9]/.test(password) && /[^a-zA-Z0-9]/.test(password)) score += 1;

  if (password.length < 8) {
    return { score: 1, label: 'Weak', hint: 'Must be at least 8 characters' };
  }

  if (score === 1) {
    return { score: 1, label: 'Weak', hint: 'Add numbers, symbols or uppercase' };
  } else if (score === 2) {
    return { score: 2, label: 'Fair', hint: 'Good, add symbols for strong' };
  } else {
    return { score: 3, label: 'Strong', hint: 'Excellent password security' };
  }
}

function handleRegisterPasswordInput() {
  clearFieldError('register-password');
  const password = document.getElementById('register-password').value;
  const container = document.getElementById('password-strength-container');
  const b1 = document.getElementById('str-bar-1');
  const b2 = document.getElementById('str-bar-2');
  const b3 = document.getElementById('str-bar-3');
  const label = document.getElementById('str-label');
  const hint = document.getElementById('str-hint');

  if (!container || !b1 || !b2 || !b3 || !label) return;

  if (!password) {
    container.style.display = 'none';
    return;
  }

  container.style.display = 'flex';
  const strength = evaluatePasswordStrength(password);

  b1.className = 'strength-bar';
  b2.className = 'strength-bar';
  b3.className = 'strength-bar';

  if (strength.score === 1) {
    b1.classList.add('weak');
    label.textContent = strength.label;
    label.style.color = 'var(--color-danger)';
  } else if (strength.score === 2) {
    b1.classList.add('fair');
    b2.classList.add('fair');
    label.textContent = strength.label;
    label.style.color = 'var(--color-amber)';
  } else if (strength.score >= 3) {
    b1.classList.add('strong');
    b2.classList.add('strong');
    b3.classList.add('strong');
    label.textContent = strength.label;
    label.style.color = 'var(--accent-primary)';
  }

  if (hint && strength.hint) {
    hint.textContent = strength.hint;
  }
}

/* ==========================================================================
   VIEW NAVIGATION: LOGIN <-> REGISTER
   ========================================================================== */

function switchToRegisterView() {
  hideLoginAlert();
  dismissLoginInfoBanner();
  clearAllRegisterErrors();

  const loginView = document.getElementById('login-view');
  const registerView = document.getElementById('register-view');
  if (loginView) loginView.style.display = 'none';
  if (registerView) {
    registerView.style.display = 'flex';
    const emailInput = document.getElementById('register-email');
    if (emailInput) setTimeout(() => emailInput.focus(), 80);
  }
}

function switchToLoginView(prefilledEmail = null, successMessage = null) {
  clearAllRegisterErrors();
  hideLoginAlert();
  dismissLoginInfoBanner();

  const registerView = document.getElementById('register-view');
  const loginView = document.getElementById('login-view');
  if (registerView) registerView.style.display = 'none';
  if (loginView) {
    loginView.style.display = 'flex';

    const emailInput = document.getElementById('login-email');
    const passwordInput = document.getElementById('login-password');

    if (prefilledEmail && emailInput) {
      emailInput.value = prefilledEmail;
      if (passwordInput) setTimeout(() => passwordInput.focus(), 80);
    } else if (emailInput) {
      setTimeout(() => emailInput.focus(), 80);
    }

    if (successMessage) {
      showLoginAlert(successMessage, true);
    }
  }
}

function handleForgotPasswordClick() {
  showLoginInfoBanner("Password recovery will be supported in an upcoming update. Please sign in with your account credentials.");
}

function handleCreateAccountClick() {
  switchToRegisterView();
}

/* ==========================================================================
   LOGIN SUBMISSION
   ========================================================================== */

async function handleLoginSubmit(event) {
  if (event) event.preventDefault();
  hideLoginAlert();
  dismissLoginInfoBanner();

  const emailInput = document.getElementById('login-email');
  const passwordInput = document.getElementById('login-password');
  const submitBtn = document.getElementById('btn-login-submit');
  const btnText = document.getElementById('btn-login-text');
  const btnSpinner = document.getElementById('btn-login-spinner');

  if (!emailInput || !passwordInput) return;

  const email = emailInput.value.trim();
  const password = passwordInput.value;

  // Frontend validation
  if (!email) {
    showLoginAlert("Please enter your email address.");
    emailInput.focus();
    return;
  }

  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  if (!emailRegex.test(email)) {
    showLoginAlert("Please enter a valid email address (e.g. name@example.com).");
    emailInput.focus();
    return;
  }

  if (!password) {
    showLoginAlert("Please enter your password.");
    passwordInput.focus();
    return;
  }

  // Loading state
  if (submitBtn) submitBtn.disabled = true;
  if (btnText) btnText.style.display = 'none';
  if (btnSpinner) btnSpinner.style.display = 'inline';

  try {
    const data = await API.login(email, password);
    if (data && data.user) {
      currentUser = data.user;
      isAuthenticated = true;
      transitionToAuthenticatedApp(currentUser);
    }
  } catch (err) {
    const msg = (err && err.message) ? err.message : "Unable to connect. Please try again.";
    showLoginAlert(msg);
  } finally {
    if (submitBtn) submitBtn.disabled = false;
    if (btnText) btnText.style.display = 'inline';
    if (btnSpinner) btnSpinner.style.display = 'none';
  }
}

/* ==========================================================================
   REGISTRATION SUBMISSION
   ========================================================================== */

async function handleRegisterSubmit(event) {
  if (event) event.preventDefault();
  clearAllRegisterErrors();

  const emailInput = document.getElementById('register-email');
  const passwordInput = document.getElementById('register-password');
  const confirmInput = document.getElementById('register-confirm-password');
  const submitBtn = document.getElementById('btn-register-submit');
  const btnText = document.getElementById('btn-register-text');
  const btnSpinner = document.getElementById('btn-register-spinner');

  if (!emailInput || !passwordInput || !confirmInput) return;

  const email = emailInput.value.trim();
  const password = passwordInput.value;
  const confirmPassword = confirmInput.value;

  // Client-side validations
  let hasError = false;

  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  if (!email) {
    showFieldError('register-email', 'Please enter your email address.');
    emailInput.focus();
    hasError = true;
  } else if (!emailRegex.test(email)) {
    showFieldError('register-email', 'Please enter a valid email address (e.g. name@example.com).');
    emailInput.focus();
    hasError = true;
  }

  if (!password) {
    showFieldError('register-password', 'Please enter a password.');
    if (!hasError) passwordInput.focus();
    hasError = true;
  } else if (password.length < 8) {
    showFieldError('register-password', 'Password must be at least 8 characters long.');
    if (!hasError) passwordInput.focus();
    hasError = true;
  }

  if (!confirmPassword) {
    showFieldError('register-confirm-password', 'Please confirm your password.');
    if (!hasError) confirmInput.focus();
    hasError = true;
  } else if (password && confirmPassword && password !== confirmPassword) {
    showFieldError('register-confirm-password', 'Passwords do not match. Please re-enter.');
    if (!hasError) confirmInput.focus();
    hasError = true;
  }

  if (hasError) return;

  // Loading state
  if (submitBtn) submitBtn.disabled = true;
  if (btnText) btnText.style.display = 'none';
  if (btnSpinner) btnSpinner.style.display = 'inline';

  try {
    const data = await API.register(email, password);
    // Success: backend created user profile
    if (data && (data.id || data.email)) {
      // Clear registration inputs
      emailInput.value = '';
      passwordInput.value = '';
      confirmInput.value = '';
      document.getElementById('password-strength-container').style.display = 'none';

      // Switch to Login view, prefill email, and display success banner
      switchToLoginView(email, 'Account created successfully! Please sign in with your password.');
    }
  } catch (err) {
    const rawMsg = (err && err.message) ? err.message : '';
    if (rawMsg.toLowerCase().includes('already exists')) {
      showRegisterAlert(
        `An account with this email already exists.`,
        `An account with this email already exists. <button type="button" class="alert-action-btn" id="btn-alert-signin">Sign in instead</button>`
      );
      const signinBtn = document.getElementById('btn-alert-signin');
      if (signinBtn) {
        signinBtn.onclick = () => switchToLoginView(email);
      }
      showFieldError('register-email', 'Email is already registered.');
      emailInput.focus();
    } else {
      showRegisterAlert(rawMsg || 'Unable to create account. Please check your network connection and try again.');
    }
  } finally {
    if (submitBtn) submitBtn.disabled = false;
    if (btnText) btnText.style.display = 'inline';
    if (btnSpinner) btnSpinner.style.display = 'none';
  }
}

/* ==========================================================================
   AUTHENTICATED SESSION TRANSITIONS
   ========================================================================== */

function transitionToAuthenticatedApp(user) {
  // Update header state
  const headerActions = document.getElementById('header-authenticated-actions');
  const userEmail = document.getElementById('header-user-email');
  const userName = document.getElementById('header-user-name');
  const avatarBadge = document.getElementById('header-avatar-badge');

  if (headerActions) headerActions.style.display = 'flex';
  if (userEmail) {
    userEmail.textContent = (user && user.email) ? user.email : 'Learner';
  }
  if (userName) {
    userName.textContent = (user && user.email) ? user.email.split('@')[0] : 'Learner';
  }
  if (avatarBadge) {
    avatarBadge.textContent = (user && user.email) ? user.email[0].toUpperCase() : 'U';
  }

  // Load enriched profile if available
  if (typeof loadHeaderProfile === 'function') {
    loadHeaderProfile();
  }

  // Hide login and register views, reveal app workspace
  const loginView = document.getElementById('login-view');
  const registerView = document.getElementById('register-view');
  const appWorkspace = document.getElementById('app-workspace');
  if (loginView) loginView.style.display = 'none';
  if (registerView) registerView.style.display = 'none';
  if (appWorkspace) {
    appWorkspace.style.display = 'block';
  }

  // Load user's recent journeys
  if (typeof loadRecentJourneys === 'function') {
    loadRecentJourneys();
  }

  // Check LLM status
  if (typeof checkLlmStatus === 'function') {
    checkLlmStatus();
  }

  // Check for deep-linked journey or note
  const params = new URLSearchParams(window.location.search);
  const jid = params.get('journey_id');
  const nid = params.get('note_id');

  if (jid) {
    API.requestOrNull(`/journeys/${jid}/note`).then(note => {
      if (note) {
        currentJourneyId = jid;
        if (typeof resetCopilotState === 'function') resetCopilotState();
        if (typeof renderNote === 'function') renderNote(note);
      }
    }).catch(e => console.warn("Could not load deep-linked note:", e));
  } else if (nid) {
    API.requestOrNull(`/notes/${nid}`).then(note => {
      if (note) {
        currentJourneyId = note.journey_id;
        if (typeof resetCopilotState === 'function') resetCopilotState();
        if (typeof renderNote === 'function') renderNote(note);
      }
    }).catch(e => console.warn("Could not load deep-linked note:", e));
  }
}

async function handleLogout() {
  try {
    await API.logout();
  } catch (err) {
    console.warn("Logout error:", err);
  } finally {
    handleUnauthenticatedSession();
  }
}

function handleUnauthenticatedSession() {
  currentUser = null;
  isAuthenticated = false;
  currentProfile = null;
  currentLearnerSettings = null;
  currentJourneyId = null;
  currentNote = null;

  // Update header
  const headerActions = document.getElementById('header-authenticated-actions');
  const userEmail = document.getElementById('header-user-email');
  const userName = document.getElementById('header-user-name');
  const avatarBadge = document.getElementById('header-avatar-badge');

  if (headerActions) headerActions.style.display = 'none';
  if (userEmail) userEmail.textContent = '';
  if (userName) userName.textContent = 'Learner';
  if (avatarBadge) avatarBadge.textContent = '?';

  // Close any open modals or drawers
  document.querySelectorAll('.modal-overlay').forEach(modal => {
    modal.style.display = 'none';
  });
  if (typeof closeCopilotDrawer === 'function') closeCopilotDrawer();

  // Hide application workspace and register view, reveal login
  const appWorkspace = document.getElementById('app-workspace');
  const registerView = document.getElementById('register-view');
  const loginView = document.getElementById('login-view');
  if (appWorkspace) appWorkspace.style.display = 'none';
  if (registerView) registerView.style.display = 'none';
  if (loginView) {
    loginView.style.display = 'flex';
    hideLoginAlert();
    dismissLoginInfoBanner();
    const emailInput = document.getElementById('login-email');
    if (emailInput) setTimeout(() => emailInput.focus(), 100);
  }
}

/**
 * Bootstrap authentication session on initial application load.
 * Verifies with /auth/me to check if a valid HttpOnly session cookie exists.
 */
async function bootstrapAuthSession() {
  try {
    const user = await API.getMe();
    if (user && user.id) {
      currentUser = user;
      isAuthenticated = true;
      transitionToAuthenticatedApp(user);
      return;
    }
  } catch (e) {
    // Unauthenticated or network error
  }
  handleUnauthenticatedSession();
}
