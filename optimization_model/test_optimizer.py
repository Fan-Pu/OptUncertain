import importlib.util
import os
import pathlib
import sys
import types
import unittest


GUROBI_PYTHON_LIB = r"D:\gurobi1201\win64\python311\lib"
if os.path.isdir(GUROBI_PYTHON_LIB) and GUROBI_PYTHON_LIB not in sys.path:
    sys.path.append(GUROBI_PYTHON_LIB)

helper_stub = types.ModuleType("Helper")
helper_stub.TYPE_VP = 1

_original_helper = sys.modules.get("Helper")
sys.modules["Helper"] = helper_stub

module_path = pathlib.Path(__file__).resolve().parent / "optimizer.py"
spec = importlib.util.spec_from_file_location("optimizer_under_test_multi", module_path)
optimizer_under_test = importlib.util.module_from_spec(spec)
spec.loader.exec_module(optimizer_under_test)
RollingHorizonOptimizer = optimizer_under_test.RollingHorizonOptimizer


def tearDownModule():
    if _original_helper is None:
        sys.modules.pop("Helper", None)
    else:
        sys.modules["Helper"] = _original_helper


class _FakeNode:
    def __init__(
        self,
        node_type,
        grounded,
        exist_prob,
        target_probs,
        node_visit_times=0,
    ):
        self.type = node_type
        self.grounded = grounded
        self.exist_prob = exist_prob
        self.target_probs = dict(target_probs)
        self.node_visit_times = node_visit_times


class _FakeEdge:
    def __init__(self, source_node_id, target_node_id, distance_mean, exist_prob):
        self.source_node_id = source_node_id
        self.target_node_id = target_node_id
        self.distance_mean = distance_mean
        self.exist_prob = exist_prob


class _FakeGraph:
    def __init__(self):
        self.target_descriptions = ["green plant", "glass on table"]
        self.target_ids = ["green plant", "glass on table"]
        self.target_id_to_description = {
            "green plant": "green plant",
            "glass on table": "glass on table",
        }
        self.observation_step = 0
        self.nodes = {
            1: _FakeNode(1, True, 1.0, {"green plant": 0.0, "glass on table": 0.0}),
            2: _FakeNode(1, True, 1.0, {"green plant": 0.0, "glass on table": 0.0}),
            3: _FakeNode(1, True, 1.0, {"green plant": 0.9, "glass on table": 0.1}),
            4: _FakeNode(1, True, 1.0, {"green plant": 0.1, "glass on table": 0.9}),
            5: _FakeNode(0, False, 0.6, {"green plant": 0.2, "glass on table": 0.2}),
            6: _FakeNode(1, False, 1.0, {"green plant": 0.95, "glass on table": 0.95}),
            7: _FakeNode(1, False, 1.0, {"green plant": 0.95, "glass on table": 0.95}),
            8: _FakeNode(1, False, 1.0, {"green plant": 0.95, "glass on table": 0.95}),
        }
        self.edges = {
            (1, 3): _FakeEdge(1, 3, 0.1, 1.0),
            (1, 4): _FakeEdge(1, 4, 0.2, 1.0),
            (1, 5): _FakeEdge(1, 5, 0.05, 0.9),
            (2, 3): _FakeEdge(2, 3, 0.2, 1.0),
            (2, 4): _FakeEdge(2, 4, 0.1, 1.0),
            (2, 5): _FakeEdge(2, 5, 0.05, 0.9),
            (3, 5): _FakeEdge(3, 5, 0.05, 0.9),
            (4, 5): _FakeEdge(4, 5, 0.05, 0.9),
            (6, 7): _FakeEdge(6, 7, 0.1, 1.0),
            (7, 8): _FakeEdge(7, 8, 0.1, 1.0),
            (6, 8): _FakeEdge(6, 8, 0.1, 1.0),
        }


class _RevisitPenaltyGraph:
    def __init__(self):
        self.target_ids = ["target"]
        self.target_id_to_description = {"target": "target"}
        self.observation_step = 0
        self.nodes = {
            1: _FakeNode(1, True, 1.0, {"target": 0.0}),
            2: _FakeNode(1, True, 1.0, {"target": 1.0}, node_visit_times=5),
            3: _FakeNode(1, True, 1.0, {"target": 1.0}, node_visit_times=0),
        }
        self.edges = {
            (1, 2): _FakeEdge(1, 2, 1.0, 1.0),
            (1, 3): _FakeEdge(1, 3, 1.0, 1.0),
        }


class MultiAgentOptimizerTest(unittest.TestCase):
    def test_assigns_each_unfound_target_at_most_once_across_agents(self):
        optimizer = RollingHorizonOptimizer()
        result = optimizer.solve(
            hypothesis_graph=_FakeGraph(),
            agent_current_vp_ids={"agent0": 1, "agent1": 2},
            target_found_flags={"green plant": False, "glass on table": False},
        )

        self.assertEqual(len(result["target_assignments"]), 2)
        self.assertEqual(
            sorted(item["target_id"] for item in result["target_assignments"]),
            ["glass on table", "green plant"],
        )

    def test_masks_found_targets_and_first_hop_is_viewpoint_for_each_agent(self):
        optimizer = RollingHorizonOptimizer()
        result = optimizer.solve(
            hypothesis_graph=_FakeGraph(),
            agent_current_vp_ids={"agent0": 1, "agent1": 2},
            target_found_flags={"green plant": True, "glass on table": False},
        )

        self.assertEqual(
            [item["target_id"] for item in result["target_assignments"]],
            ["glass on table"],
        )
        self.assertEqual(result["agent_paths"]["agent0"]["next_vp_node_id"], 3)
        self.assertEqual(result["agent_paths"]["agent1"]["next_vp_node_id"], 4)

    def test_revisit_penalty_avoids_visited_viewpoint_when_other_terms_match(self):
        optimizer = RollingHorizonOptimizer()
        result = optimizer.solve(
            hypothesis_graph=_RevisitPenaltyGraph(),
            agent_current_vp_ids={"agent0": 1},
            target_found_flags={"target": False},
        )

        self.assertEqual(result["agent_paths"]["agent0"]["next_vp_node_id"], 3)

    def test_detached_high_reward_cycle_is_not_selected(self):
        optimizer = RollingHorizonOptimizer()
        result = optimizer.solve(
            hypothesis_graph=_FakeGraph(),
            agent_current_vp_ids={"agent0": 1, "agent1": 2},
            target_found_flags={"green plant": False, "glass on table": False},
        )

        selected_cycle_nodes = {
            node_id
            for agent_path in result["agent_paths"].values()
            for node_id in agent_path["planned_path_node_ids"]
            if node_id in {6, 7, 8}
        }
        self.assertEqual(selected_cycle_nodes, set())

    def test_normalized_objective_value_is_bounded(self):
        optimizer = RollingHorizonOptimizer()
        result = optimizer.solve(
            hypothesis_graph=_FakeGraph(),
            agent_current_vp_ids={"agent0": 1, "agent1": 2},
            target_found_flags={"green plant": False, "glass on table": False},
        )

        self.assertGreaterEqual(result["objective_value"], -1.0)
        self.assertLessEqual(result["objective_value"], 1.0)


if __name__ == "__main__":
    unittest.main()
