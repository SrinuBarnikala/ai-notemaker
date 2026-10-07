/* visuals.js — Agent 7 Visual Planner & Mermaid Architecture Diagrams */

    // Stored notes carry the old indigo/emerald classDef colors from the Mermaid fallback templates;
    // remap them to the current palette at render time so they match both themes.
    const LEGACY_MERMAID_COLORS = {
      '#1e1b4b': '#3a2f1a',
      '#312e81': '#4a3a1c',
      '#6366f1': '#d9a441',
      '#818cf8': '#d9a441',
      '#064e3b': '#2f4a2a',
      '#10b981': '#7fa37a',
      '#34d399': '#7fa37a',
      '#78350f': '#6b2f20',
      '#f59e0b': '#c4684f',
      '#f8fafc': '#ece8df'
    };

    function themeMermaidSpec(spec) {
      if (!spec) return spec;
      return spec.replace(/#[0-9a-fA-F]{6}\b/g, (hex) => LEGACY_MERMAID_COLORS[hex.toLowerCase()] || hex);
    }

    function getMermaidConfig(theme) {
      const isLight = (theme === 'light');
      if (isLight) {
        return {
          startOnLoad: false,
          theme: 'base',
          themeVariables: {
            darkMode: false,
            background: '#fffdf8',
            primaryColor: '#efebe1',
            primaryTextColor: '#1f1d19',
            primaryBorderColor: '#a79f8c',
            textColor: '#1f1d19',
            mainBkg: '#efebe1',
            nodeBorder: '#a79f8c',
            clusterBkg: '#f6f3ec',
            clusterBorder: '#d3ccbb',
            edgeLabelBackground: '#fffdf8',
            lineColor: '#6b6558',
            secondaryColor: '#dde8d9',
            secondaryTextColor: '#27441f',
            secondaryBorderColor: '#3f6b3a',
            tertiaryColor: '#efebe1',
            tertiaryTextColor: '#433f37',
            tertiaryBorderColor: '#d3ccbb',
            noteBkgColor: '#f4ead2',
            noteTextColor: '#5c3b08',
            noteBorderColor: '#a8741a',
            fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif",
            fontSize: '13px',
          },
          flowchart: { curve: 'basis', htmlLabels: true },
          sequence: { showSequenceNumbers: true },
          securityLevel: 'loose',
        };
      }
      return {
        startOnLoad: false,
        theme: 'base',
        themeVariables: {
          darkMode: true,
          background: '#100f0d',
          primaryColor: '#24221f',
          primaryTextColor: '#ece8df',
          primaryBorderColor: '#6b6558',
          textColor: '#ece8df',
          mainBkg: '#24221f',
          nodeBorder: '#6b6558',
          clusterBkg: '#1c1b18',
          clusterBorder: '#504c44',
          edgeLabelBackground: '#1c1b18',
          lineColor: '#b3aa97',
          secondaryColor: '#26331f',
          secondaryTextColor: '#cfe3cb',
          secondaryBorderColor: '#7fa37a',
          tertiaryColor: '#24221f',
          tertiaryTextColor: '#c9c3b6',
          tertiaryBorderColor: '#504c44',
          noteBkgColor: '#33281a',
          noteTextColor: '#f1d9a0',
          noteBorderColor: '#b8862f',
          fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif",
          fontSize: '13px',
        },
        flowchart: { curve: 'basis', htmlLabels: true },
        sequence: { showSequenceNumbers: true },
        securityLevel: 'loose',
      };
    }

    // Mermaid sizes node boxes from measured text. If the web font has not loaded yet it measures
    // with the fallback font and the labels get clipped once Plus Jakarta Sans swaps in.
    async function waitForUiFonts() {
      if (!document.fonts || !document.fonts.load) return;
      try {
        await Promise.all([
          document.fonts.load("400 13px 'Plus Jakarta Sans'"),
          document.fonts.load("600 13px 'Plus Jakarta Sans'"),
        ]);
      } catch (err) {
        console.debug("UI font preload skipped:", err);
      }
    }

    async function ensureMermaidLoaded(maxWaitMs = 6000) {
      const start = Date.now();
      while (!window.mermaid && (Date.now() - start) < maxWaitMs) {
        await new Promise(r => setTimeout(r, 100));
      }
      await waitForUiFonts();
      if (window.mermaid) {
        const activeTheme = (typeof getTheme === 'function') ? getTheme() : (document.documentElement.getAttribute('data-theme') || 'dark');
        if (!window._mermaidInitialized || window._mermaidCurrentTheme !== activeTheme) {
          try {
            mermaid.initialize(getMermaidConfig(activeTheme));
            window._mermaidInitialized = true;
            window._mermaidCurrentTheme = activeTheme;
          } catch (err) {
            console.warn("Mermaid initialize warning:", err);
          }
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
        const cleanSpec = (rawEl && rawEl.value) ? rawEl.value.trim() : (el.dataset.mermaidSpec || '');
        if (!cleanSpec) continue;
        el.dataset.mermaidSpec = cleanSpec;

        try {
          const cleanId = id.replace(/[^a-zA-Z0-9]/g, '');
          const svgId = 'svg-' + cleanId + '-' + Math.random().toString(36).substring(2, 7);
          const { svg } = await mermaid.render(svgId, themeMermaidSpec(cleanSpec));
          el.innerHTML = svg;
          el.classList.add('rendered');
        } catch (err) {
          console.warn('Mermaid rendering fallback for', id, err);
          el.innerHTML = `
            <div class="diagram-render-fallback">
              <div class="fallback-note">${uiIcon('zap')} Visual Architecture Specification:</div>
              <pre class="diagram-spec-pre">${escapeHtml(cleanSpec)}</pre>
            </div>
          `;
        }
      }
    }

    // Re-initialize and re-render Mermaid on theme change
    document.addEventListener('themechange', async (e) => {
      const newTheme = e.detail && e.detail.theme ? e.detail.theme : ((typeof getTheme === 'function') ? getTheme() : 'dark');
      if (window.mermaid) {
        try {
          mermaid.initialize(getMermaidConfig(newTheme));
          window._mermaidCurrentTheme = newTheme;
        } catch (err) {
          console.warn("Mermaid re-init error:", err);
        }

        // Re-render all diagrams on page
        await renderAllMermaidDiagrams();

        // If diagram fullscreen modal is open, re-render its content
        const modal = document.getElementById('diag-fullscreen-modal');
        if (modal && (modal.style.display === 'flex' || modal.style.display === 'block') && currentModalDiagId) {
          const rawEl = document.getElementById('raw-' + currentModalDiagId);
          const modalSpec = (rawEl && rawEl.value) ? rawEl.value.trim() : '';
          const canvas = document.getElementById('diag-modal-svg-canvas');
          if (canvas && modalSpec) {
            try {
              const modalSvgId = 'modal-svg-' + Math.random().toString(36).substring(2, 7);
              const { svg } = await mermaid.render(modalSvgId, themeMermaidSpec(modalSpec));
              canvas.innerHTML = svg;
              const newSvg = canvas.querySelector('svg');
              if (newSvg) {
                newSvg.style.maxWidth = '100%';
                newSvg.style.height = 'auto';
                newSvg.style.maxHeight = '70vh';
              }
            } catch (err) {
              console.warn("Modal re-render on theme change error:", err);
            }
          }
        }
      }
    });

    function copyDiagramSpec(btn, diagId) {
      const rawEl = document.getElementById('raw-' + diagId);
      const spec = rawEl ? rawEl.value : '';
      if (!spec) return;
      navigator.clipboard.writeText(spec).then(() => {
        const orig = btn.innerHTML;
        btn.innerHTML = '<span>' + uiIcon('circle-check') + ' Copied!</span>';
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
            const res = await mermaid.render(tempId, themeMermaidSpec(spec));
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
      if (modalBadge) setIconLabel(modalBadge, 'zap', (diagType || 'ARCHITECTURE').toUpperCase());
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
            const { svg } = await mermaid.render(modalSvgId, themeMermaidSpec(spec));
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
          canvas.innerHTML = `<pre class="diagram-spec-pre text-md" style="padding: 2rem;">${escapeHtml(spec)}</pre>`;
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
        await API.request(`/journeys/${currentJourneyId}/sections/${targetSectionForVisual}/visual`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            visual_type: selectedVisualType,
            custom_prompt: promptVal || undefined,
          }),
        }, 'Failed to generate visual');

        // Refresh note
        const updatedNote = await API.requestOrNull(`/journeys/${currentJourneyId}/note`);
        if (updatedNote) {
          renderNote(updatedNote);
        }
        closeSectionVisualModal();
      } catch (err) {
        statusEl.style.display = 'block';
        statusEl.style.background = 'var(--color-danger-tint)';
        statusEl.style.color = 'var(--danger-text)';
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
        btn.innerHTML = '<span>' + uiIcon('loader-circle', 'icon-spin') + ' Planning Visuals...</span>';
      }

      try {
        const plan = await API.request(`/journeys/${currentJourneyId}/visuals/plan`, {
          method: 'POST',
        }, 'Visual planning failed');

        // Fetch and re-render updated note
        const updatedNote = await API.requestOrNull(`/journeys/${currentJourneyId}/note`);
        if (updatedNote) {
          renderNote(updatedNote);
        }

        alert(`Planned ${plan.total_diagrams} architecture diagram(s) across your note.`);
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

