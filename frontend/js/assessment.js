/* assessment.js — Agent 6 Active Recall & Mastery Assessment (3D Flashcards & Quiz) */

    async function openAssessmentModal() {
      const journeyId = (currentNote && currentNote.journey_id) || currentJourneyId;
      if (!journeyId) {
        alert('Please create or load a living note first to test your mastery.');
        return;
      }

      initAssessmentControls();
      const modal = document.getElementById('assessment-modal');
      modal.style.display = 'flex';
      switchAssessmentTab('flashcards');

      if (!currentAssessment || currentAssessment.journey_id !== journeyId) {
        await loadAssessment();
      } else {
        renderFlashcardsUI();
        renderQuizUI();
      }
    }

    function closeAssessmentModal() {
      const modal = document.getElementById('assessment-modal');
      modal.style.display = 'none';
    }

    function switchAssessmentTab(tab) {
      const tabFc = document.getElementById('tab-flashcards');
      const tabQz = document.getElementById('tab-quiz');
      const panelFc = document.getElementById('flashcards-panel');
      const panelQz = document.getElementById('quiz-panel');

      if (tab === 'flashcards') {
        tabFc.classList.add('active');
        tabQz.classList.remove('active');
        panelFc.style.display = 'block';
        panelQz.style.display = 'none';
      } else {
        tabFc.classList.remove('active');
        tabQz.classList.add('active');
        panelFc.style.display = 'none';
        panelQz.style.display = 'block';
      }
    }

    async function loadAssessment(forceGenerate = false) {
      const loading = document.getElementById('assessment-loading');
      const panelFc = document.getElementById('flashcards-panel');
      const panelQz = document.getElementById('quiz-panel');

      loading.style.display = 'block';
      panelFc.style.display = 'none';
      panelQz.style.display = 'none';

      const journeyId = (currentNote && currentNote.journey_id) || currentJourneyId;
      if (!journeyId) return;

      try {
        let res = null;
        if (!forceGenerate) {
          res = await fetch(`/journeys/${journeyId}/assessment`);
        }
        if (!res || !res.ok) {
          // Generate new assessment
          res = await fetch(`/journeys/${journeyId}/assessment/generate`, { method: 'POST' });
        }

        if (!res.ok) throw new Error('Failed to load assessment materials');
        currentAssessment = await res.json();
        activeCardIndex = 0;
        userQuizAnswers = {};

        renderFlashcardsUI();
        renderQuizUI();
        switchAssessmentTab('flashcards');
      } catch (err) {
        alert('Error loading assessment: ' + err.message);
      } finally {
        loading.style.display = 'none';
      }
    }

    function renderFlashcardsUI() {
      if (!currentAssessment || !currentAssessment.flashcards || currentAssessment.flashcards.length === 0) return;
      activeCardIndex = 0;
      updateFlashcardDisplay();
    }

    function updateFlashcardDisplay() {
      const cards = currentAssessment.flashcards;
      if (!cards || cards.length === 0) return;

      if (activeCardIndex < 0) activeCardIndex = 0;
      if (activeCardIndex >= cards.length) activeCardIndex = cards.length - 1;

      const card = cards[activeCardIndex];
      const cardEl = document.getElementById('active-flashcard');
      if (cardEl) {
        cardEl.classList.remove('flipped');
      }

      const counterEl = document.getElementById('fc-counter');
      if (counterEl) counterEl.textContent = `Card ${activeCardIndex + 1} of ${cards.length}`;

      const conceptEl = document.getElementById('fc-concept');
      if (conceptEl) conceptEl.textContent = card.concept;
      
      const diffEl = document.getElementById('fc-diff');
      if (diffEl) {
        diffEl.textContent = card.difficulty.toUpperCase();
        diffEl.className = `card-diff-badge diff-${card.difficulty}`;
      }

      const frontText = document.getElementById('fc-front-text');
      if (frontText) frontText.textContent = card.front;

      const backText = document.getElementById('fc-back-text');
      if (backText) backText.textContent = card.back;

      const prevBtn = document.getElementById('btn-prev-card');
      if (prevBtn) prevBtn.disabled = (activeCardIndex === 0);

      const nextBtn = document.getElementById('btn-next-card');
      if (nextBtn) nextBtn.disabled = (activeCardIndex === cards.length - 1);
    }

    function flipFlashcard() {
      const cardEl = document.getElementById('active-flashcard');
      if (cardEl) {
        cardEl.classList.toggle('flipped');
      }
    }

    function navigateFlashcard(step) {
      activeCardIndex += step;
      updateFlashcardDisplay();
    }

    /* Assessment Font Size & Window Size Controls */
    function initAssessmentControls() {
      try {
        const savedScale = localStorage.getItem('ai_notemaker_assessment_font_scale');
        if (savedScale) {
          assessmentFontScale = parseFloat(savedScale) || 1.0;
        }
      } catch (e) {}
      applyAssessmentFontSize();
    }

    function adjustAssessmentFontSize(delta) {
      assessmentFontScale = Math.round((assessmentFontScale + delta) * 100) / 100;
      if (assessmentFontScale < 0.8) assessmentFontScale = 0.8;
      if (assessmentFontScale > 1.3) assessmentFontScale = 1.3;
      applyAssessmentFontSize();
    }

    function applyAssessmentFontSize() {
      document.documentElement.style.setProperty('--assessment-font-scale', assessmentFontScale.toString());
      const lbl = document.getElementById('assessment-scale-label');
      if (lbl) lbl.textContent = `${Math.round(assessmentFontScale * 100)}%`;
      try {
        localStorage.setItem('ai_notemaker_assessment_font_scale', assessmentFontScale.toString());
      } catch (e) {}
    }

    function toggleAssessmentMaximize() {
      const modal = document.getElementById('assessment-modal');
      if (!modal) return;
      const dialog = modal.querySelector('.modal-dialog');
      if (!dialog) return;
      const isMax = dialog.classList.toggle('is-maximized');
      const btn = document.getElementById('btn-toggle-assessment-maximize');
      if (btn) btn.textContent = isMax ? '🗗' : '⛶';
    }

    function toggleModalMaximize(modalId) {
      const modal = document.getElementById(modalId);
      if (!modal) return;
      const dialog = modal.querySelector('.modal-dialog') || modal.querySelector('.modal-card');
      if (dialog) dialog.classList.toggle('is-maximized');
    }

    function setQuizViewMode(mode) {
      quizViewMode = mode;
      const btnFocus = document.getElementById('quiz-mode-focus-btn');
      const btnAll = document.getElementById('quiz-mode-all-btn');
      if (btnFocus && btnAll) {
        if (mode === 'focus') {
          btnFocus.classList.add('active');
          btnAll.classList.remove('active');
        } else {
          btnFocus.classList.remove('active');
          btnAll.classList.add('active');
        }
      }
      renderQuizUI();
    }

    function navigateQuizQuestion(delta) {
      if (!currentAssessment || !currentAssessment.quiz_questions) return;
      const total = currentAssessment.quiz_questions.length;
      activeQuizQuestionIndex += delta;
      if (activeQuizQuestionIndex < 0) activeQuizQuestionIndex = 0;
      if (activeQuizQuestionIndex >= total) activeQuizQuestionIndex = total - 1;
      renderQuizUI();
    }

    function jumpToQuizQuestion(idx) {
      activeQuizQuestionIndex = idx;
      if (quizViewMode !== 'focus') {
        setQuizViewMode('focus');
      } else {
        renderQuizUI();
      }
    }

    // Keyboard support for flashcards and quiz
    document.addEventListener('keydown', function(e) {
      const modal = document.getElementById('assessment-modal');
      if (!modal || modal.style.display === 'none') return;

      if (e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA')) return;

      const tabFc = document.getElementById('tab-flashcards');
      const isFlashcards = tabFc && tabFc.classList.contains('active');

      if (isFlashcards) {
        if (e.code === 'Space' || e.key === ' ') {
          e.preventDefault();
          flipFlashcard();
        } else if (e.code === 'ArrowLeft' || e.key === 'ArrowLeft') {
          e.preventDefault();
          navigateFlashcard(-1);
        } else if (e.code === 'ArrowRight' || e.key === 'ArrowRight') {
          e.preventDefault();
          navigateFlashcard(1);
        }
      } else {
        // Quiz tab keyboard shortcuts
        if (quizViewMode === 'focus') {
          if (e.code === 'ArrowLeft' || e.key === 'ArrowLeft') {
            e.preventDefault();
            navigateQuizQuestion(-1);
          } else if (e.code === 'ArrowRight' || e.key === 'ArrowRight') {
            e.preventDefault();
            navigateQuizQuestion(1);
          }
        }
      }
    });

    function updateQuizProgress() {
      if (!currentAssessment || !currentAssessment.quiz_questions) return;
      const total = currentAssessment.quiz_questions.length;
      const answered = Object.keys(userQuizAnswers).length;
      const pct = total > 0 ? Math.round((answered / total) * 100) : 0;

      const label = document.getElementById('quiz-progress-label');
      if (label) label.textContent = `${answered}/${total} Answered (${pct}%)`;

      const fill = document.getElementById('quiz-progress-fill');
      if (fill) fill.style.width = `${pct}%`;
    }

    function renderQuizUI() {
      if (!currentAssessment || !currentAssessment.quiz_questions) return;
      const container = document.getElementById('quiz-questions-list');
      const questions = currentAssessment.quiz_questions;

      if (activeQuizQuestionIndex >= questions.length) {
        activeQuizQuestionIndex = Math.max(0, questions.length - 1);
      }

      // Render question stepper jump pills
      const pillsContainer = document.getElementById('quiz-stepper-pills');
      if (pillsContainer && questions.length > 0) {
        pillsContainer.innerHTML = questions.map((q, idx) => {
          const isAnswered = userQuizAnswers[q.id] !== undefined;
          const isActive = (quizViewMode === 'focus' && idx === activeQuizQuestionIndex);
          return `
            <button type="button" class="qstep-pill ${isActive ? 'active' : ''} ${isAnswered ? 'answered' : ''}" onclick="jumpToQuizQuestion(${idx})" title="Jump to Question ${idx + 1}">
              <span>Q${idx + 1}</span>
              ${isAnswered ? '<span style="font-size: 0.7rem; color: #34d399;">✓</span>' : ''}
            </button>
          `;
        }).join('');
      }

      // Render questions (in focus mode, only active question card is visible)
      container.innerHTML = questions.map((q, qIdx) => {
        const letters = ['A', 'B', 'C', 'D', 'E'];
        const isAnswered = userQuizAnswers[q.id] !== undefined;
        const isVisible = (quizViewMode === 'all' || qIdx === activeQuizQuestionIndex);
        return `
          <div class="quiz-question-card ${isAnswered ? 'answered' : ''}" id="quiz-card-${q.id}" style="display: ${isVisible ? 'block' : 'none'};">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.65rem;">
              <span style="font-family: var(--font-mono); font-size: 0.75rem; color: #a5b4fc; font-weight: 700; letter-spacing: 0.05em;">QUESTION ${qIdx + 1} OF ${questions.length} &bull; ${escapeHtml(q.concept)}</span>
              <span class="card-diff-badge diff-medium" style="font-size: 0.675rem;">SCENARIO</span>
            </div>
            <div class="quiz-question-title">${escapeHtml(q.question)}</div>
            <div class="quiz-options-list">
              ${q.options.map((opt, oIdx) => {
                const isSelected = userQuizAnswers[q.id] === oIdx;
                return `
                  <button type="button" class="quiz-opt-btn ${isSelected ? 'selected' : ''}" id="opt-${q.id}-${oIdx}" onclick="selectQuizOption('${q.id}', ${oIdx})">
                    <span class="opt-radio-circle"><span class="opt-radio-dot"></span></span>
                    <span class="opt-letter">${letters[oIdx] || oIdx}</span>
                    <span class="opt-text">${escapeHtml(opt)}</span>
                    <span class="opt-selected-tag" style="display: ${isSelected ? 'inline-flex' : 'none'};">✓ Selected</span>
                  </button>
                `;
              }).join('')}
            </div>
            <div class="quiz-explanation-box" id="expl-${q.id}" style="display: none;"></div>
          </div>
        `;
      }).join('');

      // Update focus navigation controls
      const focusNav = document.getElementById('quiz-focus-nav');
      const indicator = document.getElementById('quiz-card-indicator');
      const btnPrev = document.getElementById('btn-quiz-prev');
      const btnNext = document.getElementById('btn-quiz-next');
      if (focusNav) {
        focusNav.style.display = (quizViewMode === 'focus') ? 'flex' : 'none';
      }
      if (indicator) {
        indicator.textContent = `Question ${activeQuizQuestionIndex + 1} of ${questions.length}`;
      }
      if (btnPrev) {
        btnPrev.disabled = (activeQuizQuestionIndex === 0);
      }
      if (btnNext) {
        btnNext.disabled = (activeQuizQuestionIndex === questions.length - 1);
      }

      updateQuizProgress();
    }

    function selectQuizOption(qId, optIdx) {
      userQuizAnswers[qId] = optIdx;
      const q = currentAssessment.quiz_questions.find(item => item.id === qId);
      if (!q) return;

      const card = document.getElementById(`quiz-card-${qId}`);
      if (card) card.classList.add('answered');

      q.options.forEach((_, idx) => {
        const btn = document.getElementById(`opt-${qId}-${idx}`);
        if (btn) {
          const tag = btn.querySelector('.opt-selected-tag');
          if (idx === optIdx) {
            btn.classList.add('selected');
            if (tag) tag.style.display = 'inline-flex';
          } else {
            btn.classList.remove('selected');
            if (tag) tag.style.display = 'none';
          }
        }
      });

      // Update stepper pills answered indicator
      const pillsContainer = document.getElementById('quiz-stepper-pills');
      if (pillsContainer) {
        const questions = currentAssessment.quiz_questions;
        pillsContainer.innerHTML = questions.map((item, idx) => {
          const isAnswered = userQuizAnswers[item.id] !== undefined;
          const isActive = (quizViewMode === 'focus' && idx === activeQuizQuestionIndex);
          return `
            <button type="button" class="qstep-pill ${isActive ? 'active' : ''} ${isAnswered ? 'answered' : ''}" onclick="jumpToQuizQuestion(${idx})" title="Jump to Question ${idx + 1}">
              <span>Q${idx + 1}</span>
              ${isAnswered ? '<span style="font-size: 0.7rem; color: #34d399;">✓</span>' : ''}
            </button>
          `;
        }).join('');
      }

      updateQuizProgress();
    }

    async function submitQuizAnswers() {
      const questions = (currentAssessment && currentAssessment.quiz_questions) || [];
      if (questions.length === 0) return;

      const unanswered = questions.filter(q => userQuizAnswers[q.id] === undefined);
      if (unanswered.length > 0) {
        const proceed = confirm(`You have ${unanswered.length} unanswered question(s). Unanswered questions will be scored as incorrect. Do you want to submit anyway?`);
        if (!proceed) {
          return;
        }
      }

      const btn = document.getElementById('btn-submit-quiz');
      const btnText = document.getElementById('btn-quiz-text');
      const btnSpinner = document.getElementById('btn-quiz-spinner');

      btn.disabled = true;
      btnText.style.display = 'none';
      btnSpinner.style.display = 'inline';

      const journeyId = (currentAssessment && currentAssessment.journey_id) || currentJourneyId || (currentNote ? currentNote.journey_id : null);
      if (!journeyId) {
        alert('Could not find active journey ID for submission.');
        btn.disabled = false;
        btnText.style.display = 'inline';
        btnSpinner.style.display = 'none';
        return;
      }

      try {
        const res = await fetch(`/journeys/${journeyId}/assessment/submit`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ answers: userQuizAnswers })
        });

        if (!res.ok) {
          const errData = await res.json().catch(() => ({}));
          throw new Error(errData.detail || 'Failed to evaluate quiz submission');
        }
        const result = await res.json();

        // Render Score Banner HTML
        const masteredHtml = (result.mastered_concepts && result.mastered_concepts.length > 0) ? `
          <div style="margin-top: 0.6rem; font-size: 0.8rem; color: #e0e7ff; display: flex; align-items: center; gap: 0.4rem; flex-wrap: wrap;">
            <strong style="color: #818cf8;">🚀 Promoted to Mastered:</strong>
            ${result.mastered_concepts.map(c => `<span class="card-concept-badge" style="color: #34d399; border-color: rgba(16, 185, 129, 0.4); background: rgba(16, 185, 129, 0.15);">${escapeHtml(c)}</span>`).join('')}
          </div>
        ` : '';

        const scoreHtml = `
          <div class="quiz-score-banner">
            <div>
              <div style="font-size: 0.75rem; font-family: var(--font-mono); color: #a5b4fc; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 700;">AGENT 6 &bull; MASTERY EVALUATION</div>
              <div style="font-size: 1.25rem; font-weight: 800; color: #ffffff; margin-top: 0.25rem;">${escapeHtml(result.message)}</div>
              <div style="font-size: 0.85rem; color: #a7f3d0; margin-top: 0.4rem; display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap;">
                <span>🧠 Mental Model Confidence:</span>
                <span style="background: rgba(16, 185, 129, 0.2); border: 1px solid rgba(16, 185, 129, 0.4); color: #34d399; font-weight: 700; padding: 0.15rem 0.6rem; border-radius: 9999px; font-size: 0.75rem;">${escapeHtml(result.updated_confidence.toUpperCase())}</span>
              </div>
              ${masteredHtml}
            </div>
            <div style="text-align: right; min-width: 130px;">
              <div class="score-badge-num">${result.percentage}%</div>
              <div style="font-size: 0.85rem; font-family: var(--font-mono); font-weight: 700; color: #cbd5e1;">${result.score} of ${result.total} Correct</div>
              <div style="font-size: 0.725rem; color: ${result.percentage >= 70 ? '#34d399' : '#f59e0b'}; margin-top: 0.25rem; font-weight: 600;">${result.percentage >= 70 ? '🎯 Technical Mastery Standard Met' : '📖 Knowledge Gaps Retained for Review'}</div>
            </div>
          </div>
        `;

        // Render into BOTH top and bottom containers
        const topScoreBox = document.getElementById('quiz-score-container');
        if (topScoreBox) {
          topScoreBox.style.display = 'block';
          topScoreBox.innerHTML = scoreHtml;
        }

        const bottomScoreBox = document.getElementById('quiz-bottom-score-container');
        if (bottomScoreBox) {
          bottomScoreBox.style.display = 'block';
          bottomScoreBox.innerHTML = scoreHtml;
        }

        // Highlight correct/incorrect options & show rich explanations
        result.breakdown.forEach(item => {
          const q = questions.find(question => question.id === item.question_id);
          if (!q) return;

          const card = document.getElementById(`quiz-card-${item.question_id}`);
          if (card) {
            card.style.borderColor = item.is_correct ? 'rgba(16, 185, 129, 0.5)' : 'rgba(239, 68, 68, 0.5)';
          }

          q.options.forEach((_, oIdx) => {
            const optBtn = document.getElementById(`opt-${item.question_id}-${oIdx}`);
            if (optBtn) {
              optBtn.disabled = true;
              optBtn.classList.remove('selected');
              if (oIdx === item.correct_index) {
                optBtn.classList.add('correct');
              } else if (oIdx === item.selected_index && !item.is_correct) {
                optBtn.classList.add('incorrect');
              }
            }
          });

          const explBox = document.getElementById(`expl-${item.question_id}`);
          if (explBox) {
            explBox.style.display = 'block';
            explBox.className = `quiz-explanation-box ${item.is_correct ? 'correct-expl' : 'incorrect-expl'}`;
            explBox.innerHTML = `
              <div style="display: flex; align-items: center; gap: 0.4rem; font-weight: 700; color: ${item.is_correct ? '#34d399' : '#f87171'}; margin-bottom: 0.35rem;">
                <span>${item.is_correct ? '✅ Correct Answer (+1)' : '❌ Incorrect Selection (0/1)'}</span>
              </div>
              <div style="font-size: 0.85rem; line-height: 1.5; color: #e2e8f0;">${escapeHtml(item.explanation)}</div>
            `;
          }
        });

        // Switch view to 'all' so learner can review all explanations together
        setQuizViewMode('all');

        // Hide submit button and show retake quiz button
        btn.style.display = 'none';
        const retakeBtn = document.getElementById('btn-retake-quiz');
        if (retakeBtn) retakeBtn.style.display = 'inline-flex';

        // Auto-scroll modal body smoothly to the top so learner sees the full score banner
        const modalBody = document.getElementById('assessment-modal-body');
        if (modalBody) {
          modalBody.scrollTo({ top: 0, behavior: 'smooth' });
        }

        // If profile exists, reload it to reflect newly mastered concepts
        if (currentJourneyId) {
          fetch(`/journeys/${currentJourneyId}/knowledge-profile`)
            .then(r => r.ok ? r.json() : null)
            .then(p => { if (p) renderProfile(p); })
            .catch(() => {});
        }
      } catch (err) {
        alert('Submission error: ' + err.message);
        btn.disabled = false;
        btnText.style.display = 'inline';
        btnSpinner.style.display = 'none';
      }
    }

    function retakeQuiz() {
      userQuizAnswers = {};
      activeQuizQuestionIndex = 0;
      const topScoreBox = document.getElementById('quiz-score-container');
      if (topScoreBox) {
        topScoreBox.style.display = 'none';
        topScoreBox.innerHTML = '';
      }
      const bottomScoreBox = document.getElementById('quiz-bottom-score-container');
      if (bottomScoreBox) {
        bottomScoreBox.style.display = 'none';
        bottomScoreBox.innerHTML = '';
      }
      const submitBtn = document.getElementById('btn-submit-quiz');
      if (submitBtn) {
        submitBtn.style.display = 'block';
        submitBtn.disabled = false;
        const btnText = document.getElementById('btn-quiz-text');
        if (btnText) {
          btnText.style.display = 'inline';
          btnText.textContent = 'Submit Quiz & Update Mastery Profile';
        }
        const btnSpinner = document.getElementById('btn-quiz-spinner');
        if (btnSpinner) btnSpinner.style.display = 'none';
      }
      const retakeBtn = document.getElementById('btn-retake-quiz');
      if (retakeBtn) retakeBtn.style.display = 'none';

      setQuizViewMode('focus');
      renderQuizUI();
      const modalBody = document.getElementById('assessment-modal-body');
      if (modalBody) modalBody.scrollTo({ top: 0, behavior: 'smooth' });
    }

    /* ==========================================================================
       JOURNEY RESUMPTION & HISTORY
       ========================================================================== */



