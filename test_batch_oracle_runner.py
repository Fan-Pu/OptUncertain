import json
from pathlib import Path

import oracle_runner
from route_plotter import EnvironmentGraph


def _line_graph():
    return EnvironmentGraph(
        scan_id="scan",
        viewpoint_id_by_index={0: "vp0", 1: "vp1", 2: "vp2"},
        coords_by_node_id={
            0: (0.0, 0.0),
            1: (1.0, 0.0),
            2: (2.0, 0.0),
        },
        edge_distances={(0, 1): 1.0, (1, 2): 1.0},
    )


def test_build_oracle_instance_uses_detectable_viewpoint_candidates(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        oracle_runner,
        "load_environment_graph",
        lambda scan_id, connectivity_dir: _line_graph(),
    )

    instance = oracle_runner.build_oracle_instance(
        {
            "test_case": "scan_case_0001",
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
                    "target_id": "7",
                    "description": "target",
                    "detectable_viewpoint_ids": ["vp1", "vp2"],
                }
            ],
        },
        project_root=tmp_path,
    )

    assert instance.agent_current_vp_ids == {"agent0": 0}
    assert instance.target_candidate_node_ids_by_target_id == {"7": [1, 2]}
    assert instance.graph.nodes[0].target_probs["7"] == 0.0
    assert instance.graph.nodes[1].target_probs["7"] == 1.0
    assert instance.graph.nodes[2].target_probs["7"] == 1.0


def test_shortest_walk_oracle_allows_revisited_transit_viewpoint():
    environment_graph = EnvironmentGraph(
        scan_id="scan",
        viewpoint_id_by_index={0: "vp0", 1: "vp1", 2: "vp2", 3: "vp3"},
        coords_by_node_id={
            0: (0.0, 0.0),
            1: (1.0, 0.0),
            2: (2.0, 1.0),
            3: (2.0, -1.0),
        },
        edge_distances={(0, 1): 1.0, (1, 2): 1.0, (1, 3): 1.0},
    )
    nodes = {
        0: oracle_runner.OracleNode(
            node_id=0,
            label="vp0",
            type=oracle_runner.TYPE_VP,
            exist_prob=1.0,
            grounded=True,
            target_probs={"a": 0.0, "b": 0.0},
            connected_node_ids={1},
        ),
        1: oracle_runner.OracleNode(
            node_id=1,
            label="vp1",
            type=oracle_runner.TYPE_VP,
            exist_prob=1.0,
            grounded=True,
            target_probs={"a": 0.0, "b": 0.0},
            connected_node_ids={0, 2, 3},
        ),
        2: oracle_runner.OracleNode(
            node_id=2,
            label="vp2",
            type=oracle_runner.TYPE_VP,
            exist_prob=1.0,
            grounded=True,
            target_probs={"a": 1.0, "b": 0.0},
            connected_node_ids={1},
        ),
        3: oracle_runner.OracleNode(
            node_id=3,
            label="vp3",
            type=oracle_runner.TYPE_VP,
            exist_prob=1.0,
            grounded=True,
            target_probs={"a": 0.0, "b": 1.0},
            connected_node_ids={1},
        ),
    }
    edges = {
        edge_id: oracle_runner.OracleEdge(
            source_node_id=edge_id[0],
            target_node_id=edge_id[1],
            distance_mean=distance,
            distance_var=0.0,
            cond_exist_prob=1.0,
            exist_prob=1.0,
            grounded=True,
        )
        for edge_id, distance in environment_graph.edge_distances.items()
    }
    instance = oracle_runner.OracleInstance(
        test_case="branch_case",
        scan_id="scan",
        graph=oracle_runner.OracleGraph(
            target_records=[
                {"target_id": "a", "description": "target a"},
                {"target_id": "b", "description": "target b"},
            ],
            nodes=nodes,
            edges=edges,
        ),
        agent_current_vp_ids={"agent0": 0},
        environment_graph=environment_graph,
        target_node_ids_by_target_id={"a": 2, "b": 3},
        target_candidate_node_ids_by_target_id={"a": [2], "b": [3]},
    )

    result = oracle_runner._solve_oracle_shortest_walk(instance)

    assert result["agent_paths"]["agent0"]["route_node_ids"] in (
        [0, 1, 2, 1, 3],
        [0, 1, 3, 1, 2],
    )
    assert result["objective_value"] == 4.0
    assert sorted(
        (item["target_id"], item["node_id"]) for item in result["target_assignments"]
    ) == [("a", 2), ("b", 3)]


def test_run_batch_oracles_loads_generated_cases_and_writes_summary(
    monkeypatch,
    tmp_path,
):
    batch_path = tmp_path / "scenarios" / "batch.json"
    generated_cases_path = (
        tmp_path / "mllm_debug_outputs" / "batch" / "generated_cases.json"
    )
    batch_path.parent.mkdir(parents=True)
    generated_cases_path.parent.mkdir(parents=True)

    batch_path.write_text(
        json.dumps(
            {
                "scans": [
                    {
                        "scan_id": "scan",
                        "targets": [
                            {
                                "target_id": "7",
                                "description": "target",
                                "detectable_viewpoint_ids": ["vp1", "vp2"],
                            }
                        ],
                    }
                ],
                "agent_num_selections": [{"agent_number": 1, "case_number": 1}],
                "target_num_selections": [{"target_number": 1, "case_number": 1}],
            }
        ),
        encoding="utf-8",
    )
    generated_cases_path.write_text(
        json.dumps(
            {
                "batch_id": "batch",
                "case_order": ["scan_case_0001"],
                "cases": {
                    "scan_case_0001": {
                        "test_case": "scan_case_0001",
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
                                "target_id": "7",
                                "description": "target",
                            }
                        ],
                        "debug_output_dir": "mllm_debug_outputs/scan_case_0001",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    captured_calls = []

    def fake_run_oracle(
        scenario,
        project_root,
        connectivity_dir,
        output_dir,
        wait_for_debugger,
        print_summary,
        write_model_lp,
        use_shortest_walk_solver,
    ):
        captured_calls.append(
            {
                "scenario": scenario,
                "project_root": Path(project_root),
                "connectivity_dir": Path(connectivity_dir),
                "output_dir": Path(output_dir),
                "wait_for_debugger": wait_for_debugger,
                "print_summary": print_summary,
                "write_model_lp": write_model_lp,
                "use_shortest_walk_solver": use_shortest_walk_solver,
            }
        )
        return {
            "test_case": scenario["test_case"],
            "target_node_ids_by_target_id": {"7": 1},
            "agents": [],
            "total_distance": 0.0,
            "maximum_agent_distance": 0.0,
        }

    monkeypatch.setattr(oracle_runner, "run_oracle", fake_run_oracle)

    result = oracle_runner.run_batch_oracles(batch_path, project_root=tmp_path)

    assert result["oracle_case_count"] == 1
    assert captured_calls == [
        {
            "scenario": {
                "test_case": "scan_case_0001",
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
                        "target_id": "7",
                        "description": "target",
                        "detectable_viewpoint_ids": ["vp1", "vp2"],
                    }
                ],
            },
            "project_root": tmp_path,
            "connectivity_dir": tmp_path / "connectivity",
            "output_dir": tmp_path / "mllm_debug_outputs" / "scan_case_0001",
            "wait_for_debugger": False,
            "print_summary": False,
            "write_model_lp": False,
            "use_shortest_walk_solver": True,
        }
    ]

    summary_path = tmp_path / "mllm_debug_outputs" / "batch" / "oracle_summaries.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["oracle_case_count"] == 1
    assert summary["case_order"] == ["scan_case_0001"]


def test_run_batch_oracles_skips_completed_cases_and_rebuilds_summary(
    monkeypatch,
    tmp_path,
):
    batch_path = tmp_path / "scenarios" / "batch.json"
    generated_cases_path = (
        tmp_path / "mllm_debug_outputs" / "batch" / "generated_cases.json"
    )
    completed_output_dir = tmp_path / "mllm_debug_outputs" / "scan_case_0001"
    pending_output_dir = tmp_path / "mllm_debug_outputs" / "scan_case_0002"
    batch_path.parent.mkdir(parents=True)
    generated_cases_path.parent.mkdir(parents=True)
    completed_output_dir.mkdir(parents=True)

    batch_path.write_text(
        json.dumps(
            {
                "scans": [
                    {
                        "scan_id": "scan",
                        "targets": [
                            {
                                "target_id": "7",
                                "description": "target",
                                "detectable_viewpoint_ids": ["vp1"],
                            }
                        ],
                    }
                ],
                "agent_num_selections": [{"agent_number": 1, "case_number": 2}],
                "target_num_selections": [{"target_number": 1, "case_number": 1}],
            }
        ),
        encoding="utf-8",
    )
    generated_cases_path.write_text(
        json.dumps(
            {
                "batch_id": "batch",
                "case_order": ["scan_case_0001", "scan_case_0002"],
                "cases": {
                    "scan_case_0001": {
                        "test_case": "scan_case_0001",
                        "scan_id": "scan",
                        "agents": [
                            {
                                "id": "agent0",
                                "start_viewpoint_id": "vp0",
                                "heading": 0.0,
                                "elevation": 0.0,
                            }
                        ],
                        "targets": [{"target_id": "7", "description": "target"}],
                        "debug_output_dir": "mllm_debug_outputs/scan_case_0001",
                    },
                    "scan_case_0002": {
                        "test_case": "scan_case_0002",
                        "scan_id": "scan",
                        "agents": [
                            {
                                "id": "agent0",
                                "start_viewpoint_id": "vp0",
                                "heading": 0.0,
                                "elevation": 0.0,
                            }
                        ],
                        "targets": [{"target_id": "7", "description": "target"}],
                        "debug_output_dir": "mllm_debug_outputs/scan_case_0002",
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    completed_summary = {
        "test_case": "scan_case_0001",
        "target_node_ids_by_target_id": {"7": 1},
        "agents": [],
        "total_distance": 1.0,
        "maximum_agent_distance": 1.0,
    }
    (completed_output_dir / "scan_case_0001_oracle_route_summary.txt").write_text(
        json.dumps(completed_summary),
        encoding="utf-8",
    )
    (completed_output_dir / "optimizer_routes_oracle.json").write_text(
        json.dumps({"agents": []}),
        encoding="utf-8",
    )

    captured_calls = []

    def fake_run_oracle(
        scenario,
        project_root,
        connectivity_dir,
        output_dir,
        wait_for_debugger,
        print_summary,
        write_model_lp,
        use_shortest_walk_solver,
    ):
        captured_calls.append(
            {
                "test_case": scenario["test_case"],
                "output_dir": Path(output_dir),
                "write_model_lp": write_model_lp,
                "use_shortest_walk_solver": use_shortest_walk_solver,
            }
        )
        pending_output_dir.mkdir(parents=True)
        pending_summary = {
            "test_case": scenario["test_case"],
            "target_node_ids_by_target_id": {"7": 1},
            "agents": [],
            "total_distance": 2.0,
            "maximum_agent_distance": 2.0,
        }
        (pending_output_dir / "scan_case_0002_oracle_route_summary.txt").write_text(
            json.dumps(pending_summary),
            encoding="utf-8",
        )
        (pending_output_dir / "optimizer_routes_oracle.json").write_text(
            json.dumps({"agents": []}),
            encoding="utf-8",
        )
        return pending_summary

    monkeypatch.setattr(oracle_runner, "run_oracle", fake_run_oracle)

    result = oracle_runner.run_batch_oracles(batch_path, project_root=tmp_path)

    assert result["oracle_case_count"] == 2
    assert captured_calls == [
        {
            "test_case": "scan_case_0002",
            "output_dir": pending_output_dir,
            "write_model_lp": False,
            "use_shortest_walk_solver": True,
        }
    ]

    summary_path = tmp_path / "mllm_debug_outputs" / "batch" / "oracle_summaries.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["oracle_case_count"] == 2
    assert summary["case_order"] == ["scan_case_0001", "scan_case_0002"]
    assert summary["cases"]["scan_case_0001"] == completed_summary
    assert summary["cases"]["scan_case_0002"]["total_distance"] == 2.0
