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
let lastQuizSubmissionResult = null;
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

let activeCopilotSectionId = null;
let activeCopilotSectionTitle = null;
let activeCopilotSelectedText = null;
let copilotHistory = [];
let lastPinCandidate = null;

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

function normalizeLatexEscapes(text) {
  if (!text) return '';
  let str = String(text);
  // Normalize double-escaped backslashes from JSON stringification: \\frac -> \frac, \\sum -> \sum, etc.
  str = str.replace(/\\\\([a-zA-Z]+|[()\[\]{}_^+\-*,.<>=|/])/g, '\\$1');
  // Normalize standard bracket-style math delimiters: \[ ... \] -> $$ ... $$, \( ... \) -> $ ... $
  str = str.replace(/\\\[([\s\S]*?)\\\]/g, '$$$1$$');
  str = str.replace(/\\\(([\s\S]*?)\\\)/g, '$$$1$');
  return str;
}

function formatInlineMarkdown(text) {
  if (!text) return '';
  let str = normalizeLatexEscapes(text);
  let safe = escapeHtml(str);
  safe = safe.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  safe = safe.replace(/\*([^*\n]+)\*/g, '<em>$1</em>');
  safe = safe.replace(/`([^`]+)`/g, '<code style="font-family: var(--font-mono); background: rgba(255,255,255,0.06); padding: 0.15rem 0.4rem; border-radius: 4px; color: #a5b4fc; font-size: 0.9em;">$1</code>');
  return safe;
}

function renderMarkdownText(rawText) {
  if (!rawText) return '';
  const text = normalizeLatexEscapes(rawText);
  const lines = text.split(/\r?\n/);
  const blocks = [];
  let currentTableLines = [];
  let currentTextLines = [];

  function flushText() {
    if (currentTextLines.length > 0) {
      const paragraphText = currentTextLines.join('\n').trim();
      if (paragraphText) {
        // Check for block math ($$ ... $$)
        if (paragraphText.startsWith('$$') && paragraphText.endsWith('$$') && paragraphText.length > 4) {
          blocks.push(`<div class="math-block-wrap">${escapeHtml(paragraphText)}</div>`);
        } else {
          // Format linebreaks and markdown
          const formatted = paragraphText.split(/\n\s*\n/).map(p => {
            return `<div class="block-para-sub">${formatInlineMarkdown(p).replace(/\n/g, '<br>')}</div>`;
          }).join('');
          blocks.push(formatted);
        }
      }
      currentTextLines = [];
    }
  }

  function flushTable() {
    if (currentTableLines.length >= 2) {
      const headerLine = currentTableLines[0].trim();
      const sepLine = currentTableLines[1].trim();
      // Separator row matches pattern like |---|---| or |:---:|---:|
      const isSeparator = /^\|?(\s*:?-+:?\s*\|?)+$/.test(sepLine);

      if (isSeparator) {
        const splitRow = (row) => {
          let r = row.trim();
          if (r.startsWith('|')) r = r.substring(1);
          if (r.endsWith('|')) r = r.substring(0, r.length - 1);
          return r.split('|').map(c => c.trim());
        };

        const headers = splitRow(headerLine);
        const rows = currentTableLines.slice(2).map(splitRow).filter(r => r.some(c => c.length > 0));

        let tableHtml = '<div class="comparison-table-wrapper"><table class="comparison-table"><thead><tr>';
        headers.forEach(h => {
          tableHtml += `<th>${formatInlineMarkdown(h)}</th>`;
        });
        tableHtml += '</tr></thead><tbody>';
        rows.forEach(r => {
          tableHtml += '<tr>';
          for (let i = 0; i < headers.length; i++) {
            const cell = r[i] !== undefined ? r[i] : '';
            tableHtml += `<td>${formatInlineMarkdown(cell)}</td>`;
          }
          tableHtml += '</tr>';
        });
        tableHtml += '</tbody></table></div>';
        blocks.push(tableHtml);
        currentTableLines = [];
        return;
      }
    }
    // If not a valid table, push accumulated lines as text
    currentTableLines.forEach(l => currentTextLines.push(l));
    currentTableLines = [];
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();
    // A markdown table row contains pipes and column structure
    const isPipeRow = trimmed.length > 2 && (trimmed.startsWith('|') || (trimmed.endsWith('|') && trimmed.includes('|')) || /^\|?([^\n|]+\|)+[^\n|]+\|?$/.test(trimmed));

    if (isPipeRow) {
      flushText();
      currentTableLines.push(line);
    } else {
      if (currentTableLines.length > 0) {
        flushTable();
      }
      currentTextLines.push(line);
    }
  }
  if (currentTableLines.length > 0) {
    flushTable();
  }
  flushText();

  return blocks.join('\n');
}

function applyMathFallbackFormatting(container) {
  if (!container) return;
  // Greek & common math symbols map for offline fallback
  const symbolMap = {
    '\\\\times': '×',
    '\\\\cdot': '·',
    '\\\\approx': '≈',
    '\\\\leq': '≤',
    '\\\\le': '≤',
    '\\\\geq': '≥',
    '\\\\ge': '≥',
    '\\\\neq': '≠',
    '\\\\pm': '±',
    '\\\\mp': '∓',
    '\\\\to': '→',
    '\\\\leftarrow': '←',
    '\\\\rightarrow': '→',
    '\\\\in': '∈',
    '\\\\notin': '∉',
    '\\\\subset': '⊂',
    '\\\\cup': '∪',
    '\\\\cap': '∩',
    '\\\\infty': '∞',
    '\\\\nabla': '∇',
    '\\\\partial': '∂',
    '\\\\sum': '∑',
    '\\\\prod': '∏',
    '\\\\int': '∫',
    '\\\\alpha': 'α',
    '\\\\beta': 'β',
    '\\\\gamma': 'γ',
    '\\\\delta': 'δ',
    '\\\\epsilon': 'ε',
    '\\\\theta': 'θ',
    '\\\\lambda': 'λ',
    '\\\\mu': 'μ',
    '\\\\pi': 'π',
    '\\\\rho': 'ρ',
    '\\\\sigma': 'σ',
    '\\\\tau': 'τ',
    '\\\\phi': 'φ',
    '\\\\omega': 'ω'
  };

  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT, null, false);
  const textNodes = [];
  let node;
  while ((node = walker.nextNode())) {
    if (node.parentElement && !['SCRIPT', 'STYLE', 'CODE', 'PRE', 'TEXTAREA'].includes(node.parentElement.tagName)) {
      if (/(\$\$|\$|\\[a-zA-Z]+|\\[()\[\]])/.test(node.nodeValue)) {
        textNodes.push(node);
      }
    }
  }

  textNodes.forEach(tNode => {
    let val = tNode.nodeValue;
    // Replace LaTeX fraction: \frac{a}{b} -> (a / b)
    val = val.replace(/\\frac\s*\{([^{}]+)\}\s*\{([^{}]+)\}/g, '($1 / $2)');
    // Replace \sqrt{x} -> √(x)
    val = val.replace(/\\sqrt\s*\{([^{}]+)\}/g, '√($1)');
    // Replace \text{x} -> x
    val = val.replace(/\\text\s*\{([^{}]+)\}/g, '$1');
    // Replace \mathbf{x} -> x
    val = val.replace(/\\mathbf\s*\{([^{}]+)\}/g, '$1');

    for (const [pattern, sym] of Object.entries(symbolMap)) {
      val = val.replace(new RegExp(pattern, 'g'), sym);
    }
    // Clean up remaining math delimiters
    val = val.replace(/\$\$(.*?)\$\$/g, ' $1 ');
    val = val.replace(/\$([^$]+)\$/g, ' $1 ');
    val = val.replace(/\\([a-zA-Z]+)/g, '$1');
    tNode.nodeValue = val;
  });
}

function formatStatus(status) {
  if (!status) return 'In Progress';
  return status.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}
