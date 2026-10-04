/* profile.js — Learner Profile, Pedagogical Settings & Security Modal Controller */

/* ==========================================================================
   HEADER PROFILE PILL UPDATES
   ========================================================================== */

function getInitials(nameOrEmail) {
  if (!nameOrEmail) return '?';
  const clean = nameOrEmail.trim();
  if (clean.includes(' ')) {
    const parts = clean.split(' ').filter(Boolean);
    if (parts.length >= 2) {
      return (parts[0][0] + parts[1][0]).toUpperCase();
    }
  }
  return clean[0].toUpperCase();
}

function updateHeaderProfileUI(profile) {
  if (!profile) return;
  const avatarBadge = document.getElementById('header-avatar-badge');
  const displayNameEl = document.getElementById('header-user-name');
  const userEmailEl = document.getElementById('header-user-email');

  const name = profile.display_name || (profile.email ? profile.email.split('@')[0] : 'Learner');
  const initial = getInitials(profile.display_name || profile.email || 'Learner');

  if (avatarBadge) {
    avatarBadge.textContent = initial;
  }
  if (displayNameEl) {
    displayNameEl.textContent = name;
    displayNameEl.title = `Profile: ${name} (${profile.email || ''})`;
  }
  if (userEmailEl) {
    userEmailEl.textContent = name;
    userEmailEl.title = `Profile: ${name} (${profile.email || ''})`;
  }
}

async function loadHeaderProfile() {
  try {
    const profile = await API.getProfile();
    if (profile) {
      currentProfile = profile;
      updateHeaderProfileUI(profile);
    }
  } catch (err) {
    console.debug("Header profile load skipped:", err);
  }
}

/* ==========================================================================
   MODAL CONTROLS & TAB SWITCHING
   ========================================================================== */

function switchProfileTab(tabName) {
  const tabs = ['identity', 'learning', 'security'];
  tabs.forEach(t => {
    const btn = document.getElementById(`btn-ptab-${t}`);
    const content = document.getElementById(`ptab-${t}`);
    if (btn) {
      if (t === tabName) {
        btn.classList.add('active');
      } else {
        btn.classList.remove('active');
      }
    }
    if (content) {
      if (t === tabName) {
        content.classList.add('active');
      } else {
        content.classList.remove('active');
      }
    }
  });
}

function showProfileAlert(elementId, message, isSuccess = false) {
  const el = document.getElementById(elementId);
  if (!el) return;
  el.textContent = message;
  el.className = isSuccess ? 'login-alert login-alert-success' : 'login-alert';
  el.style.display = 'flex';
  el.style.marginBottom = '1rem';
}

function hideProfileAlert(elementId) {
  const el = document.getElementById(elementId);
  if (el) el.style.display = 'none';
}

async function openProfileModal(initialTab = 'identity') {
  const modal = document.getElementById('profile-modal');
  if (!modal) return;

  hideProfileAlert('profile-identity-alert');
  hideProfileAlert('profile-learning-alert');
  hideProfileAlert('profile-security-alert');

  modal.style.display = 'flex';
  switchProfileTab(initialTab);

  try {
    const [profile, learning] = await Promise.all([
      API.getProfile(),
      API.getLearnerSettings(),
    ]);

    if (profile) {
      currentProfile = profile;
      updateHeaderProfileUI(profile);

      const avatarLarge = document.getElementById('profile-avatar-large');
      const heroName = document.getElementById('profile-hero-name');
      const heroEmail = document.getElementById('profile-hero-email');
      const inputName = document.getElementById('profile-display-name');
      const inputBio = document.getElementById('profile-bio');
      const inputEmail = document.getElementById('profile-email-readonly');
      const inputCreated = document.getElementById('profile-created-readonly');

      const initial = getInitials(profile.display_name || profile.email);
      if (avatarLarge) avatarLarge.textContent = initial;
      if (heroName) heroName.textContent = profile.display_name || profile.email;
      if (heroEmail) heroEmail.textContent = profile.email;
      if (inputName) inputName.value = profile.display_name || '';
      if (inputBio) inputBio.value = profile.bio || '';
      if (inputEmail) inputEmail.value = profile.email || '';
      if (inputCreated && profile.created_at) {
        const d = new Date(profile.created_at);
        inputCreated.value = d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
      }
    }

    if (learning) {
      currentLearnerSettings = learning;
      const selExp = document.getElementById('profile-experience-level');
      const selLang = document.getElementById('profile-preferred-language');
      const selDepth = document.getElementById('profile-explanation-depth');
      const selStyle = document.getElementById('profile-learning-style');
      const txtGoals = document.getElementById('profile-target-goals');

      if (selExp && learning.experience_level) selExp.value = learning.experience_level;
      if (selLang && learning.preferred_language) selLang.value = learning.preferred_language;
      if (selDepth && learning.explanation_depth) selDepth.value = learning.explanation_depth;
      if (selStyle && learning.learning_style) selStyle.value = learning.learning_style;
      if (txtGoals) txtGoals.value = learning.target_goals || '';

      const stats = learning.stats || {};
      const sJourneys = document.getElementById('pstat-journeys');
      const sConcepts = document.getElementById('pstat-concepts');
      const sMastered = document.getElementById('pstat-mastered');
      const sGaps = document.getElementById('pstat-gaps');

      if (sJourneys) sJourneys.textContent = stats.total_journeys || 0;
      if (sConcepts) sConcepts.textContent = stats.total_concepts || 0;
      if (sMastered) sMastered.textContent = stats.mastered_concepts || 0;
      if (sGaps) sGaps.textContent = stats.unresolved_gaps || 0;
    }
  } catch (err) {
    console.error("Failed to load profile data:", err);
  }
}

function closeProfileModal() {
  const modal = document.getElementById('profile-modal');
  if (modal) {
    modal.style.display = 'none';
  }
}

/* ==========================================================================
   FORM SUBMISSION HANDLERS
   ========================================================================== */

async function saveProfileIdentity(event) {
  if (event) event.preventDefault();
  hideProfileAlert('profile-identity-alert');

  const nameInput = document.getElementById('profile-display-name');
  const bioInput = document.getElementById('profile-bio');
  const btn = document.getElementById('btn-save-profile');
  const btnText = document.getElementById('btn-save-profile-text');
  const btnSpinner = document.getElementById('btn-save-profile-spinner');

  if (!nameInput) return;

  if (btn) btn.disabled = true;
  if (btnText) btnText.style.display = 'none';
  if (btnSpinner) btnSpinner.style.display = 'inline';

  try {
    const payload = {
      display_name: nameInput.value.trim(),
      bio: bioInput ? bioInput.value.trim() : null,
    };

    const updated = await API.updateProfile(payload);
    if (updated) {
      currentProfile = updated;
      updateHeaderProfileUI(updated);

      const avatarLarge = document.getElementById('profile-avatar-large');
      const heroName = document.getElementById('profile-hero-name');
      if (avatarLarge) avatarLarge.textContent = getInitials(updated.display_name || updated.email);
      if (heroName) heroName.textContent = updated.display_name || updated.email;

      showProfileAlert('profile-identity-alert', 'Profile updated successfully!', true);
    }
  } catch (err) {
    showProfileAlert('profile-identity-alert', err.message || 'Failed to update profile.');
  } finally {
    if (btn) btn.disabled = false;
    if (btnText) btnText.style.display = 'inline';
    if (btnSpinner) btnSpinner.style.display = 'none';
  }
}

async function saveLearnerSettings(event) {
  if (event) event.preventDefault();
  hideProfileAlert('profile-learning-alert');

  const selExp = document.getElementById('profile-experience-level');
  const selLang = document.getElementById('profile-preferred-language');
  const selDepth = document.getElementById('profile-explanation-depth');
  const selStyle = document.getElementById('profile-learning-style');
  const txtGoals = document.getElementById('profile-target-goals');

  const btn = document.getElementById('btn-save-learning');
  const btnText = document.getElementById('btn-save-learning-text');
  const btnSpinner = document.getElementById('btn-save-learning-spinner');

  if (btn) btn.disabled = true;
  if (btnText) btnText.style.display = 'none';
  if (btnSpinner) btnSpinner.style.display = 'inline';

  try {
    const payload = {
      experience_level: selExp ? selExp.value : 'intermediate',
      preferred_language: selLang ? selLang.value : 'python',
      explanation_depth: selDepth ? selDepth.value : 'internals',
      learning_style: selStyle ? selStyle.value : 'code_and_visual',
      target_goals: txtGoals ? txtGoals.value.trim() : '',
    };

    const updated = await API.updateLearnerSettings(payload);
    if (updated) {
      currentLearnerSettings = updated;
      showProfileAlert('profile-learning-alert', 'Learner preferences updated successfully!', true);
    }
  } catch (err) {
    showProfileAlert('profile-learning-alert', err.message || 'Failed to update learner settings.');
  } finally {
    if (btn) btn.disabled = false;
    if (btnText) btnText.style.display = 'inline';
    if (btnSpinner) btnSpinner.style.display = 'none';
  }
}

async function submitChangePassword(event) {
  if (event) event.preventDefault();
  hideProfileAlert('profile-security-alert');

  const currInput = document.getElementById('profile-current-password');
  const newInput = document.getElementById('profile-new-password');
  const confirmInput = document.getElementById('profile-confirm-password');

  const btn = document.getElementById('btn-change-password');
  const btnText = document.getElementById('btn-change-password-text');
  const btnSpinner = document.getElementById('btn-change-password-spinner');

  if (!currInput || !newInput || !confirmInput) return;

  const currentPw = currInput.value;
  const newPw = newInput.value;
  const confirmPw = confirmInput.value;

  if (!currentPw) {
    showProfileAlert('profile-security-alert', 'Please enter your current password.');
    currInput.focus();
    return;
  }

  if (!newPw || newPw.length < 8) {
    showProfileAlert('profile-security-alert', 'New password must be at least 8 characters long.');
    newInput.focus();
    return;
  }

  if (newPw !== confirmPw) {
    showProfileAlert('profile-security-alert', 'New passwords do not match. Please re-enter.');
    confirmInput.focus();
    return;
  }

  if (btn) btn.disabled = true;
  if (btnText) btnText.style.display = 'none';
  if (btnSpinner) btnSpinner.style.display = 'inline';

  try {
    const res = await API.changePassword(currentPw, newPw);
    showProfileAlert('profile-security-alert', (res && res.message) || 'Password changed successfully!', true);
    currInput.value = '';
    newInput.value = '';
    confirmInput.value = '';
  } catch (err) {
    showProfileAlert('profile-security-alert', err.message || 'Failed to update password.');
  } finally {
    if (btn) btn.disabled = false;
    if (btnText) btnText.style.display = 'inline';
    if (btnSpinner) btnSpinner.style.display = 'none';
  }
}
