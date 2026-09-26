/**
 * Phase 15: Search and Knowledge Memory
 * Handles:
 * 1. Global Spotlight Search (Ctrl+K or Header/Toolbar buttons)
 * 2. Cross-Journey Learning History Timeline
 * 3. Concept Memory Inventory & Evolution Provenance
 * 4. Related Topics & Next Journey Recommendations
 * 5. In-Note Contextual Memory Cross-References
 */

let searchDebounceTimer = null;
let currentSearchType = 'all';
let activeSearchIndex = -1;
let currentSearchQuery = '';
let currentConceptMemories = [];

/* ==========================================================================
   1. GLOBAL SPOTLIGHT SEARCH CONTROLLER
   ========================================================================== */

function openSearchModal() {
  const modal = document.getElementById('spotlight-search-modal');
  if (!modal) return;
  modal.style.display = 'flex';
  const input = document.getElementById('spotlight-search-input');
  if (input) {
    input.value = '';
    input.focus();
  }
  setSearchTypeFilter('all');
  renderInitialSearchState();
}

function closeSearchModal() {
  const modal = document.getElementById('spotlight-search-modal');
  if (modal) modal.style.display = 'none';
}

function handleSearchKeydown(e) {
  const resultsContainer = document.getElementById('spotlight-results-container');
  const items = resultsContainer ? resultsContainer.querySelectorAll('.search-result-row') : [];

  if (e.key === 'ArrowDown') {
    e.preventDefault();
    if (items.length === 0) return;
    activeSearchIndex = (activeSearchIndex + 1) % items.length;
    updateActiveSearchResult(items);
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    if (items.length === 0) return;
    activeSearchIndex = (activeSearchIndex - 1 + items.length) % items.length;
    updateActiveSearchResult(items);
  } else if (e.key === 'Enter') {
    e.preventDefault();
    if (activeSearchIndex >= 0 && items[activeSearchIndex]) {
      items[activeSearchIndex].click();
    }
  } else if (e.key === 'Escape') {
    closeSearchModal();
  }
}

function updateActiveSearchResult(items) {
  items.forEach((item, idx) => {
    if (idx === activeSearchIndex) {
      item.classList.add('active-result');
      item.scrollIntoView({ block: 'nearest' });
    } else {
      item.classList.remove('active-result');
    }
  });
}

function setSearchTypeFilter(type) {
  currentSearchType = type;
  const pills = document.querySelectorAll('.search-filter-pill');
  pills.forEach(p => {
    if (p.getAttribute('data-type') === type) {
      p.classList.add('active');
    } else {
      p.classList.remove('active');
    }
  });
  triggerSearch();
}

function onSearchInput(e) {
  currentSearchQuery = e.target.value.trim();
  clearTimeout(searchDebounceTimer);
  searchDebounceTimer = setTimeout(() => {
    triggerSearch();
  }, 220);
}

function renderInitialSearchState() {
  const container = document.getElementById('spotlight-results-container');
  if (!container) return;
  container.innerHTML = `
    <div class="search-empty-state">
      <div style="font-size: 2.2rem; margin-bottom: 0.6rem;">🔍</div>
      <div style="font-weight: 600; color: #e2e8f0; margin-bottom: 0.3rem;">Instant Universal Technical Search</div>
      <div style="font-size: 0.82rem; color: var(--text-muted); max-width: 440px; margin: 0 auto;">
        Type any concept, code keyword, section title, or flashcard term. Press <kbd>↑</kbd> <kbd>↓</kbd> to navigate and <kbd>Enter</kbd> to jump.
      </div>
    </div>
  `;
}

async function triggerSearch() {
  const container = document.getElementById('spotlight-results-container');
  if (!container) return;

  if (!currentSearchQuery) {
    renderInitialSearchState();
    return;
  }

  container.innerHTML = `
    <div style="padding: 2rem; text-align: center; color: var(--text-muted); font-size: 0.85rem;">
      <span class="spinner-pulse">⏳</span> Searching notes, concepts, code & assessments...
    </div>
  `;

  try {
    const url = `/search?q=${encodeURIComponent(currentSearchQuery)}&type=${currentSearchType}&limit=35`;
    const res = await fetch(url);
    if (!res.ok) throw new Error('Search request failed');
    const data = await res.json();
    renderSearchResults(data);
  } catch (err) {
    container.innerHTML = `
      <div style="padding: 2rem; text-align: center; color: #f87171; font-size: 0.85rem;">
        Failed to fetch search results: ${escapeHtml(err.message)}
      </div>
    `;
  }
}

function renderSearchResults(data) {
  const container = document.getElementById('spotlight-results-container');
  if (!container) return;

  activeSearchIndex = -1;

  if (!data.results || data.results.length === 0) {
    container.innerHTML = `
      <div class="search-empty-state">
        <div style="font-size: 1.8rem; margin-bottom: 0.5rem;">🕵️</div>
        <div style="font-weight: 600; color: #e2e8f0;">No results found for "${escapeHtml(data.query)}"</div>
        <div style="font-size: 0.8rem; color: var(--text-muted); margin-top: 0.25rem;">
          Try searching for another technical concept, journey, or keyword.
        </div>
      </div>
    `;
    return;
  }

  const typeIcons = {
    journey: '🗺️',
    note: '📖',
    section: '📑',
    concept: '💡',
    code: '💻',
    flashcard: '📇',
  };

  const typeColors = {
    journey: '#818cf8',
    note: '#38bdf8',
    section: '#34d399',
    concept: '#fbbf24',
    code: '#a78bfa',
    flashcard: '#f472b6',
  };

  container.innerHTML = data.results.map((r, idx) => {
    const icon = typeIcons[r.result_type] || '🔍';
    const color = typeColors[r.result_type] || '#94a3b8';
    return `
      <div class="search-result-row" data-index="${idx}" onclick="selectSearchResult('${escapeJsString(r.id)}', '${r.result_type}', '${escapeJsString(r.journey_id || '')}', '${escapeJsString(r.note_id || '')}', '${escapeJsString(r.section_id || '')}', '${escapeJsString(r.title)}')">
        <div class="result-icon-col" style="color: ${color};">
          <span style="font-size: 1.15rem;">${icon}</span>
        </div>
        <div class="result-content-col">
          <div class="result-header-row">
            <span class="result-type-badge" style="background: ${color}20; color: ${color}; border: 1px solid ${color}40;">
              ${r.result_type.toUpperCase()}
            </span>
            <span class="result-title">${escapeHtml(r.title)}</span>
            ${r.journey_topic ? `<span class="result-journey-tag">in ${escapeHtml(r.journey_topic)}</span>` : ''}
          </div>
          <div class="result-snippet">${r.snippet}</div>
        </div>
        <div class="result-jump-arrow">&rarr;</div>
      </div>
    `;
  }).join('');
}

async function selectSearchResult(id, type, journeyId, noteId, sectionId, title) {
  closeSearchModal();

  if (type === 'concept') {
    // Open Concept Provenance modal
    openConceptProvenanceModal(title);
    return;
  }

  if (journeyId && journeyId !== currentJourneyId) {
    // Switch to this journey
    await loadJourneyById(journeyId);
  }

  // Handle section jumping
  if (sectionId) {
    setTimeout(() => {
      // Find section container
      const secEl = document.querySelector(`[data-section-id="${sectionId}"]`) || 
                    document.getElementById(`sec-${sectionId}`) ||
                    document.getElementById(sectionId);
      if (secEl) {
        secEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
        secEl.classList.add('section-highlight-pulse');
        setTimeout(() => secEl.classList.remove('section-highlight-pulse'), 2500);
      } else {
        // Fallback: scroll to note panel
        const notePanel = document.getElementById('note-panel');
        if (notePanel) notePanel.scrollIntoView({ behavior: 'smooth' });
      }
    }, 350);
  } else if (type === 'flashcard') {
    openAssessmentModal();
  } else {
    const notePanel = document.getElementById('note-panel');
    if (notePanel) notePanel.scrollIntoView({ behavior: 'smooth' });
  }
}

/* ==========================================================================
   2. KNOWLEDGE MEMORY & LEARNING HISTORY MODAL
   ========================================================================== */

function openMemoryModal(initialTab = 'history') {
  const modal = document.getElementById('knowledge-memory-modal');
  if (!modal) return;
  modal.style.display = 'flex';
  switchMemoryModalTab(initialTab);
  loadMemoryOverview();
}

function closeMemoryModal() {
  const modal = document.getElementById('knowledge-memory-modal');
  if (modal) modal.style.display = 'none';
}

function switchMemoryModalTab(tab) {
  const btnHistory = document.getElementById('btn-mtab-history');
  const btnConcepts = document.getElementById('btn-mtab-concepts');
  const btnRelated = document.getElementById('btn-mtab-related');

  const viewHistory = document.getElementById('memory-history-view');
  const viewConcepts = document.getElementById('memory-concepts-view');
  const viewRelated = document.getElementById('memory-related-view');

  [btnHistory, btnConcepts, btnRelated].forEach(b => b && b.classList.remove('active'));
  [viewHistory, viewConcepts, viewRelated].forEach(v => v && (v.style.display = 'none'));

  if (tab === 'history') {
    if (btnHistory) btnHistory.classList.add('active');
    if (viewHistory) viewHistory.style.display = 'block';
    loadLearningHistory();
  } else if (tab === 'concepts') {
    if (btnConcepts) btnConcepts.classList.add('active');
    if (viewConcepts) viewConcepts.style.display = 'block';
    loadConceptMemories();
  } else if (tab === 'related') {
    if (btnRelated) btnRelated.classList.add('active');
    if (viewRelated) viewRelated.style.display = 'block';
    loadRelatedTopics();
  }
}

async function loadMemoryOverview() {
  const container = document.getElementById('memory-overview-stats');
  if (!container) return;

  try {
    const res = await fetch('/memory/overview');
    if (!res.ok) throw new Error('Failed to load overview');
    const data = await res.json();

    container.innerHTML = `
      <div class="mstat-card">
        <div class="mstat-num">${data.total_journeys}</div>
        <div class="mstat-label">Learning Journeys</div>
      </div>
      <div class="mstat-card">
        <div class="mstat-num" style="color: #38bdf8;">${data.total_concepts_tracked}</div>
        <div class="mstat-label">Concepts Tracked</div>
      </div>
      <div class="mstat-card">
        <div class="mstat-num" style="color: #34d399;">${data.total_concepts_mastered}</div>
        <div class="mstat-label">Concepts Mastered</div>
      </div>
      <div class="mstat-card">
        <div class="mstat-num" style="color: #f87171;">${data.total_knowledge_gaps}</div>
        <div class="mstat-label">Knowledge Gaps</div>
      </div>
      <div class="mstat-card">
        <div class="mstat-num" style="color: #a78bfa;">${data.top_bridging_concepts.length}</div>
        <div class="mstat-label">Cross-Journey Bridges</div>
      </div>
    `;
  } catch (err) {
    console.warn('Memory overview load error:', err);
  }
}

async function loadLearningHistory() {
  const container = document.getElementById('memory-history-feed');
  if (!container) return;

  container.innerHTML = `
    <div style="padding: 2rem; text-align: center; color: var(--text-muted); font-size: 0.85rem;">
      <span class="spinner-pulse">⏳</span> Loading learning journeys timeline...
    </div>
  `;

  try {
    const res = await fetch('/memory/history');
    if (!res.ok) throw new Error('Failed to load history');
    const items = await res.json();

    if (!items || items.length === 0) {
      container.innerHTML = `
        <div class="search-empty-state">
          <div style="font-size: 1.8rem; margin-bottom: 0.4rem;">🌱</div>
          <div style="font-weight: 600; color: #e2e8f0;">No learning journeys yet</div>
          <div style="font-size: 0.8rem; color: var(--text-muted); margin-top: 0.2rem;">
            Start your first technical exploration using the topic intake form above!
          </div>
        </div>
      `;
      return;
    }

    container.innerHTML = items.map((item, idx) => {
      const dt = new Date(item.created_at).toLocaleDateString(undefined, {
        month: 'short',
        day: 'numeric',
        year: 'numeric'
      });

      const conceptChips = (item.concept_names || []).slice(0, 6).map(c => `
        <span class="mconcept-chip" onclick="openConceptProvenanceModal('${escapeJsString(c)}')">${escapeHtml(c)}</span>
      `).join('');

      return `
        <div class="mhistory-timeline-card">
          <div class="mhistory-left-dot"></div>
          <div class="mhistory-header">
            <div>
              <div class="mhistory-topic-title">${escapeHtml(item.topic)}</div>
              <div class="mhistory-meta">
                <span>📅 ${dt}</span>
                <span>•</span>
                <span class="mstatus-pill mstatus-${item.status}">${item.status.toUpperCase()}</span>
                ${item.note_version ? `<span>•</span><span class="mver-pill">Note v${item.note_version}</span>` : ''}
                ${item.latest_quiz_score ? `<span>•</span><span class="mscore-pill">Quiz: ${item.latest_quiz_score}</span>` : ''}
              </div>
            </div>
            <div class="mhistory-actions">
              <button type="button" class="btn-submit" onclick="selectJourneyFromHistory('${item.id}')" style="padding: 0.4rem 0.85rem; font-size: 0.775rem;">
                <span>📖 Open Living Note</span>
              </button>
            </div>
          </div>
          <div class="mhistory-concepts-row">
            <span style="font-size: 0.75rem; color: var(--text-muted); margin-right: 0.3rem;">Concepts:</span>
            ${conceptChips || '<span style="font-size: 0.75rem; color: var(--text-muted);">None recorded</span>'}
            ${(item.concept_names || []).length > 6 ? `<span style="font-size: 0.75rem; color: #a5b4fc;">+${item.concept_names.length - 6} more</span>` : ''}
          </div>
        </div>
      `;
    }).join('');
  } catch (err) {
    container.innerHTML = `
      <div style="padding: 2rem; text-align: center; color: #f87171; font-size: 0.85rem;">
        Failed to load history: ${escapeHtml(err.message)}
      </div>
    `;
  }
}

async function selectJourneyFromHistory(journeyId) {
  closeMemoryModal();
  await loadJourneyById(journeyId);
  const notePanel = document.getElementById('note-panel');
  if (notePanel) notePanel.scrollIntoView({ behavior: 'smooth' });
}

async function loadConceptMemories() {
  const container = document.getElementById('memory-concepts-grid');
  if (!container) return;

  container.innerHTML = `
    <div style="padding: 2rem; text-align: center; color: var(--text-muted); font-size: 0.85rem;">
      <span class="spinner-pulse">⏳</span> Loading concept memory inventory...
    </div>
  `;

  try {
    const res = await fetch('/memory/concepts');
    if (!res.ok) throw new Error('Failed to load concept memories');
    currentConceptMemories = await res.json();
    renderFilteredConceptGrid('');
  } catch (err) {
    container.innerHTML = `
      <div style="padding: 2rem; text-align: center; color: #f87171; font-size: 0.85rem;">
        Failed to load concepts: ${escapeHtml(err.message)}
      </div>
    `;
  }
}

function filterConceptGrid(query) {
  renderFilteredConceptGrid(query.trim().toLowerCase());
}

function renderFilteredConceptGrid(q) {
  const container = document.getElementById('memory-concepts-grid');
  if (!container) return;

  const filtered = currentConceptMemories.filter(c => {
    if (!q) return true;
    return c.concept_name.toLowerCase().includes(q) ||
           c.first_encountered_journey_topic.toLowerCase().includes(q) ||
           c.current_status.toLowerCase().includes(q);
  });

  if (filtered.length === 0) {
    container.innerHTML = `
      <div style="padding: 2rem; text-align: center; color: var(--text-muted); font-size: 0.85rem; grid-column: 1 / -1;">
        No concepts matching filter.
      </div>
    `;
    return;
  }

  container.innerHTML = filtered.map(c => {
    const isMastered = c.current_status === 'mastered' || c.current_status === 'known';
    const statusColor = isMastered ? '#34d399' : (c.current_status === 'partial' ? '#fbbf24' : '#f87171');
    const firstDate = new Date(c.first_encountered_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });

    return `
      <div class="mconcept-card" onclick="openConceptProvenanceModal('${escapeJsString(c.concept_name)}')">
        <div class="mconcept-card-header">
          <div class="mconcept-name">${escapeHtml(c.concept_name)}</div>
          <span class="mconcept-status" style="background: ${statusColor}18; color: ${statusColor}; border: 1px solid ${statusColor}40;">
            ${c.current_status.toUpperCase()}
          </span>
        </div>
        <div class="mconcept-story">${escapeHtml(c.provenance_story)}</div>
        <div class="mconcept-footer">
          <span class="mconcept-apps">🔁 ${c.total_appearances} journey${c.total_appearances > 1 ? 's' : ''}</span>
          <span class="mconcept-date">Seen ${firstDate}</span>
        </div>
      </div>
    `;
  }).join('');
}

async function loadRelatedTopics() {
  const container = document.getElementById('memory-related-container');
  if (!container) return;

  if (!currentJourneyId) {
    container.innerHTML = `
      <div class="search-empty-state">
        <div style="font-size: 1.8rem; margin-bottom: 0.4rem;">🧭</div>
        <div style="font-weight: 600; color: #e2e8f0;">No active journey selected</div>
        <div style="font-size: 0.8rem; color: var(--text-muted); margin-top: 0.2rem;">
          Select or start a learning journey to see cross-journey concept links and recommended next paths.
        </div>
      </div>
    `;
    return;
  }

  container.innerHTML = `
    <div style="padding: 2rem; text-align: center; color: var(--text-muted); font-size: 0.85rem;">
      <span class="spinner-pulse">⏳</span> Synthesizing related topics and concept bridges...
    </div>
  `;

  try {
    const res = await fetch(`/memory/related/${currentJourneyId}`);
    if (!res.ok) throw new Error('Failed to load related topics');
    const data = await res.json();

    const bridgingHtml = (data.bridging_concepts || []).length > 0 ? `
      <div class="mbridge-banner">
        <div style="font-weight: 600; color: #a5b4fc; font-size: 0.85rem; margin-bottom: 0.3rem;">
          🌉 Cross-Journey Concept Bridges (${data.bridging_concepts.length})
        </div>
        <div style="font-size: 0.8rem; color: var(--text-muted); margin-bottom: 0.6rem;">
          These foundational concepts link your current exploration with other technical domains you have studied:
        </div>
        <div style="display: flex; flex-wrap: wrap; gap: 0.4rem;">
          ${data.bridging_concepts.map(c => `
            <span class="mconcept-chip" onclick="openConceptProvenanceModal('${escapeJsString(c)}')">${escapeHtml(c)}</span>
          `).join('')}
        </div>
      </div>
    ` : '';

    const cardsHtml = (data.related_topics || []).map(item => `
      <div class="mrelated-card">
        <div class="mrelated-header">
          <div class="mrelated-title">${escapeHtml(item.topic)}</div>
          <span class="mrelated-type">${item.relationship_type.replace(/_/g, ' ').toUpperCase()}</span>
        </div>
        <div class="mrelated-reason">${escapeHtml(item.reason)}</div>
        <div class="mrelated-footer">
          ${item.existing_journey_id ? `
            <button type="button" class="btn-submit" onclick="selectJourneyFromHistory('${item.existing_journey_id}')" style="padding: 0.35rem 0.8rem; font-size: 0.775rem;">
              <span>📖 Open Existing Journey</span>
            </button>
          ` : `
            <button type="button" class="btn-submit" onclick="startNewJourneyWithTopic('${escapeJsString(item.topic)}')" style="padding: 0.35rem 0.8rem; font-size: 0.775rem; background: linear-gradient(135deg, #10b981 0%, #059669 100%);">
              <span>🚀 Start This Journey</span>
            </button>
          `}
        </div>
      </div>
    `).join('');

    container.innerHTML = `
      ${bridgingHtml}
      <div class="mrelated-grid">
        ${cardsHtml}
      </div>
    `;
  } catch (err) {
    container.innerHTML = `
      <div style="padding: 2rem; text-align: center; color: #f87171; font-size: 0.85rem;">
        Failed to load related topics: ${escapeHtml(err.message)}
      </div>
    `;
  }
}

function startNewJourneyWithTopic(topic) {
  closeMemoryModal();
  setTopic(topic);
  const intakeForm = document.getElementById('intake-card');
  if (intakeForm) intakeForm.scrollIntoView({ behavior: 'smooth' });
}

/* ==========================================================================
   3. CONCEPT PROVENANCE DEEP DIVE MODAL
   ========================================================================== */

async function openConceptProvenanceModal(conceptName) {
  const modal = document.getElementById('concept-provenance-modal');
  if (!modal) return;
  modal.style.display = 'flex';

  const titleEl = document.getElementById('cprov-title');
  const storyEl = document.getElementById('cprov-story');
  const feedEl = document.getElementById('cprov-timeline-feed');
  const relatedEl = document.getElementById('cprov-related-chips');

  titleEl.textContent = conceptName;
  storyEl.textContent = 'Retrieving concept memory provenance...';
  feedEl.innerHTML = '<div style="color: var(--text-muted); font-size: 0.85rem;">Loading timeline...</div>';
  relatedEl.innerHTML = '';

  try {
    const res = await fetch(`/memory/concepts/${encodeURIComponent(conceptName)}`);
    if (!res.ok) throw new Error('Concept memory not found');
    const data = await res.json();

    storyEl.textContent = data.provenance_story;

    // Render timeline steps
    feedEl.innerHTML = data.history.map((step, idx) => {
      const dt = new Date(step.timestamp).toLocaleDateString(undefined, {
        month: 'short',
        day: 'numeric',
        year: 'numeric'
      });
      return `
        <div class="cprov-step-item">
          <div class="cprov-step-num">${idx + 1}</div>
          <div class="cprov-step-content">
            <div style="font-weight: 600; color: #e2e8f0; font-size: 0.85rem;">${escapeHtml(step.journey_topic)}</div>
            <div style="font-size: 0.75rem; color: var(--text-muted); margin-bottom: 0.25rem;">
              <span>${dt}</span> • <span>Event: ${step.event_type.replace(/_/g, ' ')}</span> • <span style="color: #a5b4fc;">Category: ${step.category}</span>
            </div>
            ${step.context_note ? `<div style="font-size: 0.775rem; color: #cbd5e1; background: rgba(0,0,0,0.25); padding: 0.4rem; border-radius: 4px;">${escapeHtml(step.context_note)}</div>` : ''}
          </div>
        </div>
      `;
    }).join('');

    // Render related concept chips
    relatedEl.innerHTML = (data.related_concepts || []).map(rc => `
      <span class="mconcept-chip" onclick="openConceptProvenanceModal('${escapeJsString(rc)}')">${escapeHtml(rc)}</span>
    `).join('') || '<span style="font-size: 0.75rem; color: var(--text-muted);">None linked</span>';

  } catch (err) {
    storyEl.textContent = `Could not load provenance: ${err.message}`;
    feedEl.innerHTML = '';
  }
}

function closeConceptProvenanceModal() {
  const modal = document.getElementById('concept-provenance-modal');
  if (modal) modal.style.display = 'none';
}

/* ==========================================================================
   4. IN-NOTE CROSS-REFERENCES DECORATOR
   ========================================================================== */

async function loadNoteMemoryCrossReferences(noteId) {
  if (!noteId) return;
  try {
    const res = await fetch(`/memory/notes/${noteId}/cross-references`);
    if (!res.ok) return;
    const data = await res.json();
    if (data.cross_references && data.cross_references.length > 0) {
      applyInNoteMemoryBadges(data.cross_references);
    }
  } catch (err) {
    console.warn('In-note memory cross-ref load error:', err);
  }
}

function applyInNoteMemoryBadges(crossRefs) {
  crossRefs.forEach(ref => {
    // If associated with a section ID
    const secEl = ref.section_id ? document.querySelector(`[data-section-id="${ref.section_id}"]`) || document.getElementById(`sec-${ref.section_id}`) : null;
    const targetHeader = secEl ? secEl.querySelector('.section-meta-tags') : null;

    if (targetHeader && !targetHeader.querySelector(`.memory-ref-badge[data-concept="${ref.concept_name}"]`)) {
      const badge = document.createElement('button');
      badge.type = 'button';
      badge.className = 'tool-btn memory-ref-badge';
      badge.setAttribute('data-concept', ref.concept_name);
      badge.title = ref.provenance_story;
      badge.innerHTML = `<span>🧠 Memory: Seen in ${escapeHtml(ref.first_journey_topic.slice(0, 18))}...</span>`;
      badge.onclick = () => openConceptProvenanceModal(ref.concept_name);
      targetHeader.prepend(badge);
    }
  });
}

/* ==========================================================================
   5. GLOBAL KEYBOARD SHORTCUTS
   ========================================================================== */

window.addEventListener('keydown', (e) => {
  // Ctrl+K or Cmd+K opens Spotlight Search
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault();
    const modal = document.getElementById('spotlight-search-modal');
    if (modal && modal.style.display === 'flex') {
      closeSearchModal();
    } else {
      openSearchModal();
    }
  }
});
