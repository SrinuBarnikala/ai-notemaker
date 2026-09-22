/* state.js — Shared Application State & Core Utilities */

let currentJourneyId = null;
let currentTopic = "";
let currentFontSizeRem = 1.05;
let currentNote = null;
let observer = null;

let activeEvolveSectionId = null;
let activeEvolveType = 'add_code';

let currentAssessment = null;
let activeCardIndex = 0;
let userQuizAnswers = {};
let assessmentFontScale = 1.0;
let activeQuizQuestionIndex = 0;
let quizViewMode = 'focus';

let currentModalZoom = 1.0;
let currentModalDiagId = null;

let targetSectionForVisual = null;
let selectedVisualType = 'flowchart';

let pyodideInstance = null;
let pyodideLoadingPromise = null;

let targetSectionForCode = null;
let selectedCodeLanguage = 'python';

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str || '';
  return div.innerHTML;
}

function escapeJsString(str) {
  return (str || '')
    .replace(/\\/g, '\\\\')
    .replace(/`/g, '\\`')
    .replace(/\$/g, '\\$');
}

function formatInlineMarkdown(text) {
  if (!text) return '';
  let safe = escapeHtml(text);
  safe = safe.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  safe = safe.replace(/`([^`]+)`/g, '<code style="font-family: var(--font-mono); background: rgba(255,255,255,0.06); padding: 0.15rem 0.4rem; border-radius: 4px; color: #a5b4fc; font-size: 0.9em;">$1</code>');
  return safe;
}

function formatStatus(status) {
  if (!status) return 'In Progress';
  return status.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}
