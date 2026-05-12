import importlib.util
import json
import pathlib
import sys
import tempfile
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


def _targets():
    return [
        {"target_id": "green plant", "description": "green plant"},
        {"target_id": "glass on table", "description": "glass on table"},
    ]


def _observations(marker=10, current=1):
    return [
        {
            "agent_id": "agent0",
            "current_viewpoint_index": current,
            "visible_viewpoints": [
                {"viewpoint_index": 2 if current != 2 else 1, "distance": 1.0},
                {"viewpoint_index": 3, "distance": 2.0 if current == 1 else 1.0},
            ],
            "raw_panorama": marker * np.ones((2, 2, 3), dtype=np.uint8),
        }
    ]


def _step_one_payload():
    return {
        "agents": [{"agent_id": "agent0", "current_region_node_id": 10}],
        "visible_region_nodes": [
            {
                "id": 10,
                "label": "living room",
                "exist_prob": 1.0,
                "target_probs": {"green plant": 0.4, "glass on table": 0.6},
            },
            {
                "id": 11,
                "label": "dining room",
                "exist_prob": 0.8,
                "target_probs": {"green plant": 0.6, "glass on table": 0.4},
            },
        ],
        "invisible_region_nodes": [
            {
                "id": 20,
                "label": "kitchen pantry",
                "exist_prob": 0.4,
                "target_probs": {"green plant": 0.2, "glass on table": 0.8},
            }
        ],
        "viewpoint_target_probs": [
            {"id": 1, "target_probs": {"green plant": 0.0, "glass on table": 0.0}},
            {"id": 2, "target_probs": {"green plant": 0.7, "glass on table": 0.3}},
            {"id": 3, "target_probs": {"green plant": 0.3, "glass on table": 0.7}},
        ],
        "viewpoint_node_assigns": [
            {"region_node_id": 10, "assigned_viewpoint_node_indices": [1]},
            {"region_node_id": 11, "assigned_viewpoint_node_indices": [2, 3]},
        ],
        "new_edges": [
            {"i": 2, "j": 3, "edge_type": "VV", "exist_prob": 0.5, "dist": 5.0},
            {"i": 2, "j": 20, "edge_type": "VZ", "exist_prob": 0.6, "dist": 3.0},
        ],
        "edge_distance_variances": {
            "viewpoint_viewpoint": 4.0,
            "viewpoint_region": 9.0,
        },
        "detections": [
            {
                "agent_id": "agent0",
                "target_indices": ["green plant", "glass on table"],
                "founds": [False, False],
            }
        ],
    }


def _step_two_payload_only_glass():
    return {
        "agents": [{"agent_id": "agent0", "current_region_node_id": 12}],
        "visible_region_nodes": [
            {
                "id": 12,
                "label": "kitchen",
                "exist_prob": 1.0,
                "target_probs": {"glass on table": 0.8},
            }
        ],
        "invisible_region_nodes": [],
        "viewpoint_target_probs": [
            {"id": 2, "target_probs": {"glass on table": 0.0}},
            {"id": 1, "target_probs": {"glass on table": 0.9}},
            {"id": 3, "target_probs": {"glass on table": 0.5}},
        ],
        "viewpoint_node_assigns": [
            {"region_node_id": 12, "assigned_viewpoint_node_indices": [1, 2, 3]}
        ],
        "new_edges": [],
        "edge_distance_variances": {
            "viewpoint_viewpoint": 4.0,
            "viewpoint_region": 9.0,
        },
        "detections": [
            {
                "agent_id": "agent0",
                "target_indices": ["glass on table"],
                "founds": [False],
            }
        ],
    }


class HypothesisGraphUpdateTest(unittest.TestCase):
    def _build_graph_and_step_one(self):
        graph = HypothesisGraph(targets=_targets())
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
        graph.update_from_mllm(_step_one_payload(), _observations(), scorer)
        return graph, scorer

    def test_target_probabilities_normalize_separately_and_bayesian_updates_apply(self):
        graph, _ = self._build_graph_and_step_one()

        for target_id in ["green plant", "glass on table"]:
            viewpoint_sum = sum(
                node.target_probs[target_id]
                for node in graph.nodes.values()
                if node.type == helper_stub.TYPE_VP
            )
            region_sum = sum(
                node.target_probs[target_id]
                for node in graph.nodes.values()
                if node.type == helper_stub.TYPE_REGION
            )

            self.assertAlmostEqual(viewpoint_sum, 1.0)
            self.assertAlmostEqual(region_sum, 1.0)

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

        graph.update_from_mllm(
            _step_two_payload_only_glass(),
            _observations(marker=30, current=2),
            scorer,
        )

        self.assertEqual(graph.viewpoint_to_region[2], 12)
        self.assertEqual(graph.viewpoint_to_region[3], 11)
        self.assertEqual(graph.viewpoint_to_region[1], 10)

    def test_found_target_can_be_omitted_from_next_mllm_payload(self):
        graph, scorer = self._build_graph_and_step_one()
        graph.mark_target_found("green plant")

        graph.update_from_mllm(
            _step_two_payload_only_glass(),
            _observations(marker=30, current=2),
            scorer,
        )

        self.assertTrue(graph.target_found["green plant"])
        glass_region_sum = sum(
            node.target_probs["glass on table"]
            for node in graph.nodes.values()
            if node.type == helper_stub.TYPE_REGION
        )
        self.assertAlmostEqual(glass_region_sum, 1.0)

    def test_debug_snapshots_are_json_serializable_and_written(self):
        graph, _ = self._build_graph_and_step_one()

        json.dumps(graph.get_graph_layout_snapshot(), sort_keys=True)
        json.dumps(graph.get_hypothesis_snapshot(), sort_keys=True)

        with tempfile.TemporaryDirectory() as tmp_dir:
            graph.export_debug_snapshot(output_dir=tmp_dir, step_index=0)

            layout_path = pathlib.Path(tmp_dir) / "graph_layout_step_0000.json"
            hypothesis_path = pathlib.Path(tmp_dir) / "hypothesis_step_0000.json"

            self.assertTrue(layout_path.exists())
            self.assertTrue(hypothesis_path.exists())

            layout = json.loads(layout_path.read_text(encoding="utf-8"))
            hypothesis = json.loads(hypothesis_path.read_text(encoding="utf-8"))

        self.assertEqual(layout["observation_step"], 1)
        self.assertEqual(layout["region_to_viewpoints"]["10"], [1])
        self.assertEqual(layout["region_to_viewpoints"]["11"], [2, 3])

        pantry = next(node for node in hypothesis["nodes"] if node["id"] == 20)
        self.assertEqual(pantry["label"], "kitchen pantry")
        self.assertAlmostEqual(pantry["exist_prob"], 0.4)

        vz_edge = next(
            edge
            for edge in hypothesis["edges"]
            if edge["i"] == 2 and edge["j"] == 20
        )
        self.assertAlmostEqual(vz_edge["cond_exist_prob"], 0.6)
        self.assertAlmostEqual(vz_edge["exist_prob"], 0.24)


if __name__ == "__main__":
    unittest.main()
