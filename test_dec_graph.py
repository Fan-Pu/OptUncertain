import json
from pathlib import Path
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from benchmark_methods.dec_graph import (
    DecGraphAgentPhaseError,
    create_started_gurobi_environments,
    dispose_gurobi_environments,
    run_parallel_agent_phase,
)
from run_benchmark_sweep import _configured_batch, _method_run_id
from semantic_persistence.hypothesis_graph import HypothesisGraph
from semantic_persistence.mllm_client import MLLMClient


class _FakeSim:
    pass


class _FakeDecGraphHelper:
    viewpoint_index_by_vp_label = {"vp0": 0, "vp1": 1, "vp42": 42}
    viewpoint_vp_label_by_index = {0: "vp0", 1: "vp1", 42: "vp42"}

    def __init__(self):
        self.executed_move_specs = []

    def build_viewpoint_index(self, scan_id):
        return None

    def horizon_scan_individual_sims_return(
        self,
        sims,
        agent_ids,
        viewpoint_index_by_vp,
    ):
        return [
            {
                "agent_id": agent_id,
                "current_viewpoint_id": "vp%s" % agent_index,
                "current_viewpoint_index": agent_index,
                "local_actions": [],
                "best_heading_for_vp": {"vp42": 0.25},
            }
            for agent_index, agent_id in enumerate(agent_ids)
        ]

    def execute_individual_first_hops(self, sims, move_specs, render):
        self.executed_move_specs.append(list(move_specs))


class _FakeDetectorClient:
    def __init__(self):
        self.semantic_raw_output_index = 1
        self.calls = []

    def detect_targets(self, agent_observations, targets, target_found):
        self.calls.append(list(agent_observations))
        self.semantic_raw_output_index += 1
        return []


class _FakeGraphClient:
    def __init__(self, agent_id):
        self.agent_id = agent_id
        self.calls = []

    def propose_graph_hypotheses(self, agent_observations, targets, graph):
        self.calls.append(
            {
                "observations": list(agent_observations),
                "agent_ids_in_graph": dict(graph.agent_current_vp_ids),
            }
        )
        return {"agent_id": self.agent_id}


class _FakePrivateGraph:
    instances = []

    def __init__(self, targets, bayes_config):
        self.owner_index = len(self.__class__.instances)
        self.target_ids = [str(target["target_id"]) for target in targets]
        self.target_found = {target_id: False for target_id in self.target_ids}
        self.agent_current_vp_ids = {}
        self.nodes = {42: SimpleNamespace(grounded=False)}
        self.__class__.instances.append(self)

    def mark_target_found(self, target_id):
        self.target_found[str(target_id)] = True

    def sync_agent_current_viewpoints(self, observations):
        self.agent_current_vp_ids = {
            str(observation["agent_id"]): int(
                observation["current_viewpoint_index"]
            )
            for observation in observations
        }

    def update_from_mllm(self, mllm_output, agent_observations):
        self.sync_agent_current_viewpoints(agent_observations)

    def update_without_mllm(self, agent_observations):
        self.sync_agent_current_viewpoints(agent_observations)

    def export_debug_snapshot(self, output_dir, step_index):
        return None


class _FakeOptimizer:
    def __init__(self, config, gurobi_env):
        self.target_directed_mode = False
        self.target_directed_use_raw_target_probs = False

    def solve(self, hypothesis_graph, agent_current_vp_ids, target_found_flags):
        agent_id = next(iter(agent_current_vp_ids))
        start_node_id = int(agent_current_vp_ids[agent_id])
        return {
            "solver": "fake",
            "target_assignments": [],
            "agent_paths": {
                agent_id: {
                    "next_vp_node_id": 42,
                    "route_node_ids": [start_node_id, 42],
                    "objective_terms": {},
                }
            },
        }


def test_dec_graph_configuration_reuses_exact_gemma_and_normal_detector():
    default_config = json.loads(
        Path("config/default_config.json").read_text(encoding="utf-8")
    )
    batch_config = json.loads(
        Path("scenarios/batch_test.json").read_text(encoding="utf-8")
    )

    configured = _configured_batch(
        method="dec_graph",
        batch_config=batch_config,
        default_config=default_config,
    )

    assert configured["benchmark"]["method"] == "dec_graph"
    assert configured["mllm"]["detection_model_name"] == "gpt-5.4-2026-03-05"
    assert configured["mllm"]["detection_reasoning_effort"] == "medium"
    assert configured["mllm"]["detection_service_tier"] is None
    assert configured["mllm"]["graph_model_name"] == "google/gemma-4-31B-it"
    assert configured["mllm"]["graph_extra_body_enabled"] is False
    assert configured["mllm"]["graph_presence_penalty_enabled"] is False
    assert configured["mllm"]["graph_max_tokens"] == 16384
    assert configured["mllm"]["graph_thinking"] is None
    assert _method_run_id("dec_graph", "unused") == "balanced100_DecGraph"


@pytest.mark.parametrize("stage", ["graph", "optimization"])
def test_dec_graph_agent_phase_runs_all_agents_concurrently(stage):
    agent_ids = ["agent0", "agent1", "agent2"]
    barrier = threading.Barrier(len(agent_ids))

    def call(agent_id):
        barrier.wait(timeout=2.0)
        time.sleep(0.05)
        return "%s-result" % agent_id

    results, timings = run_parallel_agent_phase(
        stage=stage,
        agent_ids=agent_ids,
        call=call,
    )

    assert set(results) == set(agent_ids)
    assert max(timing.started_at for timing in timings.values()) < min(
        timing.ended_at for timing in timings.values()
    )


def test_dec_graph_agent_phase_identifies_failed_agent_and_stage():
    def call(agent_id):
        if agent_id == "agent1":
            raise ValueError("bad graph")
        return agent_id

    with pytest.raises(DecGraphAgentPhaseError) as error_info:
        run_parallel_agent_phase(
            stage="graph",
            agent_ids=["agent0", "agent1"],
            call=call,
        )

    assert error_info.value.stage == "graph"
    assert error_info.value.agent_id == "agent1"
    assert isinstance(error_info.value.cause, ValueError)


def test_graph_only_api_does_not_call_detector(tmp_path):
    client = MLLMClient(
        graph_model_name="graph-model",
        detection_model_name="detector-model",
        read_saved_raw_outputs=False,
        raw_output_dir=str(tmp_path / "raw"),
        raw_debug_dir=str(tmp_path / "debug"),
    )
    client._build_graph_image_content = Mock(return_value=[])
    client._build_detection_image_content = Mock(
        side_effect=AssertionError("detection images must not be built")
    )
    client._detect_targets = Mock(
        side_effect=AssertionError("detector must not be called")
    )
    client._build_instruction = Mock(return_value=("system", "user"))
    client._request_completion = Mock(return_value='{"payload": true}')
    client._repair_graph_mllm_payload = Mock(return_value=[])
    client._validate_payload = Mock(return_value={"payload": True})
    client._write_semantic_raw_output = Mock()
    client._write_user_message = Mock()

    graph = SimpleNamespace(
        target_found={"0": False},
        get_mllm_summary=lambda: {},
    )
    output = client.propose_graph_hypotheses(
        agent_observations=[
            {"agent_id": "agent0", "current_viewpoint_index": 7}
        ],
        targets=[{"target_id": "0", "description": "cup"}],
        graph=graph,
    )

    assert output == {"payload": True}
    client._detect_targets.assert_not_called()
    client._build_detection_image_content.assert_not_called()
    assert client.semantic_raw_output_index == 2


def test_proposed_api_still_uses_combined_detection_and_graph_path():
    client = object.__new__(MLLMClient)
    client._propose_semantic_nodes_impl = Mock(return_value={"combined": True})
    graph = object()
    output = client.propose_semantic_nodes(
        agent_observations=[{"agent_id": "agent0"}],
        targets=[{"target_id": "0", "description": "cup"}],
        graph=graph,
    )

    assert output == {"combined": True}
    client._propose_semantic_nodes_impl.assert_called_once_with(
        agent_observations=[{"agent_id": "agent0"}],
        targets=[{"target_id": "0", "description": "cup"}],
        graph=graph,
        run_detection=True,
    )


def test_dedicated_gurobi_environments_support_parallel_models():
    import gurobipy as gp

    agent_ids = ["agent0", "agent1"]
    environments = create_started_gurobi_environments(agent_ids)
    barrier = threading.Barrier(len(agent_ids))
    try:
        def solve(agent_id):
            barrier.wait(timeout=2.0)
            with gp.Model("dec_graph_env_test", env=environments[agent_id]) as model:
                variable = model.addVar(vtype=gp.GRB.BINARY, name="x")
                model.setObjective(variable, gp.GRB.MAXIMIZE)
                model.Params.OutputFlag = 0
                model.optimize()
                return variable.X

        results, timings = run_parallel_agent_phase(
            stage="optimization",
            agent_ids=agent_ids,
            call=solve,
        )
    finally:
        dispose_gurobi_environments(environments)

    assert results == {"agent0": 1.0, "agent1": 1.0}
    assert max(timing.started_at for timing in timings.values()) < min(
        timing.ended_at for timing in timings.values()
    )


def test_private_graph_contexts_never_share_agent_locations():
    targets = [{"target_id": "0", "description": "cup"}]
    graph0 = HypothesisGraph(targets)
    graph1 = HypothesisGraph(targets)
    graph0.sync_agent_current_viewpoints(
        [{"agent_id": "agent0", "current_viewpoint_index": 10}]
    )
    graph1.sync_agent_current_viewpoints(
        [{"agent_id": "agent1", "current_viewpoint_index": 20}]
    )

    assert graph0.agent_current_vp_ids == {"agent0": 10}
    assert graph1.agent_current_vp_ids == {"agent1": 20}
    graph0.mark_target_found("0")
    graph1.mark_target_found("0")
    assert graph0.target_found == graph1.target_found == {"0": True}


def test_dec_graph_loop_shares_one_detection_but_allows_overlapping_moves(
    tmp_path,
    monkeypatch,
):
    import benchmark_methods
    import main
    import optimization_model
    import semantic_persistence

    helper = _FakeDecGraphHelper()
    detector = _FakeDetectorClient()
    graph_clients = {}
    _FakePrivateGraph.instances = []

    def fake_client_factory(scenario, scan_id, test_case):
        raw_dir = Path(str(scenario["mllm"]["raw_output_dir"]))
        if "agents" not in raw_dir.parts:
            return detector
        agent_id = raw_dir.name
        graph_clients[agent_id] = _FakeGraphClient(agent_id)
        return graph_clients[agent_id]

    disposed = []
    monkeypatch.setattr(main, "_wait_for_debugger", lambda: None)
    monkeypatch.setattr(main, "_helper_module", lambda: helper)
    monkeypatch.setattr(
        main,
        "_init_agent_sims",
        lambda scenario, scan_id: [_FakeSim(), _FakeSim()],
    )
    monkeypatch.setattr(
        main,
        "_initialize_executed_routes",
        lambda scenario: {"agent0": [0], "agent1": [1]},
    )
    monkeypatch.setattr(main, "_baseline_mllm_client", fake_client_factory)
    monkeypatch.setattr(
        main,
        "_baseline_result",
        lambda **kwargs: kwargs,
    )
    monkeypatch.setattr(semantic_persistence, "HypothesisGraph", _FakePrivateGraph)
    monkeypatch.setattr(
        optimization_model,
        "RollingHorizonOptimizer",
        _FakeOptimizer,
    )
    monkeypatch.setattr(
        benchmark_methods,
        "create_started_gurobi_environments",
        lambda agent_ids: {agent_id: object() for agent_id in agent_ids},
    )
    monkeypatch.setattr(
        benchmark_methods,
        "dispose_gurobi_environments",
        lambda environments: disposed.append(dict(environments)),
    )

    result = main._run_dec_graph_scenario(
        scenario={
            "test_case": "scan_case",
            "scan_id": "scan",
            "agents": [
                {"id": "agent0", "start_viewpoint_id": "vp0"},
                {"id": "agent1", "start_viewpoint_id": "vp1"},
            ],
            "targets": [{"target_id": "0", "description": "cup"}],
            "max_steps": 1,
            "batch_id": "batch",
            "mllm": {
                "raw_output_dir": str(tmp_path / "raw"),
                "debug_output_dir": str(tmp_path / "debug"),
            },
            "bayes": {},
            "optimizer": {},
            "benchmark": {"method": "dec_graph"},
        },
        show_agent_views=False,
    )

    assert len(detector.calls) == 1
    assert [item["agent_id"] for item in detector.calls[0]] == [
        "agent0",
        "agent1",
    ]
    assert [
        observation["agent_id"]
        for observation in graph_clients["agent0"].calls[0]["observations"]
    ] == ["agent0"]
    assert [
        observation["agent_id"]
        for observation in graph_clients["agent1"].calls[0]["observations"]
    ] == ["agent1"]
    assert graph_clients["agent0"].calls[0]["agent_ids_in_graph"] == {
        "agent0": 0
    }
    assert graph_clients["agent1"].calls[0]["agent_ids_in_graph"] == {
        "agent1": 1
    }
    assert len(helper.executed_move_specs) == 1
    assert [move["target_viewpoint_id"] for move in helper.executed_move_specs[0]] == [
        "vp42",
        "vp42",
    ]
    assert result["executed_routes_by_agent"] == {
        "agent0": [0, 42],
        "agent1": [1, 42],
    }
    audit = json.loads(
        (tmp_path / "debug" / "dec_graph_step_0001.json").read_text(
            encoding="utf-8"
        )
    )
    assert audit["overlapping_first_hops"] == {
        "42": ["agent0", "agent1"]
    }
    assert disposed
