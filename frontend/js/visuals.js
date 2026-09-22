/* visuals.js — Agent 7 Visual Planner & Mermaid Architecture Diagrams */

    async function ensureMermaidLoaded(maxWaitMs = 6000) {
      const start = Date.now();
      while (!window.mermaid && (Date.now() - start) < maxWaitMs) {
        await new Promise(r => setTimeout(r, 100));
      }
      if (window.mermaid && !window._mermaidInitialized) {
        try {
          mermaid.initialize({
            startOnLoad: false,
            theme: 'dark',
            themeVariables: {
              darkMode: true,
              background: '#070b12',
              primaryColor: '#312e81',
              primaryTextColor: '#f8fafc',
              primaryBorderColor: '#6366f1',
              lineColor: '#818cf8',
              secondaryColor: '#064e3b',
              tertiaryColor: '#1e1b4b',
              fontFamily: "'JetBrains Mono', monospace",
              fontSize: '13px',
            },
            flowchart: { curve: 'basis', htmlLabels: true },
            sequence: { showSequenceNumbers: true },
            securityLevel: 'loose',
          });
          window._mermaidInitialized = true;
        } catch (err) {
          console.warn("Mermaid initialize warning:", err);
        }
      }
      return !!window.mermaid;
    }

    async function renderAllMermaidDiagrams() {
      const loaded = await ensureMermaidLoaded();
      if (!loaded) {
        console.warn("Mermaid library could not be loaded from CDN.");
        return;
      }
      const blocks = document.querySelectorAll('.mermaid-block');
      for (let el of blocks) {
        const id = el.id;
        const rawEl = document.getElementById('raw-' + id);
        const cleanSpec = rawEl ? rawEl.value.trim() : '';
        if (!cleanSpec) continue;

        try {
          const cleanId = id.replace(/[^a-zA-Z0-9]/g, '');
          const svgId = 'svg-' + cleanId + '-' + Math.random().toString(36).substring(2, 7);
          const { svg } = await mermaid.render(svgId, cleanSpec);
          el.innerHTML = svg;
          el.classList.add('rendered');
        } catch (err) {
          console.warn('Mermaid rendering fallback for', id, err);
          el.innerHTML = `
            <div class="diagram-render-fallback">
              <div class="fallback-note">⚡ Visual Architecture Specification:</div>
              <pre class="diagram-spec-pre">${escapeHtml(cleanSpec)}</pre>
            </div>
          `;
        }
      }
    }

    function copyDiagramSpec(btn, diagId) {
      const rawEl = document.getElementById('raw-' + diagId);
      const spec = rawEl ? rawEl.value : '';
      if (!spec) return;
      navigator.clipboard.writeText(spec).then(() => {
        const orig = btn.innerHTML;
        btn.innerHTML = '<span>✅ Copied!</span>';
        setTimeout(() => { btn.innerHTML = orig; }, 1800);
      });
    }

    async function downloadDiagramSvg(diagId, title) {
      const container = document.getElementById(diagId);
      let svgEl = container ? container.querySelector('svg') : null;
      if (!svgEl) {
        const modalCanvas = document.getElementById('diag-modal-svg-canvas');
        svgEl = modalCanvas ? modalCanvas.querySelector('svg') : null;
      }

      // If not yet in DOM, render on-the-fly directly from the raw spec!
      if (!svgEl && window.mermaid) {
        const rawEl = document.getElementById('raw-' + diagId);
        const spec = rawEl ? rawEl.value.trim() : '';
        if (spec) {
          try {
            const tempId = 'dl-svg-' + Math.random().toString(36).substring(2, 7);
            const res = await mermaid.render(tempId, spec);
            if (res && res.svg) {
              triggerSvgDownload(res.svg, title);
              return;
            }
          } catch (e) {
            console.warn('On-the-fly SVG render error:', e);
          }
        }
      }

      if (!svgEl) {
        alert('Diagram vector is currently unavailable.');
        return;
      }

      const svgData = new XMLSerializer().serializeToString(svgEl);
      triggerSvgDownload(svgData, title);
    }

    function triggerSvgDownload(svgData, title) {
      const blob = new Blob([svgData], { type: 'image/svg+xml;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = (title ? title.toLowerCase().replace(/[^a-z0-9]+/g, '-') : 'architecture-diagram') + '.svg';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }

    async function openDiagramFullscreen(diagId, title, diagType) {
      currentModalDiagId = diagId;
      currentModalZoom = 1.0;
      const modal = document.getElementById('diag-fullscreen-modal');
      const modalTitle = document.getElementById('diag-modal-title');
      const modalBadge = document.getElementById('diag-modal-badge');
      const canvas = document.getElementById('diag-modal-svg-canvas');
      const zoomPill = document.getElementById('diag-modal-zoom-pill');

      if (modalTitle) modalTitle.textContent = title || 'System Architecture Diagram';
      if (modalBadge) modalBadge.textContent = '⚡ ' + (diagType || 'ARCHITECTURE').toUpperCase();
      if (zoomPill) zoomPill.textContent = '100%';

      const sourceContainer = document.getElementById(diagId);
      let svgEl = sourceContainer ? sourceContainer.querySelector('svg') : null;

      if (svgEl) {
        canvas.innerHTML = svgEl.outerHTML;
        const newSvg = canvas.querySelector('svg');
        if (newSvg) {
          newSvg.style.maxWidth = '100%';
          newSvg.style.height = 'auto';
          newSvg.style.maxHeight = '70vh';
        }
      } else {
        const rawEl = document.getElementById('raw-' + diagId);
        const spec = rawEl ? rawEl.value.trim() : '';
        let rendered = false;
        if (window.mermaid && spec) {
          try {
            const modalSvgId = 'modal-svg-' + Math.random().toString(36).substring(2, 7);
            const { svg } = await mermaid.render(modalSvgId, spec);
            canvas.innerHTML = svg;
            const newSvg = canvas.querySelector('svg');
            if (newSvg) {
              newSvg.style.maxWidth = '100%';
              newSvg.style.height = 'auto';
              newSvg.style.maxHeight = '70vh';
            }
            rendered = true;
          } catch (e) {
            console.warn('Modal on-the-fly render failed:', e);
          }
        }
        if (!rendered) {
          canvas.innerHTML = `<pre class="diagram-spec-pre" style="font-size: 1rem; padding: 2rem;">${escapeHtml(spec)}</pre>`;
        }
      }

      canvas.style.transform = 'scale(1)';
      modal.style.display = 'flex';
    }

    function adjustModalZoom(delta) {
      currentModalZoom = Math.max(0.4, Math.min(3.0, currentModalZoom + delta));
      const canvas = document.getElementById('diag-modal-svg-canvas');
      if (canvas) {
        canvas.style.transform = `scale(${currentModalZoom})`;
      }
      const zoomPill = document.getElementById('diag-modal-zoom-pill');
      if (zoomPill) {
        zoomPill.textContent = `${Math.round(currentModalZoom * 100)}%`;
      }
    }

    function resetModalZoom() {
      currentModalZoom = 1.0;
      const canvas = document.getElementById('diag-modal-svg-canvas');
      if (canvas) {
        canvas.style.transform = 'scale(1)';
      }
      const zoomPill = document.getElementById('diag-modal-zoom-pill');
      if (zoomPill) {
        zoomPill.textContent = '100%';
      }
    }

    function closeDiagramModal() {
      const modal = document.getElementById('diag-fullscreen-modal');
      if (modal) modal.style.display = 'none';
    }

    function copyCurrentModalSpec() {
      if (!currentModalDiagId) return;
      const rawEl = document.getElementById('raw-' + currentModalDiagId);
      if (rawEl && rawEl.value) {
        navigator.clipboard.writeText(rawEl.value).then(() => {
          alert('Mermaid specification copied to clipboard!');
        });
      }
    }

    function downloadCurrentModalSvg() {
      if (!currentModalDiagId) return;
      const title = document.getElementById('diag-modal-title').textContent;
      downloadDiagramSvg(currentModalDiagId, title);
    }

    function openSectionVisualModal(secId, secTitle) {
      targetSectionForVisual = secId;
      selectedVisualType = 'flowchart';
      const modal = document.getElementById('section-visual-modal');
      const titleEl = document.getElementById('visual-modal-title');
      const promptInput = document.getElementById('visual-custom-prompt');
      const statusEl = document.getElementById('visual-modal-status');

      if (titleEl) titleEl.textContent = `Visual for: ${secTitle}`;
      if (promptInput) promptInput.value = '';
      if (statusEl) statusEl.style.display = 'none';

      document.querySelectorAll('.vtype-card').forEach(c => {
        c.classList.toggle('active', c.dataset.type === 'flowchart');
      });

      modal.style.display = 'flex';
    }

    function closeSectionVisualModal() {
      const modal = document.getElementById('section-visual-modal');
      if (modal) modal.style.display = 'none';
    }

    function selectVisualType(type, cardEl) {
      selectedVisualType = type;
      document.querySelectorAll('.vtype-card').forEach(c => c.classList.remove('active'));
      if (cardEl) cardEl.classList.add('active');
    }

    async function submitSectionVisual() {
      if (!currentJourneyId || !targetSectionForVisual) return;
      const promptVal = document.getElementById('visual-custom-prompt').value.trim();
      const btn = document.getElementById('btn-submit-visual');
      const textSpan = document.getElementById('btn-visual-text');
      const spinnerSpan = document.getElementById('btn-visual-spinner');
      const statusEl = document.getElementById('visual-modal-status');

      btn.disabled = true;
      textSpan.style.display = 'none';
      spinnerSpan.style.display = 'inline';
      statusEl.style.display = 'none';

      try {
        const res = await fetch(`/journeys/${currentJourneyId}/sections/${targetSectionForVisual}/visual`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            visual_type: selectedVisualType,
            custom_prompt: promptVal || undefined,
          }),
        });

        if (!res.ok) {
          const err = await res.json();
          throw new Error(err.detail || 'Failed to generate visual');
        }

        // Refresh note
        const noteRes = await fetch(`/journeys/${currentJourneyId}/note`);
        if (noteRes.ok) {
          const updatedNote = await noteRes.json();
          renderNote(updatedNote);
        }
        closeSectionVisualModal();
      } catch (err) {
        statusEl.style.display = 'block';
        statusEl.style.background = 'rgba(239, 68, 68, 0.15)';
        statusEl.style.color = '#fca5a5';
        statusEl.textContent = `Error: ${err.message}`;
      } finally {
        btn.disabled = false;
        textSpan.style.display = 'inline';
        spinnerSpan.style.display = 'none';
      }
    }

    async function triggerPlanVisuals() {
      if (!currentJourneyId) {
        alert('Please start or open a learning journey first.');
        return;
      }
      const btn = document.getElementById('btn-plan-visuals');
      const origHtml = btn ? btn.innerHTML : '';
      if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span>⏳ Planning Visuals...</span>';
      }

      try {
        const res = await fetch(`/journeys/${currentJourneyId}/visuals/plan`, {
          method: 'POST',
        });
        if (!res.ok) {
          const err = await res.json();
          throw new Error(err.detail || 'Visual planning failed');
        }
        const plan = await res.json();

        // Fetch and re-render updated note
        const noteRes = await fetch(`/journeys/${currentJourneyId}/note`);
        if (noteRes.ok) {
          const updatedNote = await noteRes.json();
          renderNote(updatedNote);
        }

        alert(`Agent 7 successfully synthesized & planned ${plan.total_diagrams} architecture diagram(s) across your note!`);
      } catch (err) {
        alert(`Visual Planner error: ${err.message}`);
      } finally {
        if (btn) {
          btn.disabled = false;
          btn.innerHTML = origHtml;
        }
      }
    }

    /* ==========================================================================
       PHASE 10: CODE PLANNER & WEBASSEMBLY SANDBOX EXECUTION (AGENT 8)
       ========================================================================== */

