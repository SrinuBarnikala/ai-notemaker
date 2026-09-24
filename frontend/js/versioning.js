/* versioning.js — Phase 13: Note Versioning, Historical Snapshots, Semantic Diff & Restore */

let activeNoteVersions = [];
let currentDiffData = null;
let viewingHistoricalVersionNum = null;
let activeModalTab = 'timeline';

async function openVersionHistoryModal(defaultTab = 'timeline') {
  if (!currentNote || !currentNote.id) {
    alert('Please open or generate a living technical note first.');
    return;
  }

  const modal = document.getElementById('version-history-modal');
  if (!modal) return;

  modal.style.display = 'flex';
  document.body.style.overflow = 'hidden';

  switchVersionModalTab(defaultTab);
  await refreshNoteVersionsList();
}

function closeVersionHistoryModal() {
  const modal = document.getElementById('version-history-modal');
  if (modal) {
    modal.style.display = 'none';
  }
  document.body.style.overflow = '';
}

function switchVersionModalTab(tabName) {
  activeModalTab = tabName;
  const tabTimelineBtn = document.getElementById('btn-vtab-timeline');
  const tabDiffBtn = document.getElementById('btn-vtab-diff');
  const viewTimeline = document.getElementById('version-timeline-view');
  const viewDiff = document.getElementById('version-diff-view');

  if (tabTimelineBtn) tabTimelineBtn.classList.toggle('active', tabName === 'timeline');
  if (tabDiffBtn) tabDiffBtn.classList.toggle('active', tabName === 'diff');

  if (viewTimeline) viewTimeline.style.display = (tabName === 'timeline') ? 'block' : 'none';
  if (viewDiff) viewDiff.style.display = (tabName === 'diff') ? 'block' : 'none';

  if (tabName === 'diff' && (!currentDiffData || currentDiffData.note_id !== currentNote.id)) {
    triggerDefaultDiffComparison();
  }
}

async function refreshNoteVersionsList() {
  const timelineContainer = document.getElementById('version-timeline-container');
  const countPill = document.getElementById('version-count-pill');
  if (timelineContainer) {
    timelineContainer.innerHTML = '<div style="padding: 2rem; text-align: center; color: var(--text-muted);">Loading version history & snapshots...</div>';
  }

  try {
    const data = await API.listVersions(currentNote.id);
    activeNoteVersions = data.versions || [];

    if (countPill) {
      countPill.textContent = data.total_versions;
    }

    populateDiffDropdowns(activeNoteVersions);
    renderVersionsTimeline(activeNoteVersions, data.current_version);
  } catch (err) {
    console.error('Failed to load note versions:', err);
    if (timelineContainer) {
      timelineContainer.innerHTML = `<div style="padding: 2rem; text-align: center; color: #f87171;">⚠️ Error loading versions: ${escapeHtml(err.message)}</div>`;
    }
  }
}

function populateDiffDropdowns(versions) {
  const fromSelect = document.getElementById('diff-from-version');
  const toSelect = document.getElementById('diff-to-version');
  if (!fromSelect || !toSelect) return;

  const currentVer = currentNote.version;
  const prevVer = Math.max(1, currentVer - 1);

  fromSelect.innerHTML = versions.map(v => `
    <option value="${v.version}" ${v.version === prevVer ? 'selected' : ''}>
      v${v.version} — ${v.evolution_type} (${formatDateShort(v.created_at)})
    </option>
  `).join('');

  toSelect.innerHTML = versions.map(v => `
    <option value="${v.version}" ${v.version === currentVer ? 'selected' : ''}>
      v${v.version} ${v.is_current ? '(Current)' : ''} — ${v.evolution_type}
    </option>
  `).join('');
}

function renderVersionsTimeline(versions, currentVersion) {
  const container = document.getElementById('version-timeline-container');
  if (!container) return;

  if (!versions || versions.length === 0) {
    container.innerHTML = '<div style="padding: 2rem; text-align: center; color: var(--text-muted);">No version records found.</div>';
    return;
  }

  // Display newest first (descending)
  const sorted = [...versions].sort((a, b) => b.version - a.version);

  container.innerHTML = sorted.map(v => {
    const isCurrent = v.version === currentVersion;
    const isInitial = v.version === 1;
    const badgeTypeClass = getEvolutionBadgeClass(v.evolution_type);

    return `
      <div class="version-timeline-card ${isCurrent ? 'is-current' : ''}">
        <div class="vcard-header">
          <div class="vcard-title-group">
            <span class="vcard-num-badge ${isCurrent ? 'badge-current' : ''}">v${v.version}</span>
            <span class="vcard-type-badge ${badgeTypeClass}">${formatEvolutionType(v.evolution_type)}</span>
            ${isCurrent ? '<span class="vcard-current-tag">ACTIVE LIVING NOTE</span>' : ''}
          </div>
          <div class="vcard-meta">
            <span class="vcard-date">${formatDateTime(v.created_at)}</span>
            <span class="vcard-sections-count">📚 ${v.total_sections} Sections</span>
          </div>
        </div>

        <div class="vcard-body">
          <div class="vcard-summary">${escapeHtml(v.change_summary || v.user_prompt || 'Living note snapshot.')}</div>
          ${v.section_title ? `<div class="vcard-target-section">🎯 Affected Section: <strong>${escapeHtml(v.section_title)}</strong></div>` : ''}
          ${v.user_prompt && !isInitial ? `<div class="vcard-prompt-quote">“${escapeHtml(v.user_prompt)}”</div>` : ''}
        </div>

        <div class="vcard-actions">
          <button type="button" class="tool-btn" onclick="viewHistoricalSnapshot(${v.version})" title="Read note as it existed at version ${v.version}">
            <span>👁️ Read Snapshot</span>
          </button>
          ${!isInitial ? `
            <button type="button" class="tool-btn" onclick="openDiffBetween(${Math.max(1, v.version - 1)}, ${v.version})" title="Compare what changed from v${v.version - 1} to v${v.version}">
              <span>🔀 Inspect Diff vs v${v.version - 1}</span>
            </button>
          ` : `
            <button type="button" class="tool-btn" onclick="openDiffBetween(1, ${currentVersion})" title="Compare Initial v1 against Latest">
              <span>🔀 Compare vs Latest</span>
            </button>
          `}
          ${!isCurrent ? `
            <button type="button" class="tool-btn vbtn-restore" onclick="triggerRestoreVersion(${v.version})" title="Restore living note to this historical version">
              <span>↺ Restore v${v.version}</span>
            </button>
          ` : ''}
        </div>
      </div>
    `;
  }).join('');
}

function getEvolutionBadgeClass(type) {
  switch (type) {
    case 'initial_generation': return 'badge-initial';
    case 'add_code': return 'badge-code';
    case 'expand_section': return 'badge-expand';
    case 'add_section': return 'badge-add';
    case 'clarify': return 'badge-clarify';
    case 'copilot_pin': return 'badge-copilot';
    case 'restore_version': return 'badge-restore';
    default: return 'badge-default';
  }
}

function formatEvolutionType(type) {
  switch (type) {
    case 'initial_generation': return '🌱 Initial Blueprint';
    case 'add_code': return '💻 Code Enhancement';
    case 'expand_section': return '🔍 Deep Dive Expansion';
    case 'add_section': return '➕ New Chapter';
    case 'clarify': return '💡 Conceptual Clarification';
    case 'copilot_pin': return '🤖 Copilot Pin';
    case 'restore_version': return '↺ Version Rollback';
    default: return type ? type.replace('_', ' ') : 'Update';
  }
}

function formatDateShort(isoStr) {
  if (!isoStr) return '';
  const d = new Date(isoStr);
  return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
}

function formatDateTime(isoStr) {
  if (!isoStr) return '';
  const d = new Date(isoStr);
  return d.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function triggerDefaultDiffComparison() {
  const currentVer = currentNote ? currentNote.version : 1;
  const prevVer = Math.max(1, currentVer - 1);
  executeDiffComparison(prevVer, currentVer);
}

function openDiffBetween(fromVer, toVer) {
  switchVersionModalTab('diff');
  const fromSelect = document.getElementById('diff-from-version');
  const toSelect = document.getElementById('diff-to-version');
  if (fromSelect) fromSelect.value = fromVer;
  if (toSelect) toSelect.value = toVer;
  executeDiffComparison(fromVer, toVer);
}

async function handleRunDiffClick() {
  const fromVer = parseInt(document.getElementById('diff-from-version').value, 10);
  const toVer = parseInt(document.getElementById('diff-to-version').value, 10);

  if (isNaN(fromVer) || isNaN(toVer)) {
    alert('Please select valid versions to compare.');
    return;
  }
  await executeDiffComparison(fromVer, toVer);
}

async function executeDiffComparison(fromVer, toVer) {
  const container = document.getElementById('version-diff-container');
  const summaryBox = document.getElementById('diff-summary-banner');
  const statsBox = document.getElementById('diff-stats-bar');

  if (container) {
    container.innerHTML = '<div style="padding: 3rem; text-align: center; color: var(--text-muted);">⚡ Analyzing semantic differences between Version ' + fromVer + ' and Version ' + toVer + '...</div>';
  }

  try {
    const diffData = await API.getDiff(currentNote.id, fromVer, toVer);
    currentDiffData = diffData;

    renderDiffView(diffData);
  } catch (err) {
    console.error('Failed to compute diff:', err);
    if (container) {
      container.innerHTML = `<div style="padding: 2rem; text-align: center; color: #f87171;">⚠️ Failed to compute diff: ${escapeHtml(err.message)}</div>`;
    }
  }
}

function renderDiffView(diff) {
  const container = document.getElementById('version-diff-container');
  const summaryBox = document.getElementById('diff-summary-banner');
  const statsBox = document.getElementById('diff-stats-bar');

  if (summaryBox) {
    summaryBox.innerHTML = `
      <div class="diff-summary-title">🔀 Comparing Version ${diff.from_version} &rarr; Version ${diff.to_version}</div>
      <div class="diff-summary-text">${escapeHtml(diff.summary)}</div>
    `;
  }

  if (statsBox) {
    const s = diff.stats;
    statsBox.innerHTML = `
      <div class="diff-stat-item stat-added"><span class="stat-num">+${s.sections_added}</span><span>Sections Added</span></div>
      <div class="diff-stat-item stat-modified"><span class="stat-num">~${s.sections_modified}</span><span>Sections Modified</span></div>
      <div class="diff-stat-item stat-removed"><span class="stat-num">-${s.sections_removed}</span><span>Sections Removed</span></div>
      <div class="diff-stat-item stat-blocks-added"><span class="stat-num">+${s.blocks_added}</span><span>Blocks Added</span></div>
      <div class="diff-stat-item stat-blocks-mod"><span class="stat-num">~${s.blocks_modified}</span><span>Blocks Updated</span></div>
    `;
  }

  if (!container) return;

  if (!diff.sections || diff.sections.length === 0) {
    container.innerHTML = '<div style="padding: 2rem; text-align: center; color: var(--text-muted);">No section differences found.</div>';
    return;
  }

  container.innerHTML = diff.sections.map(sec => {
    const statusClass = `diff-sec-${sec.status}`;
    const badgeLabel = sec.status.toUpperCase();

    // Block diffs
    const blockListHtml = (sec.block_diffs || []).map(b => {
      const bStatusClass = `diff-block-${b.status}`;
      const sign = b.status === 'added' ? '+' : (b.status === 'removed' ? '−' : (b.status === 'modified' ? '~' : ' '));

      return `
        <div class="diff-block-row ${bStatusClass}">
          <div class="diff-block-indicator">${sign}</div>
          <div class="diff-block-content-wrap">
            <div class="diff-block-type-pill">${b.type}</div>
            ${b.status === 'modified' ? `
              <div class="diff-split-view">
                <div class="diff-side diff-old">
                  <div class="diff-side-label">v${diff.from_version} (Before):</div>
                  <pre class="diff-pre">${escapeHtml(b.old_content || 'None')}</pre>
                </div>
                <div class="diff-side diff-new">
                  <div class="diff-side-label">v${diff.to_version} (After):</div>
                  <pre class="diff-pre">${escapeHtml(b.new_content || 'None')}</pre>
                </div>
              </div>
            ` : `
              <pre class="diff-pre ${b.status === 'removed' ? 'diff-strikethrough' : ''}">${escapeHtml(b.new_content || b.old_content || '')}</pre>
            `}
          </div>
        </div>
      `;
    }).join('');

    return `
      <div class="diff-section-card ${statusClass}">
        <div class="diff-sec-header">
          <div class="diff-sec-title-wrap">
            <span class="diff-status-pill status-${sec.status}">${badgeLabel}</span>
            <h4 class="diff-sec-title">${escapeHtml(sec.title)}</h4>
          </div>
          <span class="diff-sec-type-tag">${sec.new_section_type || sec.old_section_type || 'concept'} &bull; ${sec.new_depth || sec.old_depth || 'standard'}</span>
        </div>
        <div class="diff-sec-body">
          ${blockListHtml}
        </div>
      </div>
    `;
  }).join('');
}

async function viewHistoricalSnapshot(versionNumber) {
  closeVersionHistoryModal();

  try {
    const historicalNote = await API.getVersion(currentNote.id, versionNumber);
    viewingHistoricalVersionNum = versionNumber;

    // Render the historical note in reader
    renderNote(historicalNote);

    // Show sticky Historical Version Banner
    showHistoricalVersionBanner(versionNumber, currentNote.version);
  } catch (err) {
    alert(`Failed to load historical snapshot: ${err.message}`);
  }
}

function showHistoricalVersionBanner(viewingVer, latestVer) {
  const banner = document.getElementById('historical-version-banner');
  if (!banner) return;

  const title = document.getElementById('historical-banner-title');
  const sub = document.getElementById('historical-banner-sub');
  const latestSpan = document.getElementById('banner-latest-ver');

  if (title) title.textContent = `Viewing Historical Snapshot: Version ${viewingVer}`;
  if (sub) sub.textContent = `This is a read-only historical checkpoint. The active note is Version ${latestVer}.`;
  if (latestSpan) latestSpan.textContent = latestVer;

  banner.style.display = 'flex';
  banner.scrollIntoView({ behavior: 'smooth' });
}

function hideHistoricalVersionBanner() {
  const banner = document.getElementById('historical-version-banner');
  if (banner) {
    banner.style.display = 'none';
  }
  viewingHistoricalVersionNum = null;
}

async function returnToLatestVersion() {
  if (!currentNote || !currentNote.id) return;
  hideHistoricalVersionBanner();

  try {
    const latest = await API.getNoteById(currentNote.id);
    renderNote(latest);
  } catch (err) {
    alert(`Failed to return to latest version: ${err.message}`);
  }
}

async function triggerRestoreVersion(versionToRestore) {
  const targetVer = versionToRestore || viewingHistoricalVersionNum;
  if (!targetVer) return;

  const confirmed = confirm(`Are you sure you want to restore Version ${targetVer}?
This will restore all sections and blocks back to Version ${targetVer} and create a new Version checkpoint (Version ${currentNote.version + 1}).`);

  if (!confirmed) return;

  try {
    const res = await API.restoreVersion(currentNote.id, targetVer);
    closeVersionHistoryModal();
    hideHistoricalVersionBanner();

    renderNote(res.note);
    await refreshNoteVersionsList();

    alert(`✓ ${res.message}`);
  } catch (err) {
    alert(`Restore failed: ${err.message}`);
  }
}
