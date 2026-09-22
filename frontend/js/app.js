/* app.js — Main Application Bootstrap & Keyboard Navigation */

window.addEventListener('DOMContentLoaded', async () => {
  // Load previous journeys for quick resume
  if (typeof loadRecentJourneys === 'function') {
    loadRecentJourneys();
  }

  // Deep link support via ?journey_id=... or ?note_id=...
  const params = new URLSearchParams(window.location.search);
  const jid = params.get('journey_id');
  const nid = params.get('note_id');

  if (jid) {
    try {
      const res = await fetch(`/journeys/${jid}/note`);
      if (res.ok) {
        const note = await res.json();
        currentJourneyId = jid;
        renderNote(note);
      }
    } catch (e) {
      console.warn("Could not load deep-linked journey note", e);
    }
  } else if (nid) {
    try {
      const res = await fetch(`/notes/${nid}`);
      if (res.ok) {
        const note = await res.json();
        currentJourneyId = note.journey_id;
        renderNote(note);
      }
    } catch (e) {
      console.warn("Could not load deep-linked note", e);
    }
  }
});

// Global Keyboard Navigation
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    if (typeof closeDiagramModal === 'function') closeDiagramModal();
    if (typeof closeSectionVisualModal === 'function') closeSectionVisualModal();
    if (typeof closeSectionCodeModal === 'function') closeSectionCodeModal();
    if (typeof closeEvolveModal === 'function') closeEvolveModal();
    if (typeof closeAssessmentModal === 'function') closeAssessmentModal();
    const revModal = document.getElementById('revisions-modal');
    if (revModal && revModal.style.display === 'flex') revModal.style.display = 'none';
  }
});
