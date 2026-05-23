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
            "targets": [],
            "nodes": [],
            "edges": [],
        },
    )
    _write_json(
        raw_dir / ("detection_step_%s.json" % suffix),
        {"detections": []},
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
    def fake_generate_cached_topdown_texture(
        *,
        scan_id,
        project_root,
        instance_name,
        connectivity_dir,
        output_size=1800,
        cut_z_offset=0.15,
    ):
        texture_path = (
            project_root
            / "mllm_debug_outputs"
            / str(instance_name)
            / ("%s_topdown_texture.png" % str(scan_id))
        )
        texture_path.parent.mkdir(parents=True, exist_ok=True)
        texture_path.write_bytes(b"texture")
        return {
            "url": "/assets/mllm_debug_outputs/%s/%s_topdown_texture.png"
            % (str(instance_name), str(scan_id)),
            "render_mode": "interior_cutaway_v1",
            "cut_z": 1.35,
            "cut_z_offset": float(cut_z_offset),
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


def test_load_visualization_step_with_all_raw_files(tmp_path):
    _write_step(
        tmp_path,
        "case",
        1,
        target_found={"0": False},
    )

    steps = load_visualization_steps("case", project_root=tmp_path)

    assert len(steps) == 1
    assert steps[0]["semantic"] == {"visible_region_nodes": []}
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
        "url": "/assets/mllm_debug_outputs/case/scan_topdown_texture.png",
        "render_mode": "interior_cutaway_v1",
        "cut_z": 1.35,
        "cut_z_offset": 0.15,
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
        "/assets/mllm_debug_outputs/case/scan_topdown_texture.png"
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
    )

    assert payload["environment_graph"]["house_texture"]["output_size"] == 4096
    assert payload["environment_graph"]["house_texture"]["cut_z_offset"] == 0.9


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
    _patch_house_texture(monkeypatch)
    monkeypatch.setenv("MATTERPORT_CONNECTIVITY_DIR", str(tmp_path / "connectivity"))
    server = start_visualizer_server(
        "case",
        project_root=tmp_path,
        open_browser=False,
    )

    try:
        with urlopen(server.url + "api/steps", timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))

        assert payload["solutions"][0]["id"] == "mllm"
        assert payload["environment_graph"]["scan_id"] == "scan"
        assert payload["environment_graph"]["house_texture"]["url"] == (
            "/assets/mllm_debug_outputs/case/scan_topdown_texture.png"
        )

        with urlopen(
            server.url + "assets/mllm_debug_outputs/case/scan_topdown_texture.png",
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
    _patch_house_texture(monkeypatch)
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
        assert payload["environment_graph"]["house_texture"]["url"] == (
            "/assets/mllm_debug_outputs/case/scan_topdown_texture.png"
        )
    finally:
        server.shutdown()


def test_route_renderer_skips_wait_step_edges():
    html = render_viewer_html()

    assert "Number(routeNodeIds[routeIndex]) === Number(nextNodeId)" in html
    assert "sameRoutePoint(point, nextPoint)" in html
    assert 'id="houseTextureButton"' in html
    assert '"pointer-events": "none"' in html
    assert html.count("        appendHouseTexture(viewportLayer, environment, projection);") == 2
    assert "houseTextureButton.disabled = false;" in html
    assert 'id="graphZoomInButton"' in html
    assert 'id="graphZoomOutButton"' in html
    assert 'id="graphResetViewButton"' in html


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


def test_step_renderer_includes_found_target_sidebar_and_detection_normalization():
    html = render_viewer_html()

    assert 'id="foundTargetsSection"' in html
    assert "Found Targets This Step" in html
    assert "function renderFoundTargets" in html
    assert "function normalizedDetectionRows" in html
    assert "Array.isArray(detection.found_target_indices)" in html
    assert "detection.found_target_indices.map" in html
    assert "found: true" in html
    assert "detection.target_indices" in html
    assert "Boolean(detection.founds[index])" in html
    assert 'table(["agent", "target", "description", "center x"], rows)' in html
    assert 'table(["agent", "target", "found", "center x"], rows)' in html
    assert "targetDescriptionFromStep(step, targetId)" in html


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
