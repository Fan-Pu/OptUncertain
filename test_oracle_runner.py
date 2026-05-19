from __future__ import annotations

import json

from oracle_runner import build_oracle_instance, run_oracle


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


def test_run_oracle_uses_case_name_for_path_input_outputs(tmp_path, monkeypatch):
    import optimization_model

    _write_oracle_case(tmp_path)

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
