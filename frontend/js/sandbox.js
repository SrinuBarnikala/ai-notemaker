/* sandbox.js — Agent 8 Code Planner & Pyodide WebAssembly Sandbox */

    async function ensurePyodide() {
      if (pyodideInstance) return pyodideInstance;
      if (pyodideLoadingPromise) return pyodideLoadingPromise;

      pyodideLoadingPromise = (async () => {
        if (typeof loadPyodide === 'undefined') {
          await new Promise((resolve, reject) => {
            const s = document.createElement('script');
            s.src = 'https://cdn.jsdelivr.net/pyodide/v0.26.2/full/pyodide.js';
            s.onload = resolve;
            s.onerror = () => reject(new Error('Failed to load Pyodide WebAssembly runtime from CDN.'));
            document.head.appendChild(s);
          });
        }
        const py = await loadPyodide();
        pyodideInstance = py;
        return py;
      })();

      return pyodideLoadingPromise;
    }

    async function runCodeInSandbox(codeId) {
      const rawEl = document.getElementById('raw-code-' + codeId);
      if (!rawEl) return;
      const code = rawEl.value;

      const runBtn = document.getElementById('btn-run-' + codeId);
      const runText = document.getElementById('run-text-' + codeId);
      const runSpinner = document.getElementById('run-spinner-' + codeId);
      const term = document.getElementById('term-' + codeId);
      const stdoutEl = document.getElementById('stdout-' + codeId);
      const statusEl = document.getElementById('term-status-' + codeId);

      if (runBtn) runBtn.disabled = true;
      if (runText) runText.style.display = 'none';
      if (runSpinner) runSpinner.style.display = 'inline';

      if (term) term.style.display = 'block';
      if (stdoutEl) {
        stdoutEl.className = 'terminal-body';
        stdoutEl.textContent = '⏳ Initializing Pyodide WebAssembly sandbox & executing...\n';
      }
      if (statusEl) {
        statusEl.textContent = 'Executing...';
        statusEl.style.color = '#38bdf8';
      }

      const startTime = performance.now();

      try {
        const pyodide = await ensurePyodide();

        // Redirect stdout & stderr to capture output in real-time
        pyodide.runPython(`
import sys
import io
sys_stdout_backup = sys.stdout
sys_stderr_backup = sys.stderr
sys.stdout = io.StringIO()
sys.stderr = io.StringIO()
`);

        let executionError = null;
        let result = null;

        try {
          result = await pyodide.runPythonAsync(code);
        } catch (execErr) {
          executionError = execErr;
        }

        const capturedStdout = pyodide.runPython("sys.stdout.getvalue()");
        const capturedStderr = pyodide.runPython("sys.stderr.getvalue()");

        // Restore stdout/stderr
        pyodide.runPython(`
sys.stdout = sys_stdout_backup
sys.stderr = sys_stderr_backup
`);

        const durationMs = Math.round(performance.now() - startTime);

        if (executionError) {
          if (statusEl) {
            statusEl.textContent = `Error in ${durationMs}ms`;
            statusEl.style.color = '#f87171';
          }
          if (stdoutEl) {
            stdoutEl.className = 'terminal-body error-output';
            let errText = (capturedStdout ? capturedStdout + '\n' : '') + (capturedStderr ? capturedStderr + '\n' : '') + String(executionError);
            stdoutEl.textContent = errText;
          }
        } else {
          if (statusEl) {
            statusEl.textContent = `Success in ${durationMs}ms`;
            statusEl.style.color = '#34d399';
          }
          let out = capturedStdout || '';
          if (capturedStderr) out += (out ? '\n' : '') + '[stderr] ' + capturedStderr;
          if (result !== undefined && result !== null && String(result) !== 'None') {
            out += (out ? '\n' : '') + `=> Return: ${result}`;
          }
          if (!out.trim()) {
            out = 'Code executed successfully (no stdout produced).';
          }
          if (stdoutEl) {
            stdoutEl.className = 'terminal-body';
            stdoutEl.textContent = out;
          }
        }
      } catch (loadErr) {
        if (statusEl) {
          statusEl.textContent = 'Failed to load Sandbox';
          statusEl.style.color = '#f87171';
        }
        if (stdoutEl) {
          stdoutEl.className = 'terminal-body error-output';
          stdoutEl.textContent = `Sandbox runtime error: ${loadErr.message}\nMake sure you have an active internet connection to load Pyodide WebAssembly runtime.`;
        }
      } finally {
        if (runBtn) runBtn.disabled = false;
        if (runText) runText.style.display = 'inline';
        if (runSpinner) runSpinner.style.display = 'none';
      }
    }

    function clearTerminal(codeId) {
      const term = document.getElementById('term-' + codeId);
      const stdoutEl = document.getElementById('stdout-' + codeId);
      if (stdoutEl) stdoutEl.textContent = '';
      if (term) term.style.display = 'none';
    }

    function copyCodeFromBlock(btn, codeId) {
      const rawEl = document.getElementById('raw-code-' + codeId);
      const codeText = rawEl ? rawEl.value : '';
      if (!codeText) return;

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

    async function triggerPlanCode() {
      if (!currentJourneyId) {
        alert('Please start or open a learning journey first.');
        return;
      }
      const btn = document.getElementById('btn-plan-code');
      const origHtml = btn ? btn.innerHTML : '';
      if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span>⏳ Planning Code...</span>';
      }

      try {
        const res = await fetch(`/journeys/${currentJourneyId}/code/plan`, {
          method: 'POST',
        });
        if (!res.ok) {
          const err = await res.json();
          throw new Error(err.detail || 'Code planning failed');
        }
        const plan = await res.json();

        // Fetch and re-render updated note
        const noteRes = await fetch(`/journeys/${currentJourneyId}/note`);
        if (noteRes.ok) {
          const updatedNote = await noteRes.json();
          renderNote(updatedNote);
        }

        alert(`Agent 8 successfully synthesized & planned ${plan.total_code_blocks} runnable code implementation(s) across your note!`);
      } catch (err) {
        alert(`Code Planner error: ${err.message}`);
      } finally {
        if (btn) {
          btn.disabled = false;
          btn.innerHTML = origHtml;
        }
      }
    }

    function openSectionCodeModal(secId, secTitle) {
      targetSectionForCode = secId;
      selectedCodeLanguage = 'python';
      const modal = document.getElementById('section-code-modal');
      const titleEl = document.getElementById('code-modal-title');
      const promptInput = document.getElementById('code-custom-prompt');
      const statusEl = document.getElementById('code-modal-status');

      if (titleEl) titleEl.textContent = `Code Implementation for: ${secTitle}`;
      if (promptInput) promptInput.value = '';
      if (statusEl) statusEl.style.display = 'none';

      document.querySelectorAll('.clang-card').forEach(c => {
        c.classList.toggle('active', c.dataset.lang === 'python');
      });

      modal.style.display = 'flex';
    }

    function closeSectionCodeModal() {
      const modal = document.getElementById('section-code-modal');
      if (modal) modal.style.display = 'none';
    }

    function selectCodeLanguage(lang, cardEl) {
      selectedCodeLanguage = lang;
      document.querySelectorAll('.clang-card').forEach(c => c.classList.remove('active'));
      if (cardEl) cardEl.classList.add('active');
    }

    async function submitSectionCode() {
      if (!currentJourneyId || !targetSectionForCode) return;
      const promptVal = document.getElementById('code-custom-prompt').value.trim();
      const includeTests = document.getElementById('code-include-tests').checked;
      const btn = document.getElementById('btn-submit-code');
      const textSpan = document.getElementById('btn-code-text');
      const spinnerSpan = document.getElementById('btn-code-spinner');
      const statusEl = document.getElementById('code-modal-status');

      btn.disabled = true;
      textSpan.style.display = 'none';
      spinnerSpan.style.display = 'inline';
      statusEl.style.display = 'none';

      try {
        const res = await fetch(`/journeys/${currentJourneyId}/sections/${targetSectionForCode}/code`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            language: selectedCodeLanguage,
            custom_prompt: promptVal || undefined,
            include_tests: includeTests,
          }),
        });

        if (!res.ok) {
          const err = await res.json();
          throw new Error(err.detail || 'Failed to synthesize code');
        }

        // Refresh note
        const noteRes = await fetch(`/journeys/${currentJourneyId}/note`);
        if (noteRes.ok) {
          const updatedNote = await noteRes.json();
          renderNote(updatedNote);
        }
        closeSectionCodeModal();
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

    // Keyboard navigation: Close modals on Escape
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        closeDiagramModal();
        closeSectionVisualModal();
        closeSectionCodeModal();
      }
    });


