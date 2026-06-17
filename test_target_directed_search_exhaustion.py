import pytest

import Helper
import main
from semantic_persistence.hypothesis_graph import HypothesisGraph


def _graph_with_target():
    return HypothesisGraph(
        targets=[{"target_id": "5", "description": "target"}],
        bayes_config={
            "sigma_vv2": 4.0,
            "kappa_vv": 1.0,
            "varrho": 0.7,
            "epsilon": 1e-6,
        },
    )


def _add_viewpoint(
    graph,
    node_id,
    grounded,
    node_visit_times,
    target_prob=0.0,
    raw_target_prob=0.0,
):
    graph.add_or_update_node(
        node_id=node_id,
        label="vp%s" % node_id,
        node_type=Helper.TYPE_VP,
        exist_prob=1.0,
        grounded=grounded,
        target_probs={"5": target_prob},
        raw_target_probs={"5": raw_target_prob},
        node_visit_times=node_visit_times,
    )


def test_target_directed_search_exhaustion_reports_active_targets_without_endpoints():
    graph = _graph_with_target()
    graph.agent_current_vp_ids = {"agent0": 1}
    _add_viewpoint(graph, node_id=1, grounded=True, node_visit_times=1)
    _add_viewpoint(graph, node_id=2, grounded=True, node_visit_times=0)
    _add_viewpoint(graph, node_id=3, grounded=False, node_visit_times=1)

    info = main._target_directed_search_exhaustion_info(
        hypothesis_graph=graph,
        target_found_flags=graph.target_found,
    )

    assert info == {
        "target_directed_search_exhausted_target_ids": ["5"],
        "target_directed_eligible_endpoint_ids": [],
    }


def test_target_directed_search_exhaustion_ignores_zero_reward_when_endpoint_exists():
    graph = _graph_with_target()
    graph.agent_current_vp_ids = {"agent0": 1}
    _add_viewpoint(graph, node_id=1, grounded=True, node_visit_times=1)
    _add_viewpoint(graph, node_id=2, grounded=False, node_visit_times=0)

    info = main._target_directed_search_exhaustion_info(
        hypothesis_graph=graph,
        target_found_flags=graph.target_found,
    )

    assert info is None


def test_target_directed_no_positive_reward_reports_active_targets_with_zero_rewards():
    graph = _graph_with_target()
    graph.agent_current_vp_ids = {"agent0": 1}
    _add_viewpoint(graph, node_id=1, grounded=True, node_visit_times=1)
    _add_viewpoint(graph, node_id=2, grounded=False, node_visit_times=0)

    info = main._target_directed_no_positive_reward_info(
        hypothesis_graph=graph,
        target_found_flags=graph.target_found,
        use_raw_target_probs=False,
    )

    assert info == {
        "target_directed_no_positive_reward_target_ids": ["5"],
        "target_directed_eligible_endpoint_ids": [2],
        "target_directed_reward_source": "target_probs",
    }


def test_target_directed_no_positive_reward_ignores_positive_endpoint_reward():
    graph = _graph_with_target()
    graph.agent_current_vp_ids = {"agent0": 1}
    _add_viewpoint(graph, node_id=1, grounded=True, node_visit_times=1)
    _add_viewpoint(
        graph,
        node_id=2,
        grounded=False,
        node_visit_times=0,
        raw_target_prob=0.25,
    )

    info = main._target_directed_no_positive_reward_info(
        hypothesis_graph=graph,
        target_found_flags=graph.target_found,
        use_raw_target_probs=True,
    )

    assert info is None


def test_run_scenario_returns_incomplete_when_target_directed_search_is_exhausted(
    monkeypatch,
):
    class FakeOptimizer:
        target_directed_mode = True
        target_directed_use_raw_target_probs = True

        def __init__(self, optimizer_config):
            pass

        def solve(self, **kwargs):
            raise AssertionError("optimizer.solve must not run after search exhaustion")

    class FakeMLLMClient:
        semantic_raw_output_index = 1
        last_direct_detections = []

        def __init__(self, **kwargs):
            pass

        def propose_semantic_nodes(self, **kwargs):
            return None

    monkeypatch.setattr(main, "_wait_for_debugger", lambda: None)
    monkeypatch.setattr(main, "_init_agent_sims", lambda scenario, scan_id: [])
    monkeypatch.setattr(
        main,
        "_write_mllm_route_summary",
        lambda **kwargs: {
            "status": kwargs["status"],
            "stop_reason": kwargs["stop_reason"],
            **kwargs.get("extra_metadata", {}),
        },
    )
    monkeypatch.setattr(
        main.Helper,
        "build_viewpoint_index",
        lambda scan_id: None,
    )
    monkeypatch.setattr(
        main.Helper,
        "horizon_scan_individual_sims_return",
        lambda **kwargs: [
            {
                "agent_id": "agent0",
                "current_viewpoint_index": 1,
                "raw_panorama": object(),
                "visible_viewpoints": [],
            }
        ],
    )
    monkeypatch.setattr(main.Helper, "viewpoint_index_by_vp_label", {"vp1": 1})
    monkeypatch.setattr(main.Helper, "viewpoint_vp_label_by_index", {1: "vp1"})

    import optimization_model
    import semantic_persistence

    monkeypatch.setitem(
        optimization_model.__dict__,
        "RollingHorizonOptimizer",
        FakeOptimizer,
    )
    monkeypatch.setitem(semantic_persistence.__dict__, "MLLMClient", FakeMLLMClient)
    monkeypatch.setitem(semantic_persistence.__dict__, "SigLIPScorer", lambda: object())
    monkeypatch.setattr(
        semantic_persistence.HypothesisGraph,
        "export_debug_snapshot",
        lambda self, output_dir, step_index: None,
    )

    result = main.run_scenario(
        {
            "scan_id": "scan",
            "test_case": "case",
            "agents": [
                {
                    "id": "agent0",
                    "start_viewpoint_id": "vp1",
                    "heading": 0.0,
                    "elevation": 0.0,
                }
            ],
            "targets": [{"target_id": "5", "description": "target"}],
            "mllm": {
                "raw_output_dir": "raw",
                "debug_output_dir": "debug",
                "graph_model_name": "graph-model",
                "detection_model_name": "detection-model",
                "read_saved_raw_outputs": True,
            },
            "bayes": {
                "sigma_vv2": 4.0,
                "kappa_vv": 1.0,
                "varrho": 0.7,
                "epsilon": 1e-6,
            },
            "optimizer": {
                "goal_weight": 0.45,
                "dist_weight": 0.17,
                "arc_weight": 0.05,
                "node_weight": 0.03,
                "visit_weight": 0.3,
                "target_directed_mode": True,
            },
            "max_steps": 50,
        },
        show_agent_views=False,
    )

    assert result["status"] == "incomplete"
    assert result["stop_reason"] == "target_directed_search_exhausted"
    assert result["steps_completed"] == 1
    assert result["max_steps"] == 50
    assert result["target_directed_search_exhausted_target_ids"] == ["5"]
    assert result["target_directed_eligible_endpoint_ids"] == []


def test_run_scenario_returns_incomplete_when_target_directed_rewards_are_zero(
    monkeypatch,
):
    class FakeOptimizer:
        target_directed_mode = True
        target_directed_use_raw_target_probs = False

        def __init__(self, optimizer_config):
            pass

        def solve(self, **kwargs):
            raise AssertionError("optimizer.solve must not run after zero rewards")

    class FakeMLLMClient:
        semantic_raw_output_index = 1
        last_direct_detections = []

        def __init__(self, **kwargs):
            pass

        def propose_semantic_nodes(self, **kwargs):
            return None

    monkeypatch.setattr(main, "_wait_for_debugger", lambda: None)
    monkeypatch.setattr(main, "_init_agent_sims", lambda scenario, scan_id: [])
    monkeypatch.setattr(
        main,
        "_write_mllm_route_summary",
        lambda **kwargs: {
            "status": kwargs["status"],
            "stop_reason": kwargs["stop_reason"],
            **kwargs.get("extra_metadata", {}),
        },
    )
    monkeypatch.setattr(main.Helper, "build_viewpoint_index", lambda scan_id: None)
    monkeypatch.setattr(
        main.Helper,
        "horizon_scan_individual_sims_return",
        lambda **kwargs: [
            {
                "agent_id": "agent0",
                "current_viewpoint_index": 1,
                "raw_panorama": object(),
                "visible_viewpoints": [{"viewpoint_index": 2, "distance": 1.0}],
            }
        ],
    )
    monkeypatch.setattr(main.Helper, "viewpoint_index_by_vp_label", {"vp1": 1})
    monkeypatch.setattr(
        main.Helper,
        "viewpoint_vp_label_by_index",
        {1: "vp1", 2: "vp2"},
    )

    import optimization_model
    import semantic_persistence

    monkeypatch.setitem(
        optimization_model.__dict__,
        "RollingHorizonOptimizer",
        FakeOptimizer,
    )
    monkeypatch.setitem(semantic_persistence.__dict__, "MLLMClient", FakeMLLMClient)
    monkeypatch.setitem(semantic_persistence.__dict__, "SigLIPScorer", lambda: object())
    monkeypatch.setattr(
        semantic_persistence.HypothesisGraph,
        "export_debug_snapshot",
        lambda self, output_dir, step_index: None,
    )

    result = main.run_scenario(
        {
            "scan_id": "scan",
            "test_case": "case",
            "agents": [
                {
                    "id": "agent0",
                    "start_viewpoint_id": "vp1",
                    "heading": 0.0,
                    "elevation": 0.0,
                }
            ],
            "targets": [{"target_id": "5", "description": "target"}],
            "mllm": {
                "raw_output_dir": "raw",
                "debug_output_dir": "debug",
                "graph_model_name": "graph-model",
                "detection_model_name": "detection-model",
                "read_saved_raw_outputs": True,
            },
            "bayes": {
                "sigma_vv2": 4.0,
                "kappa_vv": 1.0,
                "varrho": 0.7,
                "epsilon": 1e-6,
            },
            "optimizer": {
                "goal_weight": 0.45,
                "dist_weight": 0.17,
                "arc_weight": 0.05,
                "node_weight": 0.03,
                "visit_weight": 0.3,
                "target_directed_mode": True,
                "target_directed_use_raw_target_probs": False,
            },
            "max_steps": 50,
        },
        show_agent_views=False,
    )

    assert result["status"] == "incomplete"
    assert result["stop_reason"] == "target_directed_no_positive_reward_endpoint"
    assert result["target_directed_no_positive_reward_target_ids"] == ["5"]
    assert result["target_directed_eligible_endpoint_ids"] == [2]
    assert result["target_directed_reward_source"] == "target_probs"


def test_batch_skip_record_preserves_search_exhaustion_diagnostics():
    record = main._build_batch_skip_record(
        scenario={
            "test_case": "case",
            "scan_id": "scan",
            "mllm": {
                "debug_output_dir": "debug",
                "raw_output_dir": "raw",
            },
        },
        result={
            "status": "incomplete",
            "stop_reason": "target_directed_search_exhausted",
            "steps_completed": 7,
            "target_directed_search_exhausted_target_ids": ["5"],
            "target_directed_eligible_endpoint_ids": [],
        },
    )

    assert record["reason"] == "target_directed_search_exhausted"
    assert record["target_directed_search_exhausted_target_ids"] == ["5"]
    assert record["target_directed_eligible_endpoint_ids"] == []


def test_batch_skip_record_preserves_no_positive_reward_diagnostics():
    record = main._build_batch_skip_record(
        scenario={
            "test_case": "case",
            "scan_id": "scan",
            "mllm": {
                "debug_output_dir": "debug",
                "raw_output_dir": "raw",
            },
        },
        result={
            "status": "incomplete",
            "stop_reason": "target_directed_no_positive_reward_endpoint",
            "steps_completed": 7,
            "target_directed_no_positive_reward_target_ids": ["5"],
            "target_directed_eligible_endpoint_ids": [2],
            "target_directed_reward_source": "target_probs",
        },
    )

    assert record["reason"] == "target_directed_no_positive_reward_endpoint"
    assert record["target_directed_no_positive_reward_target_ids"] == ["5"]
    assert record["target_directed_eligible_endpoint_ids"] == [2]
    assert record["target_directed_reward_source"] == "target_probs"
