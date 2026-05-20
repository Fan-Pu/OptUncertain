from __future__ import annotations

import json

from oracle_runner import build_oracle_instance, run_oracle, _oracle_optimizer_config


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _pose(x, y, z):
    pose = [0.0] * 16
    pose[3] = x
    pose[7] = y
    pose[11] = z
    return pose


def _write_oracle_case(root):
    _write_json(
        root / "scenarios" / "case.json",
        {
            "scan_id": "scan",
            "agents": [
                {
                    "id": "agent0",
                    "start_viewpoint_id": "vp0",
                    "heading": 0.0,
                    "elevation": 0.0,
                }
            ],
            "targets": [
                {
                    "target_id": "0",
                    "description": "target object",
                }
            ],
        },
    )
    _write_json(
        root / "scenarios" / "oracle_targets.json",
        {
            "case": {
                "0": 1,
            }
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


def _write_two_agent_oracle_case(root):
    _write_json(
        root / "scenarios" / "case.json",
        {
            "scan_id": "scan",
            "agents": [
                {
                    "id": "agent0",
                    "start_viewpoint_id": "vp0",
                    "heading": 0.0,
                    "elevation": 0.0,
                },
                {
                    "id": "agent1",
                    "start_viewpoint_id": "vp1",
                    "heading": 0.0,
                    "elevation": 0.0,
                },
            ],
            "targets": [
                {
                    "target_id": "0",
                    "description": "target object",
                }
            ],
        },
    )
    _write_json(
        root / "scenarios" / "oracle_targets.json",
        {
            "case": {
                "0": 2,
            }
        },
    )
    _write_json(
        root / "connectivity" / "scan_connectivity.json",
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
                "pose": _pose(2.0, 0.0, 0.0),
                "unobstructed": [False, True, False],
            },
        ],
    )


def test_build_oracle_instance_accepts_bare_case_name(tmp_path):
    _write_oracle_case(tmp_path)

    instance = build_oracle_instance(
        "case",
        project_root=tmp_path,
        connectivity_dir=tmp_path / "connectivity",
    )

    assert instance.test_case == "case"
    assert instance.scan_id == "scan"
    assert instance.agent_current_vp_ids == {"agent0": 0}
    assert instance.target_node_ids_by_target_id == {"0": 1}


def test_build_oracle_instance_accepts_scenario_config_path(tmp_path):
    _write_oracle_case(tmp_path)

    instance = build_oracle_instance(
        "scenarios/case.json",
        project_root=tmp_path,
        connectivity_dir=tmp_path / "connectivity",
    )

    assert instance.test_case == "case"
    assert instance.scan_id == "scan"
    assert instance.agent_current_vp_ids == {"agent0": 0}
    assert instance.target_node_ids_by_target_id == {"0": 1}


def test_oracle_optimizer_config_enables_unique_target_reward():
    config = _oracle_optimizer_config()

    assert config["unique_target_reward"] is True
    assert config["allow_inactive_agents"] is True
    assert config["force_positive_target_assignment"] is True
    assert config["minimize_distance_after_targets"] is True


def test_run_oracle_uses_case_name_for_path_input_outputs(tmp_path, monkeypatch):
    import oracle_runner
    import optimization_model

    _write_oracle_case(tmp_path)
    monkeypatch.setattr(oracle_runner.debugpy, "listen", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        oracle_runner.debugpy, "wait_for_client", lambda *args, **kwargs: None
    )

    class FakeOptimizer:
        def __init__(self, config):
            self.config = config

        def solve(self, hypothesis_graph, agent_current_vp_ids, target_found_flags):
            return {
                "agent_paths": {
                    "agent0": {
                        "route_node_ids": [0, 1],
                    }
                }
            }

    monkeypatch.setitem(
        optimization_model.__dict__,
        "RollingHorizonOptimizer",
        FakeOptimizer,
    )

    summary = run_oracle(
        "scenarios/case.json",
        project_root=tmp_path,
        connectivity_dir=tmp_path / "connectivity",
    )

    summary_path = (
        tmp_path / "mllm_debug_outputs" / "case" / "case_oracle_route_summary.txt"
    )
    assert summary["test_case"] == "case"
    assert summary_path.exists()
    assert not (tmp_path / "mllm_debug_outputs" / "scenarios").exists()


def test_run_oracle_pads_routes_to_equal_step_count(tmp_path, monkeypatch):
    import oracle_runner
    import optimization_model

    _write_two_agent_oracle_case(tmp_path)
    monkeypatch.setattr(oracle_runner.debugpy, "listen", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        oracle_runner.debugpy, "wait_for_client", lambda *args, **kwargs: None
    )

    class FakeOptimizer:
        def __init__(self, config):
            self.config = config

        def solve(self, hypothesis_graph, agent_current_vp_ids, target_found_flags):
            return {
                "agent_paths": {
                    "agent0": {
                        "route_node_ids": [0, 1, 2],
                    },
                    "agent1": {
                        "route_node_ids": [1, 2],
                    },
                }
            }

    monkeypatch.setitem(
        optimization_model.__dict__,
        "RollingHorizonOptimizer",
        FakeOptimizer,
    )

    summary = run_oracle(
        "case",
        project_root=tmp_path,
        connectivity_dir=tmp_path / "connectivity",
    )

    summaries_by_agent = {
        agent_summary["agent_id"]: agent_summary
        for agent_summary in summary["agents"]
    }
    assert summaries_by_agent["agent0"]["route_node_ids"] == [0, 1, 2]
    assert summaries_by_agent["agent1"]["route_node_ids"] == [1, 2, 2]
    assert summaries_by_agent["agent0"]["step_count"] == 2
    assert summaries_by_agent["agent1"]["step_count"] == 2
    assert summaries_by_agent["agent0"]["wait_steps"] == 0
    assert summaries_by_agent["agent1"]["wait_steps"] == 1
    assert summaries_by_agent["agent1"]["edge_distances"] == [1.0, 0.0]
