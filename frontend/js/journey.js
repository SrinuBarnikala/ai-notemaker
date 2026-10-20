/* journey.js — Topic Intake, Discovery Probe, Profile Matrix & Architecture Blueprint */

    function setTopic(text) {
      const input = document.getElementById('topic-input');
      input.value = text;
      input.focus();
    }

    /* Reader Controls */


    async function submitTopic(event) {
      event.preventDefault();
      const input = document.getElementById('topic-input');
      const topic = input.value.trim();
      if (!topic) return;

      const btn = document.getElementById('btn-submit');
      const btnText = document.getElementById('btn-submit-text');
      const btnSpinner = document.getElementById('btn-submit-spinner');

      btn.disabled = true;
      btnText.style.display = 'none';
      btnSpinner.style.display = 'inline';

      try {
        const journey = await API.request('/journeys', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ topic })
        }, 'Failed to create journey');
        currentJourneyId = journey.id;
        currentTopic = journey.topic;
        if (typeof resetCopilotState === 'function') resetCopilotState();

        await startDiscovery(journey.id, journey.topic);
        loadRecentJourneys();
      } catch (err) {
        alert('Error: ' + err.message);
      } finally {
        btn.disabled = false;
        btnText.style.display = 'inline';
        btnSpinner.style.display = 'none';
      }
    }

    let discoveryBusy = false;
    let currentQuestionIndex = null;

    function showDiscoveryError(message, retryable) {
      document.getElementById('disc-error-text').textContent = message;
      document.getElementById('disc-error-retry').style.display = retryable ? 'inline-block' : 'none';
      document.getElementById('disc-error').style.display = 'flex';
    }

    function clearDiscoveryError() {
      document.getElementById('disc-error').style.display = 'none';
    }

    function renderStepDots(step) {
      // An adaptive conversation has no fixed length, so show progress without a total.
      const dots = [];
      for (let i = 1; i <= step; i++) {
        dots.push(`<span class="disc-step-dot${i === step ? ' current' : ''}"></span>`);
      }
      document.getElementById('disc-steps').innerHTML = dots.join('');
    }

    async function startDiscovery(journeyId, topic) {
      currentJourneyId = journeyId;
      currentTopic = topic;
      if (typeof resetCopilotState === 'function') resetCopilotState();

      const discPanel = document.getElementById('discovery-panel');
      const profPanel = document.getElementById('profile-panel');
      const archPanel = document.getElementById('architecture-panel');
      const notePanel = document.getElementById('note-panel');
      discPanel.style.display = 'block';
      profPanel.style.display = 'none';
      archPanel.style.display = 'none';
      notePanel.style.display = 'none';
      discPanel.scrollIntoView({ behavior: 'smooth' });

      document.getElementById('disc-topic-label').textContent = topic;
      document.getElementById('disc-question-text').textContent = 'Thinking about where to begin…';
      setIconLabel(document.getElementById('disc-concept'), 'target', 'Getting started');
      document.getElementById('disc-step-label').textContent = 'Getting to know you';
      document.getElementById('disc-steps').innerHTML = '';
      document.getElementById('active-question-section').style.display = 'block';
      clearDiscoveryError();
      document.getElementById('btn-answer-submit').disabled = true;

      try {
        // Idempotent: returns the pending question, or resumes an answer that was saved but not followed up.
        const data = await API.request(`/journeys/${journeyId}/discovery/start`, { method: 'POST' }, 'Failed to start discovery');
        renderQuestion(data);
        loadDiscoveryHistory(journeyId);
      } catch (err) {
        document.getElementById('disc-question-text').textContent = 'We could not load your next question.';
        showDiscoveryError(err.message, true);
      }
    }

    function retryDiscovery() {
      return startDiscovery(currentJourneyId, currentTopic);
    }

    function renderQuestion(data) {
      const submitBtn = document.getElementById('btn-answer-submit');
      if (data.is_finished) {
        document.getElementById('active-question-section').style.display = 'none';
        document.getElementById('disc-step-label').textContent = 'Discovery concluded';
        document.getElementById('disc-steps').innerHTML = '';
        setIconLabel(document.getElementById('disc-concept'), 'target', 'Complete');
        triggerProfileGeneration(currentJourneyId);
        return;
      }

      clearDiscoveryError();
      document.getElementById('active-question-section').style.display = 'block';
      currentQuestionIndex = data.question_index;
      document.getElementById('disc-step-label').textContent = `Getting to know you · Step ${data.question_index}`;
      renderStepDots(data.question_index);
      document.getElementById('disc-question-text').textContent = data.question_text;
      setIconLabel(document.getElementById('disc-concept'), 'target', data.concept_target);
      document.getElementById('disc-answer-input').value = '';
      document.getElementById('disc-answer-input').focus();
      submitBtn.disabled = false;
    }

    async function submitAnswer() {
      if (discoveryBusy) return; // guard against double submission
      const textarea = document.getElementById('disc-answer-input');
      const answer = textarea.value.trim();
      if (!answer) {
        showDiscoveryError('Write a few words first. Even "I\'m not sure" helps.', false);
        return;
      }

      const btn = document.getElementById('btn-answer-submit');
      const btnText = document.getElementById('btn-ans-text');
      const btnSpinner = document.getElementById('btn-ans-spinner');

      discoveryBusy = true;
      clearDiscoveryError();
      btn.disabled = true;
      btnText.style.display = 'none';
      btnSpinner.style.display = 'inline';

      try {
        const data = await API.request(`/journeys/${currentJourneyId}/discovery/answer`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ answer, question_index: currentQuestionIndex })
        }, 'Failed to submit answer');
        renderQuestion(data);
        loadDiscoveryHistory(currentJourneyId);
      } catch (err) {
        if (err.status === 503 || err.status === 409) {
          // 503: the answer is already saved on the server, so resume instead of resubmitting.
          // 409: this submission was refused (not saved); keep the draft until the user reloads the question.
          if (err.status === 503) textarea.value = '';
          showDiscoveryError(err.message, true);
          loadDiscoveryHistory(currentJourneyId);
        } else {
          // Not saved (for example, invalid input): keep the text so nothing is lost.
          showDiscoveryError(err.message, false);
          btn.disabled = false;
        }
      } finally {
        discoveryBusy = false;
        btnText.style.display = 'inline';
        btnSpinner.style.display = 'none';
      }
    }

    async function loadDiscoveryHistory(journeyId) {
      try {
        const data = await API.requestOrNull(`/journeys/${journeyId}/discovery`);
        if (!data) return;
        const feed = document.getElementById('qa-feed');

        const answered = data.interactions.filter(i => i.learner_answer);
        if (answered.length === 0) {
          feed.innerHTML = '';
          return;
        }

        feed.innerHTML = answered.map(item => `
          <div class="qa-card">
            <div class="qa-q">${escapeHtml(item.question_text)}</div>
            <div class="qa-a">${escapeHtml(item.learner_answer)}</div>
            ${item.quick_assessment ? `<div class="qa-assessment">${uiIcon('lightbulb')} Insight: ${escapeHtml(item.quick_assessment)}</div>` : ''}
          </div>
        `).join('');
      } catch (e) {
        console.error(e);
      }
    }

    async function triggerProfileGeneration(journeyId) {
      const profilePanel = document.getElementById('profile-panel');
      profilePanel.style.display = 'block';
      profilePanel.scrollIntoView({ behavior: 'smooth' });

      document.getElementById('prof-summary').textContent = 'Building your mental model from your answers…';
      document.getElementById('prof-error').style.display = 'none';

      try {
        const profile = await API.request(`/journeys/${journeyId}/knowledge-profile`, { method: 'POST' }, 'Failed to synthesize profile');
        renderProfile(profile);
      } catch (err) {
        // Discovery answers are already saved; regenerating only rebuilds the profile.
        document.getElementById('prof-summary').textContent = 'Your answers are saved, but the profile could not be built yet.';
        document.getElementById('prof-error-text').textContent = err.message;
        document.getElementById('prof-error').style.display = 'flex';
      }
    }

    function retryProfileGeneration() {
      return triggerProfileGeneration(currentJourneyId);
    }

    function renderProfile(profile) {
      const confBadge = document.getElementById('prof-confidence');
      const confidenceLabels = { unknown: 'NOT ASSESSED', developing: 'DEVELOPING' };
      confBadge.textContent = confidenceLabels[profile.overall_confidence] || profile.overall_confidence.toUpperCase();
      confBadge.className = `confidence-badge confidence-${profile.overall_confidence}`;
      document.getElementById('prof-error').style.display = 'none';
      document.getElementById('prof-fallback-notice').style.display = profile.synthesis_fallback ? 'flex' : 'none';

      document.getElementById('prof-summary').textContent = profile.summary;

      const misContainer = document.getElementById('misconceptions-container');
      const misList = document.getElementById('misconceptions-list');
      if (profile.misconceptions && profile.misconceptions.length > 0) {
        misList.innerHTML = profile.misconceptions.map(m => `
          <div class="misconception-card"><span>${uiIcon('triangle-alert')}</span><span>${escapeHtml(m)}</span></div>
        `).join('');
        misContainer.style.display = 'block';
      } else {
        misContainer.style.display = 'none';
      }

      const colKnown = document.getElementById('col-known');
      const colPartial = document.getElementById('col-partial');
      const colGaps = document.getElementById('col-gaps');

      const knownConcepts = profile.concepts.filter(c => c.category === 'known');
      const partialConcepts = profile.concepts.filter(c => c.category === 'partially_known');
      const unknownConcepts = profile.concepts.filter(c => c.category === 'unknown');

      document.getElementById('count-known').textContent = knownConcepts.length;
      document.getElementById('count-partial').textContent = partialConcepts.length;
      document.getElementById('count-gaps').textContent = (unknownConcepts.length + (profile.gaps ? profile.gaps.length : 0));

      colKnown.innerHTML = knownConcepts.length ? knownConcepts.map(renderConceptCard).join('') : '<div class="text-sm" style="color: var(--text-muted);">None identified yet.</div>';
      colPartial.innerHTML = partialConcepts.length ? partialConcepts.map(renderConceptCard).join('') : '<div class="text-sm" style="color: var(--text-muted);">None identified yet.</div>';

      let gapsHtml = unknownConcepts.map(renderConceptCard).join('');
      if (profile.gaps && profile.gaps.length > 0) {
        gapsHtml += '<div class="text-xs" style="color: var(--text-muted); margin: 0.75rem 0 0.4rem 0;">IDENTIFIED GAPS:</div>';
        gapsHtml += profile.gaps.map(g => `
          <div class="gap-badge"><span>&bull;</span><span>${escapeHtml(g)}</span></div>
        `).join('');
      }
      colGaps.innerHTML = gapsHtml || '<div class="text-sm" style="color: var(--text-muted);">None identified yet.</div>';
    }

    function renderConceptCard(c) {
      return `
        <div class="concept-item-card">
          <div class="concept-name-row">
            <span class="concept-name">${escapeHtml(c.name)}</span>
            <span class="concept-level-tag tag-${c.level}">${c.level}</span>
          </div>
          ${c.notes ? `<div class="concept-notes">${escapeHtml(c.notes)}</div>` : ''}
        </div>
      `;
    }

    async function triggerArchitectureGeneration(journeyId) {
      const targetId = journeyId || currentJourneyId;
      if (!targetId) {
        alert('No active learning journey found. Please start or select a journey first.');
        return;
      }

      const archPanel = document.getElementById('architecture-panel');
      archPanel.style.display = 'block';
      archPanel.scrollIntoView({ behavior: 'smooth' });

      document.getElementById('arch-rationale').textContent = 'Designing a section blueprint around your gaps…';
      const bList = document.getElementById('blueprint-list');
      bList.innerHTML = '<div style="text-align: center; color: var(--text-muted); padding: 1.5rem;">Designing sections...</div>';

      try {
        const arch = await API.request(`/journeys/${targetId}/architecture`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({})
        }, 'Failed to generate architecture');
        renderArchitecture(arch);
      } catch (err) {
        document.getElementById('arch-rationale').textContent = 'Failed to generate architecture: ' + err.message;
      }
    }

    function renderArchitecture(arch) {
      setNotice('arch-fallback-notice', arch.generation_status === 'llm_fallback'
        ? 'The AI service was unavailable, so this outline comes from a built-in template and is not personalised by the model. You can generate it again later.'
        : '');
      document.getElementById('arch-rationale').textContent = arch.summary_rationale;
      const bList = document.getElementById('blueprint-list');

      bList.innerHTML = arch.sections.map(s => `
        <div class="blueprint-card">
          <div class="blueprint-header">
            <div class="blueprint-title-row">
              <div class="blueprint-index">${s.order_index}</div>
              <div class="blueprint-title">${escapeHtml(s.title)}</div>
            </div>
            <div class="blueprint-badges">
              <span class="depth-badge depth-${s.depth}">${s.depth}</span>
            </div>
          </div>
          <div class="blueprint-rationale">
            <strong>Why for you:</strong> ${escapeHtml(s.rationale)}
          </div>
          <div class="blueprint-footer">
            <div class="text-xs" style="color: var(--text-muted);">
              Targets: ${s.target_concepts.map(tc => escapeHtml(tc)).join(', ')}
            </div>
            <div class="blueprint-features">
              ${s.needs_code ? '<span class="feature-pill active">' + uiIcon('code-xml') + ' Code Required</span>' : ''}
              ${s.needs_visual ? `<span class="feature-pill active">${uiIcon('chart-column')} ${escapeHtml(s.visual_type || 'Diagram')}</span>` : ''}
            </div>
          </div>
        </div>
      `).join('');
    }



    async function loadRecentJourneys() {
      const listEl = document.getElementById('history-list');
      try {
        const data = await API.requestOrNull('/journeys?limit=6');
        if (!data || !data.journeys || data.journeys.length === 0) {
          listEl.innerHTML = '<div class="text-sm" style="color: var(--text-muted); text-align: center; padding: 1rem;">No journeys yet.</div>';
          return;
        }

        listEl.innerHTML = data.journeys.map(j => `
          <div class="history-item" onclick="resumeJourney('${j.id}', '${escapeHtml(j.topic)}', '${j.status}')">
            <div>
              <div class="history-topic">${escapeHtml(j.topic)}</div>
              <div class="text-xs" style="color: var(--text-muted); margin-top: 0.2rem;">ID: ${j.id.slice(0, 8)}...</div>
            </div>
            <div style="display: flex; align-items: center; gap: 0.75rem;">
              <span class="phase-badge">${formatStatus(j.status)}</span>
              <span class="text-sm" style="color: var(--purple-text);">&rarr;</span>
            </div>
          </div>
        `).join('');
      } catch (e) {
        console.error("Failed to load journeys", e);
      }
    }

    async function resumeJourney(journeyId, topic, status) {
      currentJourneyId = journeyId;
      currentTopic = topic;
      if (typeof resetCopilotState === 'function') resetCopilotState();

      if (status === 'note_generated') {
        try {
          const note = await API.requestOrNull(`/journeys/${journeyId}/note`);
          if (note) {
            renderNote(note);
            return;
          }
        } catch (e) { console.error(e); }
      }

      if (status === 'architecture_ready') {
        try {
          const arch = await API.requestOrNull(`/journeys/${journeyId}/architecture`);
          if (arch) {
            const archPanel = document.getElementById('architecture-panel');
            archPanel.style.display = 'block';
            archPanel.scrollIntoView({ behavior: 'smooth' });
            renderArchitecture(arch);
            return;
          }
        } catch (e) { console.error(e); }
      }

      if (status === 'profile_ready') {
        try {
          const prof = await API.requestOrNull(`/journeys/${journeyId}/knowledge-profile`);
          if (prof) {
            const profPanel = document.getElementById('profile-panel');
            profPanel.style.display = 'block';
            profPanel.scrollIntoView({ behavior: 'smooth' });
            renderProfile(prof);
            return;
          }
        } catch (e) { console.error(e); }
      }

      // Default: continue discovery
      startDiscovery(journeyId, topic);
    }

    async function loadJourneyById(journeyId) {
      if (typeof resetCopilotState === 'function') resetCopilotState();
      try {
        const j = await API.requestOrNull(`/journeys/${journeyId}`);
        if (!j) return;
        currentJourneyId = j.id;
        currentTopic = j.topic;
        await resumeJourney(j.id, j.topic, j.status);
      } catch (err) {
        console.error("Failed to load journey by id:", err);
      }
    }
    window.loadJourneyById = loadJourneyById;

    /* ==========================================================================
       PHASE 9: VISUAL PLANNER & INTERACTIVE ARCHITECTURE ENGINE (AGENT 7)
       ========================================================================== */

