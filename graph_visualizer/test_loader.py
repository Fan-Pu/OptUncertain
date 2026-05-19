from __future__ import annotations

import json
import time
from urllib.request import Request, urlopen

import pytest

from graph_visualizer.loader import load_solution_payload, load_visualization_steps
from graph_visualizer.server import start_visualizer_server


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _pose(x, y, z):
    pose = [0.0] * 16
    pose[3] = x
    pose[7] = y
    pose[11] = z
    return pose


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


def _write_route_case(root, instance_name):
    _write_json(
        root / "scenarios" / ("%s.json" % instance_name),
        {
            "scan_id": "scan",
            "agents": [],
            "targets": [],
        },
    )
    _write_json(
        root / "connectivity" / "scan_connectivity.json",
        [
            {
                "image_id": "vp0",
                "included": True,
                "pose": _pose(0.0, 0.0, 0.0),
                "unobstructed": [False, True],
            },
            {
                "image_id": "vp1",
                "included": True,
                "pose": _pose(1.0, 0.0, 0.0),
                "unobstructed": [True, False],
            },
        ],
    )
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


def test_load_visualization_step_with_all_raw_files(tmp_path):
    _write_step(
        tmp_path,
        "case",
        0,
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
        0,
        target_found={"0": True, "1": True},
        semantic=False,
        user_message=False,
    )

    steps = load_visualization_steps("case", project_root=tmp_path)

    assert len(steps) == 1
    assert steps[0]["semantic"] is None
    assert steps[0]["user_message"] == ""
    assert steps[0]["files"]["semantic"] == (
        "mllm_raw_outputs/case/semantic_step_0000.json"
    )
    assert steps[0]["files"]["user_message"] == (
        "mllm_raw_outputs/case/user_message_step_0000.txt"
    )


def test_load_nonterminal_step_without_semantic_still_crashes(tmp_path):
    _write_step(
        tmp_path,
        "case",
        0,
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
    monkeypatch.setenv("MATTERPORT_CONNECTIVITY_DIR", str(tmp_path / "connectivity"))

    payload = load_solution_payload("case", project_root=tmp_path)

    assert payload["solutions"][0]["id"] == "mllm"
    assert payload["solutions"][0]["summary"]["total_distance"] == 1.0
    assert payload["environment_graph"]["scan_id"] == "scan"
    assert payload["environment_graph"]["nodes"][0]["viewpoint_id"] == "vp0"
    assert payload["environment_graph"]["edges"][0]["distance"] == pytest.approx(1.0)


def test_steps_api_includes_detected_solution_summaries(tmp_path, monkeypatch):
    _write_step(
        tmp_path,
        "case",
        0,
        target_found={"0": False},
    )
    _write_route_case(tmp_path, "case")
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
    finally:
        server.shutdown()


def test_shutdown_endpoint_stops_visualization_server(tmp_path):
    _write_step(
        tmp_path,
        "case",
        0,
        target_found={"0": False},
    )
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
