/* api.js — Centralized REST API Service for AI Note Maker */

const API = {
  async createJourney(topic) {
    const res = await fetch('/journeys', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ topic }),
    });
    if (!res.ok) throw new Error((await res.json()).detail || 'Failed to create journey');
    return res.json();
  },

  async startDiscovery(journeyId) {
    const res = await fetch(`/journeys/${journeyId}/discovery/start`, { method: 'POST' });
    if (!res.ok) throw new Error((await res.json()).detail || 'Failed to start discovery');
    return res.json();
  },

  async answerDiscovery(journeyId, answer) {
    const res = await fetch(`/journeys/${journeyId}/discovery/answer`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ answer }),
    });
    if (!res.ok) throw new Error((await res.json()).detail || 'Failed to record answer');
    return res.json();
  },

  async getDiscovery(journeyId) {
    const res = await fetch(`/journeys/${journeyId}/discovery`);
    if (!res.ok) throw new Error((await res.json()).detail || 'Failed to load discovery');
    return res.json();
  },

  async generateProfile(journeyId) {
    const res = await fetch(`/journeys/${journeyId}/knowledge-profile`, { method: 'POST' });
    if (!res.ok) throw new Error((await res.json()).detail || 'Failed to generate profile');
    return res.json();
  },

  async generateArchitecture(journeyId) {
    const res = await fetch(`/journeys/${journeyId}/architecture`, { method: 'POST' });
    if (!res.ok) throw new Error((await res.json()).detail || 'Failed to generate architecture');
    return res.json();
  },

  async generateNote(journeyId) {
    const res = await fetch(`/journeys/${journeyId}/generate-note`, { method: 'POST' });
    if (!res.ok) throw new Error((await res.json()).detail || 'Failed to generate note');
    return res.json();
  },

  async getNote(journeyId) {
    const res = await fetch(`/journeys/${journeyId}/note`);
    if (!res.ok) throw new Error((await res.json()).detail || 'Failed to load note');
    return res.json();
  },

  async getNoteById(noteId) {
    const res = await fetch(`/notes/${noteId}`);
    if (!res.ok) throw new Error((await res.json()).detail || 'Failed to load note by ID');
    return res.json();
  },

  async evolveSection(journeyId, sectionId, payload) {
    const res = await fetch(`/journeys/${journeyId}/sections/${sectionId}/evolve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error((await res.json()).detail || 'Evolution failed');
    return res.json();
  },

  async getAssessment(journeyId) {
    const res = await fetch(`/journeys/${journeyId}/assessment`);
    if (!res.ok) throw new Error((await res.json()).detail || 'Assessment fetch failed');
    return res.json();
  },

  async generateAssessment(journeyId) {
    const res = await fetch(`/journeys/${journeyId}/assessment`, { method: 'POST' });
    if (!res.ok) throw new Error((await res.json()).detail || 'Assessment generation failed');
    return res.json();
  },

  async submitQuiz(journeyId, answers) {
    const res = await fetch(`/journeys/${journeyId}/assessment/quiz`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ answers }),
    });
    if (!res.ok) throw new Error((await res.json()).detail || 'Quiz evaluation failed');
    return res.json();
  },

  async generateVisual(journeyId, sectionId, payload) {
    const res = await fetch(`/journeys/${journeyId}/sections/${sectionId}/visual`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error((await res.json()).detail || 'Visual generation failed');
    return res.json();
  },

  async planVisuals(journeyId) {
    const res = await fetch(`/journeys/${journeyId}/plan-visuals`, { method: 'POST' });
    if (!res.ok) throw new Error((await res.json()).detail || 'Visual planner failed');
    return res.json();
  },

  async generateCode(journeyId, sectionId, payload) {
    const res = await fetch(`/journeys/${journeyId}/sections/${sectionId}/code`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error((await res.json()).detail || 'Code synthesis failed');
    return res.json();
  },

  async planCode(journeyId) {
    const res = await fetch(`/journeys/${journeyId}/plan-code`, { method: 'POST' });
    if (!res.ok) throw new Error((await res.json()).detail || 'Code planner failed');
    return res.json();
  },

  async listJourneys() {
    const res = await fetch('/journeys');
    if (!res.ok) throw new Error('Failed to load journeys');
    return res.json();
  }
};
