/* evolution.js — Agent 5 Living Note Evolution & Revisions History */

    function openEvolveModal(sectionId, sectionTitle, initialType = 'add_code') {
      activeEvolveSectionId = sectionId;
      const titleEl = document.getElementById('evolve-modal-title');
      if (sectionId) {
        titleEl.textContent = `Evolve: "${sectionTitle}"`;
      } else {
        titleEl.textContent = 'Expand Living Note';
      }

      // Reset and select type
      selectEvolveType(null, initialType);

      // Default prompt suggestions based on type
      const input = document.getElementById('evolve-prompt-input');
      input.value = '';
      if (initialType === 'add_code') {
        input.placeholder = 'e.g. Add a production-ready Python example with connection pooling and retry logic...';
      } else if (initialType === 'expand_section') {
        input.placeholder = 'e.g. Deepen the explanation of internal algorithms and state transitions...';
      } else if (initialType === 'clarify') {
        input.placeholder = 'e.g. Clarify common misconceptions and edge case handling...';
      } else if (initialType === 'add_section') {
        input.placeholder = 'e.g. Add a section exploring Kubernetes sidecar observability patterns...';
      } else {
        input.placeholder = 'e.g. What happens when leader network partitions occur?';
      }

      const statusMsg = document.getElementById('evolve-status-msg');
      if (statusMsg) statusMsg.style.display = 'none';

      const modal = document.getElementById('evolve-modal');
      modal.style.display = 'flex';
      input.focus();
    }

    function closeEvolveModal() {
      const modal = document.getElementById('evolve-modal');
      modal.style.display = 'none';
      activeEvolveSectionId = null;
    }

    function closeModalOnOverlay(event) {
      if (event.target.classList.contains('modal-overlay')) {
        event.target.style.display = 'none';
        activeEvolveSectionId = null;
      }
    }

    function selectEvolveType(targetBtn, type) {
      activeEvolveType = type;
      const pills = document.querySelectorAll('#evolve-type-selector .type-pill');
      pills.forEach(p => {
        if (p.getAttribute('data-type') === type) {
          p.classList.add('active');
        } else {
          p.classList.remove('active');
        }
      });
    }

    function setEvolvePrompt(text) {
      const input = document.getElementById('evolve-prompt-input');
      input.value = text;
      input.focus();
    }

    async function submitEvolution() {
      const promptInput = document.getElementById('evolve-prompt-input');
      const userPrompt = promptInput.value.trim();
      if (!userPrompt) {
        alert('Please enter instructions for how you want to evolve this note.');
        promptInput.focus();
        return;
      }

      if (!currentNote && !currentJourneyId) {
        alert('No active living note to evolve.');
        return;
      }

      const btn = document.getElementById('btn-submit-evolve');
      const btnText = document.getElementById('btn-evolve-text');
      const btnSpinner = document.getElementById('btn-evolve-spinner');
      const statusMsg = document.getElementById('evolve-status-msg');

      btn.disabled = true;
      btnText.style.display = 'none';
      btnSpinner.style.display = 'inline';
      statusMsg.style.display = 'block';
      statusMsg.textContent = 'Agent 5 synthesizing evolution updates and blocks...';

      const payload = {
        evolution_type: activeEvolveType,
        section_id: activeEvolveSectionId,
        user_prompt: userPrompt
      };

      const noteId = currentNote ? currentNote.id : null;
      const endpoint = noteId ? `/notes/${noteId}/evolve` : `/journeys/${currentJourneyId}/note/evolve`;

      try {
        const res = await fetch(endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });

        if (!res.ok) {
          const errData = await res.json().catch(() => ({}));
          throw new Error(errData.detail || 'Failed to evolve living note');
        }

        const updatedNote = await res.json();
        closeEvolveModal();
        renderNote(updatedNote);

        // Highlight updated section or scroll to it
        if (activeEvolveSectionId) {
          const targetSec = updatedNote.sections.find(s => s.id === activeEvolveSectionId);
          if (targetSec) {
            smoothScrollTo(new Event('click'), `sec-${targetSec.order_index}`);
          }
        }
      } catch (err) {
        statusMsg.style.color = '#f87171';
        statusMsg.textContent = 'Evolution Error: ' + err.message;
      } finally {
        btn.disabled = false;
        btnText.style.display = 'inline';
        btnSpinner.style.display = 'none';
      }
    }



    function toggleRevisionsDrawer() {
      const modal = document.getElementById('revisions-modal');
      if (modal.style.display === 'flex') {
        modal.style.display = 'none';
        return;
      }

      const body = document.getElementById('revisions-list-body');
      const revisions = (currentNote && currentNote.revisions) ? currentNote.revisions : [];

      if (revisions.length === 0) {
        body.innerHTML = `
          <div style="text-align: center; padding: 2rem; color: var(--text-muted);">
            <div style="font-size: 2rem; margin-bottom: 0.5rem;">🌱</div>
            <div style="font-weight: 600; color: #cbd5e1;">Version 1 (Initial Generation)</div>
            <p style="font-size: 0.85rem; margin-top: 0.4rem;">No evolutions yet. Use the "🌱 Evolve section" buttons to expand and refine your living note.</p>
          </div>
        `;
      } else {
        body.innerHTML = `
          <div style="margin-bottom: 1rem; font-size: 0.85rem; color: #a5b4fc;">
            Showing <strong>${revisions.length}</strong> evolution checkpoint(s):
          </div>
          ${revisions.map(r => `
            <div class="revision-item">
              <div class="rev-top-row">
                <span class="rev-badge">VERSION ${r.version}</span>
                <span class="rev-time">${new Date(r.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
              </div>
              <div class="rev-type-tag">
                🎯 ${r.evolution_type.replace('_', ' ').toUpperCase()} ${r.section_title ? `&bull; "${escapeHtml(r.section_title)}"` : ''}
              </div>
              <div class="rev-prompt">"${escapeHtml(r.user_prompt)}"</div>
            </div>
          `).join('')}
        `;
      }

      modal.style.display = 'flex';
    }

    /* ==========================================================================
       PHASE 8: ACTIVE RECALL & MASTERY ASSESSMENT LOGIC
       ========================================================================== */

