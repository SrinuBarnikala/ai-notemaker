/* api.js — Centralized REST API Service for AI Note Maker & Auth Session */

let inMemoryToken = null;

function getAuthToken() {
  return inMemoryToken || sessionStorage.getItem('notemaker_auth_token');
}

function setAuthToken(token) {
  inMemoryToken = token;
  if (token) {
    sessionStorage.setItem('notemaker_auth_token', token);
  } else {
    sessionStorage.removeItem('notemaker_auth_token');
  }
}

function clearAuthSession() {
  inMemoryToken = null;
  sessionStorage.removeItem('notemaker_auth_token');
  currentUser = null;
  isAuthenticated = false;
}

/**
 * Build request options with credentials: 'same-origin' (for HttpOnly cookies)
 * and optional Bearer Authorization header if token is present.
 */
function buildRequestOptions(options = {}) {
  const opts = { ...options };
  opts.credentials = opts.credentials || 'same-origin';

  const headers = new Headers(opts.headers || {});
  const token = getAuthToken();
  if (token && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  opts.headers = headers;
  return opts;
}

/**
 * Generic fetch wrapper: throws an Error (preferring the backend's `detail`
 * message, falling back to fallbackErrorMessage) on a non-OK response,
 * otherwise resolves with the parsed JSON body.
 */
async function apiRequest(url, options, fallbackErrorMessage) {
  const finalOptions = buildRequestOptions(options);
  const res = await fetch(url, finalOptions);

  if (!res.ok) {
    if (res.status === 401 && !url.startsWith('/auth/login')) {
      clearAuthSession();
      if (typeof handleUnauthenticatedSession === 'function') {
        handleUnauthenticatedSession();
      }
    }

    let detail;
    try {
      const data = await res.json();
      detail = data && data.detail;
    } catch (_) {
      // non-JSON error body — fall back to the provided message
    }
    throw new Error(detail || fallbackErrorMessage || `Request failed with status ${res.status}`);
  }
  return res.json();
}

/**
 * Generic fetch wrapper for best-effort/background loads: resolves with the
 * parsed JSON body on success, or null on a non-OK response.
 */
async function apiRequestOrNull(url, options) {
  try {
    const finalOptions = buildRequestOptions(options);
    const res = await fetch(url, finalOptions);
    if (!res.ok) {
      if (res.status === 401 && !url.startsWith('/auth/login')) {
        clearAuthSession();
      }
      return null;
    }
    return res.json();
  } catch (_) {
    return null;
  }
}

const API = {
  request: apiRequest,
  requestOrNull: apiRequestOrNull,
  setAuthToken,
  getAuthToken,
  clearAuthSession,

  /* ========================================================================
     AUTHENTICATION APIS
     ======================================================================== */
  async login(email, password, rememberMe = false) {
    const data = await apiRequest('/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password, remember_me: Boolean(rememberMe) }),
    }, 'Invalid email or password.');

    if (data && data.access_token) {
      setAuthToken(data.access_token);
      currentUser = data.user;
      isAuthenticated = true;
    }
    return data;
  },

  async getMe() {
    return apiRequestOrNull('/auth/me');
  },

  async logout() {
    try {
      await apiRequestOrNull('/auth/logout', { method: 'POST' });
    } finally {
      clearAuthSession();
    }
  },

  async register(email, password) {
    return apiRequest('/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    }, 'Failed to register account.');
  },

  /* ========================================================================
     PROFILE & LEARNER SETTINGS APIS
     ======================================================================== */
  async getProfile() {
    return apiRequestOrNull('/profile/me');
  },

  async updateProfile(payload) {
    return apiRequest('/profile/me', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }, 'Failed to update profile.');
  },

  async getLearnerSettings() {
    return apiRequestOrNull('/profile/me/learning');
  },

  async updateLearnerSettings(payload) {
    return apiRequest('/profile/me/learning', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }, 'Failed to update learner preferences.');
  },

  async changePassword(currentPassword, newPassword) {
    return apiRequest('/profile/me/change-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    }, 'Failed to update password.');
  },

  /* ========================================================================
     APPLICATION APIS
     ======================================================================== */
  async createJourney(topic) {
    return apiRequest('/journeys', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ topic }),
    }, 'Failed to create journey');
  },

  async startDiscovery(journeyId) {
    return apiRequest(`/journeys/${journeyId}/discovery/start`, { method: 'POST' }, 'Failed to start discovery');
  },

  async answerDiscovery(journeyId, answer) {
    return apiRequest(`/journeys/${journeyId}/discovery/answer`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ answer }),
    }, 'Failed to record answer');
  },

  async getDiscovery(journeyId) {
    return apiRequest(`/journeys/${journeyId}/discovery`, {}, 'Failed to load discovery');
  },

  async generateProfile(journeyId) {
    return apiRequest(`/journeys/${journeyId}/knowledge-profile`, { method: 'POST' }, 'Failed to generate profile');
  },

  async generateArchitecture(journeyId) {
    return apiRequest(`/journeys/${journeyId}/architecture`, { method: 'POST' }, 'Failed to generate architecture');
  },

  async generateNote(journeyId) {
    return apiRequest(`/journeys/${journeyId}/generate-note`, { method: 'POST' }, 'Failed to generate note');
  },

  async getNote(journeyId) {
    return apiRequest(`/journeys/${journeyId}/note`, {}, 'Failed to load note');
  },

  async getNoteById(noteId) {
    return apiRequest(`/notes/${noteId}`, {}, 'Failed to load note by ID');
  },

  async evolveSection(journeyId, sectionId, payload) {
    return apiRequest(`/journeys/${journeyId}/sections/${sectionId}/evolve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }, 'Evolution failed');
  },

  async getAssessment(journeyId) {
    return apiRequest(`/journeys/${journeyId}/assessment`, {}, 'Assessment fetch failed');
  },

  async generateAssessment(journeyId) {
    return apiRequest(`/journeys/${journeyId}/assessment`, { method: 'POST' }, 'Assessment generation failed');
  },

  async submitQuiz(journeyId, answers) {
    return apiRequest(`/journeys/${journeyId}/assessment/quiz`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ answers }),
    }, 'Quiz evaluation failed');
  },

  async generateVisual(journeyId, sectionId, payload) {
    return apiRequest(`/journeys/${journeyId}/sections/${sectionId}/visual`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }, 'Visual generation failed');
  },

  async planVisuals(journeyId) {
    return apiRequest(`/journeys/${journeyId}/plan-visuals`, { method: 'POST' }, 'Visual planner failed');
  },

  async generateCode(journeyId, sectionId, payload) {
    return apiRequest(`/journeys/${journeyId}/sections/${sectionId}/code`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }, 'Code synthesis failed');
  },

  async planCode(journeyId) {
    return apiRequest(`/journeys/${journeyId}/plan-code`, { method: 'POST' }, 'Code planner failed');
  },

  async listJourneys() {
    return apiRequest('/journeys', {}, 'Failed to load journeys');
  },

  async listVersions(noteId) {
    return apiRequest(`/notes/${noteId}/versions`, {}, 'Failed to load note versions');
  },

  async getVersion(noteId, version) {
    return apiRequest(`/notes/${noteId}/versions/${version}`, {}, `Failed to load version ${version}`);
  },

  async getDiff(noteId, fromVersion, toVersion) {
    return apiRequest(`/notes/${noteId}/diff?from_version=${fromVersion}&to_version=${toVersion}`, {}, 'Failed to compute version diff');
  },

  async restoreVersion(noteId, version) {
    return apiRequest(`/notes/${noteId}/versions/${version}/restore`, { method: 'POST' }, `Failed to restore version ${version}`);
  },

  getNoteExportUrl(noteId, format = 'pdf') {
    return `/notes/${noteId}/export?format=${format}`;
  },

  getJourneyNoteExportUrl(journeyId, format = 'pdf') {
    return `/journeys/${journeyId}/note/export?format=${format}`;
  }
};
