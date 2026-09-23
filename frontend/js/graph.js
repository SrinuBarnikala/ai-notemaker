/* graph.js — Agent 10 Interactive Concept Knowledge Graph, Deterministic Static Map & Learning Engine */

let graphData = null;
let rawGlobalGraphData = null;
let globalAdjacency = { inMap: new Map(), outMap: new Map(), nodeMap: new Map(), journeyMap: new Map() };

let graphNodes = [];
let graphEdges = [];
let graphCanvas = null;
let graphCtx = null;

let graphCamera = { x: 0, y: 0, zoom: 1.0 };
let targetCamera = null;
let cameraTransitionId = null;
let renderPending = false;

let isDraggingNode = null;
let dragOffset = { x: 0, y: 0 };
let isPanning = false;
let panStart = { x: 0, y: 0 };
let hoveredNode = null;
let selectedNode = null;
let activeFilter = 'all';
let searchQuery = '';
let isGlobalMode = false;
let activeExploreCenterId = null;

// Learning Navigation & Scope State
let neighborhoodScope = 'neighbor'; // 'neighbor' (1-hop focus) or 'all' (full network / domain overview)
let isLearningPathMode = false;
let learningPathNodes = new Set();
let learningPathEdges = new Set();

// Fullscreen Workspace State
let isGraphFullscreen = false;
let graphResizeObserver = null;

const COLOR_MAP = {
  known: { fill: '#059669', stroke: '#34d399', glow: 'rgba(52, 211, 153, 0.45)', text: '#a7f3d0' },
  partial: { fill: '#d97706', stroke: '#fbbf24', glow: 'rgba(251, 191, 36, 0.45)', text: '#fde68a' },
  gap: { fill: '#7c3aed', stroke: '#c084fc', glow: 'rgba(192, 132, 252, 0.45)', text: '#e9d5ff' },
  misconception: { fill: '#dc2626', stroke: '#f87171', glow: 'rgba(248, 113, 113, 0.55)', text: '#fecaca' },
  topic: { fill: '#4338ca', stroke: '#818cf8', glow: 'rgba(129, 140, 248, 0.5)', text: '#e0e7ff' },
  journey: { fill: '#4338ca', stroke: '#818cf8', glow: 'rgba(129, 140, 248, 0.5)', text: '#e0e7ff' }
};

// Relation Typography & Styling Tokens
const RELATION_STYLES = {
  prerequisite: { stroke: '#38bdf8', width: 2.2, dash: [], arrow: '#38bdf8', label: 'prerequisite' },
  subconcept: { stroke: '#a855f7', width: 1.8, dash: [6, 4], arrow: '#a855f7', label: 'subconcept' },
  implements: { stroke: '#34d399', width: 2.2, dash: [], arrow: '#34d399', label: 'implements' },
  compares_to: { stroke: '#f87171', width: 1.8, dash: [3, 3], arrow: '#f87171', label: 'compares to' },
  relates_to: { stroke: 'rgba(148, 163, 184, 0.4)', width: 1.2, dash: [], arrow: 'rgba(148, 163, 184, 0.6)', label: 'relates to' }
};

// --------------------------------------------------------------------------
// On-Demand Render Scheduler (No continuous animation loop when idle)
// --------------------------------------------------------------------------

function requestRender() {
  if (!renderPending) {
    renderPending = true;
    requestAnimationFrame(() => {
      renderPending = false;
      renderGraph();
    });
  }
}

// --------------------------------------------------------------------------
// Lifecycle & Graph Loading
// --------------------------------------------------------------------------

function openGraphModal(asGlobal = false) {
  isGlobalMode = asGlobal;
  const modal = document.getElementById('graph-modal');
  if (!modal) return;

  modal.style.display = 'flex';
  document.body.style.overflow = 'hidden';

  const titleEl = document.getElementById('graph-modal-title');
  if (titleEl) {
    titleEl.textContent = isGlobalMode 
      ? '🌐 Explore Knowledge: Multi-Journey Topology' 
      : (currentTopic ? `🕸️ Concept Dependency Graph: ${currentTopic}` : '🕸️ Concept Dependency Graph');
  }

  const globalToggleBtn = document.getElementById('btn-graph-mode-global');
  const journeyToggleBtn = document.getElementById('btn-graph-mode-journey');
  if (globalToggleBtn && journeyToggleBtn) {
    globalToggleBtn.classList.toggle('active', isGlobalMode);
    journeyToggleBtn.classList.toggle('active', !isGlobalMode);
  }

  // Default to 1-Hop Focus
  selectedNode = null;
  activeExploreCenterId = null;
  exitLearningPathMode();
  setNeighborhoodScope('neighbor');
  closeConceptInspector();

  loadGraphData();
}

function closeGraphModal() {
  const modal = document.getElementById('graph-modal');
  if (modal) modal.style.display = 'none';
  document.body.style.overflow = '';

  if (cameraTransitionId) {
    cancelAnimationFrame(cameraTransitionId);
    cameraTransitionId = null;
  }
  targetCamera = null;

  if (isGraphFullscreen) {
    isGraphFullscreen = false;
    applyGraphFullscreenState();
  }
  closeConceptInspector();
  exitLearningPathMode();

  const dropdown = document.getElementById('graph-search-dropdown');
  if (dropdown) dropdown.style.display = 'none';
}

function switchGraphMode(mode) {
  isGlobalMode = (mode === 'global');
  const globalToggleBtn = document.getElementById('btn-graph-mode-global');
  const journeyToggleBtn = document.getElementById('btn-graph-mode-journey');
  if (globalToggleBtn && journeyToggleBtn) {
    globalToggleBtn.classList.toggle('active', isGlobalMode);
    journeyToggleBtn.classList.toggle('active', !isGlobalMode);
  }

  const titleEl = document.getElementById('graph-modal-title');
  if (titleEl) {
    titleEl.textContent = isGlobalMode 
      ? '🌐 Explore Knowledge: Multi-Journey Topology' 
      : (currentTopic ? `🕸️ Concept Dependency Graph: ${currentTopic}` : '🕸️ Concept Dependency Graph');
  }

  selectedNode = null;
  activeExploreCenterId = null;
  closeConceptInspector();
  exitLearningPathMode();
  loadGraphData();
}

async function loadGraphData() {
  const loading = document.getElementById('graph-loading');
  if (loading) loading.style.display = 'flex';

  try {
    const url = isGlobalMode 
      ? '/graph/global' 
      : (currentJourneyId ? `/journeys/${currentJourneyId}/graph` : '/graph/global');

    let payload = null;
    if (isGlobalMode && rawGlobalGraphData) {
      payload = rawGlobalGraphData;
    } else {
      const res = await fetch(url);
      if (!res.ok) throw new Error('Failed to load concept graph.');
      payload = await res.json();
    }

    if (isGlobalMode) {
      rawGlobalGraphData = payload;
      buildGlobalAdjacencyIndex(rawGlobalGraphData);

      const exploreHud = document.getElementById('graph-explore-hud');
      if (exploreHud) exploreHud.style.display = 'flex';

      initGraphCanvas();

      let initialFocusId = null;
      if (currentTopic && rawGlobalGraphData.nodes) {
        const match = rawGlobalGraphData.nodes.find(n => 
          n.name.toLowerCase() === currentTopic.toLowerCase() || 
          (n.journey_topic && n.journey_topic.toLowerCase() === currentTopic.toLowerCase())
        );
        if (match) initialFocusId = match.id;
      }

      if (initialFocusId) {
        extractFocusedSubgraph(initialFocusId);
      } else {
        generateClusterOverview();
      }
    } else {
      rawGlobalGraphData = null;
      const exploreHud = document.getElementById('graph-explore-hud');
      const subgraphPill = document.getElementById('graph-subgraph-hud');
      if (exploreHud) exploreHud.style.display = 'none';
      if (subgraphPill) subgraphPill.style.display = 'none';

      graphData = payload;
      initGraphCanvas();
      populateGraphUI(graphData);
    }
  } catch (err) {
    alert('Knowledge Graph error: ' + err.message);
  } finally {
    if (loading) loading.style.display = 'none';
  }
}

// --------------------------------------------------------------------------
// Global Adjacency Index & Subgraph Extraction (Explore Knowledge Engine)
// --------------------------------------------------------------------------

function buildGlobalAdjacencyIndex(data) {
  globalAdjacency = {
    inMap: new Map(),
    outMap: new Map(),
    nodeMap: new Map(),
    journeyMap: new Map()
  };

  const nodes = data.nodes || [];
  for (const n of nodes) {
    globalAdjacency.nodeMap.set(n.id, n);
    if (n.journey_id) {
      if (!globalAdjacency.journeyMap.has(n.journey_id)) {
        globalAdjacency.journeyMap.set(n.journey_id, []);
      }
      globalAdjacency.journeyMap.get(n.journey_id).push(n);
    }
  }

  const edges = data.edges || [];
  for (const e of edges) {
    if (!globalAdjacency.outMap.has(e.source)) {
      globalAdjacency.outMap.set(e.source, []);
    }
    globalAdjacency.outMap.get(e.source).push(e);

    if (!globalAdjacency.inMap.has(e.target)) {
      globalAdjacency.inMap.set(e.target, []);
    }
    globalAdjacency.inMap.get(e.target).push(e);
  }
}

function extractFocusedSubgraph(centerId, maxNodes = 36) {
  if (!rawGlobalGraphData || !globalAdjacency.nodeMap.has(centerId)) return;

  const centerNode = globalAdjacency.nodeMap.get(centerId);
  activeExploreCenterId = centerId;

  const collectedNodeIds = new Set();
  const collectedEdges = [];
  const seenEdgeKeys = new Set();

  collectedNodeIds.add(centerId);

  // 1. Direct incoming prerequisites (Hop 1)
  const inEdges = globalAdjacency.inMap.get(centerId) || [];
  for (const e of inEdges) {
    if (collectedNodeIds.size < maxNodes) {
      collectedNodeIds.add(e.source);
      const edgeKey = `${e.source}->${e.target}`;
      if (!seenEdgeKeys.has(edgeKey)) {
        seenEdgeKeys.add(edgeKey);
        collectedEdges.push(e);
      }
    }
  }

  // 2. Direct outgoing unlocks & subconcepts (Hop 1)
  const outEdges = globalAdjacency.outMap.get(centerId) || [];
  for (const e of outEdges) {
    if (collectedNodeIds.size < maxNodes) {
      collectedNodeIds.add(e.target);
      const edgeKey = `${e.source}->${e.target}`;
      if (!seenEdgeKeys.has(edgeKey)) {
        seenEdgeKeys.add(edgeKey);
        collectedEdges.push(e);
      }
    }
  }

  // 3. Connect to associated journey anchor node
  if (centerNode.journey_id) {
    for (const n of rawGlobalGraphData.nodes) {
      if (n.group === 'journey' && n.journey_id === centerNode.journey_id) {
        collectedNodeIds.add(n.id);
        break;
      }
    }
  }

  // 4. Hop 2: prerequisites of direct prerequisites if budget allows
  if (collectedNodeIds.size < maxNodes - 6) {
    const hop1Ids = Array.from(collectedNodeIds);
    for (const h1 of hop1Ids) {
      if (h1 === centerId) continue;
      const h2In = globalAdjacency.inMap.get(h1) || [];
      for (const e of h2In) {
        if (collectedNodeIds.size >= maxNodes) break;
        if (e.relationship === 'prerequisite') {
          collectedNodeIds.add(e.source);
          const edgeKey = `${e.source}->${e.target}`;
          if (!seenEdgeKeys.has(edgeKey)) {
            seenEdgeKeys.add(edgeKey);
            collectedEdges.push(e);
          }
        }
      }
      if (collectedNodeIds.size >= maxNodes) break;
    }
  }

  // Collect internal edges between all nodes in subgraph
  for (const nId of collectedNodeIds) {
    const out = globalAdjacency.outMap.get(nId) || [];
    for (const e of out) {
      if (collectedNodeIds.has(e.target)) {
        const edgeKey = `${e.source}->${e.target}`;
        if (!seenEdgeKeys.has(edgeKey)) {
          seenEdgeKeys.add(edgeKey);
          collectedEdges.push(e);
        }
      }
    }
  }

  const subNodes = Array.from(collectedNodeIds)
    .map(id => globalAdjacency.nodeMap.get(id))
    .filter(Boolean);

  graphNodes = subNodes.map(n => ({
    ...n,
    x: 0,
    y: 0,
    radius: n.size || 20
  }));

  const nodeMap = new Map(graphNodes.map(n => [n.id, n]));
  graphEdges = collectedEdges
    .map(e => ({
      ...e,
      sourceNode: nodeMap.get(e.source),
      targetNode: nodeMap.get(e.target)
    }))
    .filter(e => e.sourceNode && e.targetNode);

  const rect = graphCanvas ? graphCanvas.parentElement.getBoundingClientRect() : { width: 900, height: 600 };
  applyDeterministicLayout(graphNodes, graphEdges, rect.width, rect.height);

  // Update HUDs
  const exploreText = document.getElementById('graph-explore-text');
  const resetHubBtn = document.getElementById('btn-explore-reset-hub');
  const subgraphPill = document.getElementById('graph-subgraph-hud');

  if (exploreText) {
    exploreText.textContent = `Viewing Subgraph for "${centerNode.name}" (${graphNodes.length} nodes, ${graphEdges.length} connections across journeys)`;
  }
  if (resetHubBtn) resetHubBtn.style.display = 'inline-block';
  if (subgraphPill) {
    subgraphPill.style.display = 'inline-block';
    subgraphPill.textContent = `🎯 Subgraph: ${centerNode.name.substring(0, 16)}${centerNode.name.length > 16 ? '...' : ''}`;
  }

  const nodeInGraph = graphNodes.find(n => n.id === centerId);
  if (nodeInGraph) {
    selectConceptNode(nodeInGraph);
  }

  smoothCenterOnNode(nodeInGraph);
  populateGraphUI({
    total_nodes: graphNodes.length,
    mastery_breakdown: calculateBreakdown(graphNodes),
    summary: `Focused 1-2 hop subgraph around "${centerNode.name}".`
  });

  requestRender();
}

function generateClusterOverview() {
  if (!rawGlobalGraphData) return;

  const rect = graphCanvas ? graphCanvas.parentElement.getBoundingClientRect() : { width: 900, height: 600 };
  const journeyNodes = rawGlobalGraphData.nodes.filter(n => n.group === 'journey');
  const overviewNodes = journeyNodes.slice(0, 24);
  const overviewNodeIds = new Set(overviewNodes.map(n => n.id));

  const overviewEdges = (rawGlobalGraphData.edges || [])
    .filter(e => overviewNodeIds.has(e.source) && overviewNodeIds.has(e.target))
    .slice(0, 48);

  graphNodes = overviewNodes.map(n => ({
    ...n,
    x: 0,
    y: 0,
    radius: 28
  }));

  const nodeMap = new Map(graphNodes.map(n => [n.id, n]));
  graphEdges = overviewEdges
    .map(e => ({
      ...e,
      sourceNode: nodeMap.get(e.source),
      targetNode: nodeMap.get(e.target)
    }))
    .filter(e => e.sourceNode && e.targetNode);

  applyDeterministicLayout(graphNodes, graphEdges, rect.width, rect.height);

  const exploreText = document.getElementById('graph-explore-text');
  const resetHubBtn = document.getElementById('btn-explore-reset-hub');
  const subgraphPill = document.getElementById('graph-subgraph-hud');

  if (exploreText) {
    exploreText.textContent = `Domain Constellation Overview (${rawGlobalGraphData.total_nodes} concepts across journeys). Click any domain or search to explore.`;
  }
  if (resetHubBtn) resetHubBtn.style.display = 'none';
  if (subgraphPill) subgraphPill.style.display = 'none';

  selectedNode = null;
  activeExploreCenterId = null;
  closeConceptInspector();

  populateGraphUI({
    total_nodes: rawGlobalGraphData.total_nodes,
    mastery_breakdown: rawGlobalGraphData.mastery_breakdown,
    summary: `Global Knowledge Universe (${rawGlobalGraphData.total_nodes} concepts). Search or click to explore.`
  });

  requestRender();
}

function resetExploreOverview() {
  if (isGlobalMode && rawGlobalGraphData) {
    generateClusterOverview();
  }
}

function calculateBreakdown(nodes) {
  const bk = { known: 0, partial: 0, gap: 0, misconception: 0 };
  for (const n of nodes) {
    if (bk[n.status] !== undefined) bk[n.status]++;
  }
  return bk;
}

// --------------------------------------------------------------------------
// Deterministic Static Layout Engine (No Wobbling, No Floating, Fixed Coordinates)
// --------------------------------------------------------------------------

function applyDeterministicLayout(nodes, edges, w, h) {
  if (!nodes || nodes.length === 0) return;

  const cx = w / 2;
  const cy = h / 2;

  if (nodes.length === 1) {
    nodes[0].x = cx;
    nodes[0].y = cy;
    return;
  }

  // 1. Ego-subgraph centered on focused concept in Explore Knowledge mode
  if (isGlobalMode && activeExploreCenterId) {
    layoutEgoSubgraph(nodes, edges, activeExploreCenterId, cx, cy);
    return;
  }

  // 2. Clustered Domain Overview
  if (isGlobalMode) {
    layoutDomainOverview(nodes, cx, cy);
    return;
  }

  // 3. Hierarchical / Layered Flow for Active Note Graph
  layoutHierarchical(nodes, edges, cx, cy, w, h);
}

function layoutHierarchical(nodes, edges, cx, cy, w, h) {
  const nodeMap = new Map(nodes.map(n => [n.id, n]));
  const inDegree = new Map(nodes.map(n => [n.id, 0]));
  const prereqParents = new Map(nodes.map(n => [n.id, []]));

  for (const e of edges) {
    if (e.relationship === 'prerequisite' || e.relationship === 'subconcept') {
      if (inDegree.has(e.targetNode.id)) {
        inDegree.set(e.targetNode.id, inDegree.get(e.targetNode.id) + 1);
        prereqParents.get(e.targetNode.id).push(e.sourceNode.id);
      }
    }
  }

  // Assign layers deterministically
  const layerMap = new Map();
  const layers = [];

  // Layer 0: Topic Anchor Node (if present)
  const topicNode = nodes.find(n => n.group === 'topic' || n.group === 'journey');
  if (topicNode) {
    layerMap.set(topicNode.id, 0);
  }

  // Layer 1: Foundational root concepts (0 incoming prerequisites)
  const layer1 = nodes.filter(n => n !== topicNode && (inDegree.get(n.id) === 0 || n.status === 'known'));
  layer1.forEach(n => layerMap.set(n.id, 1));

  // Layer 2: Intermediate mechanisms & partial concepts
  const layer2 = nodes.filter(n => !layerMap.has(n.id) && (n.status === 'partial' || inDegree.get(n.id) === 1));
  layer2.forEach(n => layerMap.set(n.id, 2));

  // Layer 3: Advanced, gaps, and pitfalls
  const layer3 = nodes.filter(n => !layerMap.has(n.id));
  layer3.forEach(n => layerMap.set(n.id, 3));

  // Group into layers array
  const rawLayers = [[], [], [], []];
  if (topicNode) rawLayers[0].push(topicNode);
  layer1.forEach(n => rawLayers[1].push(n));
  layer2.forEach(n => rawLayers[2].push(n));
  layer3.forEach(n => rawLayers[3].push(n));

  const activeLayers = rawLayers.filter(l => l.length > 0);
  const totalLayers = activeLayers.length;
  const layerHeight = Math.min(180, Math.max(130, (h - 180) / Math.max(1, totalLayers - 1)));
  const startY = cy - ((totalLayers - 1) * layerHeight) / 2;

  activeLayers.forEach((layerNodes, lIdx) => {
    // Sort deterministically by name for consistent positioning
    layerNodes.sort((a, b) => a.name.localeCompare(b.name));
    const count = layerNodes.length;
    const spacing = Math.min(220, Math.max(140, (w - 200) / Math.max(1, count)));
    const startX = cx - ((count - 1) * spacing) / 2;
    const y = startY + lIdx * layerHeight;

    layerNodes.forEach((node, nIdx) => {
      node.x = startX + nIdx * spacing;
      node.y = y;
    });
  });
}

function layoutEgoSubgraph(nodes, edges, centerId, cx, cy) {
  const centerNode = nodes.find(n => n.id === centerId);
  if (centerNode) {
    centerNode.x = cx;
    centerNode.y = cy;
  }

  const prereqNodes = [];
  const unlockNodes = [];
  const contrastNodes = [];
  const otherNodes = [];

  for (const n of nodes) {
    if (n.id === centerId) continue;
    if (n.group === 'journey') {
      n.x = cx - 280;
      n.y = cy - 160;
      continue;
    }

    const isPrereq = edges.some(e => e.targetNode.id === centerId && e.sourceNode.id === n.id);
    const isUnlock = edges.some(e => e.sourceNode.id === centerId && e.targetNode.id === n.id);
    const isContrast = edges.some(e => (e.sourceNode.id === centerId && e.targetNode.id === n.id && e.relationship === 'compares_to') ||
                                       (e.targetNode.id === centerId && e.sourceNode.id === n.id && e.relationship === 'compares_to'));

    if (isPrereq) prereqNodes.push(n);
    else if (isUnlock) unlockNodes.push(n);
    else if (isContrast) contrastNodes.push(n);
    else otherNodes.push(n);
  }

  // Position Prerequisites above in clean arc / horizontal tier
  prereqNodes.sort((a, b) => a.name.localeCompare(b.name));
  const pCount = prereqNodes.length;
  const pSpacing = Math.min(180, Math.max(130, 600 / Math.max(1, pCount)));
  const pStartX = cx - ((pCount - 1) * pSpacing) / 2;
  prereqNodes.forEach((n, i) => {
    n.x = pStartX + i * pSpacing;
    n.y = cy - 160;
  });

  // Position Unlocks below in clean horizontal tier
  unlockNodes.sort((a, b) => a.name.localeCompare(b.name));
  const uCount = unlockNodes.length;
  const uSpacing = Math.min(180, Math.max(130, 600 / Math.max(1, uCount)));
  const uStartX = cx - ((uCount - 1) * uSpacing) / 2;
  unlockNodes.forEach((n, i) => {
    n.x = uStartX + i * uSpacing;
    n.y = cy + 160;
  });

  // Position Contrasting concepts horizontally to the sides
  contrastNodes.forEach((n, i) => {
    n.x = i % 2 === 0 ? cx - 260 : cx + 260;
    n.y = cy + (Math.floor(i / 2) * 80);
  });

  // Position other companion nodes in outer orbit
  otherNodes.forEach((n, i) => {
    const angle = (i / Math.max(1, otherNodes.length)) * Math.PI * 2;
    n.x = cx + Math.cos(angle) * 310;
    n.y = cy + Math.sin(angle) * 230;
  });
}

function layoutDomainOverview(nodes, cx, cy) {
  const count = nodes.length;
  nodes.sort((a, b) => a.name.localeCompare(b.name));

  nodes.forEach((n, i) => {
    // Two clean concentric orbits
    const isInner = i < 8;
    const r = isInner ? 170 : 290;
    const angle = isInner 
      ? (i / 8) * Math.PI * 2 - Math.PI / 2
      : ((i - 8) / Math.max(1, count - 8)) * Math.PI * 2 - Math.PI / 2;

    n.x = cx + Math.cos(angle) * r;
    n.y = cy + Math.sin(angle) * r;
  });
}

// --------------------------------------------------------------------------
// Canvas Setup & Event Binding
// --------------------------------------------------------------------------

function initGraphCanvas() {
  graphCanvas = document.getElementById('graph-canvas');
  if (!graphCanvas) return;

  const rect = graphCanvas.parentElement.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  const w = rect.width;
  const h = rect.height;

  graphCanvas.width = w * dpr;
  graphCanvas.height = h * dpr;
  graphCanvas.style.width = `${w}px`;
  graphCanvas.style.height = `${h}px`;

  graphCtx = graphCanvas.getContext('2d');
  graphCtx.scale(dpr, dpr);

  graphCamera = { x: 0, y: 0, zoom: 1.0 };
  targetCamera = null;

  if (!isGlobalMode && graphData) {
    const rawNodes = graphData.nodes || [];
    graphNodes = rawNodes.map(n => ({
      ...n,
      x: 0,
      y: 0,
      radius: n.size || 20
    }));

    const nodeMap = new Map(graphNodes.map(n => [n.id, n]));
    graphEdges = (graphData.edges || [])
      .map(e => ({
        ...e,
        sourceNode: nodeMap.get(e.source),
        targetNode: nodeMap.get(e.target)
      }))
      .filter(e => e.sourceNode && e.targetNode);

    applyDeterministicLayout(graphNodes, graphEdges, w, h);
  }

  bindCanvasEvents(graphCanvas, w, h);
  setupGraphResizeObserver();
  requestRender();
}

function populateGraphUI(data) {
  const bk = data.mastery_breakdown || {};
  const pillTotal = document.getElementById('gcount-total');
  const pillKnown = document.getElementById('gcount-known');
  const pillGaps = document.getElementById('gcount-gaps');
  const pillMisc = document.getElementById('gcount-misc');

  if (pillTotal) pillTotal.textContent = data.total_nodes || 0;
  if (pillKnown) pillKnown.textContent = bk.known || 0;
  if (pillGaps) pillGaps.textContent = bk.gap || 0;
  if (pillMisc) pillMisc.textContent = bk.misconception || 0;

  const summaryEl = document.getElementById('graph-summary-hud');
  if (summaryEl) {
    summaryEl.textContent = data.summary || '';
  }
}

function bindCanvasEvents(canvas, baseW, baseH) {
  canvas.onmousedown = (e) => {
    const mousePos = getCanvasMousePos(e, canvas);
    const worldPos = screenToWorld(mousePos.x, mousePos.y);

    const clicked = findNodeAt(worldPos.x, worldPos.y);
    if (clicked) {
      isDraggingNode = clicked;
      dragOffset = { x: clicked.x - worldPos.x, y: clicked.y - worldPos.y };
      targetCamera = null;
    } else {
      isPanning = true;
      panStart = { x: e.clientX, y: e.clientY };
      targetCamera = null;
    }
  };

  window.onmousemove = (e) => {
    if (!graphCanvas) return;
    const rect = graphCanvas.getBoundingClientRect();
    if (isDraggingNode) {
      const mouseX = e.clientX - rect.left;
      const mouseY = e.clientY - rect.top;
      const worldPos = screenToWorld(mouseX, mouseY);
      isDraggingNode.x = worldPos.x + dragOffset.x;
      isDraggingNode.y = worldPos.y + dragOffset.y;
      requestRender();
    } else if (isPanning) {
      const dx = e.clientX - panStart.x;
      const dy = e.clientY - panStart.y;
      graphCamera.x += dx;
      graphCamera.y += dy;
      panStart = { x: e.clientX, y: e.clientY };
      requestRender();
    } else {
      const mouseX = e.clientX - rect.left;
      const mouseY = e.clientY - rect.top;
      const worldPos = screenToWorld(mouseX, mouseY);
      const prevHovered = hoveredNode;
      hoveredNode = findNodeAt(worldPos.x, worldPos.y);
      updateGraphTooltip(hoveredNode, e.clientX, e.clientY);
      graphCanvas.style.cursor = hoveredNode ? 'pointer' : 'default';
      if (prevHovered !== hoveredNode) {
        requestRender();
      }
    }
  };

  window.onmouseup = () => {
    // Node remains stationary right where it was released
    isDraggingNode = null;
    isPanning = false;
  };

  canvas.onclick = (e) => {
    const mousePos = getCanvasMousePos(e, canvas);
    const worldPos = screenToWorld(mousePos.x, mousePos.y);
    const clicked = findNodeAt(worldPos.x, worldPos.y);
    if (clicked) {
      if (isGlobalMode) {
        if (clicked.group === 'journey') {
          extractFocusedSubgraph(clicked.id);
        } else if (clicked.id !== activeExploreCenterId) {
          extractFocusedSubgraph(clicked.id);
        } else {
          selectConceptNode(clicked);
        }
      } else {
        selectConceptNode(clicked);
      }
    }
  };

  canvas.onwheel = (e) => {
    e.preventDefault();
    const mousePos = getCanvasMousePos(e, canvas);
    const zoomFactor = e.deltaY < 0 ? 1.12 : 0.88;
    const newZoom = Math.max(0.25, Math.min(3.5, graphCamera.zoom * zoomFactor));

    graphCamera.x = mousePos.x - (mousePos.x - graphCamera.x) * (newZoom / graphCamera.zoom);
    graphCamera.y = mousePos.y - (mousePos.y - graphCamera.y) * (newZoom / graphCamera.zoom);
    graphCamera.zoom = newZoom;
    targetCamera = null;

    const zoomPill = document.getElementById('graph-zoom-pill');
    if (zoomPill) zoomPill.textContent = `${Math.round(graphCamera.zoom * 100)}%`;

    requestRender();
  };
}

function getCanvasMousePos(e, canvas) {
  const rect = canvas.getBoundingClientRect();
  return {
    x: e.clientX - rect.left,
    y: e.clientY - rect.top
  };
}

function screenToWorld(sx, sy) {
  return {
    x: (sx - graphCamera.x) / graphCamera.zoom,
    y: (sy - graphCamera.y) / graphCamera.zoom
  };
}

function worldToScreen(wx, wy) {
  return {
    x: wx * graphCamera.zoom + graphCamera.x,
    y: wy * graphCamera.zoom + graphCamera.y
  };
}

function findNodeAt(wx, wy) {
  for (let i = graphNodes.length - 1; i >= 0; i--) {
    const n = graphNodes[i];
    if (isNodeFiltered(n)) continue;
    const dx = wx - n.x;
    const dy = wy - n.y;
    if (dx * dx + dy * dy <= (n.radius + 6) * (n.radius + 6)) {
      return n;
    }
  }
  return null;
}

function isNodeFiltered(n) {
  if (activeFilter === 'gaps' && n.status !== 'gap') return true;
  if (activeFilter === 'known' && n.status !== 'known') return true;
  if (activeFilter === 'misc' && n.status !== 'misconception') return true;

  if (searchQuery && !isGlobalMode) {
    return !n.name.toLowerCase().includes(searchQuery.toLowerCase());
  }
  return false;
}

function isNodeInVisualScope(node) {
  if (isLearningPathMode && learningPathNodes.size > 0) {
    return learningPathNodes.has(node.id);
  }
  if (neighborhoodScope === 'neighbor' && selectedNode) {
    if (node.id === selectedNode.id) return true;
    return graphEdges.some(e => 
      (e.sourceNode.id === selectedNode.id && e.targetNode.id === node.id) ||
      (e.targetNode.id === selectedNode.id && e.sourceNode.id === node.id)
    );
  }
  return true;
}

function smoothCenterOnNode(node) {
  if (!graphCanvas || !node) return;
  const rect = graphCanvas.getBoundingClientRect();
  const w = rect.width;
  const h = rect.height;

  targetCamera = {
    x: (w / 2) - node.x * graphCamera.zoom,
    y: (h / 2) - node.y * graphCamera.zoom
  };

  startCameraTransition();
}

function startCameraTransition() {
  if (cameraTransitionId) return;

  function step() {
    if (targetCamera) {
      graphCamera.x += (targetCamera.x - graphCamera.x) * 0.22;
      graphCamera.y += (targetCamera.y - graphCamera.y) * 0.22;
      renderGraph();

      if (Math.abs(targetCamera.x - graphCamera.x) < 0.5 && Math.abs(targetCamera.y - graphCamera.y) < 0.5) {
        graphCamera.x = targetCamera.x;
        graphCamera.y = targetCamera.y;
        targetCamera = null;
        cameraTransitionId = null;
        renderGraph();
        return;
      }
      cameraTransitionId = requestAnimationFrame(step);
    } else {
      cameraTransitionId = null;
    }
  }

  cameraTransitionId = requestAnimationFrame(step);
}

// --------------------------------------------------------------------------
// Concept Inspector & Selection Management
// --------------------------------------------------------------------------

function selectConceptNode(node) {
  selectedNode = node;
  smoothCenterOnNode(node);

  const panel = document.getElementById('graph-inspector-panel');
  if (panel) panel.style.display = 'flex';

  const titleEl = document.getElementById('inspector-concept-title');
  if (titleEl) titleEl.textContent = node.name;

  const statusBadge = document.getElementById('inspector-status-badge');
  if (statusBadge) {
    statusBadge.textContent = node.status.toUpperCase();
    statusBadge.className = 'inspector-status-badge status-' + (node.status || 'known');
  }

  const groupPill = document.getElementById('inspector-group-pill');
  if (groupPill) {
    groupPill.textContent = (node.group || 'CONCEPT').toUpperCase();
  }

  const descEl = document.getElementById('inspector-concept-desc');
  if (descEl) {
    descEl.textContent = node.summary || `Core architectural concept relevant to ${node.journey_topic || currentTopic || 'the curriculum'}.`;
  }

  const secBlock = document.getElementById('inspector-section-block');
  const secNum = document.getElementById('inspector-sec-num');
  const secDepth = document.getElementById('inspector-sec-depth');
  const secTitle = document.getElementById('inspector-sec-title');

  if (node.section_title || node.section_id) {
    if (secBlock) secBlock.style.display = 'flex';
    if (secNum) {
      let order = '';
      if (currentNote && currentNote.sections) {
        const sMatch = currentNote.sections.find(s => s.id === node.section_id || s.title === node.section_title);
        if (sMatch) order = `Section ${sMatch.order_index}`;
      }
      secNum.textContent = order || 'Living Note Section';
    }
    if (secDepth) {
      secDepth.textContent = node.depth || 'standard';
      secDepth.className = `depth-badge depth-${node.depth || 'standard'}`;
    }
    if (secTitle) secTitle.textContent = node.section_title || node.name;
  } else {
    if (secBlock) secBlock.style.display = 'flex';
    if (secNum) secNum.textContent = node.journey_topic ? 'Domain Journey' : 'Topic Domain';
    if (secDepth) {
      secDepth.textContent = node.journey_topic ? 'cross-journey' : 'global';
      secDepth.className = 'depth-badge depth-standard';
    }
    if (secTitle) secTitle.textContent = node.journey_topic || currentTopic || 'Technical Curriculum';
  }

  const prereqEdges = graphEdges.filter(e => e.targetNode.id === node.id && (e.relationship === 'prerequisite' || e.relationship === 'subconcept'));
  const prereqList = document.getElementById('inspector-prereqs-list');
  const prereqCount = document.getElementById('inspector-prereq-count');

  if (prereqCount) prereqCount.textContent = prereqEdges.length;
  if (prereqList) {
    if (prereqEdges.length === 0) {
      prereqList.innerHTML = `<span style="font-size: 0.78rem; color: var(--text-muted);">None — Foundational root concept!</span>`;
    } else {
      prereqList.innerHTML = prereqEdges.map(e => {
        const p = e.sourceNode;
        const statusColor = COLOR_MAP[p.status]?.stroke || '#34d399';
        return `
          <div class="inspector-chip" onclick="inspectNodeById('${p.id}')" title="Inspect prerequisite: ${escapeHtml(p.name)}">
            <div style="display: flex; align-items: center; gap: 0.4rem; overflow: hidden;">
              <span style="width: 7px; height: 7px; border-radius: 50%; background: ${statusColor}; flex-shrink: 0;"></span>
              <span style="font-weight: 600; text-overflow: ellipsis; overflow: hidden; white-space: nowrap;">${escapeHtml(p.name)}</span>
            </div>
            <span class="chip-relation-tag">${escapeHtml(e.relationship)}</span>
          </div>
        `;
      }).join('');
    }
  }

  const unlockEdges = graphEdges.filter(e => e.sourceNode.id === node.id && (e.relationship === 'prerequisite' || e.relationship === 'subconcept'));
  const unlockList = document.getElementById('inspector-unlocks-list');
  const unlockCount = document.getElementById('inspector-unlock-count');

  if (unlockCount) unlockCount.textContent = unlockEdges.length;
  if (unlockList) {
    if (unlockEdges.length === 0) {
      unlockList.innerHTML = `<span style="font-size: 0.78rem; color: var(--text-muted);">Terminal concept or specialized leaf topic.</span>`;
    } else {
      unlockList.innerHTML = unlockEdges.map(e => {
        const u = e.targetNode;
        const statusColor = COLOR_MAP[u.status]?.stroke || '#c084fc';
        return `
          <div class="inspector-chip" onclick="inspectNodeById('${u.id}')" title="Inspect unlocked concept: ${escapeHtml(u.name)}">
            <div style="display: flex; align-items: center; gap: 0.4rem; overflow: hidden;">
              <span style="width: 7px; height: 7px; border-radius: 50%; background: ${statusColor}; flex-shrink: 0;"></span>
              <span style="font-weight: 600; text-overflow: ellipsis; overflow: hidden; white-space: nowrap;">${escapeHtml(u.name)}</span>
            </div>
            <span class="chip-relation-tag">${escapeHtml(e.relationship)}</span>
          </div>
        `;
      }).join('');
    }
  }

  const gapBlock = document.getElementById('inspector-gap-block');
  const gapText = document.getElementById('inspector-gap-text');
  if (gapBlock && gapText) {
    if (node.status === 'misconception') {
      gapBlock.style.display = 'block';
      gapText.textContent = node.summary || `Flagged misconception: Review contrasting mechanisms with Copilot to correct faulty mental models.`;
    } else if (node.status === 'gap') {
      gapBlock.style.display = 'block';
      gapText.textContent = node.summary || `Identified comprehension gap. Master direct prerequisites before advancing.`;
    } else {
      gapBlock.style.display = 'none';
    }
  }

  const recText = document.getElementById('inspector-recommendation-text');
  if (recText) {
    recText.textContent = generateRecommendation(node, prereqEdges, unlockEdges);
  }

  if (isLearningPathMode) {
    traceLearningPath(node);
  }

  requestRender();
}

function inspectNodeById(nodeId) {
  if (isGlobalMode) {
    extractFocusedSubgraph(nodeId);
  } else {
    const node = graphNodes.find(n => n.id === nodeId);
    if (node) {
      selectConceptNode(node);
    }
  }
}

function closeConceptInspector() {
  const panel = document.getElementById('graph-inspector-panel');
  if (panel) panel.style.display = 'none';
  selectedNode = null;
  requestRender();
}

function generateRecommendation(node, prereqEdges, unlockEdges) {
  const unmasteredPrereqs = prereqEdges.filter(e => e.sourceNode.status !== 'known');

  if (node.status === 'misconception') {
    return `⚠️ Prioritize Socratic Copilot: Active misconception detected. Click "🤖 Copilot" to clarify mental models against code examples.`;
  }
  if (node.status === 'gap') {
    if (unmasteredPrereqs.length > 0) {
      const first = unmasteredPrereqs[0].sourceNode.name;
      return `⚠️ Bridge Foundation First: You have ${unmasteredPrereqs.length} unmastered prerequisite(s). Study "${first}" before tackling this concept to avoid comprehension roadblocks.`;
    }
    return `📖 Core Knowledge Gap: Review the Living Note section and practice with active recall flashcards to establish mastery.`;
  }
  if (node.status === 'partial') {
    return `⏳ Deepen Understanding: Run interactive sandbox simulations or expand section depth to solidify this concept.`;
  }
  if (unlockEdges.length > 0) {
    const nextTarget = unlockEdges[0].targetNode.name;
    return `✅ Mastered! Prereqs satisfied. Ready to advance downstream to "${nextTarget}".`;
  }
  return `✅ Mastered: Solid grasp verified. Review periodic flashcards to maintain retention.`;
}

// --------------------------------------------------------------------------
// Scope Controls & Learning Path Engine
// --------------------------------------------------------------------------

function setNeighborhoodScope(scope) {
  neighborhoodScope = scope;
  const btnNeighbor = document.getElementById('btn-graph-scope-neighbor');
  const btnAll = document.getElementById('btn-graph-scope-all');
  if (btnNeighbor) btnNeighbor.classList.toggle('active', scope === 'neighbor');
  if (btnAll) btnAll.classList.toggle('active', scope === 'all');

  if (isGlobalMode && scope === 'all' && rawGlobalGraphData && rawGlobalGraphData.total_nodes > 100) {
    generateClusterOverview();
  }

  requestRender();
}

function toggleLearningPathMode() {
  if (isLearningPathMode) {
    exitLearningPathMode();
  } else {
    isLearningPathMode = true;
    updateLearningPathButtonState();
    if (selectedNode) {
      traceLearningPath(selectedNode);
    } else {
      const banner = document.getElementById('graph-path-banner');
      const bannerSteps = document.getElementById('graph-path-steps');
      if (banner && bannerSteps) {
        banner.style.display = 'flex';
        bannerSteps.textContent = 'Click any concept node to trace its complete prerequisite learning path.';
      }
    }
  }
  requestRender();
}

function exitLearningPathMode() {
  isLearningPathMode = false;
  learningPathNodes.clear();
  learningPathEdges.clear();
  updateLearningPathButtonState();
  const banner = document.getElementById('graph-path-banner');
  if (banner) banner.style.display = 'none';
  requestRender();
}

function updateLearningPathButtonState() {
  const btn = document.getElementById('btn-graph-learning-path');
  if (btn) btn.classList.toggle('active', isLearningPathMode);
}

function traceLearningPath(targetNode) {
  if (!targetNode) return;
  isLearningPathMode = true;
  updateLearningPathButtonState();

  const visited = new Set();
  const pathEdges = new Set();
  const queue = [targetNode.id];
  visited.add(targetNode.id);

  while (queue.length > 0) {
    const currId = queue.shift();
    for (const edge of graphEdges) {
      if (edge.targetNode.id === currId && (edge.relationship === 'prerequisite' || edge.relationship === 'subconcept')) {
        pathEdges.add(edge);
        if (!visited.has(edge.sourceNode.id)) {
          visited.add(edge.sourceNode.id);
          queue.push(edge.sourceNode.id);
        }
      }
    }
  }

  learningPathNodes = visited;
  learningPathEdges = pathEdges;

  const nodeMap = new Map(graphNodes.map(n => [n.id, n]));
  const banner = document.getElementById('graph-path-banner');
  const bannerSteps = document.getElementById('graph-path-steps');

  if (banner && bannerSteps) {
    banner.style.display = 'flex';
    const prereqNodes = Array.from(visited)
      .map(id => nodeMap.get(id))
      .filter(n => n && n.id !== targetNode.id);

    if (prereqNodes.length === 0) {
      bannerSteps.innerHTML = `<span style="color: #6ee7b7; font-weight: 700;">${escapeHtml(targetNode.name)}</span> is a foundational concept with no prior prerequisites. You can start here!`;
    } else {
      const stepsHtml = prereqNodes.map(n => {
        const isMastered = n.status === 'known';
        const color = isMastered ? '#6ee7b7' : (n.status === 'partial' ? '#fde68a' : '#c084fc');
        const icon = isMastered ? '✓ ' : (n.status === 'gap' ? '⚠️ ' : '⏳ ');
        return `<span style="color: ${color}; cursor: pointer; text-decoration: underline;" onclick="inspectNodeById('${n.id}')">${icon}${escapeHtml(n.name)}</span>`;
      }).join(' <span style="color: rgba(255,255,255,0.4); margin: 0 4px;">➔</span> ');

      bannerSteps.innerHTML = `${stepsHtml} <span style="color: rgba(255,255,255,0.4); margin: 0 4px;">➔</span> <strong style="color: #fde047;">${escapeHtml(targetNode.name)} (Target)</strong>`;
    }
  }

  requestRender();
}

// --------------------------------------------------------------------------
// Inspector Action Handlers
// --------------------------------------------------------------------------

function goToSectionFromInspector() {
  if (!selectedNode) return;
  const node = selectedNode;
  closeGraphModal();

  let secEl = node.section_id ? document.getElementById(`sec-${node.section_id}`) : null;
  if (!secEl && currentNote && currentNote.sections) {
    const match = currentNote.sections.find(s => s.id === node.section_id || s.title === node.section_title);
    if (match) {
      secEl = document.getElementById(`sec-${match.order_index}`);
    }
  }
  if (secEl) {
    setTimeout(() => {
      secEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
      secEl.classList.add('section-highlight-flash');
      setTimeout(() => secEl.classList.remove('section-highlight-flash'), 2400);
    }, 350);
  }
}

function askCopilotFromInspector() {
  if (!selectedNode) return;
  const node = selectedNode;
  const prefill = `Can you explain the concept "${node.name}" in depth? How does it connect to its prerequisites and where does it fit in the technical architecture?`;
  closeGraphModal();
  openCopilotDrawer(node.section_id || null, node.section_title || null, prefill, null);
}

function tracePathFromInspector() {
  if (!selectedNode) return;
  traceLearningPath(selectedNode);
}

function updateGraphTooltip(node, clientX, clientY) {
  const tooltip = document.getElementById('graph-tooltip');
  if (!tooltip) return;

  if (!node) {
    tooltip.style.display = 'none';
    return;
  }

  const statusLabel = node.status.toUpperCase();
  const color = COLOR_MAP[node.status] || COLOR_MAP.known;
  const domainLabel = node.journey_topic || node.group.toUpperCase();

  tooltip.innerHTML = `
    <div style="display: flex; align-items: center; justify-content: space-between; gap: 0.75rem; margin-bottom: 0.35rem;">
      <span style="font-size: 0.68rem; font-family: var(--font-mono); font-weight: 700; color: ${color.stroke}; background: ${color.fill}33; padding: 0.15rem 0.45rem; border-radius: 4px;">
        ${statusLabel}
      </span>
      <span style="font-size: 0.72rem; color: var(--text-muted); font-family: var(--font-mono);">${escapeHtml(domainLabel)}</span>
    </div>
    <div style="font-size: 0.95rem; font-weight: 800; color: #ffffff; margin-bottom: 0.25rem;">${escapeHtml(node.name)}</div>
    ${node.summary ? `<div style="font-size: 0.8rem; color: #cbd5e1; line-height: 1.4; margin-bottom: 0.35rem;">${escapeHtml(node.summary)}</div>` : ''}
    <div style="font-size: 0.74rem; color: #a5b4fc; font-family: var(--font-mono); margin-top: 0.25rem;">💡 Click to inspect prerequisites &amp; explore neighborhood</div>
  `;

  tooltip.style.left = `${clientX + 14}px`;
  tooltip.style.top = `${clientY + 14}px`;
  tooltip.style.display = 'block';
}

function setGraphFilter(filterName, btn) {
  activeFilter = filterName;
  document.querySelectorAll('.graph-filter-btn').forEach(b => {
    if (b.id !== 'btn-graph-scope-neighbor' && b.id !== 'btn-graph-scope-all' && b.id !== 'btn-graph-learning-path') {
      b.classList.remove('active');
    }
  });
  if (btn) btn.classList.add('active');
  requestRender();
}

// --------------------------------------------------------------------------
// Search & Autocomplete
// --------------------------------------------------------------------------

function handleGraphSearchFocus(input) {
  if (isGlobalMode && rawGlobalGraphData && input.value.trim()) {
    handleGraphSearch(input);
  }
}

function handleGraphSearch(input) {
  searchQuery = input.value.trim();

  if (isGlobalMode && rawGlobalGraphData) {
    const dropdown = document.getElementById('graph-search-dropdown');
    if (!dropdown) return;

    if (!searchQuery) {
      dropdown.style.display = 'none';
      return;
    }

    const matches = rawGlobalGraphData.nodes
      .filter(n => n.name.toLowerCase().includes(searchQuery.toLowerCase()))
      .slice(0, 10);

    if (matches.length === 0) {
      dropdown.innerHTML = `<div style="padding: 0.6rem 0.8rem; font-size: 0.78rem; color: var(--text-muted);">No matching concepts found</div>`;
      dropdown.style.display = 'flex';
      return;
    }

    dropdown.innerHTML = matches.map(n => {
      const color = COLOR_MAP[n.status]?.stroke || '#38bdf8';
      const statusLabel = n.status.toUpperCase();
      const domain = n.journey_topic || (n.group === 'journey' ? 'Domain Hub' : 'Technical Concept');
      return `
        <div class="search-dropdown-item" onclick="selectSearchConcept('${n.id}')">
          <div class="search-item-title">
            <span>${escapeHtml(n.name)}</span>
            <span style="font-size: 0.65rem; color: ${color}; font-family: var(--font-mono);">${statusLabel}</span>
          </div>
          <div class="search-item-meta">${escapeHtml(domain)}</div>
        </div>
      `;
    }).join('');
    dropdown.style.display = 'flex';
  } else {
    requestRender();
  }
}

function selectSearchConcept(nodeId) {
  const dropdown = document.getElementById('graph-search-dropdown');
  const searchInput = document.getElementById('graph-search-input');
  if (dropdown) dropdown.style.display = 'none';
  if (searchInput) searchInput.value = '';
  searchQuery = '';

  if (isGlobalMode) {
    extractFocusedSubgraph(nodeId);
  } else {
    const node = graphNodes.find(n => n.id === nodeId);
    if (node) selectConceptNode(node);
  }
}

document.addEventListener('click', (e) => {
  const dropdown = document.getElementById('graph-search-dropdown');
  const searchInput = document.getElementById('graph-search-input');
  if (dropdown && !dropdown.contains(e.target) && e.target !== searchInput) {
    dropdown.style.display = 'none';
  }
});

function resetGraphZoom() {
  graphCamera = { x: 0, y: 0, zoom: 1.0 };
  targetCamera = null;
  const zoomPill = document.getElementById('graph-zoom-pill');
  if (zoomPill) zoomPill.textContent = '100%';
  requestRender();
}

function adjustGraphZoom(delta) {
  const newZoom = Math.max(0.25, Math.min(3.5, graphCamera.zoom + delta));
  graphCamera.zoom = newZoom;
  targetCamera = null;
  const zoomPill = document.getElementById('graph-zoom-pill');
  if (zoomPill) zoomPill.textContent = `${Math.round(graphCamera.zoom * 100)}%`;
  requestRender();
}

// --------------------------------------------------------------------------
// In-App Fullscreen Workspace & Responsive Canvas Sizing
// --------------------------------------------------------------------------

function toggleGraphFullscreen() {
  isGraphFullscreen = !isGraphFullscreen;
  applyGraphFullscreenState();
}

function applyGraphFullscreenState() {
  const modal = document.getElementById('graph-modal');
  const icon = document.getElementById('graph-fullscreen-icon');
  const label = document.getElementById('graph-fullscreen-label');
  const btn = document.getElementById('btn-graph-fullscreen');
  const badge = document.getElementById('graph-workspace-badge');

  if (modal) {
    modal.classList.toggle('is-fullscreen', isGraphFullscreen);
  }

  if (icon) {
    icon.textContent = isGraphFullscreen ? '🗗' : '⛶';
  }
  if (label) {
    label.textContent = isGraphFullscreen ? 'Exit Fullscreen' : 'Fullscreen';
  }
  if (btn) {
    btn.title = isGraphFullscreen ? 'Exit Fullscreen Workspace (F / Esc)' : 'Toggle In-App Fullscreen Workspace (F)';
  }
  if (badge) {
    badge.style.display = isGraphFullscreen ? 'inline-block' : 'none';
  }

  handleCanvasResizeTransition();
}

function handleCanvasResizeTransition() {
  resizeGraphCanvas();
  setTimeout(() => {
    resizeGraphCanvas();
  }, 290);
}

function resizeGraphCanvas() {
  if (!graphCanvas || !graphCtx) return;
  const container = graphCanvas.parentElement;
  if (!container) return;

  const rect = container.getBoundingClientRect();
  if (rect.width === 0 || rect.height === 0) return;

  const dpr = window.devicePixelRatio || 1;
  const oldW = graphCanvas.width / dpr;
  const oldH = graphCanvas.height / dpr;

  const newW = rect.width;
  const newH = rect.height;

  graphCanvas.width = newW * dpr;
  graphCanvas.height = newH * dpr;
  graphCanvas.style.width = `${newW}px`;
  graphCanvas.style.height = `${newH}px`;

  graphCtx.scale(dpr, dpr);

  if (selectedNode) {
    smoothCenterOnNode(selectedNode);
  } else if (oldW > 0 && oldH > 0) {
    const dw = (newW - oldW) / 2;
    const dh = (newH - oldH) / 2;
    graphCamera.x += dw;
    graphCamera.y += dh;
  }

  requestRender();
}

function setupGraphResizeObserver() {
  if (window.ResizeObserver && !graphResizeObserver) {
    const container = document.getElementById('graph-canvas-container');
    if (container) {
      graphResizeObserver = new ResizeObserver(() => {
        if (graphCanvas && graphCanvas.offsetParent !== null) {
          resizeGraphCanvas();
        }
      });
      graphResizeObserver.observe(container);
    }
  }
}

// Global Keyboard Shortcuts for Graph Modal
window.addEventListener('keydown', (e) => {
  const modal = document.getElementById('graph-modal');
  if (!modal || modal.style.display === 'none') return;

  const activeTag = document.activeElement ? document.activeElement.tagName.toLowerCase() : '';
  if (activeTag === 'input' || activeTag === 'textarea') return;

  if (e.key === 'f' || e.key === 'F') {
    e.preventDefault();
    toggleGraphFullscreen();
  } else if (e.key === 'Escape') {
    if (isGraphFullscreen) {
      e.preventDefault();
      e.stopPropagation();
      toggleGraphFullscreen();
    }
  }
});

// --------------------------------------------------------------------------
// Canvas Rendering with Level of Detail (LOD) & Viewport Culling
// --------------------------------------------------------------------------

function roundRect(ctx, x, y, w, h, r) {
  if (w < 2 * r) r = w / 2;
  if (h < 2 * r) r = h / 2;
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

function renderGraph() {
  if (!graphCtx || !graphCanvas) return;
  const rect = graphCanvas.getBoundingClientRect();
  const w = rect.width;
  const h = rect.height;

  graphCtx.clearRect(0, 0, w, h);

  graphCtx.save();
  graphCtx.translate(graphCamera.x, graphCamera.y);
  graphCtx.scale(graphCamera.zoom, graphCamera.zoom);

  const minWorld = screenToWorld(-80, -80);
  const maxWorld = screenToWorld(w + 80, h + 80);
  const isZoomedOut = graphCamera.zoom < 0.72;

  // ------------------------------------------------------------------------
  // 1. Draw Edges
  // ------------------------------------------------------------------------
  for (const edge of graphEdges) {
    const s = edge.sourceNode;
    const t = edge.targetNode;

    if ((s.x < minWorld.x && t.x < minWorld.x) || (s.x > maxWorld.x && t.x > maxWorld.x) ||
        (s.y < minWorld.y && t.y < minWorld.y) || (s.y > maxWorld.y && t.y > maxWorld.y)) {
      continue;
    }

    const isFiltered = isNodeFiltered(s) || isNodeFiltered(t);
    const inScopeS = isNodeInVisualScope(s);
    const inScopeT = isNodeInVisualScope(t);
    const isEdgeInScope = inScopeS && inScopeT && 
      (neighborhoodScope === 'all' || !selectedNode || s === selectedNode || t === selectedNode || (isLearningPathMode && learningPathEdges.has(edge)));

    const isPathEdge = isLearningPathMode && learningPathEdges.has(edge);
    const isHighlighted = (hoveredNode && (s === hoveredNode || t === hoveredNode)) ||
                          (selectedNode && (s === selectedNode || t === selectedNode));

    const style = RELATION_STYLES[edge.relationship] || RELATION_STYLES.prerequisite;

    graphCtx.save();
    graphCtx.beginPath();
    graphCtx.moveTo(s.x, s.y);
    graphCtx.lineTo(t.x, t.y);

    if (isFiltered || !isEdgeInScope) {
      graphCtx.strokeStyle = 'rgba(255, 255, 255, 0.04)';
      graphCtx.lineWidth = 0.8;
      graphCtx.stroke();
      graphCtx.restore();
      continue;
    }

    if (isPathEdge) {
      graphCtx.strokeStyle = '#facc15';
      graphCtx.lineWidth = 3.6;
      graphCtx.shadowColor = 'rgba(250, 204, 21, 0.85)';
      graphCtx.shadowBlur = 12;
      graphCtx.setLineDash([]);
    } else if (isHighlighted) {
      graphCtx.strokeStyle = 'rgba(129, 140, 248, 0.95)';
      graphCtx.lineWidth = 2.8;
      graphCtx.shadowColor = 'rgba(129, 140, 248, 0.6)';
      graphCtx.shadowBlur = 8;
      graphCtx.setLineDash([]);
    } else {
      graphCtx.strokeStyle = style.stroke;
      graphCtx.lineWidth = style.width;
      if (style.dash.length > 0) graphCtx.setLineDash(style.dash);
    }

    graphCtx.stroke();
    graphCtx.restore();

    // Directional Arrow Indicator
    const angle = Math.atan2(t.y - s.y, t.x - s.x);
    const arrowDist = t.radius + 6;
    const arrowX = t.x - Math.cos(angle) * arrowDist;
    const arrowY = t.y - Math.sin(angle) * arrowDist;

    graphCtx.save();
    graphCtx.beginPath();
    graphCtx.fillStyle = isPathEdge ? '#facc15' : (isHighlighted ? '#818cf8' : style.arrow);
    graphCtx.moveTo(arrowX, arrowY);
    graphCtx.lineTo(arrowX - 8 * Math.cos(angle - Math.PI / 6), arrowY - 8 * Math.sin(angle - Math.PI / 6));
    graphCtx.lineTo(arrowX - 8 * Math.cos(angle + Math.PI / 6), arrowY - 8 * Math.sin(angle + Math.PI / 6));
    graphCtx.closePath();
    graphCtx.fill();
    graphCtx.restore();

    // Midpoint Relationship Label
    if (isHighlighted || isPathEdge) {
      const midX = (s.x + t.x) / 2;
      const midY = (s.y + t.y) / 2;
      const relLabel = edge.label || style.label;

      graphCtx.save();
      graphCtx.font = 'bold 9px "JetBrains Mono", monospace';
      const textW = graphCtx.measureText(relLabel).width + 8;
      const textH = 14;

      graphCtx.fillStyle = 'rgba(11, 15, 28, 0.92)';
      graphCtx.strokeStyle = isPathEdge ? '#facc15' : 'rgba(255, 255, 255, 0.2)';
      graphCtx.lineWidth = 1;
      roundRect(graphCtx, midX - textW / 2, midY - textH / 2, textW, textH, 4);
      graphCtx.fill();
      graphCtx.stroke();

      graphCtx.fillStyle = isPathEdge ? '#fef08a' : '#e2e8f0';
      graphCtx.textAlign = 'center';
      graphCtx.textBaseline = 'middle';
      graphCtx.fillText(relLabel, midX, midY);
      graphCtx.restore();
    }
  }

  // ------------------------------------------------------------------------
  // 2. Draw Nodes
  // ------------------------------------------------------------------------
  for (const node of graphNodes) {
    if (node.x < minWorld.x || node.x > maxWorld.x || node.y < minWorld.y || node.y > maxWorld.y) {
      continue;
    }

    const isFiltered = isNodeFiltered(node);
    const inScope = isNodeInVisualScope(node);
    const isHovered = (hoveredNode === node);
    const isSelected = (selectedNode === node);
    const isPathNode = isLearningPathMode && learningPathNodes.has(node.id);
    const isNeighbor = hoveredNode && graphEdges.some(e => 
      (e.sourceNode === hoveredNode && e.targetNode === node) || 
      (e.targetNode === hoveredNode && e.sourceNode === node)
    );

    const colors = COLOR_MAP[node.group === 'topic' || node.group === 'journey' ? 'topic' : node.status] || COLOR_MAP.known;
    const radius = node.radius + (isHovered || isSelected ? 4 : 0);

    if (isFiltered || !inScope) {
      graphCtx.beginPath();
      graphCtx.arc(node.x, node.y, node.radius, 0, Math.PI * 2);
      graphCtx.fillStyle = 'rgba(255, 255, 255, 0.04)';
      graphCtx.fill();
      graphCtx.strokeStyle = 'rgba(255, 255, 255, 0.08)';
      graphCtx.lineWidth = 1;
      graphCtx.stroke();
      continue;
    }

    // Glow aura
    if (isHovered || isSelected || isNeighbor || isPathNode) {
      graphCtx.beginPath();
      graphCtx.arc(node.x, node.y, radius + (isPathNode ? 12 : 8), 0, Math.PI * 2);
      graphCtx.fillStyle = isPathNode ? 'rgba(250, 204, 21, 0.35)' : colors.glow;
      graphCtx.fill();
    }

    // Main Circle Fill
    graphCtx.beginPath();
    graphCtx.arc(node.x, node.y, radius, 0, Math.PI * 2);
    graphCtx.fillStyle = colors.fill;
    graphCtx.fill();

    // Node Border
    graphCtx.strokeStyle = isPathNode ? '#facc15' : (isSelected ? '#ffffff' : (isHovered ? '#ffffff' : colors.stroke));
    graphCtx.lineWidth = isSelected ? 3.5 : (isHovered || isPathNode ? 3 : 2);
    graphCtx.stroke();

    // Selection Outer Ring
    if (isSelected) {
      graphCtx.beginPath();
      graphCtx.arc(node.x, node.y, radius + 5, 0, Math.PI * 2);
      graphCtx.strokeStyle = 'rgba(255, 255, 255, 0.7)';
      graphCtx.lineWidth = 1.5;
      graphCtx.stroke();
    }

    // Level of Detail (LOD) Label Filtering
    const shouldDrawLabel = !isZoomedOut || isSelected || isHovered || isPathNode || isNeighbor || node.group === 'journey' || node.group === 'topic';

    if (shouldDrawLabel && (!isFiltered || isHovered)) {
      graphCtx.font = `${(isSelected || isHovered || isPathNode) ? 'bold ' : ''}11px "Plus Jakarta Sans", sans-serif`;
      graphCtx.textAlign = 'center';
      graphCtx.textBaseline = 'top';

      const label = node.name.length > 22 ? node.name.substring(0, 20) + '...' : node.name;

      const textMetrics = graphCtx.measureText(label);
      const textW = textMetrics.width + 10;
      const textH = 15;
      const pillY = node.y + radius + 4;

      graphCtx.fillStyle = isSelected ? 'rgba(15, 23, 42, 0.95)' : 'rgba(4, 7, 17, 0.78)';
      roundRect(graphCtx, node.x - textW / 2, pillY, textW, textH, 4);
      graphCtx.fill();

      if (isSelected || isPathNode) {
        graphCtx.strokeStyle = isPathNode ? 'rgba(250, 204, 21, 0.7)' : 'rgba(255, 255, 255, 0.4)';
        graphCtx.lineWidth = 1;
        graphCtx.stroke();
      }

      graphCtx.fillStyle = isSelected ? '#ffffff' : (isPathNode ? '#fde047' : colors.text);
      graphCtx.fillText(label, node.x, pillY + 2);
    }
  }

  graphCtx.restore();
}
