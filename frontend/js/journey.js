/* journey.js — Topic Intake, Discovery Probe, Profile Matrix & Architecture Blueprint */

    function setTopic(text) {
      const input = document.getElementById('topic-input');
      input.value = text;
      input.focus();
    }

    function addAnswerStarter(text) {
      const textarea = document.getElementById('disc-answer-input');
      textarea.value = text;
      textarea.focus();
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
        const res = await fetch('/journeys', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ topic })
        });
        if (!res.ok) throw new Error('Failed to create journey');
        const journey = await res.json();
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
      document.getElementById('disc-question-text').textContent = 'Consulting Knowledge Discovery Agent...';
      document.getElementById('disc-concept').textContent = '🎯 Probing baseline...';
      document.getElementById('disc-step-label').textContent = 'Question 1 of 4';
      document.getElementById('disc-progress').style.width = '25%';
      document.getElementById('active-question-section').style.display = 'block';

      try {
        const res = await fetch(`/journeys/${journeyId}/discovery/start`, { method: 'POST' });
        if (!res.ok) throw new Error('Failed to start discovery');
        const data = await res.json();
        renderQuestion(data);
        loadDiscoveryHistory(journeyId);

        if (data.is_finished) {
          triggerProfileGeneration(journeyId);
        }
      } catch (err) {
        document.getElementById('disc-question-text').textContent = 'Error: ' + err.message;
      }
    }

    function renderQuestion(data) {
      if (data.is_finished) {
        document.getElementById('active-question-section').style.display = 'none';
        document.getElementById('disc-progress').style.width = '100%';
        document.getElementById('disc-step-label').textContent = 'Discovery Concluded';
        document.getElementById('disc-concept').textContent = '🎯 Complete';
        triggerProfileGeneration(currentJourneyId);
        return;
      }

      const maxQ = data.max_questions || 4;
      document.getElementById('disc-step-label').textContent = `Question ${data.question_index} of ${maxQ}`;
      document.getElementById('disc-question-text').textContent = data.question_text;
      document.getElementById('disc-concept').textContent = `🎯 ${data.concept_target}`;
      document.getElementById('disc-progress').style.width = `${Math.min((data.question_index / maxQ) * 100, 100)}%`;
      document.getElementById('disc-answer-input').value = '';
      document.getElementById('disc-answer-input').focus();
    }

    async function submitAnswer() {
      const textarea = document.getElementById('disc-answer-input');
      const answer = textarea.value.trim();
      if (!answer) {
        alert('Please enter an answer or select a starter chip.');
        return;
      }

      const btn = document.getElementById('btn-answer-submit');
      const btnText = document.getElementById('btn-ans-text');
      const btnSpinner = document.getElementById('btn-ans-spinner');

      btn.disabled = true;
      btnText.style.display = 'none';
      btnSpinner.style.display = 'inline';

      try {
        const res = await fetch(`/journeys/${currentJourneyId}/discovery/answer`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ answer })
        });
        if (!res.ok) throw new Error('Failed to submit answer');
        const data = await res.json();
        renderQuestion(data);
        loadDiscoveryHistory(currentJourneyId);
      } catch (err) {
        alert('Error: ' + err.message);
      } finally {
        btn.disabled = false;
        btnText.style.display = 'inline';
        btnSpinner.style.display = 'none';
      }
    }

    async function loadDiscoveryHistory(journeyId) {
      try {
        const res = await fetch(`/journeys/${journeyId}/discovery`);
        if (!res.ok) return;
        const data = await res.json();
        const feed = document.getElementById('qa-feed');

        const answered = data.interactions.filter(i => i.learner_answer);
        if (answered.length === 0) {
          feed.innerHTML = '';
          return;
        }

        feed.innerHTML = answered.map(item => `
          <div class="qa-card">
            <div class="qa-q">Q${item.question_index} (${item.concept_target}): ${escapeHtml(item.question_text)}</div>
            <div class="qa-a">${escapeHtml(item.learner_answer)}</div>
            ${item.quick_assessment ? `<div class="qa-assessment">💡 Insight: ${escapeHtml(item.quick_assessment)}</div>` : ''}
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

      document.getElementById('prof-summary').textContent = '🤖 Agent 2 analyzing discovery data to build mental model...';

      try {
        const res = await fetch(`/journeys/${journeyId}/knowledge-profile`, { method: 'POST' });
        if (!res.ok) throw new Error('Failed to synthesize profile');
        const profile = await res.json();
        renderProfile(profile);
      } catch (err) {
        document.getElementById('prof-summary').textContent = 'Failed to generate profile: ' + err.message;
      }
    }

    function renderProfile(profile) {
      const confBadge = document.getElementById('prof-confidence');
      confBadge.textContent = profile.overall_confidence.toUpperCase();
      confBadge.className = `confidence-badge confidence-${profile.overall_confidence}`;

      document.getElementById('prof-summary').textContent = profile.summary;

      const misContainer = document.getElementById('misconceptions-container');
      const misList = document.getElementById('misconceptions-list');
      if (profile.misconceptions && profile.misconceptions.length > 0) {
        misList.innerHTML = profile.misconceptions.map(m => `
          <div class="misconception-card"><span>⚠️</span><span>${escapeHtml(m)}</span></div>
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

      colKnown.innerHTML = knownConcepts.length ? knownConcepts.map(renderConceptCard).join('') : '<div style="font-size: 0.8rem; color: var(--text-muted);">None identified yet.</div>';
      colPartial.innerHTML = partialConcepts.length ? partialConcepts.map(renderConceptCard).join('') : '<div style="font-size: 0.8rem; color: var(--text-muted);">None identified yet.</div>';

      let gapsHtml = unknownConcepts.map(renderConceptCard).join('');
      if (profile.gaps && profile.gaps.length > 0) {
        gapsHtml += '<div style="font-size: 0.75rem; color: var(--text-muted); font-family: var(--font-mono); margin: 0.75rem 0 0.4rem 0;">IDENTIFIED GAPS:</div>';
        gapsHtml += profile.gaps.map(g => `
          <div class="gap-badge"><span>&bull;</span><span>${escapeHtml(g)}</span></div>
        `).join('');
      }
      colGaps.innerHTML = gapsHtml || '<div style="font-size: 0.8rem; color: var(--text-muted);">None identified yet.</div>';
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

      document.getElementById('arch-rationale').textContent = '🤖 Agent 3 designing personalized section blueprint around your gaps...';
      const bList = document.getElementById('blueprint-list');
      bList.innerHTML = '<div style="text-align: center; color: var(--text-muted); padding: 1.5rem;">Designing sections...</div>';

      try {
        const res = await fetch(`/journeys/${targetId}/architecture`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ learning_goal: 'Master core mechanics, resolve gaps, and implement in production' })
        });
        if (!res.ok) throw new Error('Failed to generate architecture');
        const arch = await res.json();
        renderArchitecture(arch);
      } catch (err) {
        document.getElementById('arch-rationale').textContent = 'Failed to generate architecture: ' + err.message;
      }
    }

    function renderArchitecture(arch) {
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
            <div style="font-size: 0.775rem; color: var(--text-muted); font-family: var(--font-mono);">
              Targets: ${s.target_concepts.map(tc => escapeHtml(tc)).join(', ')}
            </div>
            <div class="blueprint-features">
              ${s.needs_code ? '<span class="feature-pill active">💻 Code Required</span>' : ''}
              ${s.needs_visual ? `<span class="feature-pill active">📊 ${escapeHtml(s.visual_type || 'Diagram')}</span>` : ''}
            </div>
          </div>
        </div>
      `).join('');
    }



    async function loadRecentJourneys() {
      const listEl = document.getElementById('history-list');
      try {
        const res = await fetch('/journeys?limit=6');
        if (!res.ok) return;
        const data = await res.json();
        if (!data.journeys || data.journeys.length === 0) {
          listEl.innerHTML = '<div style="color: var(--text-muted); font-size: 0.875rem; text-align: center; padding: 1rem;">No journeys yet.</div>';
          return;
        }

        listEl.innerHTML = data.journeys.map(j => `
          <div class="history-item" onclick="resumeJourney('${j.id}', '${escapeHtml(j.topic)}', '${j.status}')">
            <div>
              <div class="history-topic">${escapeHtml(j.topic)}</div>
              <div style="font-size: 0.775rem; color: var(--text-muted); font-family: var(--font-mono); margin-top: 0.2rem;">ID: ${j.id.slice(0, 8)}...</div>
            </div>
            <div style="display: flex; align-items: center; gap: 0.75rem;">
              <span class="phase-badge">${formatStatus(j.status)}</span>
              <span style="font-size: 0.85rem; color: #a5b4fc;">&rarr;</span>
            </div>
          </div>
        `).join('');
      } catch (e) {
        console.error("Failed to load journeys", e);
      }
    }

    function formatStatus(status) {
      if (status === 'note_generated') return 'NOTE READY';
      if (status === 'architecture_ready') return 'ARCH READY';
      if (status === 'profile_ready') return 'PROFILE READY';
      if (status === 'probing') return 'DISCOVERY';
      return status.toUpperCase();
    }

    async function resumeJourney(journeyId, topic, status) {
      currentJourneyId = journeyId;
      currentTopic = topic;
      if (typeof resetCopilotState === 'function') resetCopilotState();

      if (status === 'note_generated') {
        try {
          const res = await fetch(`/journeys/${journeyId}/note`);
          if (res.ok) {
            const note = await res.json();
            renderNote(note);
            return;
          }
        } catch (e) { console.error(e); }
      }

      if (status === 'architecture_ready') {
        try {
          const res = await fetch(`/journeys/${journeyId}/architecture`);
          if (res.ok) {
            const arch = await res.json();
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
          const res = await fetch(`/journeys/${journeyId}/knowledge-profile`);
          if (res.ok) {
            const prof = await res.json();
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
        const res = await fetch(`/journeys/${journeyId}`);
        if (!res.ok) return;
        const j = await res.json();
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

