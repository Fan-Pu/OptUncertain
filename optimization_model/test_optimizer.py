import unittest
import sys
import types

cv2_stub = types.ModuleType("cv2")
cv2_stub.FONT_HERSHEY_SIMPLEX = 0
cv2_stub.namedWindow = lambda *args, **kwargs: None
cv2_stub.imshow = lambda *args, **kwargs: None
cv2_stub.waitKey = lambda *args, **kwargs: -1
cv2_stub.putText = lambda *args, **kwargs: None
cv2_stub.rectangle = lambda *args, **kwargs: None
cv2_stub.getTextSize = lambda *args, **kwargs: ((0, 0), 0)
sys.modules.setdefault("cv2", cv2_stub)

matter_sim_stub = types.ModuleType("MatterSim")
matter_sim_stub.Simulator = object
sys.modules.setdefault("MatterSim", matter_sim_stub)

from optimization_model import RollingHorizonOptimizer
from semantic_persistence.hypothesis_graph import HypothesisGraph


class RollingHorizonOptimizerTest(unittest.TestCase):
    def _build_graph(self):
        graph = HypothesisGraph()
        graph.add_or_update_a_node(1, "vp-1", 1, 1.0, 0.0, True)
        graph.add_or_update_a_node(2, "vp-2", 1, 1.0, 0.0, True)
        graph.add_or_update_a_node(3, "vp-3", 1, 1.0, 0.0, True)
        graph.add_or_update_a_node(4, "vp-4", 1, 1.0, 0.0, True)

        graph.add_or_update_a_node(10, "region-10", 0, 1.0, 0.8, True)
        graph.add_or_update_a_node(11, "region-11", 0, 1.0, 0.3, True)
        graph.add_or_update_a_node(12, "region-12", 0, 0.7, 0.8, True)
        graph.add_or_update_a_node(13, "region-13", 0, 1.0, 0.6, True)

        graph.viewpoint_to_region[1] = 12
        graph.viewpoint_to_region[2] = 10
        graph.viewpoint_to_region[3] = 11
        graph.viewpoint_to_region[4] = 13
        graph.region_to_viewpoints[10] = {2}
        graph.region_to_viewpoints[11] = {3}
        graph.region_to_viewpoints[12] = {1}
        graph.region_to_viewpoints[13] = {4}

        graph.add_or_update_an_edge(graph.nodes[1], graph.nodes[2], 1.0, 1.0)
        graph.add_or_update_an_edge(graph.nodes[1], graph.nodes[3], 1.0, 1.0)
        graph.add_or_update_an_edge(graph.nodes[1], graph.nodes[4], 1.0, 1.0)
        return graph

    def test_selects_higher_reward_first_hop(self):
        graph = self._build_graph()
        optimizer = RollingHorizonOptimizer()

        result = optimizer.solve(graph, 1)

        self.assertEqual(result["next_vp_node_id"], 2)

    def test_prefers_safer_edge_when_rewards_match(self):
        graph = self._build_graph()
        graph.nodes[10].target_prob = 0.6
        graph.nodes[11].target_prob = 0.6
        graph.nodes[13].target_prob = 0.1
        graph.edges[(1, 2)].exist_prob = 1.0
        graph.edges[(1, 3)].exist_prob = 0.1
        optimizer = RollingHorizonOptimizer()

        result = optimizer.solve(graph, 1)

        self.assertEqual(result["next_vp_node_id"], 2)

    def test_visibility_zeroes_reward_for_seen_node(self):
        graph = self._build_graph()
        optimizer = RollingHorizonOptimizer()

        optimizer.solve(graph, 2)
        result = optimizer.solve(graph, 1)

        self.assertEqual(result["next_vp_node_id"], 4)


if __name__ == "__main__":
    unittest.main()
