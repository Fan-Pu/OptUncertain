from __future__ import annotations


def render_viewer_html() -> str:
    return r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Graph Hypothesis Visualizer</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --ink: #1f2933;
      --muted: #667085;
      --line: #d0d5dd;
      --region: #1f7a8c;
      --viewpoint: #7a5cfa;
      --grounded: #15803d;
      --current: #d97706;
      --arrival: #dc2626;
      --edge: #667085;
      --edge-vz: #9a3412;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Arial, Helvetica, sans-serif;
      background: var(--bg);
      color: var(--ink);
    }
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 16px;
      padding: 14px 18px;
      background: #111827;
      color: white;
    }
    h1 {
      margin: 0;
      font-size: 18px;
      font-weight: 700;
      letter-spacing: 0;
    }
    button {
      border: 1px solid #98a2b3;
      background: white;
      color: #111827;
      border-radius: 6px;
      padding: 8px 12px;
      font-size: 14px;
      cursor: pointer;
    }
    button:disabled {
      color: #98a2b3;
      cursor: default;
      background: #f2f4f7;
    }
    button[aria-pressed="true"] {
      border-color: #7a5cfa;
      background: #eef2ff;
      color: #312e81;
      font-weight: 700;
    }
    .controls {
      display: flex;
      align-items: center;
      justify-content: flex-end;
      flex-wrap: wrap;
      gap: 10px;
    }
    .controls button {
      white-space: nowrap;
    }
    .solution-buttons {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      align-items: center;
    }
    #stepLabel {
      min-width: 104px;
      text-align: center;
      font-weight: 700;
      font-size: 14px;
    }
    main {
      display: grid;
      grid-template-columns: minmax(520px, 1fr) 430px;
      gap: 14px;
      padding: 14px;
      min-height: calc(100vh - 62px);
    }
    .workspace {
      display: grid;
      grid-template-rows: minmax(480px, 1fr) auto;
      gap: 14px;
      min-width: 0;
    }
    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      min-width: 0;
    }
    .graph-panel {
      position: relative;
      overflow: hidden;
    }
    .graph-toolbar {
      position: absolute;
      top: 10px;
      right: 10px;
      z-index: 2;
      display: flex;
      gap: 6px;
      align-items: center;
    }
    .graph-toolbar button {
      width: 32px;
      height: 32px;
      padding: 0;
      font-size: 16px;
      font-weight: 700;
      line-height: 1;
      box-shadow: 0 1px 3px rgba(16, 24, 40, 0.16);
    }
    .graph-toolbar .graph-reset-button {
      width: auto;
      padding: 0 10px;
      font-size: 13px;
    }
    .graph-toolbar .house-texture-button {
      width: auto;
      padding: 0 10px;
      font-size: 13px;
    }
    .graph-toolbar .house-texture-button.loading {
      color: #475467;
      background: #f2f4f7;
    }
    .texture-status {
      display: inline-flex;
      align-items: center;
      min-height: 32px;
      padding: 0 10px;
      border: 1px solid #98a2b3;
      border-radius: 6px;
      background: rgba(255, 255, 255, 0.94);
      color: #344054;
      font-size: 13px;
      box-shadow: 0 1px 3px rgba(16, 24, 40, 0.16);
    }
    .texture-status[hidden] {
      display: none;
    }
    svg {
      width: 100%;
      height: 100%;
      min-height: 480px;
      display: block;
      background:
        linear-gradient(#eef2f6 1px, transparent 1px),
        linear-gradient(90deg, #eef2f6 1px, transparent 1px);
      background-size: 32px 32px;
    }
    #graph:focus {
      outline: 2px solid #7a5cfa;
      outline-offset: -2px;
    }
    #graph.panning {
      cursor: grabbing;
    }
    .legend {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      padding: 10px 12px;
      font-size: 12px;
      color: var(--muted);
    }
    .legend span {
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }
    .swatch {
      width: 12px;
      height: 12px;
      border-radius: 50%;
      display: inline-block;
    }
    .side {
      display: grid;
      gap: 14px;
      align-content: start;
      overflow: auto;
      max-height: calc(100vh - 90px);
    }
    .section {
      padding: 12px;
    }
    h2 {
      margin: 0 0 10px 0;
      font-size: 14px;
      letter-spacing: 0;
    }
    .kv {
      display: grid;
      grid-template-columns: 130px 1fr;
      gap: 6px 10px;
      font-size: 13px;
    }
    .kv dt {
      color: var(--muted);
    }
    .kv dd {
      margin: 0;
      min-width: 0;
      overflow-wrap: anywhere;
      white-space: pre-wrap;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 12px;
    }
    th, td {
      border-top: 1px solid #eaecf0;
      padding: 6px 4px;
      text-align: left;
      vertical-align: top;
    }
    th {
      color: var(--muted);
      font-weight: 700;
    }
    pre {
      margin: 0;
      max-height: 260px;
      overflow: auto;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      font-size: 12px;
      line-height: 1.35;
      background: #f8fafc;
      border: 1px solid #eaecf0;
      border-radius: 6px;
      padding: 10px;
    }
    .images {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 12px;
      padding: 12px;
    }
    figure {
      margin: 0;
    }
    img {
      width: 100%;
      display: block;
      border-radius: 6px;
      border: 1px solid var(--line);
    }
    figcaption {
      margin-top: 5px;
      color: var(--muted);
      font-size: 12px;
    }
    .node {
      cursor: pointer;
    }
    .node text {
      font-size: 11px;
      fill: #111827;
      paint-order: stroke;
      stroke: white;
      stroke-width: 4px;
      stroke-linejoin: round;
      pointer-events: none;
    }
    .edge {
      cursor: pointer;
    }
    .edge line {
      stroke: var(--edge);
      stroke-width: 2;
    }
    .edge.vz line {
      stroke: var(--edge-vz);
      stroke-dasharray: 6 4;
    }
    .edge.ungrounded line {
      opacity: 0.45;
    }
    .edge.arrival line {
      stroke: var(--arrival);
      stroke-width: 5;
      opacity: 1;
    }
    .route-environment-edge {
      stroke: #c7ced8;
      stroke-width: 1;
    }
    .route-node {
      fill: #475467;
      stroke: white;
      stroke-width: 1.5;
      cursor: pointer;
    }
    .route-line {
      fill: none;
      stroke-width: 4;
      stroke-linecap: round;
      stroke-linejoin: round;
    }
    .route-selected {
      stroke: #111827;
      stroke-width: 4;
    }
    .route-step-marker {
      stroke: white;
      stroke-width: 2;
      cursor: pointer;
    }
    .route-start-marker {
      stroke: #111827;
      stroke-width: 2;
      cursor: pointer;
    }
    .route-target-marker {
      fill: #f2c300;
      stroke: #111827;
      stroke-width: 1.5;
      cursor: pointer;
    }
    .route-summary {
      display: grid;
      gap: 12px;
      font-size: 13px;
    }
    .agent-legend {
      display: grid;
      gap: 6px;
      font-size: 13px;
    }
    .agent-legend-row {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .route-agent {
      border-top: 1px solid #eaecf0;
      padding-top: 10px;
    }
    .route-agent h3 {
      margin: 0 0 8px 0;
      font-size: 13px;
    }
    .region-boundary {
      fill-opacity: 0.18;
      stroke-width: 2;
    }
    .selected line,
    .selected circle,
    .selected polygon,
    .selected path {
      stroke: #111827;
      stroke-width: 4;
    }
    @media (max-width: 980px) {
      main {
        grid-template-columns: 1fr;
      }
      .side {
        max-height: none;
      }
    }
  </style>
</head>
<body>
  <header>
    <h1 id="title">Graph Hypothesis Visualizer</h1>
    <div class="controls">
      <div id="solutionButtons" class="solution-buttons"></div>
      <button id="prevButton" type="button">Previous</button>
      <div id="stepLabel"></div>
      <button id="nextButton" type="button">Next</button>
    </div>
  </header>
  <main>
    <div class="workspace">
      <section class="panel graph-panel">
        <div class="graph-toolbar" aria-label="Graph view controls">
          <button id="graphZoomInButton" type="button" title="Zoom in" aria-label="Zoom in">+</button>
          <button id="graphZoomOutButton" type="button" title="Zoom out" aria-label="Zoom out">-</button>
          <button id="graphResetViewButton" class="graph-reset-button" type="button" title="Reset view" aria-label="Reset view">Reset</button>
          <button id="houseTextureButton" class="house-texture-button" type="button" title="Toggle house texture" aria-label="Toggle house texture" aria-pressed="true">House texture</button>
          <div id="textureStatus" class="texture-status" role="status" aria-live="polite" hidden></div>
        </div>
        <svg id="graph" tabindex="0" role="img" aria-label="Graph layout"></svg>
      </section>
      <section class="panel">
        <div class="legend">
          <span><i class="swatch" style="background: var(--region); border-radius: 3px;"></i>Region</span>
          <span><i class="swatch" style="background: var(--viewpoint);"></i>Viewpoint</span>
          <span><i class="swatch" style="background: var(--grounded);"></i>Grounded</span>
          <span><i class="swatch" style="background: var(--current);"></i>Current agent</span>
        </div>
        <div id="images" class="images"></div>
      </section>
    </div>
    <aside class="side">
      <section id="selectionSection" class="panel section">
        <h2>Selected Item</h2>
        <div id="selection"></div>
      </section>
      <section id="summarySection" class="panel section">
        <h2 id="summaryTitle">Step Summary</h2>
        <div id="summary"></div>
      </section>
      <section id="targetDetectionsSection" class="panel section">
        <h2>Target Detections This Step</h2>
        <div id="targetDetections"></div>
      </section>
      <section id="unassignedRegionSection" class="panel section">
        <h2>Unassigned Regions</h2>
        <div id="unassignedRegions"></div>
      </section>
      <section id="nodeTableSection" class="panel section">
        <h2>Hypothesis Nodes</h2>
        <div id="nodeTable"></div>
      </section>
      <section id="edgeTableSection" class="panel section">
        <h2>Hypothesis Edges</h2>
        <div id="edgeTable"></div>
      </section>
      <section id="detectionsSection" class="panel section">
        <h2>Detections</h2>
        <div id="detections"></div>
      </section>
      <section id="semanticSection" class="panel section">
        <h2>Semantic Raw Output</h2>
        <pre id="semantic"></pre>
      </section>
      <section id="userMessageSection" class="panel section">
        <h2>User Message</h2>
        <pre id="userMessage"></pre>
      </section>
    </aside>
  </main>
  <script>
    let payload = null;
    let stepPosition = 0;
    let selected = null;
    let activeSolutionId = null;
    let panState = null;
    let showHouseTexture = true;
    const viewportStates = new Map();
    const GRAPH_MIN_SCALE = 0.2;
    const GRAPH_MAX_SCALE = 5;
    const GRAPH_ZOOM_FACTOR = 1.2;
    const GRAPH_FIT_PADDING = 56;
    const REGION_BOUNDARY_NODE_RADIUS = 38;
    const REGION_BOUNDARY_CORRIDOR_RADIUS = 18;
    const REGION_BOUNDARY_CELL_SIZE = 4;
    const ROUTE_COLORS = ["#d62728", "#1f77b4", "#2ca02c", "#ff7f0e", "#9467bd", "#17becf"];
    const REGION_COLORS = [
      "#0f766e",
      "#2563eb",
      "#ca8a04",
      "#c026d3",
      "#dc2626",
      "#16a34a",
      "#7c3aed",
      "#ea580c",
      "#0891b2",
      "#be123c"
    ];

    const graph = document.getElementById("graph");
    const solutionButtons = document.getElementById("solutionButtons");
    const graphZoomInButton = document.getElementById("graphZoomInButton");
    const graphZoomOutButton = document.getElementById("graphZoomOutButton");
    const graphResetViewButton = document.getElementById("graphResetViewButton");
    const houseTextureButton = document.getElementById("houseTextureButton");
    const textureStatus = document.getElementById("textureStatus");
    const prevButton = document.getElementById("prevButton");
    const nextButton = document.getElementById("nextButton");
    const stepLabel = document.getElementById("stepLabel");
    const selectionSection = document.getElementById("selectionSection");
    const summaryTitle = document.getElementById("summaryTitle");
    const targetDetectionsSection = document.getElementById("targetDetectionsSection");
    const unassignedRegionSection = document.getElementById("unassignedRegionSection");
    const nodeTableSection = document.getElementById("nodeTableSection");
    const edgeTableSection = document.getElementById("edgeTableSection");
    const detectionsSection = document.getElementById("detectionsSection");
    const semanticSection = document.getElementById("semanticSection");
    const userMessageSection = document.getElementById("userMessageSection");
    graphZoomInButton.addEventListener("click", () => {
      graph.focus();
      zoomGraphAtCenter(GRAPH_ZOOM_FACTOR);
    });
    graphZoomOutButton.addEventListener("click", () => {
      graph.focus();
      zoomGraphAtCenter(1 / GRAPH_ZOOM_FACTOR);
    });
    graphResetViewButton.addEventListener("click", () => {
      graph.focus();
      resetCurrentGraphViewport();
      renderCurrentGraph();
    });
    houseTextureButton.addEventListener("click", () => {
      showHouseTexture = !showHouseTexture;
      graph.focus();
      renderCurrentGraph();
    });
    prevButton.addEventListener("click", () => {
      stepPosition = Math.max(0, stepPosition - 1);
      selected = null;
      render();
    });
    nextButton.addEventListener("click", () => {
      stepPosition = Math.min(payload.steps.length - 1, stepPosition + 1);
      selected = null;
      render();
    });
    window.addEventListener("pagehide", () => {
      navigator.sendBeacon("/api/shutdown", "{}");
    });
    graph.addEventListener("pointerdown", () => {
      graph.focus();
    }, true);
    graph.addEventListener("pointerdown", event => {
      graph.focus();
      if (event.button !== 0) return;
      if (event.target !== graph) return;
      beginGraphPan(event);
    });
    graph.addEventListener("pointermove", event => {
      if (panState) {
        updateGraphPan(event);
        renderCurrentGraph();
      }
    });
    graph.addEventListener("pointerup", event => {
      if (panState) {
        updateGraphPan(event);
        graph.releasePointerCapture(panState.pointerId);
        panState = null;
        graph.classList.remove("panning");
        renderCurrentGraph();
        return;
      }
    });
    graph.addEventListener("pointercancel", () => {
      panState = null;
      graph.classList.remove("panning");
      render();
    });
    graph.addEventListener("wheel", event => {
      if (!event.ctrlKey) return;
      event.preventDefault();
      graph.focus();
      const factor = event.deltaY < 0 ? GRAPH_ZOOM_FACTOR : 1 / GRAPH_ZOOM_FACTOR;
      zoomGraphAtPoint(factor, graphScreenPoint(event));
    }, { passive: false });

    fetch("/api/steps")
      .then(response => response.json())
      .then(data => {
        payload = data;
        document.getElementById("title").textContent =
          `Graph Hypothesis Visualizer: ${payload.instance_name}`;
        render();
        fetchHouseTexture();
        window.addEventListener("resize", renderCurrentGraph);
      });

    function fetchHouseTexture() {
      setTextureLoading(true);
      showTextureStatus("Preparing house texture...");
      fetch("/api/house-texture")
        .then(response => response.json())
        .then(houseTexture => {
          payload.environment_graph.house_texture = houseTexture;
          clearDefaultViewportStates();
          if (showHouseTexture) renderCurrentGraph();
          setTextureLoading(false);
          showTextureStatus("House texture ready", 1800);
        });
    }

    function setTextureLoading(isLoading) {
      houseTextureButton.disabled = Boolean(isLoading);
      houseTextureButton.classList.toggle("loading", Boolean(isLoading));
      houseTextureButton.setAttribute("aria-busy", String(Boolean(isLoading)));
    }

    function showTextureStatus(message, hideAfterMs) {
      textureStatus.textContent = message;
      textureStatus.hidden = false;
      if (hideAfterMs) {
        window.setTimeout(() => {
          if (textureStatus.textContent === message) textureStatus.hidden = true;
        }, hideAfterMs);
      }
    }

    function currentStep() {
      return payload.steps[stepPosition];
    }

    function currentSolution() {
      return (payload.solutions || []).find(solution => solution.id === activeSolutionId) || null;
    }

    function render() {
      renderSolutionButtons();
      const activeSolution = currentSolution();
      if (activeSolution) {
        prevButton.disabled = true;
        nextButton.disabled = true;
        graphZoomInButton.disabled = false;
        graphZoomOutButton.disabled = false;
        graphResetViewButton.disabled = false;
        houseTextureButton.disabled = false;
        houseTextureButton.setAttribute("aria-pressed", String(showHouseTexture));
        stepLabel.textContent = activeSolution.label;
        renderRouteGraph(activeSolution);
        renderSolutionDetails(activeSolution);
        document.getElementById("images").innerHTML = "";
        return;
      }
      const step = currentStep();
      graphZoomInButton.disabled = false;
      graphZoomOutButton.disabled = false;
      graphResetViewButton.disabled = false;
      houseTextureButton.disabled = false;
      houseTextureButton.setAttribute("aria-pressed", String(showHouseTexture));
      prevButton.disabled = stepPosition === 0;
      nextButton.disabled = stepPosition === payload.steps.length - 1;
      showStepSections();
      stepLabel.textContent = `Step ${step.step_index} / ${payload.steps.length}`;
      renderGraph(step);
      renderSelection(step);
      renderSummary(step);
      renderTargetDetections(step);
      renderUnassignedRegions(step);
      renderNodeTable(step);
      renderEdgeTable(step);
      renderDetections(step);
      renderImages(step);
      document.getElementById("semantic").textContent =
        step.semantic === null ? "" : JSON.stringify(step.semantic, null, 2);
      document.getElementById("userMessage").textContent = step.user_message;
    }

    function renderSolutionButtons() {
      const solutions = payload.solutions || [];
      if (!solutions.length) {
        solutionButtons.innerHTML = "";
        return;
      }
      const stepPressed = activeSolutionId === null;
      solutionButtons.innerHTML = [
        `<button type="button" data-solution-id="" aria-pressed="${stepPressed}">Step view</button>`,
        ...solutions.map(solution => `
          <button type="button" data-solution-id="${escapeAttr(solution.id)}" aria-pressed="${String(activeSolutionId === solution.id)}">
            ${escapeHtml(solution.label)}
          </button>
        `)
      ].join("");
      for (const button of solutionButtons.querySelectorAll("button")) {
        button.addEventListener("click", () => {
          activeSolutionId = button.dataset.solutionId || null;
          selected = null;
          panState = null;
          render();
        });
      }
    }

    function showStepSections() {
      selectionSection.hidden = false;
      targetDetectionsSection.hidden = false;
      unassignedRegionSection.hidden = false;
      nodeTableSection.hidden = false;
      edgeTableSection.hidden = false;
      detectionsSection.hidden = false;
      semanticSection.hidden = false;
      userMessageSection.hidden = false;
      summaryTitle.textContent = "Step Summary";
    }

    function renderSolutionDetails(solution) {
      selectionSection.hidden = false;
      targetDetectionsSection.hidden = true;
      unassignedRegionSection.hidden = true;
      nodeTableSection.hidden = true;
      edgeTableSection.hidden = true;
      detectionsSection.hidden = true;
      semanticSection.hidden = true;
      userMessageSection.hidden = true;
      summaryTitle.textContent = solution.label;
      renderRouteSelection(solution);
      document.getElementById("summary").innerHTML = routeSummaryHtml(solution.summary);
    }

    function routeSummaryHtml(summary) {
      const targetRows = routeTargetRows(summary).map(item => [
        item.target_id,
        item.description,
        item.node_id,
        item.agent_ids.join(", ")
      ]);
      const agentBlocks = (summary.agents || []).map(agent => `
        <div class="route-agent">
          <h3>${escapeHtml(agent.agent_id)}</h3>
          ${definitionList({
            route_node_ids: (agent.route_node_ids || []).join(", "),
            route_viewpoint_ids: (agent.route_viewpoint_ids || []).join("\n"),
            edge_distances: (agent.edge_distances || []).map(formatNumber).join(", "),
            path_distance: formatNumber(agent.path_distance)
          })}
        </div>
      `).join("");
      return `
        <div class="route-summary">
          ${definitionList({
            test_case: summary.test_case,
            total_distance: formatNumber(summary.total_distance)
          })}
          <div>
            <h3>Target viewpoint indices</h3>
            ${table(["target", "description", "node", "found by"], targetRows)}
          </div>
          <div>
            <h3>Agent Legend</h3>
            ${routeAgentLegendHtml(summary)}
          </div>
          ${agentBlocks}
        </div>
      `;
    }

    function routeTargetRows(summary) {
      return Object.entries(summary.target_node_ids_by_target_id || {})
        .sort((a, b) => String(a[0]).localeCompare(String(b[0])))
        .map(([targetId, nodeId]) => ({
          target_id: targetId,
          description: targetDescription(targetId),
          node_id: nodeId,
          agent_ids: routeAgentsForNode(summary, nodeId)
        }));
    }

    function routeAgentsForNode(summary, nodeId) {
      return (summary.agents || [])
        .filter(agent => (agent.route_node_ids || []).some(routeNodeId => Number(routeNodeId) === Number(nodeId)))
        .map(agent => agent.agent_id);
    }

    function routeAgentLegendRows(summary) {
      return (summary.agents || []).map((agent, agentIndex) => ({
        agent_id: agent.agent_id,
        color: routeAgentColor(agentIndex)
      }));
    }

    function routeAgentLegendHtml(summary) {
      const rows = routeAgentLegendRows(summary);
      if (!rows.length) return "<p style=\"margin:0;color:var(--muted);font-size:13px;\">No agents.</p>";
      return `<div class="agent-legend">${rows.map(item => `
        <div class="agent-legend-row">
          <span class="swatch" style="background:${escapeAttr(item.color)};"></span>
          <span>${escapeHtml(item.agent_id)}</span>
        </div>
      `).join("")}</div>`;
    }

    function routeAgentColor(agentIndex) {
      return ROUTE_COLORS[agentIndex % ROUTE_COLORS.length];
    }

    function renderRouteSelection(solution) {
      const target = document.getElementById("selection");
      if (!selected || selected.kind !== "route-node") {
        target.innerHTML = "<p style=\"margin:0;color:var(--muted);font-size:13px;\">Click a route node in the graph.</p>";
        return;
      }
      const nodeId = Number(selected.node_id);
      const node = payload.environment_graph.nodes.find(item => Number(item.node_id) === nodeId);
      const targetRows = routeTargetRows(solution.summary)
        .filter(item => Number(item.node_id) === nodeId);
      const targetIds = targetRows.map(item => item.target_id);
      const targetDescriptions = targetRows
        .map(item => `${item.target_id}: ${item.description}`)
        .join("\n");
      const visits = (solution.summary.agents || []).flatMap(agent => {
        return (agent.route_node_ids || [])
          .map((routeNodeId, routeIndex) => ({ routeNodeId, routeIndex }))
          .filter(item => Number(item.routeNodeId) === nodeId)
          .map(item => `${agent.agent_id}: step ${item.routeIndex}`);
      });
      target.innerHTML = definitionList({
        node_id: nodeId,
        map_x: formatNumber(node.x),
        map_y: formatNumber(node.y),
        target_ids: targetIds.join(", "),
        target_descriptions: targetDescriptions,
        route_visits: visits.join(", ")
      });
    }

    function renderRouteGraph(solution) {
      while (graph.firstChild) graph.removeChild(graph.firstChild);
      const width = graph.clientWidth || 900;
      const height = graph.clientHeight || 560;
      graph.setAttribute("viewBox", `0 0 ${width} ${height}`);
      const environment = payload.environment_graph;
      const projection = routeProjection(environment, width, height);
      const positions = routePositions(environment.nodes, projection);
      const contentBounds = computeRouteContentBounds(solution, positions, projection);

      const defs = svgEl("defs", {});
      graph.appendChild(defs);
      (solution.summary.agents || []).forEach((agent, agentIndex) => {
        appendRouteArrowMarker(
          defs,
          routeArrowMarkerId(agentIndex),
          routeAgentColor(agentIndex)
        );
      });

      const viewportLayer = svgEl("g", {});
      graph.appendChild(viewportLayer);

      if (showHouseTexture && environment.house_texture) {
        appendHouseTexture(viewportLayer, environment, projection);
      }

      const edgeLayer = svgEl("g", {});
      viewportLayer.appendChild(edgeLayer);
      for (const edge of environment.edges) {
        const source = positions.get(String(edge.i));
        const target = positions.get(String(edge.j));
        edgeLayer.appendChild(svgEl("line", {
          class: "route-environment-edge",
          x1: source.x,
          y1: source.y,
          x2: target.x,
          y2: target.y
        }));
      }

      const nodeLayer = svgEl("g", {});
      viewportLayer.appendChild(nodeLayer);
      for (const node of environment.nodes) {
        const position = positions.get(String(node.node_id));
        const marker = svgEl("circle", {
          class: routeNodeClass("route-node", node.node_id),
          cx: position.x,
          cy: position.y,
          r: 4
        });
        marker.addEventListener("click", event => selectRouteNode(event, node.node_id));
        const title = svgEl("title", {});
        title.textContent = `node ${node.node_id}`;
        marker.appendChild(title);
        nodeLayer.appendChild(marker);
      }

      const routeLayer = svgEl("g", {});
      viewportLayer.appendChild(routeLayer);
      (solution.summary.agents || []).forEach((agent, agentIndex) => {
        const color = routeAgentColor(agentIndex);
        const routeNodeIds = (agent.route_node_ids || []).map(Number);
        const routePoints = routeNodeIds.map(nodeId => positions.get(String(nodeId)));
        routePoints.slice(0, -1).forEach((point, routeIndex) => {
          const nextNodeId = routeNodeIds[routeIndex + 1];
          if (Number(routeNodeIds[routeIndex]) === Number(nextNodeId)) return;
          const nextPoint = routePoints[routeIndex + 1];
          if (sameRoutePoint(point, nextPoint)) return;
          const segment = routeSegmentEndpoints(
            point,
            nextPoint,
            routeIndex === 0 ? 8 : 6,
            10
          );
          const line = svgEl("line", {
            class: "route-line",
            x1: segment.x1,
            y1: segment.y1,
            x2: segment.x2,
            y2: segment.y2,
            stroke: color,
            "marker-end": `url(#${routeArrowMarkerId(agentIndex)})`
          });
          const title = svgEl("title", {});
          title.textContent = `${agent.agent_id} step ${routeIndex} to ${routeIndex + 1}`;
          line.appendChild(title);
          routeLayer.appendChild(line);
        });
        routePoints.forEach((point, routeIndex) => {
          const nodeId = routeNodeIds[routeIndex];
          const circle = svgEl("circle", {
            class: routeNodeClass(
              routeIndex === 0 ? "route-start-marker" : "route-step-marker",
              nodeId
            ),
            cx: point.x,
            cy: point.y,
            r: routeIndex === 0 ? 8 : 6,
            fill: color
          });
          circle.addEventListener("click", event => selectRouteNode(event, nodeId));
          const circleTitle = svgEl("title", {});
          circleTitle.textContent = `${agent.agent_id} step ${routeIndex}: node ${nodeId}`;
          circle.appendChild(circleTitle);
          routeLayer.appendChild(circle);
        });
      });

      const targetLayer = svgEl("g", {});
      viewportLayer.appendChild(targetLayer);
      for (const routeTarget of routeTargetRows(solution.summary)) {
        const position = positions.get(String(routeTarget.node_id));
        const star = svgEl("polygon", {
          class: routeNodeClass("route-target-marker", routeTarget.node_id),
          points: starPoints(position.x, position.y, 12, 5)
        });
        star.addEventListener("click", event => selectRouteNode(event, routeTarget.node_id));
        const title = svgEl("title", {});
        title.textContent = `target ${routeTarget.target_id}: ${routeTarget.description}; node ${routeTarget.node_id}; agents ${routeTarget.agent_ids.join(", ")}`;
        star.appendChild(title);
        targetLayer.appendChild(star);
        const label = svgEl("text", {
          x: position.x + 12,
          y: position.y - 10,
          "font-size": 12,
          "font-weight": 700,
          fill: "#111827",
          "paint-order": "stroke",
          stroke: "white",
          "stroke-width": 4
        });
        label.textContent = `${routeTarget.target_id}`;
        targetLayer.appendChild(label);
      }
      viewportLayer.setAttribute(
        "transform",
        viewportTransform(getViewportState(solutionViewportKey(solution), width, height, contentBounds))
      );
    }

    function appendHouseTexture(viewportLayer, environment, projection) {
      const texture = environment.house_texture;
      const image = svgEl("image", {
        href: texture.url,
        x: projection.offsetX,
        y: projection.offsetY,
        width: projection.usedWidth,
        height: projection.usedHeight,
        preserveAspectRatio: "none",
        "pointer-events": "none"
      });
      viewportLayer.appendChild(image);
    }

    function appendRouteArrowMarker(defs, markerId, color) {
      const marker = svgEl("marker", {
        id: markerId,
        viewBox: "0 0 8 8",
        markerWidth: 3,
        markerHeight: 3,
        refX: 7,
        refY: 4,
        orient: "auto",
        markerUnits: "strokeWidth"
      });
      marker.appendChild(svgEl("path", {
        d: "M 0 0 L 8 4 L 0 8 z",
        fill: color
      }));
      defs.appendChild(marker);
    }

    function routeArrowMarkerId(agentIndex) {
      return `route-arrow-${agentIndex}`;
    }

    function routeNodeClass(baseClass, nodeId) {
      return `${baseClass} ${isSelectedRouteNode(nodeId) ? "route-selected" : ""}`;
    }

    function isSelectedRouteNode(nodeId) {
      return selected
        && selected.kind === "route-node"
        && Number(selected.node_id) === Number(nodeId);
    }

    function selectRouteNode(event, nodeId) {
      event.stopPropagation();
      selected = { kind: "route-node", node_id: Number(nodeId) };
      render();
    }

    function routeSegmentEndpoints(source, target, startPadding, endPadding) {
      const dx = target.x - source.x;
      const dy = target.y - source.y;
      const length = Math.hypot(dx, dy);
      const ux = dx / length;
      const uy = dy / length;
      return {
        x1: source.x + ux * startPadding,
        y1: source.y + uy * startPadding,
        x2: target.x - ux * endPadding,
        y2: target.y - uy * endPadding
      };
    }

    function renderGraph(step) {
      while (graph.firstChild) graph.removeChild(graph.firstChild);
      const width = graph.clientWidth || 900;
      const height = graph.clientHeight || 560;
      graph.setAttribute("viewBox", `0 0 ${width} ${height}`);

      const layoutNodes = step.layout.nodes;
      const graphEdges = graphVisibleEdges(step);
      const hypothesisEdgeById = new Map(step.hypothesis.edges.map(edge => [edgeKey(edge.i, edge.j), edge]));
      const graphState = buildGraphRenderState(step, width, height);
      const environment = graphState.environment;
      const projection = graphState.projection;
      const positions = graphState.positions;
      const contentBounds = graphState.contentBounds;
      const viewportLayer = svgEl("g", {});
      graph.appendChild(viewportLayer);

      if (showHouseTexture && environment.house_texture) {
        appendHouseTexture(viewportLayer, environment, projection);
      }

      const regionLayer = svgEl("g", {});
      viewportLayer.appendChild(regionLayer);
      for (const node of layoutNodes.filter(item => item.type === "region" && isAssignedRegion(item)).sort(byId)) {
        const geometry = graphState.regionGeometries.get(String(node.id));
        const center = geometry.center;
        const group = svgEl("g", {
          class: `node region ${isSelectedNode(node.id) ? "selected" : ""}`
        });
        group.addEventListener("click", event => {
          event.stopPropagation();
          selected = { kind: "node", id: node.id };
          render();
        });
        const title = svgEl("title", {});
        title.textContent = `${node.type} ${node.id}: ${node.label}`;
        group.appendChild(title);
        const color = regionColor(node.id);
        for (const component of geometry.components) {
          group.appendChild(svgEl("path", {
            class: "region-boundary",
            d: component.path,
            fill: color,
            stroke: color
          }));
        }
        const idText = svgEl("text", {
          x: center.x,
          y: center.y + 4,
          "text-anchor": "middle",
          "font-weight": 700
        });
        idText.textContent = String(node.id);
        group.appendChild(idText);
        regionLayer.appendChild(group);
      }

      const edgeLayer = svgEl("g", {});
      viewportLayer.appendChild(edgeLayer);
      const arrivalEdgeLayer = svgEl("g", {});
      viewportLayer.appendChild(arrivalEdgeLayer);
      const arrivalEdgeKeys = agentArrivalEdgeKeys(step);
      for (const edge of graphEdges) {
        const source = positions.get(String(edge.i));
        const target = positions.get(String(edge.j));
        const hyp = hypothesisEdgeById.get(edgeKey(edge.i, edge.j)) || edge;
        const isArrivalEdge = arrivalEdgeKeys.has(edgeKey(edge.i, edge.j));
        includeGraphPoint(contentBounds, source.x, source.y, 8);
        includeGraphPoint(contentBounds, target.x, target.y, 8);
        const edgeGroup = svgEl("g", {
          class: `edge ${edge.type === "vz" ? "vz" : "vv"} ${edge.grounded ? "" : "ungrounded"} ${isArrivalEdge ? "arrival" : ""} ${isSelectedEdge(edge) ? "selected" : ""}`
        });
        edgeGroup.addEventListener("click", () => {
          selected = { kind: "edge", i: edge.i, j: edge.j };
          render();
        });
        edgeGroup.appendChild(svgEl("line", {
          x1: source.x,
          y1: source.y,
          x2: target.x,
          y2: target.y
        }));
        const midpoint = { x: (source.x + target.x) / 2, y: (source.y + target.y) / 2 };
        includeGraphPoint(contentBounds, midpoint.x, midpoint.y, 18);
        const label = svgEl("text", {
          x: midpoint.x,
          y: midpoint.y - 5,
          "text-anchor": "middle",
          "font-size": 10,
          fill: "#475467",
          "paint-order": "stroke",
          stroke: "white",
          "stroke-width": 3
        });
        label.textContent = edgeLabel(hyp);
        edgeGroup.appendChild(label);
        (isArrivalEdge ? arrivalEdgeLayer : edgeLayer).appendChild(edgeGroup);
      }

      const nodeLayer = svgEl("g", {});
      viewportLayer.appendChild(nodeLayer);
      for (const node of layoutNodes.filter(item => item.type === "viewpoint").sort(byId)) {
        const pos = positions.get(String(node.id));
        const currentAgent = agentAtNode(step, node.id);
        includeGraphPoint(contentBounds, pos.x, pos.y, currentAgent ? 42 : 22);
        const group = svgEl("g", {
          class: `node viewpoint ${isSelectedNode(node.id) ? "selected" : ""}`
        });
        group.addEventListener("click", event => {
          event.stopPropagation();
          selected = { kind: "node", id: node.id };
          render();
        });
        group.appendChild(svgEl("circle", {
          cx: pos.x,
          cy: pos.y,
          r: currentAgent ? 20 : 16,
          fill: node.grounded ? "var(--grounded)" : "var(--viewpoint)",
          stroke: currentAgent ? "var(--current)" : "#ffffff",
          "stroke-width": currentAgent ? 5 : 2
        }));
        const title = svgEl("title", {});
        title.textContent = `${node.type} ${node.id}: ${node.label}`;
        group.appendChild(title);
        const idText = svgEl("text", {
          x: pos.x,
          y: pos.y + 4,
          "text-anchor": "middle",
          "font-weight": 700
        });
        idText.textContent = String(node.id);
        group.appendChild(idText);
        if (currentAgent) {
          const agentText = svgEl("text", {
            x: pos.x,
            y: pos.y - 25,
            "text-anchor": "middle",
            "font-weight": 700,
            fill: "var(--current)"
          });
          agentText.textContent = currentAgent;
          group.appendChild(agentText);
        }
        nodeLayer.appendChild(group);
      }
      viewportLayer.setAttribute("transform", viewportTransform(getViewportState(stepViewportKey(step), width, height, contentBounds)));
    }

    function buildGraphRenderState(step, width, height) {
      const environment = payload.environment_graph;
      const projection = routeProjection(environment, width, height);
      const positions = routePositions(environment.nodes, projection);
      const regionGeometries = new Map();
      const contentBounds = emptyBounds();
      const graphEdges = graphVisibleEdges(step);
      includeGraphPoint(contentBounds, projection.offsetX, projection.offsetY, 0);
      includeGraphPoint(
        contentBounds,
        projection.offsetX + projection.usedWidth,
        projection.offsetY + projection.usedHeight,
        0
      );

      const regionNodes = step.layout.nodes
        .filter(item => item.type === "region" && isAssignedRegion(item))
        .sort(byId);
      for (const region of regionNodes) {
        const geometry = regionGeometry(region, positions, environment);
        regionGeometries.set(String(region.id), geometry);
        positions.set(String(region.id), geometry.center);
        includeRegionGeometryBounds(contentBounds, geometry);
      }

      for (const edge of graphEdges) {
        const source = positions.get(String(edge.i));
        const target = positions.get(String(edge.j));
        includeGraphPoint(contentBounds, source.x, source.y, 8);
        includeGraphPoint(contentBounds, target.x, target.y, 8);
        includeGraphPoint(contentBounds, (source.x + target.x) / 2, (source.y + target.y) / 2, 18);
      }
      for (const node of step.layout.nodes.filter(item => item.type === "viewpoint").sort(byId)) {
        const pos = positions.get(String(node.id));
        includeGraphPoint(contentBounds, pos.x, pos.y, agentAtNode(step, node.id) ? 42 : 22);
      }

      return {
        environment: environment,
        projection: projection,
        positions: positions,
        regionGeometries: regionGeometries,
        contentBounds: contentBounds
      };
    }

    function includeRegionGeometryBounds(bounds, geometry) {
      for (const point of geometry.points) {
        includeGraphPoint(bounds, point.x, point.y, 8);
      }
      includeGraphPoint(bounds, geometry.center.x, geometry.center.y, 18);
    }

    function regionColor(regionId) {
      const index = Math.abs(Number(regionId)) % REGION_COLORS.length;
      return REGION_COLORS[index];
    }

    function agentArrivalEdgeKeys(step) {
      const result = new Set();
      if (stepPosition === 0) return result;
      const previousStep = payload.steps[stepPosition - 1];
      const layoutEdgeKeys = new Set(step.layout.edges.map(edge => edgeKey(edge.i, edge.j)));
      for (const [agentId, currentViewpointId] of Object.entries(step.layout.agent_current_vp_ids || {})) {
        const previousViewpointId = previousStep.layout.agent_current_vp_ids[agentId];
        if (Number(previousViewpointId) === Number(currentViewpointId)) continue;
        const key = edgeKey(previousViewpointId, currentViewpointId);
        if (layoutEdgeKeys.has(key)) result.add(key);
      }
      return result;
    }

    function regionTightBoundary(region, positions, environment) {
      const assignedIds = assignedRegionViewpointIds(region);
      const primitives = regionBoundaryPrimitives(assignedIds, positions, environment);
      const bounds = emptyBounds();
      for (const id of assignedIds) {
        const center = positions.get(id);
        includeGraphPoint(bounds, center.x, center.y, REGION_BOUNDARY_NODE_RADIUS + REGION_BOUNDARY_CELL_SIZE * 2);
      }
      const components = marchingSquaresRegionBoundary(
        primitives,
        bounds,
        REGION_BOUNDARY_CELL_SIZE
      );
      const points = components.flatMap(component => component.points);
      return {
        kind: "boundary",
        components: components,
        points: points,
        center: assignedRegionCenter(assignedIds, positions)
      };
    }

    function regionBoundaryPrimitives(assignedIds, positions, environment) {
      const assigned = new Set(assignedIds);
      const primitives = assignedIds.map(id => ({
        kind: "disk",
        center: positions.get(id),
        radius: REGION_BOUNDARY_NODE_RADIUS
      }));
      for (const edge of environment.edges) {
        if (!assigned.has(String(edge.i)) || !assigned.has(String(edge.j))) continue;
        primitives.push({
          kind: "capsule",
          source: positions.get(String(edge.i)),
          target: positions.get(String(edge.j)),
          radius: REGION_BOUNDARY_CORRIDOR_RADIUS
        });
      }
      return primitives;
    }

    function marchingSquaresRegionBoundary(primitives, bounds, cellSize) {
      const minX = bounds.minX;
      const minY = bounds.minY;
      const columnCount = Math.ceil((bounds.maxX - bounds.minX) / cellSize);
      const rowCount = Math.ceil((bounds.maxY - bounds.minY) / cellSize);
      const values = [];
      for (let row = 0; row <= rowCount; row += 1) {
        const valueRow = [];
        for (let column = 0; column <= columnCount; column += 1) {
          valueRow.push(signedDistanceToRegion(
            { x: minX + column * cellSize, y: minY + row * cellSize },
            primitives
          ));
        }
        values.push(valueRow);
      }

      const segments = [];
      for (let row = 0; row < rowCount; row += 1) {
        for (let column = 0; column < columnCount; column += 1) {
          const x0 = minX + column * cellSize;
          const y0 = minY + row * cellSize;
          const corners = {
            topLeft: { x: x0, y: y0, value: values[row][column] },
            topRight: { x: x0 + cellSize, y: y0, value: values[row][column + 1] },
            bottomRight: { x: x0 + cellSize, y: y0 + cellSize, value: values[row + 1][column + 1] },
            bottomLeft: { x: x0, y: y0 + cellSize, value: values[row + 1][column] }
          };
          const caseIndex =
            (corners.topLeft.value <= 0 ? 1 : 0) |
            (corners.topRight.value <= 0 ? 2 : 0) |
            (corners.bottomRight.value <= 0 ? 4 : 0) |
            (corners.bottomLeft.value <= 0 ? 8 : 0);
          for (const segment of marchingSquareSegments(caseIndex, corners)) {
            segments.push(segment);
          }
        }
      }
      return traceBoundaryContours(segments);
    }

    function assignedRegionViewpointIds(region) {
      return (region.assigned_viewpoint_ids || []).map(String).sort(numericStringCompare);
    }

    function isAssignedRegion(node) {
      return assignedRegionViewpointIds(node).length > 0;
    }

    function graphVisibleNodeIds(step) {
      return new Set(step.layout.nodes
        .filter(node => node.type !== "region" || isAssignedRegion(node))
        .map(node => String(node.id)));
    }

    function graphVisibleEdges(step) {
      const visibleNodeIds = graphVisibleNodeIds(step);
      return step.layout.edges.filter(edge => (
        visibleNodeIds.has(String(edge.i)) && visibleNodeIds.has(String(edge.j))
      ));
    }

    function regionGeometry(region, positions, environment) {
      return regionTightBoundary(region, positions, environment);
    }

    function assignedRegionCenter(assignedIds, positions) {
      const total = assignedIds.reduce((acc, id) => {
        const point = positions.get(id);
        return { x: acc.x + point.x, y: acc.y + point.y };
      }, { x: 0, y: 0 });
      return {
        x: total.x / assignedIds.length,
        y: total.y / assignedIds.length
      };
    }

    function signedDistanceToRegion(point, primitives) {
      return Math.min(...primitives.map(primitive => {
        if (primitive.kind === "disk") {
          return Math.hypot(point.x - primitive.center.x, point.y - primitive.center.y) - primitive.radius;
        }
        return distanceToSegment(point, primitive.source, primitive.target) - primitive.radius;
      }));
    }

    function distanceToSegment(point, source, target) {
      const dx = target.x - source.x;
      const dy = target.y - source.y;
      const lengthSquared = dx * dx + dy * dy;
      const t = clamp(
        ((point.x - source.x) * dx + (point.y - source.y) * dy) / lengthSquared,
        0,
        1
      );
      return Math.hypot(point.x - (source.x + t * dx), point.y - (source.y + t * dy));
    }

    function marchingSquareSegments(caseIndex, corners) {
      const edgePoints = {
        top: interpolateBoundaryPoint(corners.topLeft, corners.topRight),
        right: interpolateBoundaryPoint(corners.topRight, corners.bottomRight),
        bottom: interpolateBoundaryPoint(corners.bottomLeft, corners.bottomRight),
        left: interpolateBoundaryPoint(corners.topLeft, corners.bottomLeft)
      };
      const segmentEdgesByCase = {
        0: [],
        1: [["left", "top"]],
        2: [["top", "right"]],
        3: [["left", "right"]],
        4: [["right", "bottom"]],
        5: [["left", "bottom"], ["top", "right"]],
        6: [["top", "bottom"]],
        7: [["left", "bottom"]],
        8: [["bottom", "left"]],
        9: [["top", "bottom"]],
        10: [["top", "left"], ["right", "bottom"]],
        11: [["right", "bottom"]],
        12: [["right", "left"]],
        13: [["top", "right"]],
        14: [["left", "top"]],
        15: []
      };
      return segmentEdgesByCase[caseIndex].map(([sourceEdge, targetEdge]) => ({
        source: edgePoints[sourceEdge],
        target: edgePoints[targetEdge]
      }));
    }

    function interpolateBoundaryPoint(source, target) {
      const t = source.value / (source.value - target.value);
      return {
        x: source.x + (target.x - source.x) * t,
        y: source.y + (target.y - source.y) * t
      };
    }

    function traceBoundaryContours(segments) {
      const adjacency = new Map();
      segments.forEach((segment, index) => {
        addContourAdjacency(adjacency, contourPointKey(segment.source), index);
        addContourAdjacency(adjacency, contourPointKey(segment.target), index);
      });

      const used = new Set();
      const contours = [];
      segments.forEach((segment, index) => {
        if (used.has(index)) return;
        used.add(index);
        const points = [segment.source, segment.target];
        const startKey = contourPointKey(segment.source);
        let currentKey = contourPointKey(segment.target);
        while (currentKey !== startKey) {
          const nextIndex = adjacency.get(currentKey).find(candidate => !used.has(candidate));
          used.add(nextIndex);
          const nextSegment = segments[nextIndex];
          const nextPoint = contourPointKey(nextSegment.source) === currentKey
            ? nextSegment.target
            : nextSegment.source;
          points.push(nextPoint);
          currentKey = contourPointKey(nextPoint);
        }
        contours.push({
          points: points,
          path: contourPath(points)
        });
      });
      return contours;
    }

    function addContourAdjacency(adjacency, key, segmentIndex) {
      if (!adjacency.has(key)) adjacency.set(key, []);
      adjacency.get(key).push(segmentIndex);
    }

    function contourPointKey(point) {
      return `${point.x.toFixed(3)},${point.y.toFixed(3)}`;
    }

    function contourPath(points) {
      const [first, ...rest] = points;
      return `M ${first.x} ${first.y} ${rest.map(point => `L ${point.x} ${point.y}`).join(" ")} Z`;
    }

    function renderSelection(step) {
      const target = document.getElementById("selection");
      if (!selected) {
        target.innerHTML = "<p style=\"margin:0;color:var(--muted);font-size:13px;\">Click a node or edge in the graph.</p>";
        return;
      }
      if (selected.kind === "node") {
        const layout = step.layout.nodes.find(node => String(node.id) === String(selected.id));
        const hyp = step.hypothesis.nodes.find(node => String(node.id) === String(selected.id));
        target.innerHTML = definitionList({
          id: layout.id,
          type: layout.type,
          label: hyp.label,
          grounded: hyp.grounded,
          exist_prob: formatNumber(hyp.exist_prob),
          node_visit_times: hyp.node_visit_times,
          current_agent: agentAtNode(step, layout.id) || "",
          assigned_viewpoint_ids: (layout.assigned_viewpoint_ids || []).join(", "),
          target_probs: formatObject(hyp.target_probs),
          raw_target_probs: formatObject(hyp.raw_target_probs)
        });
      } else {
        const hyp = step.hypothesis.edges.find(edge => edgeKey(edge.i, edge.j) === edgeKey(selected.i, selected.j));
        target.innerHTML = definitionList({
          edge: `${hyp.i} - ${hyp.j}`,
          type: hyp.type,
          grounded: hyp.grounded,
          distance_mean: formatNumber(hyp.distance_mean),
          distance_var: formatNumber(hyp.distance_var),
          cond_exist_prob: formatNumber(hyp.cond_exist_prob),
          exist_prob: formatNumber(hyp.exist_prob)
        });
      }
    }

    function renderSummary(step) {
      const targetFound = formatObject(step.hypothesis.target_found);
      const agents = formatObject(step.layout.agent_current_vp_ids);
      const targets = step.hypothesis.targets
        .map(target => `${target.target_id}: ${target.description}`)
        .join("\n");
      document.getElementById("summary").innerHTML = definitionList({
        step_index: step.step_index,
        observation_step: step.layout.observation_step,
        nodes: step.layout.nodes.length,
        edges: step.layout.edges.length,
        current_agents: agents,
        target_found: targetFound,
        targets: targets
      });
    }

    function renderTargetDetections(step) {
      const rows = normalizedDetectionRows(step)
        .filter(item => item.raw_found)
        .map(item => [
          item.agent_id,
          item.target_id,
          item.description,
          item.verification,
          formatNumber(item.score),
          formatNumber(item.score_threshold),
          formatNumber(item.target_center_x)
        ]);
      const target = document.getElementById("targetDetections");
      if (!rows.length) {
        target.innerHTML = "<p style=\"margin:0;color:var(--muted);font-size:13px;\">No target detections in this step.</p>";
        return;
      }
      target.innerHTML = table(["agent", "target", "description", "verification", "score", "threshold", "center x"], rows);
    }

    function renderUnassignedRegions(step) {
      const hypById = new Map(step.hypothesis.nodes.map(node => [String(node.id), node]));
      const rows = step.layout.nodes
        .filter(node => node.type === "region" && !isAssignedRegion(node))
        .sort(byId)
        .map(node => {
          const hyp = hypById.get(String(node.id)) || node;
          return `
            <tr data-node-id="${escapeAttr(node.id)}">
              <td>${escapeHtml(String(node.id))}</td>
              <td>${escapeHtml(shortLabel(node.label, 34))}</td>
              <td>${escapeHtml(formatNumber(hyp.exist_prob))}</td>
              <td>${escapeHtml(formatObject(hyp.target_probs))}</td>
              <td>${escapeHtml(formatObject(hyp.raw_target_probs))}</td>
            </tr>
          `;
        });
      const target = document.getElementById("unassignedRegions");
      if (!rows.length) {
        target.innerHTML = "<p style=\"margin:0;color:var(--muted);font-size:13px;\">No unassigned regions.</p>";
        return;
      }
      target.innerHTML = `<table><thead><tr><th>id</th><th>label</th><th>exist</th><th>target probs</th><th>raw target probs</th></tr></thead><tbody>${rows.join("")}</tbody></table>`;
      for (const row of target.querySelectorAll("tr[data-node-id]")) {
        row.addEventListener("click", () => {
          selected = { kind: "node", id: row.dataset.nodeId };
          render();
        });
      }
    }

    function renderNodeTable(step) {
      const rows = step.hypothesis.nodes
        .slice()
        .sort((a, b) => byId(a, b))
        .map(node => [
          node.id,
          node.type,
          shortLabel(node.label, 30),
          node.grounded,
          formatNumber(node.exist_prob),
          formatObject(node.target_probs),
          formatObject(node.raw_target_probs)
        ]);
      document.getElementById("nodeTable").innerHTML =
        table(["id", "type", "label", "grounded", "exist", "target probs", "raw target probs"], rows);
    }

    function renderEdgeTable(step) {
      const rows = step.hypothesis.edges
        .slice()
        .sort((a, b) => edgeKey(a.i, a.j).localeCompare(edgeKey(b.i, b.j)))
        .map(edge => [
          `${edge.i}-${edge.j}`,
          edge.type,
          edge.grounded,
          formatNumber(edge.distance_mean),
          formatNumber(edge.exist_prob)
        ]);
      document.getElementById("edgeTable").innerHTML =
        table(["edge", "type", "grounded", "dist", "exist"], rows);
    }

    function renderDetections(step) {
      const rows = normalizedDetectionRows(step).map(item => [
        item.agent_id,
        item.target_id,
        item.found,
        item.verification,
        formatNumber(item.target_center_x)
      ]);
      document.getElementById("detections").innerHTML =
        table(["agent", "target", "found", "verification", "center x"], rows);
    }

    function normalizedDetectionRows(step) {
      const verificationChecks = openVocabularyVerificationChecks(step);
      return (step.detection.detections || []).flatMap(detection => {
        if (Array.isArray(detection.found_target_indices)) {
          return detection.found_target_indices.map((targetId, index) =>
            normalizedDetectionRow({
              step: step,
              verificationChecks: verificationChecks,
              agentId: detection.agent_id,
              targetId: targetId,
              rawFound: true,
              targetCenterX: detection.target_center_xs ? detection.target_center_xs[index] : ""
            })
          );
        }
        return (detection.target_indices || []).map((targetId, index) =>
          normalizedDetectionRow({
            step: step,
            verificationChecks: verificationChecks,
            agentId: detection.agent_id,
            targetId: targetId,
            rawFound: Boolean(detection.founds[index]),
            targetCenterX: detection.target_center_xs ? detection.target_center_xs[index] : ""
          })
        );
      });
    }

    function normalizedDetectionRow({ step, verificationChecks, agentId, targetId, rawFound, targetCenterX }) {
      const check = verificationChecks.get(verificationKey(agentId, targetId));
      const verification = verificationStatus(check);
      return {
        agent_id: agentId,
        target_id: String(targetId),
        description: targetDescriptionFromStep(step, targetId),
        raw_found: rawFound,
        found: verifiedFound(rawFound, verification),
        verification: verification,
        score: check ? check.score : "",
        score_threshold: check ? check.score_threshold : "",
        target_center_x: targetCenterX
      };
    }

    function openVocabularyVerificationChecks(step) {
      const checks = new Map();
      for (const check of ((step.open_vocab_verification || {}).checks || [])) {
        checks.set(verificationKey(check.agent_id, check.target_id), check);
      }
      return checks;
    }

    function verificationKey(agentId, targetId) {
      return `${String(agentId)}\u0000${String(targetId)}`;
    }

    function verificationStatus(check) {
      if (!check) return "unverified";
      return check.accepted ? "accepted" : "rejected";
    }

    function verifiedFound(rawFound, verification) {
      if (verification === "accepted") return true;
      if (verification === "rejected") return false;
      return rawFound;
    }

    function targetDescriptionFromStep(step, targetId) {
      const target = (step.hypothesis.targets || [])
        .find(item => String(item.target_id) === String(targetId));
      return target ? target.description : "";
    }

    function targetDescription(targetId) {
      for (const step of payload.steps || []) {
        const description = targetDescriptionFromStep(step, targetId);
        if (description) return description;
      }
      return "";
    }

    function renderImages(step) {
      document.getElementById("images").innerHTML = step.observation_images.map(image => `
        <figure>
          <img src="${escapeAttr(image.url)}" alt="${escapeAttr(image.agent_id)} observation">
          <figcaption>${escapeHtml(image.agent_id)} observation</figcaption>
        </figure>
      `).join("");
    }

    function routeProjection(environment, width, height) {
      const padding = 48;
      const bounds = routeWorldBounds(environment);
      const minX = bounds.minX;
      const maxX = bounds.maxX;
      const minY = bounds.minY;
      const maxY = bounds.maxY;
      const scale = Math.min(
        (width - padding * 2) / (maxX - minX),
        (height - padding * 2) / (maxY - minY)
      );
      const usedWidth = (maxX - minX) * scale;
      const usedHeight = (maxY - minY) * scale;
      const offsetX = (width - usedWidth) / 2;
      const offsetY = (height - usedHeight) / 2;
      return {
        minX: minX,
        maxX: maxX,
        minY: minY,
        maxY: maxY,
        scale: scale,
        usedWidth: usedWidth,
        usedHeight: usedHeight,
        offsetX: offsetX,
        offsetY: offsetY,
        screenX: worldX => offsetX + (worldX - minX) * scale,
        screenY: worldY => height - offsetY - (worldY - minY) * scale
      };
    }

    function routeWorldBounds(environment) {
      const texture = environment.house_texture;
      if (texture) {
        return {
          minX: Number(texture.min_x),
          maxX: Number(texture.max_x),
          minY: Number(texture.min_y),
          maxY: Number(texture.max_y)
        };
      }
      const xs = environment.nodes.map(node => node.x);
      const ys = environment.nodes.map(node => node.y);
      return {
        minX: Math.min(...xs),
        maxX: Math.max(...xs),
        minY: Math.min(...ys),
        maxY: Math.max(...ys)
      };
    }

    function routePositions(nodes, projection) {
      const positions = new Map();
      for (const node of nodes) {
        positions.set(String(node.node_id), {
          x: projection.screenX(node.x),
          y: projection.screenY(node.y)
        });
      }
      return positions;
    }

    function sameRoutePoint(source, target) {
      return source.x === target.x && source.y === target.y;
    }

    function starPoints(cx, cy, outerRadius, innerRadius) {
      const points = [];
      for (let index = 0; index < 10; index += 1) {
        const radius = index % 2 === 0 ? outerRadius : innerRadius;
        const angle = -Math.PI / 2 + index * Math.PI / 5;
        points.push(`${cx + Math.cos(angle) * radius},${cy + Math.sin(angle) * radius}`);
      }
      return points.join(" ");
    }

    function definitionList(items) {
      return `<dl class="kv">${Object.entries(items).map(([key, value]) => `
        <dt>${escapeHtml(key)}</dt><dd>${escapeHtml(String(value))}</dd>
      `).join("")}</dl>`;
    }

    function table(headers, rows) {
      return `<table><thead><tr>${headers.map(h => `<th>${escapeHtml(h)}</th>`).join("")}</tr></thead>
        <tbody>${rows.map(row => `<tr>${row.map(cell => `<td>${escapeHtml(String(cell))}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
    }

    function svgEl(name, attrs) {
      const el = document.createElementNS("http://www.w3.org/2000/svg", name);
      for (const [key, value] of Object.entries(attrs)) {
        el.setAttribute(key, value);
      }
      return el;
    }

    function agentAtNode(step, nodeId) {
      for (const [agentId, viewpointId] of Object.entries(step.layout.agent_current_vp_ids || {})) {
        if (String(viewpointId) === String(nodeId)) return agentId;
      }
      return "";
    }

    function isSelectedNode(nodeId) {
      if (!selected) return false;
      return selected.kind === "node" && String(selected.id) === String(nodeId);
    }

    function isSelectedEdge(edge) {
      return selected && selected.kind === "edge" && edgeKey(selected.i, selected.j) === edgeKey(edge.i, edge.j);
    }

    function edgeKey(i, j) {
      const a = Number(i);
      const b = Number(j);
      return a < b ? `${a}:${b}` : `${b}:${a}`;
    }

    function edgeLabel(edge) {
      return edge.type;
    }

    function emptyBounds() {
      return {
        minX: Infinity,
        minY: Infinity,
        maxX: -Infinity,
        maxY: -Infinity
      };
    }

    function includeGraphPoint(bounds, x, y, padding) {
      bounds.minX = Math.min(bounds.minX, x - padding);
      bounds.minY = Math.min(bounds.minY, y - padding);
      bounds.maxX = Math.max(bounds.maxX, x + padding);
      bounds.maxY = Math.max(bounds.maxY, y + padding);
    }

    function computeGraphContentBounds(step, width, height) {
      return buildGraphRenderState(step, width, height).contentBounds;
    }

    function computeRouteContentBounds(solution, positions, projection) {
      const bounds = emptyBounds();
      const environment = payload.environment_graph;
      includeGraphPoint(bounds, projection.offsetX, projection.offsetY, 0);
      includeGraphPoint(
        bounds,
        projection.offsetX + projection.usedWidth,
        projection.offsetY + projection.usedHeight,
        0
      );
      for (const edge of environment.edges) {
        const source = positions.get(String(edge.i));
        const target = positions.get(String(edge.j));
        includeGraphPoint(bounds, source.x, source.y, 8);
        includeGraphPoint(bounds, target.x, target.y, 8);
      }
      for (const node of environment.nodes) {
        const position = positions.get(String(node.node_id));
        includeGraphPoint(bounds, position.x, position.y, 8);
      }
      for (const agent of solution.summary.agents || []) {
        (agent.route_node_ids || []).forEach((nodeId, routeIndex) => {
          const position = positions.get(String(nodeId));
          includeGraphPoint(bounds, position.x, position.y, routeIndex === 0 ? 12 : 10);
        });
      }
      for (const [targetId, nodeId] of Object.entries(solution.summary.target_node_ids_by_target_id || {})) {
        const position = positions.get(String(nodeId));
        includeGraphPoint(bounds, position.x, position.y, 30 + String(targetId).length * 7);
      }
      return bounds;
    }

    function stepViewportKey(step) {
      return `step:${step.step_index}`;
    }

    function solutionViewportKey(solution) {
      return `solution:${solution.id}`;
    }

    function currentViewportKey() {
      const solution = currentSolution();
      return solution ? solutionViewportKey(solution) : stepViewportKey(currentStep());
    }

    function renderCurrentGraph() {
      const solution = currentSolution();
      if (solution) {
        renderRouteGraph(solution);
      } else {
        renderGraph(currentStep());
      }
    }

    function viewportTransform(viewport) {
      return `translate(${viewport.translateX},${viewport.translateY}) scale(${viewport.scale})`;
    }

    function getViewportState(key, width, height, bounds) {
      const current = viewportStates.get(key);
      if (!current || (current.isDefault && (current.width !== width || current.height !== height))) {
        const fitted = fitViewportToBounds(bounds, width, height);
        viewportStates.set(key, fitted);
        return fitted;
      }
      return current;
    }

    function clearDefaultViewportStates() {
      for (const [key, viewport] of viewportStates.entries()) {
        if (viewport.isDefault) viewportStates.delete(key);
      }
    }

    function fitViewportToBounds(bounds, width, height) {
      const contentWidth = bounds.maxX - bounds.minX;
      const contentHeight = bounds.maxY - bounds.minY;
      const scale = clamp(
        Math.min((width - GRAPH_FIT_PADDING * 2) / contentWidth, (height - GRAPH_FIT_PADDING * 2) / contentHeight),
        GRAPH_MIN_SCALE,
        GRAPH_MAX_SCALE
      );
      return {
        scale: scale,
        translateX: width / 2 - ((bounds.minX + bounds.maxX) / 2) * scale,
        translateY: height / 2 - ((bounds.minY + bounds.maxY) / 2) * scale,
        width: width,
        height: height,
        isDefault: true
      };
    }

    function resetCurrentGraphViewport() {
      const width = graph.clientWidth || 900;
      const height = graph.clientHeight || 560;
      const solution = currentSolution();
      if (solution) {
        const projection = routeProjection(payload.environment_graph, width, height);
        const positions = routePositions(payload.environment_graph.nodes, projection);
        viewportStates.set(
          solutionViewportKey(solution),
          fitViewportToBounds(
            computeRouteContentBounds(solution, positions, projection),
            width,
            height
          )
        );
      } else {
        const step = currentStep();
        viewportStates.set(
          stepViewportKey(step),
          fitViewportToBounds(computeGraphContentBounds(step, width, height), width, height)
        );
      }
    }

    function zoomGraphAtCenter(factor) {
      const width = graph.clientWidth || 900;
      const height = graph.clientHeight || 560;
      zoomGraphAtPoint(factor, { x: width / 2, y: height / 2 });
    }

    function zoomGraphAtPoint(factor, anchor) {
      const key = currentViewportKey();
      const viewport = viewportStates.get(key);
      const scale = clamp(viewport.scale * factor, GRAPH_MIN_SCALE, GRAPH_MAX_SCALE);
      const anchorX = (anchor.x - viewport.translateX) / viewport.scale;
      const anchorY = (anchor.y - viewport.translateY) / viewport.scale;
      viewportStates.set(key, {
        scale: scale,
        translateX: anchor.x - anchorX * scale,
        translateY: anchor.y - anchorY * scale,
        width: viewport.width,
        height: viewport.height,
        isDefault: false
      });
      renderCurrentGraph();
    }

    function beginGraphPan(event) {
      const point = graphScreenPoint(event);
      const viewport = viewportStates.get(currentViewportKey());
      panState = {
        pointerId: event.pointerId,
        startX: point.x,
        startY: point.y,
        translateX: viewport.translateX,
        translateY: viewport.translateY
      };
      graph.setPointerCapture(event.pointerId);
      graph.classList.add("panning");
      event.preventDefault();
    }

    function updateGraphPan(event) {
      const point = graphScreenPoint(event);
      const key = currentViewportKey();
      const viewport = viewportStates.get(key);
      viewportStates.set(key, {
        scale: viewport.scale,
        translateX: panState.translateX + point.x - panState.startX,
        translateY: panState.translateY + point.y - panState.startY,
        width: viewport.width,
        height: viewport.height,
        isDefault: false
      });
    }

    function graphScreenPoint(event) {
      const point = graph.createSVGPoint();
      point.x = event.clientX;
      point.y = event.clientY;
      return point.matrixTransform(graph.getScreenCTM().inverse());
    }

    function byId(a, b) {
      return Number(a.id) - Number(b.id);
    }

    function numericStringCompare(a, b) {
      return Number(a) - Number(b);
    }

    function formatObject(value) {
      return Object.entries(value || {})
        .map(([key, item]) => `${key}: ${typeof item === "number" ? formatNumber(item) : item}`)
        .join(", ");
    }

    function formatNumber(value) {
      if (typeof value !== "number") return value;
      return Number.isInteger(value) ? String(value) : value.toFixed(4);
    }

    function shortLabel(value, maxLength) {
      const text = String(value);
      return text.length <= maxLength ? text : `${text.slice(0, maxLength - 1)}...`;
    }

    function clamp(value, min, max) {
      return Math.max(min, Math.min(max, value));
    }

    function escapeHtml(value) {
      return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
    }

    function escapeAttr(value) {
      return escapeHtml(value);
    }
  </script>
</body>
</html>
"""
