/* viewer.js — Living Note Viewer, TOC Scrollspy, Block Renderers & Reader Controls */

    function adjustFontSize(delta) {
      currentFontSizeRem = Math.max(0.9, Math.min(1.35, currentFontSizeRem + (delta * 0.08)));
      document.getElementById('note-content-body').style.fontSize = `${currentFontSizeRem}rem`;
      document.querySelectorAll('.tool-btn').forEach(b => {
        if (b.id === 'btn-font-reset') b.classList.toggle('active', Math.abs(currentFontSizeRem - 1.05) < 0.02);
      });
    }

    function resetFontSize() {
      currentFontSizeRem = 1.05;
      document.getElementById('note-content-body').style.fontSize = `1.05rem`;
      document.getElementById('btn-font-reset').classList.add('active');
    }

    function toggleFocusMode() {
      document.body.classList.toggle('focus-mode');
      const isFocus = document.body.classList.contains('focus-mode');
      const focusBtn = document.getElementById('btn-focus-toggle');
      if (focusBtn) {
        focusBtn.classList.toggle('active', isFocus);
        focusBtn.innerHTML = isFocus ? '<span>✕ Exit Focus</span>' : '<span>📖 Focus Mode</span>';
      }
      if (isFocus) {
        document.getElementById('note-panel').scrollIntoView({ behavior: 'smooth' });
      }
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

    /* Reading Progress & Scrollspy */
    window.addEventListener('scroll', () => {
      const notePanel = document.getElementById('note-panel');
      const progressBar = document.getElementById('reading-progress-bar');
      const progressText = document.getElementById('toc-progress-text');

      if (!notePanel || notePanel.style.display === 'none') {
        progressBar.style.width = '0%';
        return;
      }

      const rect = notePanel.getBoundingClientRect();
      const totalHeight = notePanel.offsetHeight - window.innerHeight;
      if (totalHeight > 0) {
        const currentProgress = Math.min(100, Math.max(0, ((-rect.top) / totalHeight) * 100));
        progressBar.style.width = `${currentProgress}%`;
        if (progressText) progressText.textContent = `${Math.round(currentProgress)}%`;
      }
    });

    function setupScrollSpy() {
      if (observer) observer.disconnect();
      const sections = document.querySelectorAll('.note-section-container');
      const tocLinks = document.querySelectorAll('.toc-item');

      observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            const id = entry.target.id;
            tocLinks.forEach(link => {
              if (link.getAttribute('href') === `#${id}`) {
                link.classList.add('active');
              } else {
                link.classList.remove('active');
              }
            });
          }
        });
      }, { rootMargin: '-100px 0px -60% 0px', threshold: 0.1 });

      sections.forEach(sec => observer.observe(sec));
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
            <button type="button" class="btn-submit" style="width: auto; padding: 0.65rem 1.4rem;" onclick="openEvolveModal(null, 'Living Note Exploration', 'add_section')">
              <span>+ Add New Section</span>
            </button>
            <button type="button" class="tool-btn" style="padding: 0.65rem 1.25rem; background: rgba(16, 185, 129, 0.18); border-color: var(--success); color: #a7f3d0;" onclick="triggerPlanCode()">
              <span>💻 Plan Interactive Code</span>
            </button>
            <button type="button" class="tool-btn" style="padding: 0.65rem 1.25rem; background: rgba(99, 102, 241, 0.2); border-color: var(--accent); color: #ffffff;" onclick="openAssessmentModal()">
              <span>🧠 Test Mastery &amp; Flashcards</span>
            </button>
            <button type="button" class="tool-btn" style="padding: 0.65rem 1.25rem; background: rgba(6, 182, 212, 0.18); border-color: var(--cyan); color: #a5f3fc;" onclick="triggerPlanVisuals()">
              <span>📊 Plan Visual Architecture</span>
            </button>
          </div>
        </div>
      `;


      bodyContainer.innerHTML = sectionsHtml + globalEvolveCard;

      // Render interactive Mermaid diagrams
      setTimeout(renderAllMermaidDiagrams, 80);

      // Initialize ScrollSpy
      setTimeout(setupScrollSpy, 150);
    }




    function smoothScrollTo(event, elementId) {
      event.preventDefault();
      const el = document.getElementById(elementId);
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'start' });
        // Update URL hash without jump
        history.replaceState(null, null, `#${elementId}`);
      }
    }

    function renderNoteBlock(b, sectionId = null) {
      if (b.type === 'paragraph') {
        return `<div class="block-paragraph">${formatInlineMarkdown(b.content || '')}</div>`;
      }
      if (b.type === 'definition') {
        return `
          <div class="block-definition">
            <div class="def-term"><span>📖</span><span>${escapeHtml(b.term || 'Definition')}</span></div>
            <div class="def-content">${formatInlineMarkdown(b.content || '')}</div>
          </div>
        `;
      }
      if (b.type === 'warning') {
        return `
          <div class="block-warning">
            <div class="warning-title"><span>⚠️</span><span>${escapeHtml(b.title || 'Important Note / Misconception')}</span></div>
            <div class="warning-content">${formatInlineMarkdown(b.content || '')}</div>
          </div>
        `;
      }
      if (b.type === 'example') {
        return `
          <div class="block-example">
            <div class="example-title"><span>💡</span><span>${escapeHtml(b.title || 'Example Walkthrough')}</span></div>
            <div class="example-content">${formatInlineMarkdown(b.content || '')}</div>
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
        let rows = '';
        if (b.items && b.items.length) {
          const keys = Object.keys(b.items[0]);
          const headers = keys.map(k => `<th>${escapeHtml(k)}</th>`).join('');
          rows = `
            <table class="comparison-table">
              <thead><tr>${headers}</tr></thead>
              <tbody>
                ${b.items.map(it => `
                  <tr>${keys.map(k => `<td>${escapeHtml(String(it[k] || ''))}</td>`).join('')}</tr>
                `).join('')}
              </tbody>
            </table>
          `;
        }
        return `
          <div class="block-comparison">
            <div class="comparison-title">${escapeHtml(b.title || 'Conceptual Comparison')}</div>
            ${b.content ? `<div style="font-size: 0.95rem; color: var(--text-secondary); margin-bottom: 0.75rem;">${formatInlineMarkdown(b.content)}</div>` : ''}
            ${rows}
          </div>
        `;
      }
      return `<div class="block-paragraph">${formatInlineMarkdown(b.content || '')}</div>`;
    }



    async function exportNote(format = 'markdown') {
      if (!currentNote && !currentJourneyId) {
        alert('Please generate or open a living note before exporting.');
        return;
      }

      const noteId = currentNote ? currentNote.id : null;
      const exportUrl = noteId ? `/notes/${noteId}/export?format=${format}` : `/journeys/${currentJourneyId}/note/export?format=${format}`;

      try {
        const res = await fetch(exportUrl);
        if (!res.ok) throw new Error('Failed to download note export');

        const blob = await res.blob();
        const disposition = res.headers.get('content-disposition') || '';
        let filename = `${(currentTopic || 'technical_note').toLowerCase().replace(/\s+/g, '_')}_v${currentNote ? currentNote.version : 1}.md`;
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
      }
    }


