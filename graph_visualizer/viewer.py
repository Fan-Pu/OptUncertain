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
    .route-agent {
      border-top: 1px solid #eaecf0;
      padding-top: 10px;
    }
    .route-agent h3 {
      margin: 0 0 8px 0;
      font-size: 13px;
    }
    .region-hull {
      fill-opacity: 0.18;
      stroke-width: 2;
    }
    .selected line,
    .selected circle,
    .selected polygon {
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

    const graph = document.getElementById("graph");
    const solutionButtons = document.getElementById("solutionButtons");
    const graphZoomInButton = document.getElementById("graphZoomInButton");
    const graphZoomOutButton = document.getElementById("graphZoomOutButton");
    const graphResetViewButton = document.getElementById("graphResetViewButton");
    const houseTextureButton = document.getElementById("houseTextureButton");
    const prevButton = document.getElementById("prevButton");
    const nextButton = document.getElementById("nextButton");
    const stepLabel = document.getElementById("stepLabel");
    const selectionSection = document.getElementById("selectionSection");
    const summaryTitle = document.getElementById("summaryTitle");
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
        window.addEventListener("resize", renderCurrentGraph);
      });

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
      stepLabel.textContent = `Step ${stepPosition + 1} / ${payload.steps.length}`;
      renderGraph(step);
      renderSelection(step);
      renderSummary(step);
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
      nodeTableSection.hidden = false;
      edgeTableSection.hidden = false;
      detectionsSection.hidden = false;
      semanticSection.hidden = false;
      userMessageSection.hidden = false;
      summaryTitle.textContent = "Step Summary";
    }

    function renderSolutionDetails(solution) {
      selectionSection.hidden = false;
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
      const targetRows = Object.entries(summary.target_node_ids_by_target_id || {})
        .sort((a, b) => String(a[0]).localeCompare(String(b[0])))
        .map(([targetId, nodeId]) => [targetId, nodeId]);
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
            ${table(["target", "node"], targetRows)}
          </div>
          ${agentBlocks}
        </div>
      `;
    }

    function renderRouteSelection(solution) {
      const target = document.getElementById("selection");
      if (!selected || selected.kind !== "route-node") {
        target.innerHTML = "<p style=\"margin:0;color:var(--muted);font-size:13px;\">Click a route node in the graph.</p>";
        return;
      }
      const nodeId = Number(selected.node_id);
      const node = payload.environment_graph.nodes.find(item => Number(item.node_id) === nodeId);
      const targetIds = Object.entries(solution.summary.target_node_ids_by_target_id || {})
        .filter(([, targetNodeId]) => Number(targetNodeId) === nodeId)
        .map(([targetId]) => targetId);
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
      const colors = ["#d62728", "#1f77b4", "#2ca02c", "#ff7f0e", "#9467bd", "#17becf"];

      const defs = svgEl("defs", {});
      graph.appendChild(defs);
      (solution.summary.agents || []).forEach((agent, agentIndex) => {
        appendRouteArrowMarker(
          defs,
          routeArrowMarkerId(agentIndex),
          colors[agentIndex % colors.length]
        );
      });

      const viewportLayer = svgEl("g", {});
      graph.appendChild(viewportLayer);

      if (showHouseTexture) {
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
        const color = colors[agentIndex % colors.length];
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
      for (const [targetId, nodeId] of Object.entries(solution.summary.target_node_ids_by_target_id || {})) {
        const position = positions.get(String(nodeId));
        const star = svgEl("polygon", {
          class: routeNodeClass("route-target-marker", nodeId),
          points: starPoints(position.x, position.y, 12, 5)
        });
        star.addEventListener("click", event => selectRouteNode(event, nodeId));
        const title = svgEl("title", {});
        title.textContent = `target ${targetId}: node ${nodeId}`;
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
        label.textContent = String(targetId);
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
      const hypothesisEdgeById = new Map(step.hypothesis.edges.map(edge => [edgeKey(edge.i, edge.j), edge]));
      const environment = payload.environment_graph;
      const projection = routeProjection(environment, width, height);
      const positions = routePositions(environment.nodes, projection);
      const contentBounds = emptyBounds();
      const viewportLayer = svgEl("g", {});
      graph.appendChild(viewportLayer);
      includeGraphPoint(contentBounds, projection.offsetX, projection.offsetY, 0);
      includeGraphPoint(
        contentBounds,
        projection.offsetX + projection.usedWidth,
        projection.offsetY + projection.usedHeight,
        0
      );

      if (showHouseTexture) {
        appendHouseTexture(viewportLayer, environment, projection);
      }

      const regionLayer = svgEl("g", {});
      viewportLayer.appendChild(regionLayer);
      const regionMarkerGroups = [];
      for (const node of layoutNodes.filter(item => item.type === "region").sort(byId)) {
        const geometry = regionGeometry(node, positions);
        const center = geometry.center;
        positions.set(String(node.id), center);
        for (const point of geometry.points) {
          includeGraphPoint(contentBounds, point.x, point.y, 8);
        }
        includeGraphPoint(contentBounds, center.x, center.y, geometry.kind === "marker" ? 28 : 18);
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
        group.appendChild(svgEl("polygon", {
          class: "region-hull",
          points: geometry.points.map(point => `${point.x},${point.y}`).join(" "),
          fill: node.grounded ? "var(--grounded)" : "var(--region)",
          stroke: node.grounded ? "var(--grounded)" : "var(--region)"
        }));
        const idText = svgEl("text", {
          x: center.x,
          y: center.y + 4,
          "text-anchor": "middle",
          "font-weight": 700
        });
        idText.textContent = String(node.id);
        group.appendChild(idText);
        if (geometry.kind === "marker") {
          regionMarkerGroups.push(group);
        } else {
          regionLayer.appendChild(group);
        }
      }

      const edgeLayer = svgEl("g", {});
      viewportLayer.appendChild(edgeLayer);
      for (const edge of step.layout.edges) {
        const source = positions.get(String(edge.i));
        const target = positions.get(String(edge.j));
        const hyp = hypothesisEdgeById.get(edgeKey(edge.i, edge.j)) || edge;
        includeGraphPoint(contentBounds, source.x, source.y, 8);
        includeGraphPoint(contentBounds, target.x, target.y, 8);
        const edgeGroup = svgEl("g", {
          class: `edge ${edge.type === "vz" ? "vz" : "vv"} ${edge.grounded ? "" : "ungrounded"} ${isSelectedEdge(edge) ? "selected" : ""}`
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
        edgeLayer.appendChild(edgeGroup);
      }

      const regionMarkerLayer = svgEl("g", {});
      viewportLayer.appendChild(regionMarkerLayer);
      for (const group of regionMarkerGroups) {
        regionMarkerLayer.appendChild(group);
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

    function regionHull(region, positions) {
      const padding = 42;
      const samples = [];
      const assignedIds = assignedRegionViewpointIds(region);
      assignedIds.forEach(id => {
        const center = positions.get(id);
        for (let index = 0; index < 16; index += 1) {
          const angle = (2 * Math.PI * index) / 16;
          samples.push({
            x: center.x + Math.cos(angle) * padding,
            y: center.y + Math.sin(angle) * padding
          });
        }
      });
      return convexHull(samples);
    }

    function assignedRegionViewpointIds(region) {
      return (region.assigned_viewpoint_ids || []).map(String).sort(numericStringCompare);
    }

    function regionGeometry(region, positions) {
      const assignedIds = assignedRegionViewpointIds(region);
      if (assignedIds.length > 0) {
        const points = regionHull(region, positions);
        return {
          kind: "hull",
          points: points,
          center: polygonCentroid(points)
        };
      }

      const center = positions.get(String(region.id));
      const radius = 24;
      return {
        kind: "marker",
        center: center,
        points: [
          { x: center.x, y: center.y - radius },
          { x: center.x + radius, y: center.y },
          { x: center.x, y: center.y + radius },
          { x: center.x - radius, y: center.y }
        ]
      };
    }

    function convexHull(points) {
      const sorted = points
        .slice()
        .sort((a, b) => a.x === b.x ? a.y - b.y : a.x - b.x);
      const lower = [];
      for (const point of sorted) {
        while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], point) <= 0) {
          lower.pop();
        }
        lower.push(point);
      }
      const upper = [];
      for (let index = sorted.length - 1; index >= 0; index -= 1) {
        const point = sorted[index];
        while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], point) <= 0) {
          upper.pop();
        }
        upper.push(point);
      }
      lower.pop();
      upper.pop();
      return lower.concat(upper);
    }

    function cross(origin, a, b) {
      return (a.x - origin.x) * (b.y - origin.y) - (a.y - origin.y) * (b.x - origin.x);
    }

    function polygonCentroid(points) {
      const total = points.reduce((acc, point) => ({
        x: acc.x + point.x,
        y: acc.y + point.y
      }), { x: 0, y: 0 });
      return {
        x: total.x / points.length,
        y: total.y / points.length
      };
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
          target_probs: formatObject(hyp.target_probs)
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
          formatObject(node.target_probs)
        ]);
      document.getElementById("nodeTable").innerHTML =
        table(["id", "type", "label", "grounded", "exist", "target probs"], rows);
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
      const rows = (step.detection.detections || []).flatMap(detection => {
        return detection.target_indices.map((targetId, index) => [
          detection.agent_id,
          targetId,
          detection.founds[index],
          detection.target_center_xs ? detection.target_center_xs[index] : ""
        ]);
      });
      document.getElementById("detections").innerHTML =
        table(["agent", "target", "found", "center x"], rows);
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
      const bounds = emptyBounds();
      const projection = routeProjection(payload.environment_graph, width, height);
      const positions = routePositions(payload.environment_graph.nodes, projection);
      includeGraphPoint(bounds, projection.offsetX, projection.offsetY, 0);
      includeGraphPoint(
        bounds,
        projection.offsetX + projection.usedWidth,
        projection.offsetY + projection.usedHeight,
        0
      );
      for (const node of step.layout.nodes.filter(item => item.type === "region").sort(byId)) {
        const geometry = regionGeometry(node, positions);
        const center = geometry.center;
        positions.set(String(node.id), center);
        for (const point of geometry.points) {
          includeGraphPoint(bounds, point.x, point.y, 8);
        }
        includeGraphPoint(bounds, center.x, center.y, geometry.kind === "marker" ? 28 : 18);
      }
      for (const edge of step.layout.edges) {
        const source = positions.get(String(edge.i));
        const target = positions.get(String(edge.j));
        includeGraphPoint(bounds, source.x, source.y, 8);
        includeGraphPoint(bounds, target.x, target.y, 8);
        includeGraphPoint(bounds, (source.x + target.x) / 2, (source.y + target.y) / 2, 18);
      }
      for (const node of step.layout.nodes.filter(item => item.type === "viewpoint").sort(byId)) {
        const pos = positions.get(String(node.id));
        includeGraphPoint(bounds, pos.x, pos.y, agentAtNode(step, node.id) ? 42 : 22);
      }
      return bounds;
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
