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
helper_stub.TYPE_REGION = 0
helper_stub.TYPE_VP = 1

_original_helper = sys.modules.get("Helper")
sys.modules["Helper"] = helper_stub

module_path = pathlib.Path(__file__).resolve().parent / "optimizer.py"
spec = importlib.util.spec_from_file_location("optimizer_under_test_multi", module_path)
optimizer_under_test = importlib.util.module_from_spec(spec)
spec.loader.exec_module(optimizer_under_test)
RollingHorizonOptimizer = optimizer_under_test.RollingHorizonOptimizer


OPTIMIZER_CONFIG = {
    "goal_weight": 0.2222,
    "dist_weight": 0.2222,
    "arc_weight": 0.3333,
    "node_weight": 0.1111,
    "visit_weight": 0.1111,
}

UNIQUE_TARGET_REWARD_CONFIG = dict(OPTIMIZER_CONFIG, unique_target_reward=True)
INACTIVE_AGENT_CONFIG = dict(OPTIMIZER_CONFIG, allow_inactive_agents=True)
ORACLE_INACTIVE_AGENT_CONFIG = dict(
    UNIQUE_TARGET_REWARD_CONFIG,
    allow_inactive_agents=True,
)
ORACLE_EXACT_COVERAGE_CONFIG = dict(
    ORACLE_INACTIVE_AGENT_CONFIG,
    force_positive_target_assignment=True,
    minimize_distance_after_targets=True,
)
GOAL_ONLY_OPTIMIZER_CONFIG = dict(
    OPTIMIZER_CONFIG,
    goal_weight=1.0,
    dist_weight=0.0,
    arc_weight=0.0,
    node_weight=0.0,
    visit_weight=0.0,
)


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
    def __init__(
        self,
        source_node_id,
        target_node_id,
        distance_mean,
        exist_prob,
        grounded=True,
        cond_exist_prob=None,
    ):
        self.source_node_id = source_node_id
        self.target_node_id = target_node_id
        self.distance_mean = distance_mean
        self.exist_prob = exist_prob
        self.cond_exist_prob = (
            exist_prob if cond_exist_prob is None else cond_exist_prob
        )
        self.grounded = grounded


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
            6: _FakeNode(
                1,
                False,
                1.0,
                {"green plant": 0.95, "glass on table": 0.95},
                node_visit_times=3,
            ),
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
            2: _FakeNode(1, True, 0.9, {"target": 1.0}, node_visit_times=5),
            3: _FakeNode(1, True, 0.9, {"target": 1.0}, node_visit_times=0),
        }
        self.edges = {
            (1, 2): _FakeEdge(1, 2, 1.0, 0.9),
            (1, 3): _FakeEdge(1, 3, 1.0, 0.9),
        }


class _VisitedGroundedLeafGraph:
    def __init__(self):
        self.target_ids = ["target"]
        self.target_id_to_description = {"target": "target"}
        self.observation_step = 0
        self.nodes = {
            1: _FakeNode(1, True, 1.0, {"target": 0.0}),
            2: _FakeNode(1, True, 1.0, {"target": 1.0}, node_visit_times=5),
            3: _FakeNode(1, True, 1.0, {"target": 0.0}),
        }
        self.edges = {
            (1, 2): _FakeEdge(1, 2, 1.0, 1.0),
            (1, 3): _FakeEdge(1, 3, 1.0, 1.0),
        }


class _VisitedGroundedNonLeafGraph:
    def __init__(self):
        self.target_ids = ["target"]
        self.target_id_to_description = {"target": "target"}
        self.observation_step = 0
        self.nodes = {
            1: _FakeNode(1, True, 1.0, {"target": 0.0}),
            2: _FakeNode(1, True, 1.0, {"target": 1.0}, node_visit_times=5),
            3: _FakeNode(1, True, 1.0, {"target": 0.0}),
            4: _FakeNode(1, True, 1.0, {"target": 0.0}),
        }
        self.edges = {
            (1, 2): _FakeEdge(1, 2, 1.0, 1.0),
            (1, 3): _FakeEdge(1, 3, 1.0, 1.0),
            (2, 4): _FakeEdge(2, 4, 1.0, 1.0),
        }


class _UngroundedFirstHopGraph:
    def __init__(self):
        self.target_ids = ["target"]
        self.target_id_to_description = {"target": "target"}
        self.observation_step = 0
        self.nodes = {
            1: _FakeNode(1, True, 1.0, {"target": 0.0}),
            2: _FakeNode(1, True, 1.0, {"target": 1.0}),
            3: _FakeNode(1, True, 1.0, {"target": 0.0}),
        }
        self.edges = {
            (1, 2): _FakeEdge(1, 2, 0.01, 1.0, grounded=False),
            (1, 3): _FakeEdge(1, 3, 10.0, 1.0, grounded=True),
        }


class _ObjectiveBoundsUngroundedFirstHopGraph:
    def __init__(self):
        self.target_ids = ["target"]
        self.target_id_to_description = {"target": "target"}
        self.observation_step = 0
        self.nodes = {
            1: _FakeNode(1, True, 1.0, {"target": 0.0}),
            2: _FakeNode(1, True, 1.0, {"target": 0.9}, node_visit_times=3),
            3: _FakeNode(1, True, 1.0, {"target": 0.4}, node_visit_times=7),
        }
        self.edges = {
            (1, 2): _FakeEdge(1, 2, 1.0, 0.2, grounded=False),
            (1, 3): _FakeEdge(1, 3, 5.0, 0.6, grounded=True),
        }


class _InactiveAgentUngroundedOnlyGraph:
    def __init__(self):
        self.target_ids = ["target"]
        self.target_id_to_description = {"target": "target"}
        self.observation_step = 0
        self.nodes = {
            1: _FakeNode(1, True, 1.0, {"target": 0.0}),
            2: _FakeNode(1, True, 1.0, {"target": 0.0}),
            3: _FakeNode(1, True, 1.0, {"target": 1.0}),
            4: _FakeNode(1, True, 1.0, {"target": 0.0}),
        }
        self.edges = {
            (1, 3): _FakeEdge(1, 3, 0.1, 1.0, grounded=True),
            (2, 4): _FakeEdge(2, 4, 0.1, 1.0, grounded=False),
        }


class _ObjectiveBoundsGraph:
    def __init__(self):
        self.target_ids = ["target"]
        self.target_id_to_description = {"target": "target"}
        self.observation_step = 0
        self.nodes = {
            1: _FakeNode(1, True, 1.0, {"target": 0.0}),
            2: _FakeNode(1, True, 0.8, {"target": 0.5}, node_visit_times=2),
            3: _FakeNode(1, False, 0.6, {"target": 0.9}, node_visit_times=4),
            4: _FakeNode(0, False, 0.7, {"target": 0.8}, node_visit_times=99),
        }
        self.edges = {
            (1, 2): _FakeEdge(1, 2, 2.0, 0.9),
            (1, 3): _FakeEdge(1, 3, 3.0, 0.7),
            (1, 4): _FakeEdge(1, 4, 1.0, 0.6),
        }


class _RegionVisitGraph:
    def __init__(self):
        self.target_ids = ["target"]
        self.target_id_to_description = {"target": "target"}
        self.observation_step = 0
        self.nodes = {
            1: _FakeNode(1, True, 1.0, {"target": 0.0}),
            2: _FakeNode(1, True, 0.8, {"target": 1.0}, node_visit_times=0),
            3: _FakeNode(0, False, 0.7, {"target": 1.0}, node_visit_times=99),
        }
        self.edges = {
            (1, 2): _FakeEdge(1, 2, 1.0, 0.8),
            (1, 3): _FakeEdge(1, 3, 1.0, 0.8),
        }


class _VZConditionalEdgeGraph:
    def __init__(self):
        self.target_ids = ["target"]
        self.target_id_to_description = {"target": "target"}
        self.observation_step = 0
        self.nodes = {
            1: _FakeNode(1, True, 1.0, {"target": 0.0}),
            2: _FakeNode(1, True, 1.0, {"target": 0.1}),
            3: _FakeNode(0, False, 0.2, {"target": 1.0}),
        }
        self.edges = {
            (1, 2): _FakeEdge(1, 2, 0.0, 1.0, grounded=True),
            (2, 3): _FakeEdge(
                2,
                3,
                0.0,
                0.14,
                grounded=False,
                cond_exist_prob=0.7,
            ),
        }


class _UngroundedViewpointAndRegionRewardGraph:
    def __init__(self):
        self.target_ids = ["target"]
        self.target_id_to_description = {"target": "target"}
        self.observation_step = 0
        self.nodes = {
            1: _FakeNode(1, True, 1.0, {"target": 0.0}),
            2: _FakeNode(1, False, 1.0, {"target": 0.5}),
            3: _FakeNode(0, False, 1.0, {"target": 0.5}),
        }
        self.edges = {
            (1, 2): _FakeEdge(1, 2, 0.0, 1.0),
            (2, 3): _FakeEdge(2, 3, 0.0, 1.0),
        }


class _OtherAgentCurrentNodeGraph:
    def __init__(self):
        self.target_ids = ["target"]
        self.target_id_to_description = {"target": "target"}
        self.observation_step = 0
        self.nodes = {
            1: _FakeNode(1, True, 1.0, {"target": 0.0}),
            2: _FakeNode(1, True, 1.0, {"target": 1.0}),
            3: _FakeNode(1, True, 1.0, {"target": 0.0}),
        }
        self.edges = {
            (1, 2): _FakeEdge(1, 2, 0.1, 1.0),
            (2, 3): _FakeEdge(2, 3, 0.1, 1.0),
        }


class _SharedTargetGraph:
    def __init__(self):
        self.target_ids = ["target"]
        self.target_id_to_description = {"target": "target"}
        self.observation_step = 0
        self.nodes = {
            1: _FakeNode(1, True, 1.0, {"target": 0.0}),
            2: _FakeNode(1, True, 1.0, {"target": 0.0}),
            3: _FakeNode(1, True, 1.0, {"target": 1.0}),
            4: _FakeNode(1, True, 1.0, {"target": 0.0}),
        }
        self.edges = {
            (1, 3): _FakeEdge(1, 3, 0.1, 1.0),
            (2, 3): _FakeEdge(2, 3, 0.1, 1.0),
            (2, 4): _FakeEdge(2, 4, 0.2, 1.0),
        }


class _SharedFirstHopChoiceGraph:
    def __init__(self):
        self.target_ids = ["target"]
        self.target_id_to_description = {"target": "target"}
        self.observation_step = 0
        self.nodes = {
            1: _FakeNode(1, True, 1.0, {"target": 0.0}),
            2: _FakeNode(1, True, 1.0, {"target": 0.0}),
            3: _FakeNode(1, True, 1.0, {"target": 1.0}),
            4: _FakeNode(1, True, 1.0, {"target": 0.1}),
            5: _FakeNode(1, True, 1.0, {"target": 0.1}),
        }
        self.edges = {
            (1, 3): _FakeEdge(1, 3, 0.1, 1.0),
            (1, 4): _FakeEdge(1, 4, 0.2, 1.0),
            (2, 3): _FakeEdge(2, 3, 0.1, 1.0),
            (2, 5): _FakeEdge(2, 5, 0.2, 1.0),
        }


class _LaterOverlapAllowedGraph:
    def __init__(self):
        self.target_ids = ["target"]
        self.target_id_to_description = {"target": "target"}
        self.observation_step = 0
        self.nodes = {
            1: _FakeNode(1, True, 1.0, {"target": 0.0}),
            2: _FakeNode(1, True, 1.0, {"target": 0.0}),
            3: _FakeNode(1, True, 1.0, {"target": 0.1}),
            4: _FakeNode(1, True, 1.0, {"target": 0.1}),
            5: _FakeNode(1, True, 1.0, {"target": 1.0}),
        }
        self.edges = {
            (1, 3): _FakeEdge(1, 3, 0.1, 1.0),
            (2, 4): _FakeEdge(2, 4, 0.1, 1.0),
            (3, 5): _FakeEdge(3, 5, 0.1, 1.0),
            (4, 5): _FakeEdge(4, 5, 0.1, 1.0),
        }


class _InactiveCurrentBlocksFirstHopGraph:
    def __init__(self):
        self.target_ids = ["target"]
        self.target_id_to_description = {"target": "target"}
        self.observation_step = 0
        self.nodes = {
            1: _FakeNode(1, True, 1.0, {"target": 0.0}),
            2: _FakeNode(1, True, 1.0, {"target": 1.0}),
            3: _FakeNode(1, True, 1.0, {"target": 0.5}),
        }
        self.edges = {
            (1, 2): _FakeEdge(1, 2, 0.1, 1.0),
            (1, 3): _FakeEdge(1, 3, 0.2, 1.0),
        }


class _OneAgentCoversAllTargetsGraph:
    def __init__(self):
        self.target_ids = ["target0", "target1"]
        self.target_id_to_description = {
            "target0": "target0",
            "target1": "target1",
        }
        self.observation_step = 0
        self.nodes = {
            1: _FakeNode(
                1,
                True,
                1.0,
                {"target0": 1.0, "target1": 0.0},
            ),
            2: _FakeNode(
                1,
                True,
                1.0,
                {"target0": 0.0, "target1": 0.0},
            ),
            3: _FakeNode(
                1,
                True,
                1.0,
                {"target0": 0.0, "target1": 0.0},
            ),
            4: _FakeNode(
                1,
                True,
                1.0,
                {"target0": 0.0, "target1": 1.0},
            ),
            5: _FakeNode(
                1,
                True,
                1.0,
                {"target0": 0.0, "target1": 0.0},
            ),
        }
        self.edges = {
            (1, 3): _FakeEdge(1, 3, 0.1, 1.0),
            (3, 4): _FakeEdge(3, 4, 0.1, 1.0),
            (2, 5): _FakeEdge(2, 5, 0.1, 1.0),
        }


class _OracleDistanceChoiceGraph:
    def __init__(self):
        self.target_ids = ["target0", "target1"]
        self.target_id_to_description = {
            "target0": "target0",
            "target1": "target1",
        }
        self.observation_step = 0
        self.nodes = {
            1: _FakeNode(
                1,
                True,
                1.0,
                {"target0": 1.0, "target1": 0.0},
            ),
            2: _FakeNode(
                1,
                True,
                1.0,
                {"target0": 0.0, "target1": 0.0},
            ),
            3: _FakeNode(
                1,
                True,
                1.0,
                {"target0": 0.0, "target1": 0.0},
            ),
            4: _FakeNode(
                1,
                True,
                1.0,
                {"target0": 0.0, "target1": 1.0},
            ),
            5: _FakeNode(
                1,
                True,
                1.0,
                {"target0": 0.0, "target1": 0.0},
            ),
        }
        self.edges = {
            (1, 3): _FakeEdge(1, 3, 0.1, 1.0),
            (3, 4): _FakeEdge(3, 4, 0.1, 1.0),
            (2, 5): _FakeEdge(2, 5, 0.1, 1.0),
            (4, 5): _FakeEdge(5, 4, 1.0, 1.0),
        }


class _ZeroRewardAssignmentGraph:
    def __init__(self):
        self.target_ids = ["target"]
        self.target_id_to_description = {"target": "target"}
        self.observation_step = 0
        self.nodes = {
            1: _FakeNode(1, True, 1.0, {"target": 0.0}),
            2: _FakeNode(1, True, 1.0, {"target": 1.0}),
        }
        self.edges = {
            (1, 2): _FakeEdge(1, 2, 1.0, 1.0),
        }


class MultiAgentOptimizerTest(unittest.TestCase):
    def _objective_bounds_for_graph(
        self,
        graph,
        agent_current_vp_ids,
        target_found_flags,
    ):
        optimizer = RollingHorizonOptimizer(OPTIMIZER_CONFIG)
        agent_ids = list(agent_current_vp_ids)
        target_ids = list(graph.target_ids)
        all_node_ids = sorted(graph.nodes)
        candidate_node_ids_by_agent = {
            agent_id: [
                node_id
                for node_id in all_node_ids
                if node_id != int(agent_current_vp_ids[agent_id])
            ]
            for agent_id in agent_ids
        }
        candidate_viewpoint_node_ids_by_agent = {
            agent_id: [
                node_id
                for node_id in candidate_node_ids_by_agent[agent_id]
                if graph.nodes[node_id].type == 1
            ]
            for agent_id in agent_ids
        }
        directed_edges = optimizer._build_directed_edges(hypothesis_graph=graph)
        edge_distance = {
            (source_id, target_id): graph.edges[
                tuple(sorted((source_id, target_id)))
            ].distance_mean
            for source_id, target_id in directed_edges
        }
        edge_nonexist_penalty = {
            (source_id, target_id): 1.0
            - graph.edges[tuple(sorted((source_id, target_id)))].cond_exist_prob
            for source_id, target_id in directed_edges
        }
        node_nonexist_penalty = {
            node_id: 1.0 - graph.nodes[node_id].exist_prob
            for node_id in all_node_ids
        }
        revisit_penalty = {
            node_id: (
                float(graph.nodes[node_id].node_visit_times)
                if graph.nodes[node_id].type == 1
                else 0.0
            )
            for node_id in all_node_ids
        }
        node_reward = {}
        for node_id in all_node_ids:
            node = graph.nodes[node_id]
            node_reward[node_id] = {
                target_id: node.target_probs.get(target_id, 0.0)
                for target_id in target_ids
            }

        return optimizer._objective_bounds(
            hypothesis_graph=graph,
            agent_current_vp_ids=agent_current_vp_ids,
            target_found_flags=target_found_flags,
            target_ids=target_ids,
            all_node_ids=all_node_ids,
            candidate_node_ids_by_agent=candidate_node_ids_by_agent,
            candidate_viewpoint_node_ids_by_agent=(
                candidate_viewpoint_node_ids_by_agent
            ),
            directed_edges=directed_edges,
            edge_distance=edge_distance,
            edge_nonexist_penalty=edge_nonexist_penalty,
            node_reward=node_reward,
            node_nonexist_penalty=node_nonexist_penalty,
            revisit_penalty=revisit_penalty,
        )

    def test_revisit_penalty_avoids_visited_viewpoint_when_other_terms_match(self):
        optimizer = RollingHorizonOptimizer(OPTIMIZER_CONFIG)
        result = optimizer.solve(
            hypothesis_graph=_RevisitPenaltyGraph(),
            agent_current_vp_ids={"agent0": 1},
            target_found_flags={"target": False},
        )

        self.assertEqual(result["agent_paths"]["agent0"]["next_vp_node_id"], 3)

    def test_visited_grounded_leaf_viewpoint_cannot_be_revisited(self):
        optimizer = RollingHorizonOptimizer(GOAL_ONLY_OPTIMIZER_CONFIG)
        result = optimizer.solve(
            hypothesis_graph=_VisitedGroundedLeafGraph(),
            agent_current_vp_ids={"agent0": 1},
            target_found_flags={"target": False},
        )

        self.assertEqual(result["agent_paths"]["agent0"]["next_vp_node_id"], 3)
        self.assertNotIn(2, result["agent_paths"]["agent0"]["planned_path_node_ids"])
        self.assertNotIn((1, 2), result["selected_edges"]["agent0"])

    def test_visited_grounded_non_leaf_viewpoint_can_be_revisited(self):
        optimizer = RollingHorizonOptimizer(GOAL_ONLY_OPTIMIZER_CONFIG)
        result = optimizer.solve(
            hypothesis_graph=_VisitedGroundedNonLeafGraph(),
            agent_current_vp_ids={"agent0": 1},
            target_found_flags={"target": False},
        )

        self.assertEqual(result["agent_paths"]["agent0"]["next_vp_node_id"], 2)
        self.assertIn(2, result["agent_paths"]["agent0"]["planned_path_node_ids"])
        self.assertIn((1, 2), result["selected_edges"]["agent0"])

    def test_first_hop_must_use_grounded_vv_edge(self):
        optimizer = RollingHorizonOptimizer(OPTIMIZER_CONFIG)
        result = optimizer.solve(
            hypothesis_graph=_UngroundedFirstHopGraph(),
            agent_current_vp_ids={"agent0": 1},
            target_found_flags={"target": False},
        )

        self.assertEqual(result["agent_paths"]["agent0"]["next_vp_node_id"], 3)
        self.assertIn((1, 3), result["selected_edges"]["agent0"])
        self.assertNotIn((1, 2), result["selected_edges"]["agent0"])

    def test_detached_high_reward_cycle_is_not_selected(self):
        optimizer = RollingHorizonOptimizer(OPTIMIZER_CONFIG)
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

    def test_assigns_each_unfound_target_at_most_once_across_agents(self):
        optimizer = RollingHorizonOptimizer(UNIQUE_TARGET_REWARD_CONFIG)
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
        optimizer = RollingHorizonOptimizer(UNIQUE_TARGET_REWARD_CONFIG)
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

    def test_unique_target_reward_can_assign_target_at_current_viewpoint(self):
        optimizer = RollingHorizonOptimizer(UNIQUE_TARGET_REWARD_CONFIG)
        result = optimizer.solve(
            hypothesis_graph=_OtherAgentCurrentNodeGraph(),
            agent_current_vp_ids={"agent0": 1, "agent1": 2},
            target_found_flags={"target": False},
        )

        self.assertIn(2, result["agent_paths"]["agent0"]["planned_path_node_ids"])
        self.assertTrue(
            any(
                assignment["agent_id"] == "agent1"
                and assignment["node_id"] == 2
                and assignment["target_id"] == "target"
                for assignment in result["target_assignments"]
            )
        )

    def test_default_mode_keeps_target_assignments_empty(self):
        optimizer = RollingHorizonOptimizer(OPTIMIZER_CONFIG)
        result = optimizer.solve(
            hypothesis_graph=_SharedTargetGraph(),
            agent_current_vp_ids={"agent0": 1, "agent1": 2},
            target_found_flags={"target": False},
        )

        self.assertEqual(result["target_assignments"], [])

    def test_unique_target_reward_assigns_shared_target_once(self):
        optimizer = RollingHorizonOptimizer(UNIQUE_TARGET_REWARD_CONFIG)
        result = optimizer.solve(
            hypothesis_graph=_SharedTargetGraph(),
            agent_current_vp_ids={"agent0": 1, "agent1": 2},
            target_found_flags={"target": False},
        )

        self.assertEqual(len(result["target_assignments"]), 1)
        self.assertEqual(result["target_assignments"][0]["target_id"], "target")
        self.assertEqual(result["target_assignments"][0]["node_id"], 3)

    def test_agents_choose_distinct_first_viewpoints(self):
        optimizer = RollingHorizonOptimizer(OPTIMIZER_CONFIG)
        result = optimizer.solve(
            hypothesis_graph=_SharedFirstHopChoiceGraph(),
            agent_current_vp_ids={"agent0": 1, "agent1": 2},
            target_found_flags={"target": False},
        )

        next_viewpoints = {
            result["agent_paths"]["agent0"]["next_vp_node_id"],
            result["agent_paths"]["agent1"]["next_vp_node_id"],
        }
        self.assertEqual(len(next_viewpoints), 2)
        self.assertIn(3, next_viewpoints)

    def test_later_route_overlap_is_allowed_when_first_viewpoints_differ(self):
        optimizer = RollingHorizonOptimizer(OPTIMIZER_CONFIG)
        result = optimizer.solve(
            hypothesis_graph=_LaterOverlapAllowedGraph(),
            agent_current_vp_ids={"agent0": 1, "agent1": 2},
            target_found_flags={"target": False},
        )

        self.assertEqual(result["agent_paths"]["agent0"]["next_vp_node_id"], 3)
        self.assertEqual(result["agent_paths"]["agent1"]["next_vp_node_id"], 4)
        self.assertIn(5, result["agent_paths"]["agent0"]["planned_path_node_ids"])
        self.assertIn(5, result["agent_paths"]["agent1"]["planned_path_node_ids"])

    def test_agent_can_enter_other_agents_start_if_other_agent_departs(self):
        optimizer = RollingHorizonOptimizer(
            dict(OPTIMIZER_CONFIG, allow_inactive_agents=True)
        )
        result = optimizer.solve(
            hypothesis_graph=_InactiveCurrentBlocksFirstHopGraph(),
            agent_current_vp_ids={"agent0": 1, "agent1": 2},
            target_found_flags={"target": False},
        )

        self.assertEqual(result["agent_paths"]["agent0"]["next_vp_node_id"], 2)
        self.assertNotEqual(result["agent_paths"]["agent1"]["route_node_ids"], [2])

    def test_oracle_mode_allows_unassigned_agent_to_wait_at_start(self):
        optimizer = RollingHorizonOptimizer(ORACLE_INACTIVE_AGENT_CONFIG)
        result = optimizer.solve(
            hypothesis_graph=_OneAgentCoversAllTargetsGraph(),
            agent_current_vp_ids={"agent0": 1, "agent1": 2},
            target_found_flags={"target0": False, "target1": False},
        )

        self.assertEqual(result["agent_paths"]["agent1"]["route_node_ids"], [2])
        self.assertEqual(
            result["agent_paths"]["agent1"]["planned_path_node_ids"],
            [],
        )
        self.assertEqual(
            sorted(
                (assignment["agent_id"], assignment["target_id"])
                for assignment in result["target_assignments"]
            ),
            [("agent0", "target0"), ("agent0", "target1")],
        )

    def test_inactive_agent_does_not_need_grounded_first_hop(self):
        optimizer = RollingHorizonOptimizer(INACTIVE_AGENT_CONFIG)
        result = optimizer.solve(
            hypothesis_graph=_InactiveAgentUngroundedOnlyGraph(),
            agent_current_vp_ids={"agent0": 1, "agent1": 2},
            target_found_flags={"target": False},
        )

        self.assertEqual(result["agent_paths"]["agent0"]["route_node_ids"], [1, 3])
        self.assertEqual(result["agent_paths"]["agent1"]["route_node_ids"], [2])
        self.assertEqual(
            result["agent_paths"]["agent1"]["planned_path_node_ids"],
            [],
        )

    def test_default_mode_still_forces_each_agent_to_depart(self):
        optimizer = RollingHorizonOptimizer(OPTIMIZER_CONFIG)
        result = optimizer.solve(
            hypothesis_graph=_OneAgentCoversAllTargetsGraph(),
            agent_current_vp_ids={"agent0": 1, "agent1": 2},
            target_found_flags={"target0": False, "target1": False},
        )

        self.assertNotEqual(result["agent_paths"]["agent1"]["route_node_ids"], [2])

    def test_default_mode_leaves_oracle_exact_coverage_flags_disabled(self):
        optimizer = RollingHorizonOptimizer(OPTIMIZER_CONFIG)

        self.assertFalse(optimizer.unique_target_reward)
        self.assertFalse(optimizer.force_positive_target_assignment)
        self.assertFalse(optimizer.minimize_distance_after_targets)

    def test_oracle_exact_coverage_assigns_target_to_lower_distance_agent(self):
        optimizer = RollingHorizonOptimizer(ORACLE_EXACT_COVERAGE_CONFIG)
        result = optimizer.solve(
            hypothesis_graph=_OracleDistanceChoiceGraph(),
            agent_current_vp_ids={"agent0": 1, "agent1": 2},
            target_found_flags={"target0": False, "target1": False},
        )

        self.assertEqual(result["agent_paths"]["agent0"]["route_node_ids"], [1, 3, 4])
        self.assertEqual(result["agent_paths"]["agent1"]["route_node_ids"], [2])
        self.assertEqual(
            sorted(
                (assignment["agent_id"], assignment["node_id"], assignment["target_id"])
                for assignment in result["target_assignments"]
            ),
            [("agent0", 1, "target0"), ("agent0", 4, "target1")],
        )

    def test_zero_reward_assignments_do_not_satisfy_oracle_target_coverage(self):
        optimizer = RollingHorizonOptimizer(ORACLE_EXACT_COVERAGE_CONFIG)
        result = optimizer.solve(
            hypothesis_graph=_ZeroRewardAssignmentGraph(),
            agent_current_vp_ids={"agent0": 1},
            target_found_flags={"target": False},
        )

        self.assertEqual(result["agent_paths"]["agent0"]["route_node_ids"], [1, 2])
        self.assertEqual(
            result["target_assignments"],
            [{"target_id": "target", "node_id": 2, "agent_id": "agent0"}],
        )

    def test_normalized_objective_value_is_bounded(self):
        optimizer = RollingHorizonOptimizer(OPTIMIZER_CONFIG)
        result = optimizer.solve(
            hypothesis_graph=_FakeGraph(),
            agent_current_vp_ids={"agent0": 1, "agent1": 2},
            target_found_flags={"green plant": False, "glass on table": False},
        )

        self.assertGreaterEqual(result["objective_value"], -1.0)
        self.assertLessEqual(result["objective_value"], 1.0)

    def test_objective_bounds_match_paper_equations(self):
        bounds = self._objective_bounds_for_graph(
            graph=_ObjectiveBoundsGraph(),
            agent_current_vp_ids={"agent0": 1},
            target_found_flags={"target": False},
        )

        self.assertEqual(
            bounds,
            (
                0.5,
                2.2,
                2.0,
                9.0,
                0.0,
                1.2000000000000002,
                0.0,
                0.9,
                2.0,
                6.0,
            ),
        )

    def test_objective_bounds_ignore_ungrounded_first_hop_edges(self):
        bounds = self._objective_bounds_for_graph(
            graph=_ObjectiveBoundsUngroundedFirstHopGraph(),
            agent_current_vp_ids={"agent0": 1},
            target_found_flags={"target": False},
        )

        self.assertEqual(
            bounds,
            (
                0.4,
                1.3,
                5.0,
                10.0,
                0.0,
                1.6,
                0.0,
                0.0,
                7.0,
                10.0,
            ),
        )

    def test_region_visit_counts_do_not_contribute_to_visit_bounds(self):
        bounds = self._objective_bounds_for_graph(
            graph=_RegionVisitGraph(),
            agent_current_vp_ids={"agent0": 1},
            target_found_flags={"target": False},
        )

        self.assertEqual(bounds[8], 0.0)
        self.assertEqual(bounds[9], 0.0)

    def test_vz_arc_uncertainty_uses_conditional_edge_existence(self):
        result = RollingHorizonOptimizer(GOAL_ONLY_OPTIMIZER_CONFIG).solve(
            hypothesis_graph=_VZConditionalEdgeGraph(),
            agent_current_vp_ids={"agent0": 1},
            target_found_flags={"target": False},
        )

        self.assertEqual(
            result["agent_paths"]["agent0"]["planned_path_node_ids"],
            [2, 3],
        )
        raw_terms = result["agent_paths"]["agent0"]["objective_terms"]["raw"]
        self.assertAlmostEqual(raw_terms["arc_nonexistence"], 0.3)
        self.assertAlmostEqual(raw_terms["node_nonexistence"], 0.8)

    def test_ungrounded_nodes_use_raw_target_probability(self):
        result = RollingHorizonOptimizer(OPTIMIZER_CONFIG).solve(
            hypothesis_graph=_UngroundedViewpointAndRegionRewardGraph(),
            agent_current_vp_ids={"agent0": 1},
            target_found_flags={"target": False},
        )

        self.assertEqual(
            result["agent_paths"]["agent0"]["planned_path_node_ids"],
            [2, 3],
        )
        self.assertAlmostEqual(
            result["agent_paths"]["agent0"]["objective_terms"]["raw"]["goal"],
            1.0,
        )

    def test_objective_terms_global_raw_matches_selected_variables(self):
        graph = _SharedTargetGraph()
        result = RollingHorizonOptimizer(OPTIMIZER_CONFIG).solve(
            hypothesis_graph=graph,
            agent_current_vp_ids={"agent0": 1, "agent1": 2},
            target_found_flags={"target": False},
        )

        expected_distance = sum(
            graph.edges[tuple(sorted(edge))].distance_mean
            for edges in result["selected_edges"].values()
            for edge in edges
        )
        expected_arc = sum(
            1.0 - graph.edges[tuple(sorted(edge))].cond_exist_prob
            for edges in result["selected_edges"].values()
            for edge in edges
        )
        expected_node = sum(
            1.0 - graph.nodes[node_id].exist_prob
            for agent_path in result["agent_paths"].values()
            for node_id in agent_path["planned_path_node_ids"]
        )
        expected_visit = sum(
            graph.nodes[node_id].node_visit_times
            for agent_path in result["agent_paths"].values()
            for node_id in agent_path["planned_path_node_ids"]
        )
        expected_goal = sum(
            max(graph.nodes[node_id].target_probs.values())
            for agent_path in result["agent_paths"].values()
            for node_id in agent_path["planned_path_node_ids"]
        )
        global_raw = result["objective_terms"]["global"]["raw"]

        self.assertAlmostEqual(global_raw["goal"], expected_goal)
        self.assertAlmostEqual(global_raw["distance"], expected_distance)
        self.assertAlmostEqual(global_raw["arc_nonexistence"], expected_arc)
        self.assertAlmostEqual(global_raw["node_nonexistence"], expected_node)
        self.assertAlmostEqual(global_raw["revisit"], expected_visit)

    def test_objective_terms_per_agent_sum_to_global_raw(self):
        result = RollingHorizonOptimizer(OPTIMIZER_CONFIG).solve(
            hypothesis_graph=_FakeGraph(),
            agent_current_vp_ids={"agent0": 1, "agent1": 2},
            target_found_flags={"green plant": False, "glass on table": False},
        )
        terms = result["objective_terms"]

        for term_name, global_value in terms["global"]["raw"].items():
            self.assertAlmostEqual(
                sum(
                    agent_terms["raw"][term_name]
                    for agent_terms in terms["by_agent"].values()
                ),
                global_value,
            )

    def test_objective_terms_weighted_contributions_reconcile_to_objective(self):
        result = RollingHorizonOptimizer(OPTIMIZER_CONFIG).solve(
            hypothesis_graph=_FakeGraph(),
            agent_current_vp_ids={"agent0": 1, "agent1": 2},
            target_found_flags={"green plant": False, "glass on table": False},
        )
        terms = result["objective_terms"]
        per_agent_weighted_sum = sum(
            sum(agent_terms["weighted_contribution"].values())
            for agent_terms in terms["by_agent"].values()
        )

        self.assertAlmostEqual(
            per_agent_weighted_sum + terms["objective_constant_offset"],
            result["objective_value"],
        )
        self.assertAlmostEqual(
            terms["weighted_contribution_sum"],
            result["objective_value"],
        )

    def test_unique_target_reward_records_start_node_goal_for_assigned_agent(self):
        result = RollingHorizonOptimizer(ORACLE_EXACT_COVERAGE_CONFIG).solve(
            hypothesis_graph=_OracleDistanceChoiceGraph(),
            agent_current_vp_ids={"agent0": 1, "agent1": 2},
            target_found_flags={"target0": False, "target1": False},
        )

        self.assertIn(
            {"target_id": "target0", "node_id": 1, "agent_id": "agent0"},
            result["target_assignments"],
        )
        self.assertEqual(
            result["agent_paths"]["agent0"]["objective_terms"]["raw"]["goal"],
            2.0,
        )
        self.assertEqual(
            result["agent_paths"]["agent1"]["objective_terms"]["raw"]["goal"],
            0.0,
        )

    def test_inactive_agent_records_zero_route_cost_terms(self):
        result = RollingHorizonOptimizer(INACTIVE_AGENT_CONFIG).solve(
            hypothesis_graph=_OneAgentCoversAllTargetsGraph(),
            agent_current_vp_ids={"agent0": 1, "agent1": 2},
            target_found_flags={"target0": False, "target1": False},
        )
        inactive_raw = result["agent_paths"]["agent1"]["objective_terms"]["raw"]

        self.assertEqual(result["agent_paths"]["agent1"]["route_node_ids"], [2])
        self.assertEqual(inactive_raw["distance"], 0.0)
        self.assertEqual(inactive_raw["arc_nonexistence"], 0.0)
        self.assertEqual(inactive_raw["node_nonexistence"], 0.0)
        self.assertEqual(inactive_raw["revisit"], 0.0)


if __name__ == "__main__":
    unittest.main()
