import importlib.util
import pathlib
import sys
import types
import unittest

import numpy as np


helper_stub = types.ModuleType("Helper")
helper_stub.TYPE_REGION = 0
helper_stub.TYPE_VP = 1
helper_stub.viewpoint_vp_label_by_index = {1: "vp-1", 2: "vp-2", 3: "vp-3"}

_original_helper = sys.modules.get("Helper")
sys.modules["Helper"] = helper_stub

module_path = (
    pathlib.Path(__file__).resolve().parent
    / "semantic_persistence"
    / "hypothesis_graph.py"
)
spec = importlib.util.spec_from_file_location("hypothesis_graph_under_test_joint", module_path)
hypothesis_graph_under_test = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hypothesis_graph_under_test)
HypothesisGraph = hypothesis_graph_under_test.HypothesisGraph


def tearDownModule():
    if _original_helper is None:
        sys.modules.pop("Helper", None)
    else:
        sys.modules["Helper"] = _original_helper


class _FakeScorer:
    def __init__(self, score_map):
        self.score_map = score_map

    def score_images_text(self, images, text):
        best_score = 0.0
        for image in images:
            marker = int(np.asarray(image).reshape(-1)[0])
            best_score = max(best_score, self.score_map.get((marker, str(text)), 0.0))
        return best_score


class HypothesisGraphUpdateTest(unittest.TestCase):
    def _build_graph_and_step_one(self):
        graph = HypothesisGraph(
            target_descriptions={
                "plant": "green plant",
                "glass": "glass on table",
            }
        )
        scorer = _FakeScorer(
            {
                (10, "green plant"): 0.8,
                (10, "glass on table"): 0.2,
                (10, "living room"): 0.7,
                (10, "dining room"): 0.5,
                (10, "kitchen pantry"): 0.1,
                (30, "green plant"): 0.3,
                (30, "glass on table"): 0.7,
                (30, "kitchen"): 0.9,
            }
        )
        observations = [
            {
                "agent_id": "agent0",
                "current_viewpoint_index": 1,
                "visible_viewpoints": [
                    {"viewpoint_index": 2, "distance": 1.0},
                    {"viewpoint_index": 3, "distance": 2.0},
                ],
                "raw_panorama": 10 * np.ones((2, 2, 3), dtype=np.uint8),
            }
        ]
        mllm_output = {
            "agents": [
                {
                    "agent_id": "agent0",
                    "current_region_node": {
                        "id": 10,
                        "label": "living room",
                        "exist_prob": 1.0,
                        "target_probs": {"plant": 0.4, "glass": 0.6},
                    },
                    "viewpoint_target_probs": [
                        {"id": 2, "target_probs": {"plant": 0.7, "glass": 0.3}},
                        {"id": 3, "target_probs": {"plant": 0.3, "glass": 0.7}},
                    ],
                    "viewpoint_node_assigns": [
                        {"id": 2, "assign_region_node_id": 11},
                        {"id": 3, "assign_region_node_id": 11},
                    ],
                    "detections": [
                        {"target_id": "plant", "found": False, "confidence": 0.0, "strip_index": -1},
                        {"target_id": "glass", "found": False, "confidence": 0.0, "strip_index": -1},
                    ],
                }
            ],
            "new_visible_region_nodes": [
                {
                    "id": 11,
                    "label": "dining room",
                    "exist_prob": 0.8,
                    "target_probs": {"plant": 0.6, "glass": 0.4},
                }
            ],
            "new_invisible_region_nodes": [
                {
                    "id": 20,
                    "label": "kitchen pantry",
                    "exist_prob": 0.4,
                    "target_probs": {"plant": 0.2, "glass": 0.8},
                }
            ],
            "new_arcs": [
                {"i": 2, "j": 3, "exist_prob": 0.5, "dist": 5.0},
                {"i": 2, "j": 20, "exist_prob": 0.6, "dist": 3.0},
            ],
            "region_merges": [],
        }
        graph.update_from_mllm(mllm_output, observations, scorer)
        return graph, scorer

    def test_target_probabilities_normalize_separately_and_bayesian_updates_apply(self):
        graph, _ = self._build_graph_and_step_one()

        viewpoint_plant_sum = sum(
            node.target_probs["plant"]
            for node in graph.nodes.values()
            if node.type == helper_stub.TYPE_VP
        )
        region_plant_sum = sum(
            node.target_probs["plant"]
            for node in graph.nodes.values()
            if node.type == helper_stub.TYPE_REGION
        )
        viewpoint_glass_sum = sum(
            node.target_probs["glass"]
            for node in graph.nodes.values()
            if node.type == helper_stub.TYPE_VP
        )
        region_glass_sum = sum(
            node.target_probs["glass"]
            for node in graph.nodes.values()
            if node.type == helper_stub.TYPE_REGION
        )

        self.assertAlmostEqual(viewpoint_plant_sum, 1.0)
        self.assertAlmostEqual(region_plant_sum, 1.0)
        self.assertAlmostEqual(viewpoint_glass_sum, 1.0)
        self.assertAlmostEqual(region_glass_sum, 1.0)

    def test_zone_existence_distance_fusion_and_node_gated_edge_existence(self):
        graph, _ = self._build_graph_and_step_one()

        self.assertAlmostEqual(graph.nodes[20].exist_prob, 0.4)

        empirical_mean = (1.0 + 2.0) / 2.0
        empirical_var = (((1.0 - empirical_mean) ** 2) + ((2.0 - empirical_mean) ** 2)) / 2.0
        empirical_var += graph.bayes_config["epsilon"]
        cue_var = empirical_var / (1.0 + graph.bayes_config["kappa_vv"] * 1.0)
        posterior_var = 1.0 / ((1.0 / graph.bayes_config["sigma_vv2"]) + (1.0 / cue_var))
        expected_distance_mean = posterior_var * (
            (5.0 / graph.bayes_config["sigma_vv2"]) + (empirical_mean / cue_var)
        )
        self.assertAlmostEqual(graph.edges[(2, 3)].distance_mean, expected_distance_mean)

        self.assertAlmostEqual(graph.edges[(2, 20)].cond_exist_prob, 0.6)
        self.assertAlmostEqual(graph.edges[(2, 20)].exist_prob, 0.24)

    def test_assignment_persistence_and_newly_grounded_override(self):
        graph, scorer = self._build_graph_and_step_one()
        observations = [
            {
                "agent_id": "agent0",
                "current_viewpoint_index": 2,
                "visible_viewpoints": [
                    {"viewpoint_index": 1, "distance": 1.0},
                    {"viewpoint_index": 3, "distance": 1.0},
                ],
                "raw_panorama": 30 * np.ones((2, 2, 3), dtype=np.uint8),
            }
        ]
        mllm_output = {
            "agents": [
                {
                    "agent_id": "agent0",
                    "current_region_node": {
                        "id": 12,
                        "label": "kitchen",
                        "exist_prob": 1.0,
                        "target_probs": {"plant": 0.2, "glass": 0.8},
                    },
                    "viewpoint_target_probs": [
                        {"id": 1, "target_probs": {"plant": 0.1, "glass": 0.9}},
                        {"id": 3, "target_probs": {"plant": 0.5, "glass": 0.5}},
                    ],
                    "viewpoint_node_assigns": [
                        {"id": 1, "assign_region_node_id": 12},
                        {"id": 3, "assign_region_node_id": 12},
                    ],
                    "detections": [
                        {"target_id": "plant", "found": False, "confidence": 0.0, "strip_index": -1},
                        {"target_id": "glass", "found": False, "confidence": 0.0, "strip_index": -1},
                    ],
                }
            ],
            "new_visible_region_nodes": [],
            "new_invisible_region_nodes": [],
            "new_arcs": [],
            "region_merges": [],
        }

        graph.update_from_mllm(mllm_output, observations, scorer)

        self.assertEqual(graph.viewpoint_to_region[2], 12)
        self.assertEqual(graph.viewpoint_to_region[3], 11)
        self.assertEqual(graph.viewpoint_to_region[1], 10)


if __name__ == "__main__":
    unittest.main()
