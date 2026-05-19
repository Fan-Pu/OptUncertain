import json
import importlib.machinery
import importlib.util
import sys
import types

import pytest

if importlib.util.find_spec("MatterSim") is None:
    mattersim_stub = types.ModuleType("MatterSim")
    mattersim_stub.__spec__ = importlib.machinery.ModuleSpec("MatterSim", None)

    class _Simulator:
        pass

    mattersim_stub.Simulator = _Simulator
    sys.modules["MatterSim"] = mattersim_stub

if importlib.util.find_spec("cv2") is None:
    cv2_stub = types.ModuleType("cv2")
    cv2_stub.__spec__ = importlib.machinery.ModuleSpec("cv2", None)
    sys.modules["cv2"] = cv2_stub

import Helper
import main


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _pose(x, y, z):
    pose = [0.0] * 16
    pose[3] = x
    pose[7] = y
    pose[11] = z
    return pose


def _write_connectivity(tmp_path):
    _write_json(
        tmp_path / "connectivity" / "scan_connectivity.json",
        [
            {
                "image_id": "vp0",
                "included": True,
                "pose": _pose(0.0, 0.0, 0.0),
                "unobstructed": [False, True, False],
            },
            {
                "image_id": "vp1",
                "included": True,
                "pose": _pose(1.0, 0.0, 0.0),
                "unobstructed": [True, False, True],
            },
            {
                "image_id": "vp2",
                "included": True,
                "pose": _pose(1.0, 0.0, 1.0),
                "unobstructed": [False, True, False],
            },
        ],
    )


def test_executed_route_helpers_track_starts_hops_and_found_targets(monkeypatch):
    monkeypatch.setattr(
        Helper,
        "viewpoint_index_by_vp_label",
        {
            "vp0": 0,
            "vp2": 2,
        },
    )
    scenario = {
        "agents": [
            {
                "id": "agent0",
                "start_viewpoint_id": "vp0",
            },
            {
                "id": "agent1",
                "start_viewpoint_id": "vp2",
            },
        ]
    }

    executed_routes = main._initialize_executed_routes(scenario)
    main._append_executed_route_nodes(
        executed_routes_by_agent=executed_routes,
        next_route_node_ids_by_agent={
            "agent0": 1,
            "agent1": 1,
        },
        agent_ids=["agent0", "agent1"],
    )

    completed_target_node_ids = {}
    main._record_completed_target_nodes(
        completed_targets=[
            {
                "target_id": "target",
                "agent_id": "agent1",
            }
        ],
        agent_observations=[
            {
                "agent_id": "agent0",
                "current_viewpoint_index": 0,
            },
            {
                "agent_id": "agent1",
                "current_viewpoint_index": 2,
            },
        ],
        completed_target_node_ids=completed_target_node_ids,
    )

    assert executed_routes == {
        "agent0": [0, 1],
        "agent1": [2, 1],
    }
    assert completed_target_node_ids == {"target": 2}


def test_write_mllm_completion_route_summary_writes_json_distance_summary(
    tmp_path,
    monkeypatch,
):
    _write_connectivity(tmp_path)
    monkeypatch.setenv("MATTERPORT_CONNECTIVITY_DIR", str(tmp_path / "connectivity"))
    debug_output_dir = tmp_path / "mllm_debug_outputs" / "case"

    summary = main._write_mllm_completion_route_summary(
        test_case="case",
        scan_id="scan",
        debug_output_dir=str(debug_output_dir),
        executed_routes_by_agent={
            "agent0": [0, 1, 2],
        },
        completed_target_node_ids={
            "target": 2,
        },
    )

    assert summary["agents"][0]["route_node_ids"] == [0, 1, 2]
    assert summary["agents"][0]["route_viewpoint_ids"] == ["vp0", "vp1", "vp2"]
    assert summary["agents"][0]["edge_distances"] == pytest.approx([1.0, 1.0])
    assert summary["agents"][0]["path_distance"] == pytest.approx(2.0)
    assert summary["total_distance"] == pytest.approx(2.0)
    assert "plot_path" not in summary
    assert not (debug_output_dir / "case_mllm_routes.png").exists()
    summary_path = debug_output_dir / "case_mllm_route_summary.txt"
    assert json.loads(summary_path.read_text(encoding="utf-8")) == summary


def test_main_oracle_mode_calls_oracle_runner(monkeypatch):
    import oracle_runner

    calls = []

    def fake_run_oracle(test_case):
        calls.append(test_case)

    monkeypatch.setattr(oracle_runner, "run_oracle", fake_run_oracle)

    assert main.main(["test1", "--oracle"]) == 0
    assert calls == ["test1"]


def test_main_resolves_bare_test_case_to_scenario_path(monkeypatch):
    calls = []

    def fake_run_scenario(config_path):
        calls.append(config_path)

    monkeypatch.setattr(main, "run_scenario", fake_run_scenario)
    monkeypatch.setattr(main.debugpy, "breakpoint", lambda: None)

    assert main.main(["test1"]) == 0
    assert calls == ["scenarios\\test1.json"]


def test_main_accepts_existing_config_path(tmp_path, monkeypatch):
    config_path = tmp_path / "case.json"
    config_path.write_text("{}", encoding="utf-8")
    calls = []

    def fake_run_scenario(config_path):
        calls.append(config_path)

    monkeypatch.setattr(main, "run_scenario", fake_run_scenario)
    monkeypatch.setattr(main.debugpy, "breakpoint", lambda: None)

    assert main.main([str(config_path)]) == 0
    assert calls == [str(config_path)]
