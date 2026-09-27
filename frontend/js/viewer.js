/* viewer.js — Living Note Viewer, TOC Scrollspy, Block Renderers & Reader Controls */

    function adjustFontSize(delta) {
      currentFontSizeRem = Math.max(0.9, Math.min(1.35, currentFontSizeRem + (delta * 0.08)));
      document.getElementById('note-content-body').style.fontSize = `${currentFontSizeRem}rem`;
      document.querySelectorAll('.tool-btn').forEach(b => {
        if (b.id === 'btn-font-reset') b.classList.toggle('active', Math.abs(currentFontSizeRem - 1.05) < 0.02);
      });
      setTimeout(updateScrollSpyActiveSection, 50);
    }

    function resetFontSize() {
      currentFontSizeRem = 1.05;
      document.getElementById('note-content-body').style.fontSize = `1.05rem`;
      document.getElementById('btn-font-reset').classList.add('active');
      setTimeout(updateScrollSpyActiveSection, 50);
    }

    function toggleFocusMode() {
      document.body.classList.toggle('focus-mode');
      const isFocus = document.body.classList.contains('focus-mode');
      const focusBtn = document.getElementById('btn-focus-toggle');
      if (focusBtn) {
        focusBtn.classList.toggle('active', isFocus);
        focusBtn.innerHTML = isFocus
          ? '<span class="btn-icon">✕</span><span class="btn-label">Exit Focus</span>'
          : '<span class="btn-icon">📖</span><span class="btn-label">Focus Mode</span>';
      }
      if (isFocus) {
        document.getElementById('note-panel').scrollIntoView({ behavior: 'smooth' });
      }
      setTimeout(() => {
        updateReadingProgress();
        updateScrollSpyActiveSection();
      }, 100);
    }

    function copyNoteLink() {
      const url = new URL(window.location.href);
      if (currentJourneyId) {
        url.searchParams.set('journey_id', currentJourneyId);
      }
      navigator.clipboard.writeText(url.toString()).then(() => {
        const btnLinkText = document.getElementById('btn-link-text');
        const orig = btnLinkText.textContent;
        btnLinkText.textContent = '✓ Copied URL!';
        setTimeout(() => { btnLinkText.textContent = orig; }, 2000);
      });
    }

    function copyCode(btn, codeText) {
      navigator.clipboard.writeText(codeText).then(() => {
        const orig = btn.innerHTML;
        btn.classList.add('copied');
        btn.innerHTML = '<span>✓ Copied!</span>';
        setTimeout(() => {
          btn.classList.remove('copied');
          btn.innerHTML = orig;
        }, 2000);
      });
    }

    /* Reading Progress & Robust Bidirectional Scrollspy */
    let isScrollTicking = false;
    let isProgrammaticScroll = false;
    let programmaticScrollTimer = null;

    function updateReadingProgress() {
      const notePanel = document.getElementById('note-panel');
      const progressBar = document.getElementById('reading-progress-bar');
      const progressText = document.getElementById('toc-progress-text');

      if (!notePanel || notePanel.style.display === 'none') {
        if (progressBar) progressBar.style.width = '0%';
        if (progressText) progressText.textContent = '0%';
        return;
      }

      const rect = notePanel.getBoundingClientRect();
      const totalHeight = notePanel.offsetHeight - window.innerHeight;
      if (totalHeight > 0) {
        const currentProgress = Math.min(100, Math.max(0, ((-rect.top) / totalHeight) * 100));
        if (progressBar) progressBar.style.width = `${currentProgress}%`;
        if (progressText) progressText.textContent = `${Math.round(currentProgress)}%`;
      }
    }

    function setActiveTocItem(sectionId) {
      if (!sectionId) return;
      const tocLinks = document.querySelectorAll('.toc-item');
      let activeLink = null;

      tocLinks.forEach(link => {
        const href = link.getAttribute('href');
        if (href === `#${sectionId}`) {
          if (!link.classList.contains('active')) {
            link.classList.add('active');
          }
          activeLink = link;
        } else {
          link.classList.remove('active');
        }
      });

      // Keep active TOC item visible within the sticky TOC sidebar if it overflows
      if (activeLink) {
        const sidebar = document.getElementById('note-viewer-toc');
        if (sidebar && sidebar.scrollHeight > sidebar.clientHeight) {
          const linkRect = activeLink.getBoundingClientRect();
          const sidebarRect = sidebar.getBoundingClientRect();
          if (linkRect.top < sidebarRect.top + 20 || linkRect.bottom > sidebarRect.bottom - 20) {
            activeLink.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
          }
        }
      }
    }

    function updateScrollSpyActiveSection() {
      if (isProgrammaticScroll) return;

      const notePanel = document.getElementById('note-panel');
      if (!notePanel || notePanel.style.display === 'none') return;

      const sections = Array.from(document.querySelectorAll('.note-section-container'));
      if (!sections.length) return;

      const header = document.querySelector('header');
      const headerHeight = (header && window.getComputedStyle(header).display !== 'none') ? header.offsetHeight : 0;
      // Target reading line: positioned just under the sticky header / focus mode top padding
      const targetOffset = headerHeight + 70;

      // Check if user has scrolled to the bottom of the page
      const scrollBottom = window.innerHeight + window.scrollY;
      const documentHeight = Math.max(
        document.body.scrollHeight,
        document.documentElement.scrollHeight,
        document.body.offsetHeight,
        document.documentElement.offsetHeight
      );
      const isAtBottom = scrollBottom >= documentHeight - 60;

      let currentSectionId = sections[0].id;

      if (isAtBottom) {
        currentSectionId = sections[sections.length - 1].id;
      } else {
        // Find the last section whose top has reached or passed the target reading line
        for (let i = 0; i < sections.length; i++) {
          const rect = sections[i].getBoundingClientRect();
          if (rect.top <= targetOffset) {
            currentSectionId = sections[i].id;
          } else {
            break;
          }
        }
      }

      setActiveTocItem(currentSectionId);
    }

    // High performance RAF scroll listener
    window.addEventListener('scroll', () => {
      if (!isScrollTicking) {
        window.requestAnimationFrame(() => {
          updateReadingProgress();
          updateScrollSpyActiveSection();
          isScrollTicking = false;
        });
        isScrollTicking = true;
      }
    }, { passive: true });

    window.addEventListener('resize', () => {
      updateReadingProgress();
      updateScrollSpyActiveSection();
    }, { passive: true });

    // Cancel programmatic scroll override if user manually interacts
    window.addEventListener('wheel', () => { isProgrammaticScroll = false; }, { passive: true });
    window.addEventListener('touchstart', () => { isProgrammaticScroll = false; }, { passive: true });

    function setupScrollSpy() {
      if (observer) {
        try { observer.disconnect(); } catch (e) {}
      }

      // Immediately sync TOC active state with current scroll position
      updateReadingProgress();
      updateScrollSpyActiveSection();

      // Also set up an IntersectionObserver with threshold: 0 for instant boundary detection
      const sections = document.querySelectorAll('.note-section-container');
      if ('IntersectionObserver' in window && sections.length > 0) {
        observer = new IntersectionObserver(() => {
          if (!isProgrammaticScroll) {
            updateScrollSpyActiveSection();
          }
        }, {
          rootMargin: '-50px 0px -40% 0px',
          threshold: 0
        });

        sections.forEach(sec => observer.observe(sec));
      }
    }

    /* Submission & Step Handling */


    async function triggerNoteGeneration(journeyId) {
      const targetId = journeyId || currentJourneyId;
      if (!targetId) {
        alert('No active learning journey found. Please start or select a journey first.');
        return;
      }

      const btn = document.getElementById('btn-gen-note');
      const btnText = document.getElementById('btn-note-text');
      const btnSpinner = document.getElementById('btn-note-spinner');

      btn.disabled = true;
      btnText.style.display = 'none';
      btnSpinner.style.display = 'inline';

      try {
        const res = await fetch(`/journeys/${targetId}/generate-note`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ style_preference: 'rigorous_technical' })
        });
        if (!res.ok) throw new Error('Failed to generate structured note');
        const note = await res.json();
        renderNote(note);
      } catch (err) {
        alert('Error generating note: ' + err.message);
      } finally {
        btn.disabled = false;
        btnText.style.display = 'inline';
        btnSpinner.style.display = 'none';
      }
    }

    /* ==========================================================================
       PHASE 6: WEB NOTE VIEWER RENDERER
       ========================================================================== */

    function renderNote(note) {
      if (currentNote && currentNote.id !== note.id) {
        if (typeof resetCopilotState === 'function') resetCopilotState();
      }
      currentNote = note;
      const notePanel = document.getElementById('note-panel');
      notePanel.style.display = 'block';
      notePanel.scrollIntoView({ behavior: 'smooth' });

      // Note Header
      document.getElementById('note-topic-heading').textContent = note.topic;
      document.getElementById('note-summary-text').textContent = note.summary;
      
      const verBadge = document.getElementById('note-version-badge');
      verBadge.textContent = `VERSION ${note.version}`;
      verBadge.classList.remove('pulse-green');
      void verBadge.offsetWidth; // trigger reflow
      verBadge.classList.add('pulse-green');

      document.getElementById('note-sections-count').textContent = `${note.sections.length} Sections`;

      const verPill = document.getElementById('version-count-pill');
      if (verPill) {
        verPill.textContent = note.version;
      }

      const revPill = document.getElementById('rev-count-pill');
      if (revPill) {
        revPill.textContent = (note.revisions || []).length;
      }

      // Word count & estimated reading time calculation
      let totalWords = (note.summary || '').split(/\s+/).length;
      note.sections.forEach(s => {
        totalWords += (s.title || '').split(/\s+/).length;
        s.blocks.forEach(b => {
          const text = (b.content || '') + ' ' + (b.code || '') + ' ' + (b.term || '');
          totalWords += text.split(/\s+/).length;
        });
      });
      const readMins = Math.max(1, Math.ceil(totalWords / 180));
      document.getElementById('note-readtime-badge').textContent = `⏱️ ~${readMins} min read`;

      // Render Sticky Table of Contents (TOC)
      const tocList = document.getElementById('toc-list');
      tocList.innerHTML = note.sections.map((s, idx) => `
        <li>
          <a href="#sec-${s.order_index}" class="toc-item ${idx === 0 ? 'active' : ''}" onclick="smoothScrollTo(event, 'sec-${s.order_index}')">
            <span class="toc-num">${s.order_index}.</span>
            <span>${escapeHtml(s.title)}</span>
          </a>
        </li>
      `).join('');

      // Render Note Sections & Blocks with Section Evolution Bar
      const bodyContainer = document.getElementById('note-content-body');
      const sectionsHtml = note.sections.map(s => `
        <section class="note-section-container" id="sec-${s.order_index}">
          <div class="section-header-row">
            <div class="section-title-wrap">
              <span class="section-num">${s.order_index}.</span>
              <h2 class="section-heading">${escapeHtml(s.title)}</h2>
            </div>
            <div class="section-meta-tags">
              <button type="button" class="tool-btn" onclick="openCopilotDrawer('${s.id}', '${escapeJsString(s.title)}')" title="Ask Agent 9 Socratic Copilot about this section" style="padding: 0.2rem 0.55rem; font-size: 0.75rem; background: rgba(99, 102, 241, 0.18); border-color: var(--accent); color: #c7d2fe;">
                <span>🤖 Ask AI</span>
              </button>
              <span class="depth-badge depth-${s.depth}">${s.depth}</span>
              <span class="section-type-pill">${escapeHtml(s.section_type)}</span>
            </div>
          </div>
          <div class="section-blocks-feed">
            ${s.blocks.map(b => renderNoteBlock(b, s.id)).join('')}
          </div>
          <div class="section-evolve-bar">
            <span class="evolve-label">🌱 Evolve section:</span>
            <div class="evolve-actions">
              <button type="button" class="evolve-chip evolve-chip-copilot" onclick="openCopilotDrawer('${s.id}', '${escapeJsString(s.title)}')">🤖 Ask Copilot</button>
              <button type="button" class="evolve-chip" onclick="openSectionCodeModal('${s.id}', '${escapeJsString(s.title)}')">💻 + Code Implementation</button>
              <button type="button" class="evolve-chip" onclick="openSectionVisualModal('${s.id}', '${escapeJsString(s.title)}')">🎨 Add Visual Flow</button>
              <button type="button" class="evolve-chip" onclick="openEvolveModal('${s.id}', '${escapeJsString(s.title)}', 'expand_section')">🔍 Deepen Detail</button>
              <button type="button" class="evolve-chip" onclick="openEvolveModal('${s.id}', '${escapeJsString(s.title)}', 'clarify')">💡 Clarify Concept</button>
              <button type="button" class="evolve-chip" onclick="openEvolveModal('${s.id}', '${escapeJsString(s.title)}', 'custom_prompt')">💬 Ask Question...</button>
            </div>
          </div>
        </section>
      `).join('');

      // Global Note Evolution & Assessment Callout Card
      const globalEvolveCard = `
        <div class="note-global-evolve-card">
          <div class="evolve-card-left">
            <div class="evolve-card-title">🌱 Expand &amp; Verify Your Technical Mastery</div>
            <p class="evolve-card-sub">Technical mastery is an ongoing dialogue. Ask Agent 9 Socratic Copilot for instant clarification, test recall with 3D flashcards, inspect Mermaid diagrams, or execute runnable sandbox code.</p>
          </div>
          <div style="display: flex; gap: 0.75rem; flex-wrap: wrap;">
            <button type="button" class="tool-btn" style="padding: 0.65rem 1.3rem; background: rgba(99, 102, 241, 0.25); border-color: var(--accent); color: #ffffff; font-weight: 700; box-shadow: 0 0 16px rgba(99, 102, 241, 0.35);" onclick="openCopilotDrawer(null, null)">
              <span>🤖 Consult Copilot</span>
            </button>
            <button type="button" class="tool-btn" style="padding: 0.65rem 1.25rem; background: rgba(168, 85, 247, 0.2); border-color: #a855f7; color: #e9d5ff; font-weight: 700;" onclick="openGraphModal(false)">
              <span>🕸️ Knowledge Graph</span>
            </button>
            <button type="button" class="tool-btn" style="padding: 0.65rem 1.25rem; background: rgba(245, 158, 11, 0.2); border-color: #f59e0b; color: #fde68a; font-weight: 700;" onclick="openVersionHistoryModal()">
              <span>🏷️ Version History &amp; Diff</span>
            </button>
            <button type="button" class="btn-submit" style="width: auto; padding: 0.65rem 1.4rem;" onclick="openEvolveModal(null, 'Living Note Exploration', 'add_section')">
              <span>+ Add New Section</span>
            </button>
            <button type="button" class="tool-btn" style="padding: 0.65rem 1.25rem; background: rgba(16, 185, 129, 0.18); border-color: var(--success); color: #a7f3d0;" onclick="triggerPlanCode()">
              <span>💻 Plan Interactive Code</span>
            </button>
            <button type="button" class="tool-btn" style="padding: 0.65rem 1.25rem; background: rgba(99, 102, 241, 0.2); border-color: var(--accent); color: #ffffff;" onclick="openAssessmentModal()">
              <span>🧠 Test Mastery &amp; Flashcards</span>
            <button type="button" class="tool-btn" style="padding: 0.65rem 1.25rem; background: rgba(6, 182, 212, 0.18); border-color: var(--cyan); color: #a5f3fc;" onclick="triggerPlanVisuals()">
              <span>📊 Plan Visual Architecture</span>
            </button>
            <button type="button" class="tool-btn" style="padding: 0.65rem 1.25rem; background: rgba(56, 189, 248, 0.2); border-color: #38bdf8; color: #bae6fd; font-weight: 700;" onclick="openMemoryModal('history')">
              <span>🧠 Knowledge Memory</span>
            </button>
          </div>
        </div>
      `;

      bodyContainer.innerHTML = sectionsHtml + globalEvolveCard;

      // Render interactive Mermaid diagrams
      setTimeout(renderAllMermaidDiagrams, 80);

      // Render LaTeX Mathematical Expressions with KaTeX
      setTimeout(renderAllMathFormulas, 90);

      // Initialize ScrollSpy
      setTimeout(setupScrollSpy, 150);

      // Phase 15: Contextual In-Note Knowledge Memory Cross-References
      if (typeof loadNoteMemoryCrossReferences === 'function') {
        setTimeout(() => loadNoteMemoryCrossReferences(note.id), 200);
      }
    }





    function smoothScrollTo(event, elementId) {
      if (event) event.preventDefault();
      const el = document.getElementById(elementId);
      if (el) {
        // Immediately highlight clicked TOC item for instant user feedback
        setActiveTocItem(elementId);

        // Temporarily pause scroll listener overrides during smooth animation
        isProgrammaticScroll = true;
        if (programmaticScrollTimer) clearTimeout(programmaticScrollTimer);

        el.scrollIntoView({ behavior: 'smooth', block: 'start' });

        programmaticScrollTimer = setTimeout(() => {
          isProgrammaticScroll = false;
          updateScrollSpyActiveSection();
        }, 700);

        // Update URL hash without jump
        try {
          history.replaceState(null, null, `#${elementId}`);
        } catch (e) {}
      }
    }

    function renderAllMathFormulas() {
      const container = document.getElementById('note-content-body');
      if (!container) return;

      if (typeof renderMathInElement === 'function') {
        try {
          renderMathInElement(container, {
            delimiters: [
              { left: '$$', right: '$$', display: true },
              { left: '\\[', right: '\\]', display: true },
              { left: '$', right: '$', display: false },
              { left: '\\(', right: '\\)', display: false }
            ],
            throwOnError: false,
            errorColor: '#f87171'
          });
        } catch (err) {
          console.warn('KaTeX auto-render failed, applying fallback:', err);
          if (typeof applyMathFallbackFormatting === 'function') {
            applyMathFallbackFormatting(container);
          }
        }
      } else if (typeof applyMathFallbackFormatting === 'function') {
        applyMathFallbackFormatting(container);
      }
    }

    function renderNoteBlock(b, sectionId = null) {
      if (b.type === 'paragraph') {
        return `<div class="block-paragraph">${renderMarkdownText(b.content || '')}</div>`;
      }
      if (b.type === 'definition') {
        return `
          <div class="block-definition">
            <div class="def-term"><span>📖</span><span>${escapeHtml(b.term || 'Definition')}</span></div>
            <div class="def-content">${renderMarkdownText(b.content || '')}</div>
          </div>
        `;
      }
      if (b.type === 'warning') {
        return `
          <div class="block-warning">
            <div class="warning-title"><span>⚠️</span><span>${escapeHtml(b.title || 'Important Note / Misconception')}</span></div>
            <div class="warning-content">${renderMarkdownText(b.content || '')}</div>
          </div>
        `;
      }
      if (b.type === 'example') {
        return `
          <div class="block-example">
            <div class="example-title"><span>💡</span><span>${escapeHtml(b.title || 'Example Walkthrough')}</span></div>
            <div class="example-content">${renderMarkdownText(b.content || '')}</div>
          </div>
        `;
      }
      if (b.type === 'code') {
        const rawCode = b.code || b.content || '';
        const codeId = 'code-' + Math.random().toString(36).substring(2, 9);
        const lang = (b.language || 'python').toLowerCase();
        const isPython = lang === 'python' || lang === 'py';
        const isRunnable = b.runnable !== undefined ? Boolean(b.runnable) : isPython;
        const codeTitle = b.title || (isPython ? 'Python Implementation' : `${lang.toUpperCase()} Implementation`);
        const langIcons = {
          python: '🐍',
          py: '🐍',
          go: '🐹',
          golang: '🐹',
          rust: '🦀',
          rs: '🦀',
          typescript: '⚡',
          ts: '⚡',
          javascript: '🟨',
          js: '🟨',
          sql: '💾',
          bash: '⚡',
          sh: '⚡'
        };
        const langIcon = langIcons[lang] || '💻';

        return `
          <div class="block-code" id="card-${codeId}">
            <div class="code-header">
              <div class="code-header-left">
                <span class="code-lang-tag tag-${lang}">${langIcon} ${lang.toUpperCase()}</span>
                <span class="code-title-text">${escapeHtml(codeTitle)}</span>
                ${b.complexity ? `<span class="code-complexity-pill" title="Algorithmic Complexity">⚡ ${escapeHtml(b.complexity)}</span>` : ''}
              </div>
              <div class="code-actions">
                ${isRunnable ? `
                <button type="button" class="code-btn-run" id="btn-run-${codeId}" onclick="runCodeInSandbox('${codeId}')" title="Execute Python in browser WebAssembly sandbox">
                  <span id="run-text-${codeId}">▶ Run Code</span>
                  <span id="run-spinner-${codeId}" style="display:none;">⏳ Executing...</span>
                </button>` : ''}
                <button type="button" class="code-btn-copy" onclick="copyCodeFromBlock(this, '${codeId}')" title="Copy code">
                  <span>📋 Copy</span>
                </button>
                ${sectionId ? `
                <button type="button" class="code-btn-refine" onclick="openSectionCodeModal('${sectionId}', '${escapeJsString(codeTitle)}')" title="Regenerate or customize with Agent 8">
                  <span>🔄 Refine</span>
                </button>` : ''}
              </div>
            </div>
            <pre class="code-pre" id="pre-${codeId}"><code>${escapeHtml(rawCode)}</code></pre>
            ${b.expected_output ? `
            <div class="code-expected-wrap">
              <details class="code-expected-details">
                <summary>📋 Expected Output</summary>
                <pre class="expected-stdout">${escapeHtml(b.expected_output)}</pre>
              </details>
            </div>` : ''}
            <div class="code-terminal-console" id="term-${codeId}" style="display: none;">
              <div class="terminal-header">
                <div class="terminal-dots">
                  <span class="dot dot-red"></span>
                  <span class="dot dot-yellow"></span>
                  <span class="dot dot-green"></span>
                  <span class="terminal-title">TERMINAL STDOUT</span>
                </div>
                <div class="terminal-actions">
                  <span class="terminal-status" id="term-status-${codeId}">Execution finished</span>
                  <button type="button" class="terminal-clear-btn" onclick="clearTerminal('${codeId}')">Clear</button>
                </div>
              </div>
              <pre class="terminal-body" id="stdout-${codeId}"></pre>
            </div>
            <textarea id="raw-code-${codeId}" style="display:none;">${escapeHtml(rawCode)}</textarea>
          </div>
        `;
      }
      if (b.type === 'diagram') {
        const diagramRaw = b.diagram_spec || b.content || '';
        const diagId = 'mermaid-' + Math.random().toString(36).substring(2, 9);
        const diagType = b.diagram_type ? b.diagram_type.toUpperCase() : 'ARCHITECTURE';
        const diagTitle = b.title || 'Architecture Flow';
        return `
          <div class="block-diagram" id="card-${diagId}">
            <div class="diagram-header">
              <div class="diagram-title-wrap">
                <span class="diagram-badge">⚡ ${escapeHtml(diagType)}</span>
                <span class="diagram-title">${escapeHtml(diagTitle)}</span>
              </div>
              <div class="diagram-actions">
                <button type="button" class="diag-action-btn" title="Inspect Fullscreen & Zoom" onclick="openDiagramFullscreen('${diagId}', '${escapeJsString(diagTitle)}', '${escapeJsString(diagType)}')">
                  <span>🔍 Inspect</span>
                </button>
                <button type="button" class="diag-action-btn" title="Copy Mermaid Specification" onclick="copyDiagramSpec(this, '${diagId}')">
                  <span>📋 Copy Spec</span>
                </button>
                <button type="button" class="diag-action-btn" title="Download SVG Vector Image" onclick="downloadDiagramSvg('${diagId}', '${escapeJsString(diagTitle)}')">
                  <span>💾 SVG</span>
                </button>
                ${sectionId ? `
                <button type="button" class="diag-action-btn diag-btn-regen" title="Regenerate / Redesign with Agent 7" onclick="openSectionVisualModal('${sectionId}', '${escapeJsString(diagTitle)}')">
                  <span>🔄 Redesign</span>
                </button>` : ''}
              </div>
            </div>
            <div class="diagram-canvas-container" id="container-${diagId}">
              <div class="mermaid-block" id="${diagId}">
                <div class="diagram-skeleton">⚡ Rendering architecture flow...</div>
              </div>
            </div>
            ${b.caption ? `<div class="diagram-caption"><strong>Figure:</strong> ${escapeHtml(b.caption)}</div>` : ''}
            ${b.visual_description ? `<div class="diagram-desc"><strong>Mechanics:</strong> ${formatInlineMarkdown(b.visual_description)}</div>` : ''}
            <textarea id="raw-${diagId}" style="display:none;">${escapeHtml(diagramRaw)}</textarea>
          </div>
        `;
      }
      if (b.type === 'comparison') {
        let tableHtml = '';
        if (b.items && b.items.length) {
          const keys = Object.keys(b.items[0]);
          const headers = keys.map(k => `<th>${formatInlineMarkdown(k)}</th>`).join('');
          tableHtml = `
            <div class="comparison-table-wrapper">
              <table class="comparison-table">
                <thead><tr>${headers}</tr></thead>
                <tbody>
                  ${b.items.map(it => `
                    <tr>${keys.map(k => `<td>${formatInlineMarkdown(String(it[k] !== undefined ? it[k] : ''))}</td>`).join('')}</tr>
                  `).join('')}
                </tbody>
              </table>
            </div>
          `;
        }

        const contentHtml = b.content ? renderMarkdownText(b.content) : '';

        return `
          <div class="block-comparison">
            <div class="comparison-title">${escapeHtml(b.title || 'Conceptual Comparison')}</div>
            ${tableHtml ? `${contentHtml ? `<div style="font-size: 0.95rem; color: var(--text-secondary); margin-bottom: 0.75rem;">${contentHtml}</div>` : ''}${tableHtml}` : `${contentHtml}`}
          </div>
        `;
      }
      return `<div class="block-paragraph">${renderMarkdownText(b.content || '')}</div>`;
    }



    async function exportNote(format = 'markdown') {
      if (!currentNote && !currentJourneyId) {
        alert('Please generate or open a living note before exporting.');
        return;
      }

      const isPdf = format === 'pdf';
      const btn = isPdf ? document.getElementById('btn-export-pdf') : null;
      const originalHtml = btn ? btn.innerHTML : '';
      if (btn) {
        btn.innerHTML = '<span class="btn-icon">⏳</span><span class="btn-label">Compiling...</span>';
        btn.disabled = true;
      }

      const noteId = currentNote ? currentNote.id : null;
      const exportUrl = noteId ? `/notes/${noteId}/export?format=${format}` : `/journeys/${currentJourneyId}/note/export?format=${format}`;

      try {
        const res = await fetch(exportUrl);
        if (!res.ok) throw new Error('Failed to download note export');

        const blob = await res.blob();
        const disposition = res.headers.get('content-disposition') || '';
        const ext = isPdf ? 'pdf' : (format === 'json' ? 'json' : 'md');
        let filename = `${(currentTopic || 'technical_note').toLowerCase().replace(/\s+/g, '_')}_v${currentNote ? currentNote.version : 1}.${ext}`;
        const match = disposition.match(/filename="?([^"]+)"?/);
        if (match && match[1]) filename = match[1];

        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(link.href);
      } catch (err) {
        alert('Export failed: ' + err.message);
      } finally {
        if (btn) {
          btn.innerHTML = originalHtml;
          btn.disabled = false;
        }
      }
    }


