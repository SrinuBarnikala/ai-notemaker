/* copilot.js — Agent 9 Socratic AI In-Note Copilot, Contextual Explainer & Direct Note Pinning */

function resetCopilotState() {
  activeCopilotSectionId = null;
  activeCopilotSectionTitle = null;
  activeCopilotSelectedText = null;
  copilotHistory = [];

  const input = document.getElementById('copilot-input');
  if (input) input.value = '';

  const quoteWrap = document.getElementById('copilot-selected-quote');
  const quoteText = document.getElementById('copilot-quote-text');
  if (quoteWrap) quoteWrap.style.display = 'none';
  if (quoteText) quoteText.textContent = '';

  const msgContainer = document.getElementById('copilot-messages');
  if (msgContainer) msgContainer.innerHTML = '';

  const contextPill = document.getElementById('copilot-context-pill');
  if (contextPill) {
    contextPill.textContent = '📍 Note Context';
    contextPill.title = '';
  }

  const drawer = document.getElementById('copilot-drawer');
  const backdrop = document.getElementById('copilot-backdrop');
  if (drawer) drawer.classList.remove('open');
  if (backdrop) backdrop.style.display = 'none';

  const floatBadge = document.getElementById('floating-ask-badge');
  if (floatBadge) floatBadge.style.display = 'none';
}
window.resetCopilotState = resetCopilotState;

function openCopilotDrawer(sectionId = null, sectionTitle = null, prefillQuestion = "", selectedText = null) {
  if (!currentJourneyId) {
    alert("Please create or open a learning journey first to consult Agent 9 Copilot.");
    return;
  }

  // Validate that sectionId belongs to currentNote if specified
  if (sectionId && currentNote && Array.isArray(currentNote.sections)) {
    const exists = currentNote.sections.some(s => s.id === sectionId);
    if (!exists) {
      sectionId = null;
      sectionTitle = null;
    }
  }

  activeCopilotSectionId = sectionId;
  activeCopilotSectionTitle = sectionTitle;
  activeCopilotSelectedText = selectedText;

  const drawer = document.getElementById('copilot-drawer');
  const backdrop = document.getElementById('copilot-backdrop');
  if (!drawer) return;

  drawer.classList.add('open');
  if (backdrop) backdrop.style.display = 'block';

  // Update header context badge
  const contextPill = document.getElementById('copilot-context-pill');
  if (contextPill) {
    if (sectionTitle) {
      contextPill.textContent = `📍 ${sectionTitle}`;
      contextPill.title = `Grounded in section: ${sectionTitle}`;
    } else if (currentTopic) {
      contextPill.textContent = `📍 ${currentTopic} (All Sections)`;
      contextPill.title = "Grounded in entire living note";
    } else {
      contextPill.textContent = `📍 Note Context`;
    }
  }

  // Update quote preview if text was selected
  const quoteWrap = document.getElementById('copilot-selected-quote');
  const quoteText = document.getElementById('copilot-quote-text');
  if (quoteWrap && quoteText) {
    if (selectedText && selectedText.trim()) {
      quoteText.textContent = `"${selectedText.trim().substring(0, 160)}${selectedText.length > 160 ? '...' : ''}"`;
      quoteWrap.style.display = 'flex';
    } else {
      quoteWrap.style.display = 'none';
      quoteText.textContent = '';
    }
  }

  // Set prefill question if provided
  const input = document.getElementById('copilot-input');
  if (input) {
    if (prefillQuestion) {
      input.value = prefillQuestion;
    }
    input.focus();
  }

  // Initial welcome greeting if thread is empty
  const msgContainer = document.getElementById('copilot-messages');
  if (msgContainer && msgContainer.children.length === 0) {
    renderCopilotWelcome();
  }

  // Hide floating ask badge if active
  const floatBadge = document.getElementById('floating-ask-badge');
  if (floatBadge) floatBadge.style.display = 'none';

  scrollCopilotToBottom();
}

function closeCopilotDrawer() {
  const drawer = document.getElementById('copilot-drawer');
  const backdrop = document.getElementById('copilot-backdrop');
  if (drawer) drawer.classList.remove('open');
  if (backdrop) backdrop.style.display = 'none';
  activeCopilotSelectedText = null;
  const quoteWrap = document.getElementById('copilot-selected-quote');
  if (quoteWrap) quoteWrap.style.display = 'none';
}

function clearCopilotSelectedQuote() {
  activeCopilotSelectedText = null;
  const quoteWrap = document.getElementById('copilot-selected-quote');
  if (quoteWrap) quoteWrap.style.display = 'none';
}

function renderCopilotWelcome() {
  const msgContainer = document.getElementById('copilot-messages');
  if (!msgContainer) return;

  const topicName = currentTopic || "your topic";
  const welcomeHtml = `
    <div class="copilot-msg assistant">
      <div class="copilot-avatar">🤖</div>
      <div class="copilot-bubble">
        <div class="copilot-msg-header">Agent 9 &bull; Socratic Copilot</div>
        <p>I am your contextual learning copilot for <strong>${escapeHtml(topicName)}</strong>. I adapt to your mental model, address detected knowledge gaps, and can explain any paragraph, diagram, or code block.</p>
        <p style="margin-top: 0.5rem; font-size: 0.85rem; color: #a5b4fc;">Ask anything or pick a quick starter below:</p>
        <div class="copilot-followup-chips" style="margin-top: 0.65rem;">
          <button type="button" class="copilot-chip" onclick="handleQuickPrompt('Why is this architecture designed this way instead of common alternatives?')">Why this architecture?</button>
          <button type="button" class="copilot-chip" onclick="handleQuickPrompt('What are the edge-case failure modes and recovery sequence?')">Edge-case failure modes?</button>
          <button type="button" class="copilot-chip" onclick="handleQuickPrompt('Walk me through the memory and runtime complexity trade-offs.')">Complexity trade-offs?</button>
        </div>
      </div>
    </div>
  `;
  msgContainer.innerHTML = welcomeHtml;
}

function handleQuickPrompt(text) {
  const input = document.getElementById('copilot-input');
  if (input) {
    input.value = text;
    sendCopilotMessage();
  }
}

async function sendCopilotMessage() {
  const input = document.getElementById('copilot-input');
  if (!input) return;
  const question = input.value.trim();
  if (!question) return;

  if (!currentJourneyId) {
    alert("Please load or create a journey first.");
    return;
  }

  const msgContainer = document.getElementById('copilot-messages');
  const btnSend = document.getElementById('btn-send-copilot');

  // Render User Message
  const userMsgHtml = `
    <div class="copilot-msg user">
      <div class="copilot-bubble user-bubble">
        ${activeCopilotSelectedText ? `<div class="user-quote-ref">“${escapeHtml(activeCopilotSelectedText.substring(0, 100))}...”</div>` : ''}
        ${escapeHtml(question)}
      </div>
      <div class="copilot-avatar user-avatar">👤</div>
    </div>
  `;
  msgContainer.insertAdjacentHTML('beforeend', userMsgHtml);
  copilotHistory.push({ role: "user", content: question });

  // Clear input & selected quote
  input.value = "";
  const quoteWrap = document.getElementById('copilot-selected-quote');
  if (quoteWrap) quoteWrap.style.display = 'none';

  // Render Loading Indicator
  const loadingId = 'copilot-typing-' + Date.now();
  const loadingHtml = `
    <div class="copilot-msg assistant" id="${loadingId}">
      <div class="copilot-avatar">🤖</div>
      <div class="copilot-bubble copilot-typing-bubble">
        <span class="typing-dot"></span>
        <span class="typing-dot"></span>
        <span class="typing-dot"></span>
        <span style="margin-left: 0.5rem; font-size: 0.8rem; color: #a5b4fc;">Agent 9 analyzing knowledge profile &amp; note context...</span>
      </div>
    </div>
  `;
  msgContainer.insertAdjacentHTML('beforeend', loadingHtml);
  scrollCopilotToBottom();

  if (btnSend) btnSend.disabled = true;

  try {
    const payload = {
      question: question,
      section_id: activeCopilotSectionId,
      selected_text: activeCopilotSelectedText,
      history: copilotHistory.slice(-6)
    };

    const res = await fetch(`/journeys/${currentJourneyId}/copilot/ask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.detail || "Failed to consult Copilot.");
    }

    const data = await res.json();

    // Remove loading indicator
    const loader = document.getElementById(loadingId);
    if (loader) loader.remove();

    // Save assistant reply in history
    copilotHistory.push({ role: "assistant", content: data.answer });

    // Render Assistant Message with Pinning & Follow-ups
    renderAssistantResponse(data);

  } catch (err) {
    const loader = document.getElementById(loadingId);
    if (loader) loader.remove();

    const errorHtml = `
      <div class="copilot-msg assistant">
        <div class="copilot-avatar">⚠️</div>
        <div class="copilot-bubble" style="border-color: rgba(239, 68, 68, 0.4); background: rgba(239, 68, 68, 0.1);">
          <div style="font-weight: 700; color: #f87171; margin-bottom: 0.3rem;">Copilot Inquire Error</div>
          <div style="font-size: 0.85rem; color: #cbd5e1;">${escapeHtml(err.message)}</div>
        </div>
      </div>
    `;
    msgContainer.insertAdjacentHTML('beforeend', errorHtml);
  } finally {
    if (btnSend) btnSend.disabled = false;
    activeCopilotSelectedText = null;
    scrollCopilotToBottom();
  }
}

function formatMarkdownResponse(raw) {
  if (!raw) return "";
  let html = escapeHtml(raw);

  // Bold
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  
  // Headers (### and ##)
  html = html.replace(/^### (.*$)/gim, '<h4 style="font-size: 0.95rem; font-weight: 700; color: #c7d2fe; margin: 0.6rem 0 0.25rem;">$1</h4>');
  html = html.replace(/^## (.*$)/gim, '<h3 style="font-size: 1.05rem; font-weight: 800; color: #e0e7ff; margin: 0.75rem 0 0.3rem;">$1</h3>');

  // Code blocks: ```lang ... ```
  html = html.replace(/```([a-zA-Z0-9_\-\+]*)\n([\s\S]*?)```/g, function(match, lang, code) {
    return `<pre class="copilot-code-block"><code class="lang-${lang}">${code.trim()}</code></pre>`;
  });

  // Inline code `...`
  html = html.replace(/`([^`]+)`/g, '<code class="copilot-inline-code">$1</code>');

  // Bullet items
  html = html.replace(/^\- (.*$)/gim, '<li style="margin-left: 1.2rem; margin-bottom: 0.25rem;">$1</li>');
  html = html.replace(/(<li.*<\/li>)/s, '<ul style="margin: 0.4rem 0;">$1</ul>');

  // Paragraph breaks
  html = html.replace(/\n\n+/g, '<p style="margin-top: 0.5rem;"></p>');

  return html;
}

function renderAssistantResponse(data) {
  const msgContainer = document.getElementById('copilot-messages');
  if (!msgContainer) return;

  const targetSecId = data.section_id || activeCopilotSectionId;
  const targetSecTitle = data.section_title || activeCopilotSectionTitle || "Relevant Section";
  const pinCandidate = data.pin_candidate;
  const pinId = 'pin-btn-' + Date.now();

  const formattedAnswer = formatMarkdownResponse(data.answer);

  // Build Pin Action Banner if candidate exists
  let pinBannerHtml = "";
  if (pinCandidate && pinCandidate.content) {
    pinBannerHtml = `
      <div class="copilot-pin-banner">
        <div class="pin-banner-left">
          <div class="pin-banner-badge">📌 HIGH-YIELD INSIGHT</div>
          <div class="pin-banner-title">${escapeHtml(pinCandidate.title || 'Copilot Note Callout')}</div>
          <div class="pin-banner-desc">${escapeHtml(pinCandidate.content.substring(0, 120))}${pinCandidate.content.length > 120 ? '...' : ''}</div>
        </div>
        <button type="button" class="copilot-pin-btn" id="${pinId}" onclick='pinCopilotAnswerToSection("${pinId}", "${escapeJsString(targetSecId || '')}", "${escapeJsString(targetSecTitle)}", ${JSON.stringify(pinCandidate).replace(/'/g, "&#39;")})'>
          <span>📌 Pin to Note</span>
        </button>
      </div>
    `;
  }

  // Build Follow-up Suggestions
  let followupsHtml = "";
  if (data.suggested_followups && data.suggested_followups.length > 0) {
    followupsHtml = `
      <div class="copilot-followups-wrap">
        <span class="followups-label">Suggested follow-ups:</span>
        <div class="copilot-followup-chips">
          ${data.suggested_followups.map(f => `
            <button type="button" class="copilot-chip" onclick="handleQuickPrompt('${escapeJsString(f)}')">
              ${escapeHtml(f)}
            </button>
          `).join('')}
        </div>
      </div>
    `;
  }

  const assistantHtml = `
    <div class="copilot-msg assistant">
      <div class="copilot-avatar">🤖</div>
      <div class="copilot-bubble">
        <div class="copilot-msg-header">Agent 9 &bull; Socratic Explainer</div>
        <div class="copilot-answer-text">${formattedAnswer}</div>
        ${pinBannerHtml}
        ${followupsHtml}
      </div>
    </div>
  `;

  msgContainer.insertAdjacentHTML('beforeend', assistantHtml);
  scrollCopilotToBottom();
}

async function pinCopilotAnswerToSection(btnId, sectionId, sectionTitle, pinCandidate) {
  const btn = document.getElementById(btnId);
  if (!btn) return;

  if (!currentJourneyId) {
    alert("Journey context missing.");
    return;
  }

  // If no specific sectionId passed, fallback to first section
  let targetId = sectionId;
  if (!targetId && currentNote && currentNote.sections && currentNote.sections.length > 0) {
    targetId = currentNote.sections[0].id;
  }

  if (!targetId) {
    alert("Please select a specific section to pin this note into.");
    return;
  }

  const origHtml = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<span>⏳ Pinning...</span>`;

  try {
    const payload = {
      section_id: targetId,
      block_type: pinCandidate.block_type || "example",
      title: pinCandidate.title || "Key Takeaway",
      term: pinCandidate.term || null,
      content: pinCandidate.content,
      code: pinCandidate.code || null,
      language: pinCandidate.language || null
    };

    const res = await fetch(`/journeys/${currentJourneyId}/copilot/pin`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Failed to pin block.");
    }

    const resData = await res.json();

    btn.classList.add('pinned');
    btn.innerHTML = `<span>✓ Pinned (v${resData.note_version})!</span>`;

    // Automatically reload living note so the reader reflects the pinned block & version bump
    if (typeof loadNote === 'function' && currentNote) {
      await loadNote(currentNote.id || currentJourneyId);
    }

    // Scroll to the updated section
    setTimeout(() => {
      const targetSecEl = document.getElementById(`sec-${targetId}`);
      if (targetSecEl) {
        targetSecEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }, 400);

  } catch (err) {
    btn.disabled = false;
    btn.innerHTML = origHtml;
    alert("Error pinning to note: " + err.message);
  }
}

function scrollCopilotToBottom() {
  const body = document.getElementById('copilot-messages-container');
  if (body) {
    body.scrollTop = body.scrollHeight;
  }
}

/* Floating "Ask AI about this" Selection Pill */
function initSelectionDetector() {
  const noteBody = document.getElementById('note-content-body');
  const floatingBadge = document.getElementById('floating-ask-badge');
  if (!noteBody || !floatingBadge) return;

  document.addEventListener('selectionchange', () => {
    const selection = window.getSelection();
    if (!selection || selection.isCollapsed) {
      floatingBadge.style.display = 'none';
      return;
    }

    const text = selection.toString().trim();
    if (text.length < 5 || text.length > 400) {
      floatingBadge.style.display = 'none';
      return;
    }

    // Check if selection is within note body
    const anchor = selection.anchorNode;
    if (!anchor || !noteBody.contains(anchor)) {
      floatingBadge.style.display = 'none';
      return;
    }

    // Calculate position
    const range = selection.getRangeAt(0);
    const rect = range.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) {
      floatingBadge.style.display = 'none';
      return;
    }

    // Find parent section
    let currentElem = anchor.nodeType === 3 ? anchor.parentElement : anchor;
    const parentSection = currentElem ? currentElem.closest('.note-section-container') : null;
    let secId = null;
    let secTitle = null;
    if (parentSection && parentSection.id) {
      // Find section in currentNote
      const secNum = parseInt(parentSection.id.replace('sec-', ''), 10);
      if (currentNote && currentNote.sections) {
        const secObj = currentNote.sections.find(s => s.order_index === secNum);
        if (secObj) {
          secId = secObj.id;
          secTitle = secObj.title;
        }
      }
    }

    floatingBadge.style.top = `${window.scrollY + rect.top - 42}px`;
    floatingBadge.style.left = `${window.scrollX + rect.left + (rect.width / 2) - 80}px`;
    floatingBadge.style.display = 'flex';

    floatingBadge.onclick = (e) => {
      e.preventDefault();
      e.stopPropagation();
      openCopilotDrawer(secId, secTitle, "Can you clarify and break down this excerpt?", text);
      floatingBadge.style.display = 'none';
    };
  });
}

// Auto-bind selection detector on DOMContentLoaded
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initSelectionDetector);
} else {
  initSelectionDetector();
}
