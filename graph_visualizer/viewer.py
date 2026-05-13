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
      gap: 10px;
      white-space: nowrap;
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
    .node.viewpoint.draggable {
      cursor: grab;
    }
    .node.viewpoint.draggable.dragging {
      cursor: grabbing;
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
      <button id="useSavedLayoutButton" type="button" aria-pressed="false">Use saved layout: Off</button>
      <button id="resetDefaultLayoutButton" type="button" disabled>Retrieve default layout for this step</button>
      <button id="prevButton" type="button">Previous</button>
      <div id="stepLabel"></div>
      <button id="nextButton" type="button">Next</button>
    </div>
  </header>
  <main>
    <div class="workspace">
      <section class="panel graph-panel">
        <svg id="graph" role="img" aria-label="Graph layout"></svg>
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
      <section class="panel section">
        <h2>Selected Item</h2>
        <div id="selection"></div>
      </section>
      <section class="panel section">
        <h2>Step Summary</h2>
        <div id="summary"></div>
      </section>
      <section class="panel section">
        <h2>Hypothesis Nodes</h2>
        <div id="nodeTable"></div>
      </section>
      <section class="panel section">
        <h2>Hypothesis Edges</h2>
        <div id="edgeTable"></div>
      </section>
      <section class="panel section">
        <h2>Detections</h2>
        <div id="detections"></div>
      </section>
      <section class="panel section">
        <h2>Semantic Raw Output</h2>
        <pre id="semantic"></pre>
      </section>
      <section class="panel section">
        <h2>User Message</h2>
        <pre id="userMessage"></pre>
      </section>
    </aside>
  </main>
  <script>
    let payload = null;
    let stepPosition = 0;
    let selected = null;
    let dragState = null;
    let useSavedLayout = false;
    const positionOverrides = new Map();

    const graph = document.getElementById("graph");
    const useSavedLayoutButton = document.getElementById("useSavedLayoutButton");
    const resetDefaultLayoutButton = document.getElementById("resetDefaultLayoutButton");
    const prevButton = document.getElementById("prevButton");
    const nextButton = document.getElementById("nextButton");
    const stepLabel = document.getElementById("stepLabel");

    useSavedLayoutButton.addEventListener("click", () => {
      useSavedLayout = !useSavedLayout;
      dragState = null;
      render();
    });
    resetDefaultLayoutButton.addEventListener("click", () => {
      resetDefaultLayoutForStep();
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
    window.addEventListener("resize", () => renderGraph(currentStep()));
    graph.addEventListener("pointermove", event => {
      if (!dragState) return;
      const point = graphPoint(event);
      const x = clamp(point.x + dragState.offsetX, 24, graph.viewBox.baseVal.width - 24);
      const y = clamp(point.y + dragState.offsetY, 24, graph.viewBox.baseVal.height - 24);
      setPositionOverride(dragState.stepIndex, dragState.nodeId, x, y);
      renderGraph(currentStep());
    });
    graph.addEventListener("pointerup", event => {
      if (!dragState) return;
      const point = graphPoint(event);
      const x = clamp(point.x + dragState.offsetX, 24, graph.viewBox.baseVal.width - 24);
      const y = clamp(point.y + dragState.offsetY, 24, graph.viewBox.baseVal.height - 24);
      setPositionOverride(dragState.stepIndex, dragState.nodeId, x, y);
      const update = {
        step_index: dragState.stepIndex,
        node_id: dragState.nodeId,
        x: x,
        y: y
      };
      graph.releasePointerCapture(dragState.pointerId);
      dragState = null;
      renderGraph(currentStep());
      savePosition(update);
    });

    fetch("/api/steps")
      .then(response => response.json())
      .then(data => {
        payload = data;
        document.getElementById("title").textContent =
          `Graph Hypothesis Visualizer: ${payload.instance_name}`;
        render();
      });

    function currentStep() {
      return payload.steps[stepPosition];
    }

    function render() {
      const step = currentStep();
      prevButton.disabled = stepPosition === 0;
      nextButton.disabled = stepPosition === payload.steps.length - 1;
      useSavedLayoutButton.setAttribute("aria-pressed", String(useSavedLayout));
      useSavedLayoutButton.textContent = useSavedLayout
        ? "Use saved layout: On"
        : "Use saved layout: Off";
      resetDefaultLayoutButton.disabled = !useSavedLayout;
      stepLabel.textContent = `Step ${stepPosition + 1} / ${payload.steps.length}`;
      renderGraph(step);
      renderSelection(step);
      renderSummary(step);
      renderNodeTable(step);
      renderEdgeTable(step);
      renderDetections(step);
      renderImages(step);
      document.getElementById("semantic").textContent = JSON.stringify(step.semantic, null, 2);
      document.getElementById("userMessage").textContent = step.user_message;
    }

    function renderGraph(step) {
      while (graph.firstChild) graph.removeChild(graph.firstChild);
      const width = graph.clientWidth || 900;
      const height = graph.clientHeight || 560;
      graph.setAttribute("viewBox", `0 0 ${width} ${height}`);

      const layoutNodes = step.layout.nodes;
      const hypothesisEdgeById = new Map(step.hypothesis.edges.map(edge => [edgeKey(edge.i, edge.j), edge]));
      const positions = computePositions(step, width, height, {
        useSavedPositions: useSavedLayout,
        useOverrides: useSavedLayout
      });

      const regionLayer = svgEl("g", {});
      graph.appendChild(regionLayer);
      for (const node of layoutNodes.filter(item => item.type === "region").sort(byId)) {
        const hull = regionHull(node, positions);
        const center = polygonCentroid(hull);
        positions.set(String(node.id), center);
        const group = svgEl("g", {
          class: `node region ${isSelectedNode(node.id) ? "selected" : ""}`
        });
        group.addEventListener("click", () => {
          selected = { kind: "node", id: node.id };
          render();
        });
        const title = svgEl("title", {});
        title.textContent = `${node.type} ${node.id}: ${node.label}`;
        group.appendChild(title);
        group.appendChild(svgEl("polygon", {
          class: "region-hull",
          points: hull.map(point => `${point.x},${point.y}`).join(" "),
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
        regionLayer.appendChild(group);
      }

      const edgeLayer = svgEl("g", {});
      graph.appendChild(edgeLayer);
      for (const edge of step.layout.edges) {
        const source = positions.get(String(edge.i));
        const target = positions.get(String(edge.j));
        const hyp = hypothesisEdgeById.get(edgeKey(edge.i, edge.j)) || edge;
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

      const nodeLayer = svgEl("g", {});
      graph.appendChild(nodeLayer);
      for (const node of layoutNodes.filter(item => item.type === "viewpoint").sort(byId)) {
        const pos = positions.get(String(node.id));
        const currentAgent = agentAtNode(step, node.id);
        const group = svgEl("g", {
          class: `node viewpoint ${useSavedLayout ? "draggable" : ""} ${dragState && String(dragState.nodeId) === String(node.id) ? "dragging" : ""} ${isSelectedNode(node.id) ? "selected" : ""}`
        });
        group.addEventListener("pointerdown", event => {
          if (!useSavedLayout) return;
          if (event.button !== 0) return;
          const point = graphPoint(event);
          dragState = {
            stepIndex: step.step_index,
            nodeId: Number(node.id),
            pointerId: event.pointerId,
            offsetX: pos.x - point.x,
            offsetY: pos.y - point.y
          };
          graph.setPointerCapture(event.pointerId);
          selected = { kind: "node", id: node.id };
          renderSelection(step);
        });
        group.addEventListener("click", () => {
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
    }

    function computePositions(step, width, height, options = {}) {
      const useSavedPositions = options.useSavedPositions === true;
      const useOverrides = options.useOverrides === true;
      const nodes = step.layout.nodes;
      const regions = nodes.filter(node => node.type === "region").sort(byId);
      const viewpoints = nodes.filter(node => node.type === "viewpoint").sort(byId);
      const positions = new Map();
      const cx = width / 2;
      const cy = height / 2;
      const regionRadius = Math.max(110, Math.min(width, height) * 0.32);

      regions.forEach((region, index) => {
        const angle = regions.length === 1
          ? -Math.PI / 2
          : -Math.PI / 2 + (2 * Math.PI * index / regions.length);
        positions.set(String(region.id), {
          x: cx + Math.cos(angle) * regionRadius,
          y: cy + Math.sin(angle) * regionRadius
        });
      });

      const assigned = new Set();
      regions.forEach(region => {
        const assignedIds = (region.assigned_viewpoint_ids || []).map(String).sort(numericStringCompare);
        const anchor = positions.get(String(region.id));
        const radius = 76 + Math.max(0, assignedIds.length - 2) * 9;
        assignedIds.forEach((viewpointId, index) => {
          assigned.add(viewpointId);
          const angle = -Math.PI / 2 + (2 * Math.PI * index / Math.max(1, assignedIds.length));
          positions.set(viewpointId, {
            x: clamp(anchor.x + Math.cos(angle) * radius, 40, width - 40),
            y: clamp(anchor.y + Math.sin(angle) * radius, 40, height - 40)
          });
        });
      });

      const unassigned = viewpoints.filter(node => !assigned.has(String(node.id)));
      const outerRadius = Math.max(140, Math.min(width, height) * 0.43);
      unassigned.forEach((node, index) => {
        const angle = Math.PI / 2 + (2 * Math.PI * index / Math.max(1, unassigned.length));
        positions.set(String(node.id), {
          x: clamp(cx + Math.cos(angle) * outerRadius, 40, width - 40),
          y: clamp(cy + Math.sin(angle) * outerRadius, 40, height - 40)
        });
      });

      if (useSavedPositions) {
        viewpoints.forEach(node => {
          if (typeof node.x === "number" && typeof node.y === "number") {
            positions.set(String(node.id), {
              x: clamp(node.x, 24, width - 24),
              y: clamp(node.y, 24, height - 24)
            });
          }
          const override = getPositionOverride(step.step_index, node.id);
          if (useOverrides && override) {
            positions.set(String(node.id), {
              x: clamp(override.x, 24, width - 24),
              y: clamp(override.y, 24, height - 24)
            });
          }
        });
      }
      return positions;
    }

    function regionHull(region, positions) {
      const padding = 42;
      const samples = [];
      const assignedIds = (region.assigned_viewpoint_ids || []).map(String).sort(numericStringCompare);
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
      return selected && selected.kind === "node" && String(selected.id) === String(nodeId);
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

    function graphPoint(event) {
      const point = graph.createSVGPoint();
      point.x = event.clientX;
      point.y = event.clientY;
      return point.matrixTransform(graph.getScreenCTM().inverse());
    }

    function positionKey(stepIndex, nodeId) {
      return `${stepIndex}:${nodeId}`;
    }

    function getPositionOverride(stepIndex, nodeId) {
      return positionOverrides.get(positionKey(stepIndex, nodeId));
    }

    function setPositionOverride(stepIndex, nodeId, x, y) {
      positionOverrides.set(positionKey(stepIndex, nodeId), { x: x, y: y });
    }

    function clearPositionOverridesForStep(stepIndex) {
      for (const key of Array.from(positionOverrides.keys())) {
        if (key.startsWith(`${stepIndex}:`)) {
          positionOverrides.delete(key);
        }
      }
    }

    function savePosition(update) {
      const step = payload.steps.find(item => Number(item.step_index) === Number(update.step_index));
      const node = step.layout.nodes.find(item => Number(item.id) === Number(update.node_id));
      node.x = update.x;
      node.y = update.y;
      fetch("/api/layout-position", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(update)
      }).then(response => response.json());
    }

    function savePositions(update) {
      fetch("/api/layout-positions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(update)
      }).then(response => response.json());
    }

    function resetDefaultLayoutForStep() {
      if (!useSavedLayout) return;
      const step = currentStep();
      const width = graph.clientWidth || 900;
      const height = graph.clientHeight || 560;
      const positions = computePositions(step, width, height, {
        useSavedPositions: false,
        useOverrides: false
      });
      const updates = step.layout.nodes
        .filter(node => node.type === "viewpoint")
        .map(node => {
          const position = positions.get(String(node.id));
          node.x = position.x;
          node.y = position.y;
          return {
            node_id: Number(node.id),
            x: position.x,
            y: position.y
          };
        });
      clearPositionOverridesForStep(step.step_index);
      renderGraph(step);
      savePositions({
        step_index: step.step_index,
        positions: updates
      });
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
