/* app.js — Main Application Bootstrap & Keyboard Navigation */

function closeModalOnOverlay(event) {
  if (event.target.classList.contains('modal-overlay')) {
    event.target.style.display = 'none';
    activeEvolveSectionId = null;
  }
}

async function checkLlmStatus() {
  try {
    const data = await API.requestOrNull('/health');
    if (!data) return;
    const badge = document.getElementById('llm-status-badge');
    if (!badge) return;

    if (data.llm_provider === 'ollama') {
      if (data.model_available === false) {
        badge.style.display = 'inline-flex';
        badge.style.background = 'rgba(245, 158, 11, 0.15)';
        badge.style.borderColor = 'rgba(245, 158, 11, 0.4)';
        badge.style.color = '#fbbf24';
        badge.textContent = `⚠️ Model '${data.llm_model}' missing`;
        badge.title = data.model_warning || `Model '${data.llm_model}' not pulled. Notes will use deterministic offline fallbacks.`;
      } else if (data.llm_healthy) {
        badge.style.display = 'inline-flex';
        badge.style.background = 'rgba(16, 185, 129, 0.12)';
        badge.style.borderColor = 'rgba(16, 185, 129, 0.35)';
        badge.style.color = '#34d399';
        badge.textContent = `🟢 Ollama: ${data.llm_model}`;
        badge.title = `Connected to local Ollama with model '${data.llm_model}'.`;
      }
    }
  } catch (err) {
    console.debug("Health check diagnostic fetch skipped:", err);
  }
}

window.addEventListener('DOMContentLoaded', async () => {
  // Bootstrap authentication session before initializing application views
  if (typeof bootstrapAuthSession === 'function') {
    await bootstrapAuthSession();
  } else {
    const appWorkspace = document.getElementById('app-workspace');
    if (appWorkspace) appWorkspace.style.display = 'block';
    checkLlmStatus();
    if (typeof loadRecentJourneys === 'function') loadRecentJourneys();
  }
});


// Global Keyboard Navigation: Escape Closes Any Active Modal or Drawer
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    // 1. In-Note Copilot Drawer
    if (typeof closeCopilotDrawer === 'function') closeCopilotDrawer();

    // 2. Spotlight Universal Search Modal
    if (typeof closeSearchModal === 'function') closeSearchModal();

    // 3. Version History & Diff Modal
    if (typeof closeVersionHistoryModal === 'function') closeVersionHistoryModal();

    // 4. Knowledge Memory & Learning History Modal
    if (typeof closeMemoryModal === 'function') closeMemoryModal();

    // 5. Concept Provenance Modal
    if (typeof closeConceptProvenanceModal === 'function') closeConceptProvenanceModal();

    // 6. Section Evolution Modal
    if (typeof closeEvolveModal === 'function') closeEvolveModal();

    // 7. Mastery Assessment & Micro-Quiz Modal
    if (typeof closeAssessmentModal === 'function') closeAssessmentModal();

    // 8. Diagram Fullscreen & Visual Modals
    if (typeof closeDiagramModal === 'function') closeDiagramModal();
    if (typeof closeSectionVisualModal === 'function') closeSectionVisualModal();

    // 9. Code Walkthrough / Sandbox Modal
    if (typeof closeSectionCodeModal === 'function') closeSectionCodeModal();

    // 10. Concept Knowledge Graph & Inspector
    if (typeof closeGraphModal === 'function') closeGraphModal();
    if (typeof closeConceptInspector === 'function') closeConceptInspector();

    // 11. Revisions Modal & Overlay Elements
    const revModal = document.getElementById('revisions-modal');
    if (revModal && revModal.style.display === 'flex') revModal.style.display = 'none';

    // 12. Generic modal element fallback
    const allModals = document.querySelectorAll('.modal, .spotlight-overlay, .concept-drawer');
    allModals.forEach(m => {
      if (!m.classList.contains('hidden') && (m.style.display === 'flex' || m.style.display === 'block')) {
        m.classList.add('hidden');
        m.style.display = 'none';
      }
    });
  }
});
