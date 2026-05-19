import json

import pytest

from oracle_runner import (
    build_oracle_instance,
    plot_oracle_routes,
    run_oracle,
    summarize_oracle_solution,
)


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _pose(x, y, z):
    pose = [0.0] * 16
    pose[3] = x
    pose[7] = y
    pose[11] = z
    return pose


def _write_case(tmp_path):
    _write_json(
        tmp_path / "scenarios" / "case.json",
        {
            "scan_id": "scan",
            "agents": [
                {
                    "id": "agent0",
                    "start_viewpoint_id": "vp0",
                }
            ],
            "targets": [
                {
                    "target_id": "0",
                    "description": "target zero",
                },
                {
                    "target_id": "1",
                    "description": "target one",
                },
            ],
        },
    )
    _write_json(
        tmp_path / "scenarios" / "oracle_targets.json",
        {
            "case": {
                "0": 1,
                "1": 2,
            }
        },
    )
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


def test_build_oracle_instance_sets_known_graph_and_target_probs(tmp_path):
    _write_case(tmp_path)

    instance = build_oracle_instance(
        "case",
        project_root=tmp_path,
        connectivity_dir=tmp_path / "connectivity",
    )

    assert sorted(instance.graph.nodes) == [0, 1, 2]
    assert sorted(instance.graph.edges) == [(0, 1), (1, 2)]
    assert instance.agent_current_vp_ids == {"agent0": 0}

    for node in instance.graph.nodes.values():
        assert node.exist_prob == 1.0
        assert node.grounded is True
        assert node.node_visit_times == 0

    for edge in instance.graph.edges.values():
        assert edge.distance_var == 0.0
        assert edge.cond_exist_prob == 1.0
        assert edge.exist_prob == 1.0
        assert edge.grounded is True

    assert instance.graph.nodes[0].target_probs == {"0": 0.0, "1": 0.0}
    assert instance.graph.nodes[1].target_probs == {"0": 1.0, "1": 0.0}
    assert instance.graph.nodes[2].target_probs == {"0": 0.0, "1": 1.0}


def test_summarize_oracle_solution_reports_distances(tmp_path):
    _write_case(tmp_path)
    instance = build_oracle_instance(
        "case",
        project_root=tmp_path,
        connectivity_dir=tmp_path / "connectivity",
    )
    result = {
        "agent_paths": {
            "agent0": {
                "route_node_ids": [0, 1, 2],
            }
        }
    }

    summary = summarize_oracle_solution(instance, result)

    assert summary["agents"][0]["route_node_ids"] == [0, 1, 2]
    assert summary["agents"][0]["route_viewpoint_ids"] == ["vp0", "vp1", "vp2"]
    assert summary["agents"][0]["edge_distances"] == pytest.approx([1.0, 1.0])
    assert summary["agents"][0]["path_distance"] == pytest.approx(2.0)
    assert summary["total_distance"] == pytest.approx(2.0)


def test_plot_oracle_routes_writes_full_graph_route_plot(tmp_path):
    _write_case(tmp_path)
    instance = build_oracle_instance(
        "case",
        project_root=tmp_path,
        connectivity_dir=tmp_path / "connectivity",
    )
    output_path = tmp_path / "plot.png"

    plot_oracle_routes(
        instance=instance,
        agent_summaries=[
            {
                "agent_id": "agent0",
                "route_node_ids": [0, 1, 2],
            }
        ],
        output_path=output_path,
    )

    assert output_path.exists()
    assert output_path.stat().st_size > 0


def test_run_oracle_writes_summary_to_mllm_debug_outputs(tmp_path, monkeypatch):
    import optimization_model

    _write_case(tmp_path)

    class FakeOptimizer:
        def __init__(self, config):
            self.config = config

        def solve(self, hypothesis_graph, agent_current_vp_ids, target_found_flags):
            return {
                "agent_paths": {
                    "agent0": {
                        "route_node_ids": [0, 1, 2],
                    }
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

    summary_path = (
        tmp_path / "mllm_debug_outputs" / "case" / "case_oracle_route_summary.txt"
    )
    assert summary_path.exists()
    assert json.loads(summary_path.read_text(encoding="utf-8")) == summary
    assert "plot_path" not in summary
    assert not (tmp_path / "oracle_outputs" / "case_oracle_routes.png").exists()
