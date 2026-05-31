from __future__ import annotations

import json
import time
from urllib.request import Request, urlopen

import pytest

from graph_visualizer.loader import load_solution_payload, load_visualization_steps
from graph_visualizer.server import start_visualizer_server
from graph_visualizer.viewer import render_viewer_html


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _pose(x, y, z):
    pose = [0.0] * 16
    pose[3] = x
    pose[7] = y
    pose[11] = z
    return pose


def _write_connectivity(connectivity_dir, *, second_viewpoint_id="vp1"):
    _write_json(
        connectivity_dir / "scan_connectivity.json",
        [
            {
                "image_id": "vp0",
                "included": True,
                "pose": _pose(0.0, 0.0, 0.0),
                "unobstructed": [False, True],
            },
            {
                "image_id": second_viewpoint_id,
                "included": True,
                "pose": _pose(1.0, 0.0, 0.0),
                "unobstructed": [True, False],
            },
        ],
    )


def _write_step(
    root,
    instance_name,
    step_index,
    *,
    target_found,
    targets=None,
    hypothesis_nodes=None,
    detection=None,
    open_vocab_verification=None,
    semantic=True,
    user_message=True,
):
    suffix = "%04d" % int(step_index)
    raw_dir = root / "mllm_raw_outputs" / instance_name
    debug_dir = root / "mllm_debug_outputs" / instance_name

    _write_json(
        debug_dir / ("graph_layout_step_%s.json" % suffix),
        {
            "observation_step": step_index,
            "nodes": [],
            "edges": [],
            "agent_current_vp_ids": {},
        },
    )
    _write_json(
        debug_dir / ("hypothesis_step_%s.json" % suffix),
        {
            "target_found": target_found,
            "targets": targets or [],
            "nodes": hypothesis_nodes or [],
            "edges": [],
        },
    )
    _write_json(
        raw_dir / ("detection_step_%s.json" % suffix),
        detection or {"detections": []},
    )
    if open_vocab_verification is not None:
        _write_json(
            raw_dir / ("open_vocab_verification_step_%s.json" % suffix),
            open_vocab_verification,
        )

    if semantic:
        _write_json(
            raw_dir / ("semantic_step_%s.json" % suffix),
            {"visible_region_nodes": []},
        )

    if user_message:
        (raw_dir / ("user_message_step_%s.txt" % suffix)).write_text(
            "prompt text",
            encoding="utf-8",
        )


def _write_environment_case(root, instance_name):
    _write_json(
        root / "scenarios" / ("%s.json" % instance_name),
        {
            "scan_id": "scan",
            "agents": [],
            "targets": [],
        },
    )
    _write_connectivity(root / "connectivity")


def _write_route_case(root, instance_name):
    _write_environment_case(root, instance_name)
    _write_json(
        root / "mllm_debug_outputs" / instance_name / ("%s_mllm_route_summary.txt" % instance_name),
        {
            "test_case": instance_name,
            "agents": [
                {
                    "agent_id": "agent0",
                    "route_node_ids": [0, 1],
                    "route_viewpoint_ids": ["vp0", "vp1"],
                    "edge_distances": [1.0],
                    "path_distance": 1.0,
                }
            ],
            "total_distance": 1.0,
            "target_node_ids_by_target_id": {"0": 1},
        },
    )


def _patch_house_texture(monkeypatch):
    calls = []

    def fake_generate_cached_topdown_texture(
        *,
        scan_id,
        project_root,
        instance_name,
        connectivity_dir,
        output_size=1800,
        cut_z_offset=0.15,
        render_mode="multi_slice_composite",
        composite_max_z_offset=1.6,
        composite_slices=5,
    ):
        calls.append(
            {
                "scan_id": scan_id,
                "instance_name": instance_name,
                "output_size": output_size,
                "cut_z_offset": cut_z_offset,
                "render_mode": render_mode,
                "composite_max_z_offset": composite_max_z_offset,
                "composite_slices": composite_slices,
            }
        )
        texture_path = (
            project_root
            / "topdown_texture_cache"
            / str(scan_id)
            / ("%s_fake_topdown_texture.png" % str(scan_id))
        )
        texture_path.parent.mkdir(parents=True, exist_ok=True)
        texture_path.write_bytes(b"texture")
        return {
            "url": "/assets/topdown_texture_cache/%s/%s_fake_topdown_texture.png"
            % (str(scan_id), str(scan_id)),
            "render_mode": "interior_cutaway_v1",
            "cut_z": 1.35,
            "cut_z_offset": float(cut_z_offset),
            "composite_max_z": 2.8,
            "composite_max_z_offset": float(composite_max_z_offset),
            "composite_slices": int(composite_slices),
            "requested_render_mode": render_mode,
            "output_size": int(output_size),
            "min_x": 0.0,
            "max_x": 1.0,
            "min_y": 0.0,
            "max_y": 1.0,
            "width": 16,
            "height": 16,
        }

    monkeypatch.setattr(
        "graph_visualizer.loader.generate_cached_topdown_texture",
        fake_generate_cached_topdown_texture,
    )
    return calls


def test_load_visualization_step_with_all_raw_files(tmp_path):
    detection = {
        "detections": [
            {
                "agent_id": "agent0",
                "found_target_indices": ["0"],
                "target_center_xs": [0.25],
            },
        ],
    }
    open_vocab_verification = {
        "step_index": 1,
        "checks": [
            {
                "agent_id": "agent0",
                "target_id": "0",
                "description": "target zero",
                "score": 0.2,
                "score_threshold": 0.3,
                "accepted": False,
                "open_vocab_detections": [],
            },
        ],
    }
    _write_step(
        tmp_path,
        "case",
        1,
        target_found={"0": False},
        detection=detection,
        open_vocab_verification=open_vocab_verification,
    )

    steps = load_visualization_steps("case", project_root=tmp_path)

    assert len(steps) == 1
    assert steps[0]["semantic"] == {"visible_region_nodes": []}
    assert steps[0]["detection"] == detection
    assert steps[0]["open_vocab_verification"] == open_vocab_verification
    assert steps[0]["files"]["open_vocab_verification"] == (
        "mllm_raw_outputs/case/open_vocab_verification_step_0001.json"
    )
    assert steps[0]["user_message"] == "prompt text"


def test_load_terminal_detection_only_step_without_semantic_or_user_message(tmp_path):
    _write_step(
        tmp_path,
        "case",
        1,
        target_found={"0": True, "1": True},
        semantic=False,
        user_message=False,
    )

    steps = load_visualization_steps("case", project_root=tmp_path)

    assert len(steps) == 1
    assert steps[0]["semantic"] is None
    assert steps[0]["user_message"] == ""
    assert steps[0]["files"]["semantic"] == (
        "mllm_raw_outputs/case/semantic_step_0001.json"
    )
    assert steps[0]["files"]["user_message"] == (
        "mllm_raw_outputs/case/user_message_step_0001.txt"
    )


def test_load_visualization_step_preserves_raw_target_probs(tmp_path):
    _write_step(
        tmp_path,
        "case",
        1,
        target_found={"0": False},
        hypothesis_nodes=[
            {
                "id": 2,
                "label": "vp2",
                "type": "viewpoint",
                "grounded": False,
                "exist_prob": 1.0,
                "target_probs": {"0": 1.0},
                "raw_target_probs": {"0": 0.8},
                "node_visit_times": 0,
            }
        ],
    )

    steps = load_visualization_steps("case", project_root=tmp_path)

    assert steps[0]["hypothesis"]["nodes"][0]["raw_target_probs"] == {"0": 0.8}
    assert steps[0]["hypothesis"]["nodes"][0]["target_probs"] == {"0": 1.0}


def test_load_nonterminal_step_without_semantic_still_crashes(tmp_path):
    _write_step(
        tmp_path,
        "case",
        1,
        target_found={"0": False, "1": True},
        semantic=False,
    )

    with pytest.raises(FileNotFoundError):
        load_visualization_steps("case", project_root=tmp_path)


def test_load_solution_payload_detects_route_summary_and_environment_graph(
    tmp_path,
    monkeypatch,
):
    _write_route_case(tmp_path, "case")
    _patch_house_texture(monkeypatch)
    monkeypatch.setattr("graph_visualizer.loader.platform.system", lambda: "Windows")

    payload = load_solution_payload("case", project_root=tmp_path)

    assert payload["solutions"][0]["id"] == "mllm"
    assert payload["solutions"][0]["summary"]["total_distance"] == 1.0
    assert payload["environment_graph"]["scan_id"] == "scan"
    assert payload["environment_graph"]["nodes"][0]["viewpoint_id"] == "vp0"
    assert payload["environment_graph"]["edges"][0]["distance"] == pytest.approx(1.0)
    assert payload["environment_graph"]["house_texture"] == {
        "url": "/assets/topdown_texture_cache/scan/scan_fake_topdown_texture.png",
        "render_mode": "interior_cutaway_v1",
        "cut_z": 1.35,
        "cut_z_offset": 0.15,
        "composite_max_z": 2.8,
        "composite_max_z_offset": 1.6,
        "composite_slices": 5,
        "requested_render_mode": "multi_slice_composite",
        "output_size": 1800,
        "min_x": 0.0,
        "max_x": 1.0,
        "min_y": 0.0,
        "max_y": 1.0,
        "width": 16,
        "height": 16,
    }


def test_load_solution_payload_includes_environment_without_route_summaries(
    tmp_path,
    monkeypatch,
):
    _write_environment_case(tmp_path, "case")
    _patch_house_texture(monkeypatch)
    monkeypatch.setattr("graph_visualizer.loader.platform.system", lambda: "Windows")

    payload = load_solution_payload("case", project_root=tmp_path)

    assert payload["solutions"] == []
    assert payload["environment_graph"]["scan_id"] == "scan"
    assert payload["environment_graph"]["nodes"][1]["x"] == pytest.approx(1.0)
    assert payload["environment_graph"]["house_texture"]["url"] == (
        "/assets/topdown_texture_cache/scan/scan_fake_topdown_texture.png"
    )
    assert payload["environment_graph"]["house_texture"]["output_size"] == 1800
    assert payload["environment_graph"]["house_texture"]["cut_z_offset"] == 0.15


def test_load_solution_payload_forwards_texture_settings(
    tmp_path,
    monkeypatch,
):
    _write_environment_case(tmp_path, "case")
    _patch_house_texture(monkeypatch)
    monkeypatch.setattr("graph_visualizer.loader.platform.system", lambda: "Windows")

    payload = load_solution_payload(
        "case",
        project_root=tmp_path,
        texture_output_size=4096,
        texture_cut_z_offset=0.9,
        texture_render_mode="single_cutaway",
        texture_composite_max_z_offset=2.1,
        texture_composite_slices=7,
    )

    assert payload["environment_graph"]["house_texture"]["output_size"] == 4096
    assert payload["environment_graph"]["house_texture"]["cut_z_offset"] == 0.9
    assert payload["environment_graph"]["house_texture"]["requested_render_mode"] == "single_cutaway"
    assert payload["environment_graph"]["house_texture"]["composite_max_z_offset"] == 2.1
    assert payload["environment_graph"]["house_texture"]["composite_slices"] == 7


def test_load_solution_payload_keeps_environment_connectivity_on_linux(
    tmp_path,
    monkeypatch,
):
    _write_route_case(tmp_path, "case")
    env_connectivity_dir = tmp_path / "env_connectivity"
    _write_connectivity(env_connectivity_dir, second_viewpoint_id="env-vp1")
    _patch_house_texture(monkeypatch)
    monkeypatch.setattr("graph_visualizer.loader.platform.system", lambda: "Linux")
    monkeypatch.setenv("MATTERPORT_CONNECTIVITY_DIR", str(env_connectivity_dir))

    payload = load_solution_payload("case", project_root=tmp_path)

    assert payload["environment_graph"]["nodes"][1]["viewpoint_id"] == "env-vp1"


def test_steps_api_includes_detected_solution_summaries(tmp_path, monkeypatch):
    _write_step(
        tmp_path,
        "case",
        1,
        target_found={"0": False},
    )
    _write_route_case(tmp_path, "case")
    texture_calls = _patch_house_texture(monkeypatch)
    monkeypatch.setenv("MATTERPORT_CONNECTIVITY_DIR", str(tmp_path / "connectivity"))
    server = start_visualizer_server(
        "case",
        project_root=tmp_path,
        open_browser=False,
        texture_output_size=4096,
        texture_cut_z_offset=0.9,
        texture_render_mode="single_cutaway",
        texture_composite_max_z_offset=2.1,
        texture_composite_slices=7,
    )

    try:
        assert texture_calls == []

        with urlopen(server.url + "api/steps", timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))

        assert payload["solutions"][0]["id"] == "mllm"
        assert payload["environment_graph"]["scan_id"] == "scan"
        assert "house_texture" not in payload["environment_graph"]
        assert texture_calls == []

        with urlopen(server.url + "api/house-texture", timeout=5) as response:
            house_texture = json.loads(response.read().decode("utf-8"))

        assert house_texture["url"] == (
            "/assets/topdown_texture_cache/scan/scan_fake_topdown_texture.png"
        )
        assert house_texture["output_size"] == 4096
        assert house_texture["cut_z_offset"] == 0.9
        assert house_texture["requested_render_mode"] == "single_cutaway"
        assert house_texture["composite_max_z_offset"] == 2.1
        assert house_texture["composite_slices"] == 7
        assert texture_calls == [
            {
                "scan_id": "scan",
                "instance_name": "case",
                "output_size": 4096,
                "cut_z_offset": 0.9,
                "render_mode": "single_cutaway",
                "composite_max_z_offset": 2.1,
                "composite_slices": 7,
            }
        ]

        with urlopen(
            server.url + "assets/topdown_texture_cache/scan/scan_fake_topdown_texture.png",
            timeout=5,
        ) as asset_response:
            assert asset_response.status == 200
            assert asset_response.read() == b"texture"
    finally:
        server.shutdown()


def test_steps_api_includes_environment_without_solution_summaries(tmp_path, monkeypatch):
    _write_step(
        tmp_path,
        "case",
        1,
        target_found={"0": False},
    )
    _write_environment_case(tmp_path, "case")
    texture_calls = _patch_house_texture(monkeypatch)
    monkeypatch.setattr("graph_visualizer.loader.platform.system", lambda: "Windows")
    server = start_visualizer_server(
        "case",
        project_root=tmp_path,
        open_browser=False,
    )

    try:
        with urlopen(server.url + "api/steps", timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))

        assert payload["solutions"] == []
        assert payload["environment_graph"]["scan_id"] == "scan"
        assert "house_texture" not in payload["environment_graph"]
        assert texture_calls == []
    finally:
        server.shutdown()


def test_route_renderer_skips_wait_step_edges():
    html = render_viewer_html()

    assert "Number(routeNodeIds[routeIndex]) === Number(nextNodeId)" in html
    assert "sameRoutePoint(point, nextPoint)" in html
    assert 'id="houseTextureButton"' in html
    assert '"pointer-events": "none"' in html
    assert html.count("        appendHouseTexture(viewportLayer, environment, projection);") == 2
    assert html.count("if (showHouseTexture && environment.house_texture)") == 2
    assert "houseTextureButton.disabled = false;" in html
    assert 'id="graphZoomInButton"' in html
    assert 'id="graphZoomOutButton"' in html
    assert 'id="graphResetViewButton"' in html
    assert 'fetch("/api/house-texture")' in html
    assert "function fetchHouseTexture()" in html
    assert 'id="textureStatus"' in html
    assert 'role="status"' in html
    assert 'showTextureStatus("Preparing house texture...");' in html
    assert 'showTextureStatus("House texture ready", 1800);' in html
    assert "function setTextureLoading(isLoading)" in html
    assert "setTextureLoading(true);" in html
    assert "setTextureLoading(false);" in html
    assert 'houseTextureButton.setAttribute("aria-busy", String(Boolean(isLoading)));' in html
    assert "payload.environment_graph.house_texture = houseTexture;" in html
    assert "function clearDefaultViewportStates()" in html


def test_route_renderer_includes_target_descriptions_and_agent_legend():
    html = render_viewer_html()

    assert "ROUTE_COLORS" in html
    assert "function routeTargetRows" in html
    assert "targetDescription(targetId)" in html
    assert "routeAgentsForNode(summary, nodeId)" in html
    assert 'table(["target", "description", "node", "found by"], targetRows)' in html
    assert "Agent Legend" in html
    assert "function routeAgentLegendHtml" in html
    assert "function routeAgentColor" in html
    assert "routeAgentColor(agentIndex)" in html
    assert "agents ${routeTarget.agent_ids.join" in html


def test_step_renderer_removes_layout_editing_and_drag_selection_code():
    html = render_viewer_html()

    assert "Use saved layout" not in html
    assert "Retrieve default layout" not in html
    assert "Copy previous layout" not in html
    assert "Save layout" not in html
    assert "layout-positions" not in html
    assert "draggable" not in html
    assert "selection-window" not in html
    assert "node-group" not in html


def test_step_renderer_uses_tight_region_boundaries_and_arrival_edges():
    html = render_viewer_html()

    assert "function regionHull" not in html
    assert "function convexHull" not in html
    assert "marchingSquaresRegionBoundary" in html
    assert "regionBoundaryPrimitives" in html
    assert "REGION_BOUNDARY_NODE_RADIUS" in html
    assert "function regionColor" in html
    assert "REGION_COLORS" in html
    assert "function agentArrivalEdgeKeys" in html
    assert "payload.steps[stepPosition - 1]" in html
    assert "Step ${step.step_index} / ${payload.steps.length}" in html
    assert 'class: "region-boundary"' in html
    assert 'class: `edge ${edge.type === "vz" ? "vz" : "vv"} ${edge.grounded ? "" : "ungrounded"} ${isArrivalEdge ? "arrival" : ""}' in html


def test_step_renderer_moves_unassigned_regions_to_sidebar():
    html = render_viewer_html()

    assert 'id="unassignedRegionSection"' in html
    assert "Unassigned Regions" in html
    assert "function renderUnassignedRegions" in html
    assert '.filter(node => node.type === "region" && !isAssignedRegion(node))' in html
    assert "function isAssignedRegion" in html
    assert "UNANCHORED_REGION_RAIL" not in html
    assert "markerRegions" not in html
    assert "anchoredRegionMarkerCenter" not in html
    assert 'kind: "marker"' not in html


def test_step_renderer_filters_hidden_region_edges_from_graph():
    html = render_viewer_html()

    assert "function graphVisibleNodeIds" in html
    assert 'node.type !== "region" || isAssignedRegion(node)' in html
    assert "function graphVisibleEdges" in html
    assert "visibleNodeIds.has(String(edge.i)) && visibleNodeIds.has(String(edge.j))" in html
    assert "const graphEdges = graphVisibleEdges(step);" in html
    assert "for (const edge of graphEdges)" in html


def test_step_renderer_toggles_selected_nodes_and_highlights_found_targets():
    html = render_viewer_html()

    assert "function toggleNodeSelection(nodeId)" in html
    assert "if (isSelectedNode(nodeId))" in html
    assert "selected = null;" in html
    assert 'selected = { kind: "node", id: nodeId };' in html
    assert html.count("toggleNodeSelection(node.id);") == 2

    assert "function targetSummaryHtml(step)" in html
    assert "Boolean(targetFound[targetId])" in html
    assert "summary-target-found" in html
    assert "background: #dcfce7;" in html
    assert "color: #166534;" in html
    assert 'definitionList(items, htmlKeys = new Set())' in html
    assert 'definitionList({\n        step_index: step.step_index,' in html
    assert "observation_step: step.layout.observation_step" not in html
    assert '}, new Set(["targets"]));' in html


def test_step_renderer_includes_target_detection_sidebar_and_verification_normalization():
    html = render_viewer_html()

    assert 'id="targetDetectionsSection"' in html
    assert "Target Detections This Step" in html
    assert "function renderTargetDetections" in html
    assert "function normalizedDetectionRows" in html
    assert "Array.isArray(detection.found_target_indices)" in html
    assert "detection.found_target_indices.map" in html
    assert "detection.target_indices" in html
    assert "Boolean(detection.founds[index])" in html
    assert "function openVocabularyVerificationChecks" in html
    assert "verificationKey(check.agent_id, check.target_id)" in html
    assert "function verificationStatus" in html
    assert 'return check.accepted ? "accepted" : "rejected";' in html
    assert 'if (verification === "rejected") return false;' in html
    assert (
        'table(["agent", "target", "description", "verification", "score", '
        '"threshold", "center x"], rows)'
    ) in html
    assert 'table(["agent", "target", "found", "verification", "center x"], rows)' in html
    assert "targetDescriptionFromStep(step, targetId)" in html


def test_step_renderer_opens_observation_images_in_modal_with_overlays():
    html = render_viewer_html()

    assert 'id="observationModal"' in html
    assert 'id="observationModalViewport"' in html
    assert 'id="observationModalResetButton"' in html
    assert 'id="observationModalCloseButton"' in html
    assert 'class="observation-image-button"' in html
    assert 'class="observation-image-frame"' in html
    assert "function openObservationImageModal(image)" in html
    assert "function renderObservationModalImage()" in html
    assert "function closeObservationImageModal()" in html
    assert "function resetObservationModalTransform()" in html
    assert 'data-image-url="${escapeAttr(image.url)}"' in html
    assert 'data-agent-id="${escapeAttr(image.agent_id)}"' in html
    assert 'aria-label="Open ${escapeAttr(image.agent_id)} observation"' in html
    assert 'window.open("", "_blank")' not in html
    assert "childWindow.document.write" not in html
    assert "function observationDetectionsByAgent(step)" in html
    assert "normalizedDetectionRows(step).filter(row => row.found)" in html
    assert "Number(row.target_center_x)" in html
    assert "item.target_center_x * 100" in html
    assert "observationDetectionOverlayHtml" in html
    assert "observation-detection-marker" in html
    assert "observation-detection-label" in html
    assert "target: ${escapeHtml(item.target_id)}" in html
    assert "function beginObservationModalPan(event)" in html
    assert "function zoomObservationModalAtPoint(factor, point)" in html
    assert "observationModalViewport.addEventListener(\"wheel\"" in html
    assert "event.key === \"Escape\"" in html


def test_shutdown_endpoint_stops_visualization_server(tmp_path, monkeypatch):
    _write_step(
        tmp_path,
        "case",
        1,
        target_found={"0": False},
    )
    _write_environment_case(tmp_path, "case")
    _patch_house_texture(monkeypatch)
    monkeypatch.setattr("graph_visualizer.loader.platform.system", lambda: "Windows")
    server = start_visualizer_server(
        "case",
        project_root=tmp_path,
        open_browser=False,
    )

    try:
        request = Request(
            server.url + "api/shutdown",
            data=b"{}",
            method="POST",
        )
        with urlopen(request, timeout=5) as response:
            assert response.status == 200
            assert response.read() == b"{}"

        deadline = time.time() + 5
        while server.thread.is_alive() and time.time() < deadline:
            time.sleep(0.05)

        assert not server.thread.is_alive()
    finally:
        if server.thread.is_alive():
            server.shutdown()
        else:
            server.httpd.server_close()
