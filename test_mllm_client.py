import importlib.util
import pathlib
import sys
import types
import unittest

import numpy as np


openai_stub = types.ModuleType("openai")
openai_stub.BadRequestError = Exception
openai_stub.OpenAI = object

_original_openai = sys.modules.get("openai")
sys.modules["openai"] = openai_stub

module_path = (
    pathlib.Path(__file__).resolve().parent
    / "semantic_persistence"
    / "mllm_client.py"
)
spec = importlib.util.spec_from_file_location("mllm_client_under_test_joint", module_path)
mllm_client_under_test = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mllm_client_under_test)
MLLMClient = mllm_client_under_test.MLLMClient


def tearDownModule():
    if _original_openai is None:
        sys.modules.pop("openai", None)
    else:
        sys.modules["openai"] = _original_openai


class _FakeGraph:
    def get_mllm_summary(self):
        return {
            "observation_step": 3,
            "targets": {"plant": "green plant", "glass": "glass on table"},
            "target_found": {"plant": False, "glass": False},
            "agent_current_vp_ids": {"agent0": 7, "agent1": 9},
            "nodes": [],
            "edges": [],
            "viewpoint_to_region": {},
        }


class JointMLLMClientTest(unittest.TestCase):
    def test_build_instruction_maps_image_indices_to_agent_ids(self):
        client = MLLMClient.__new__(MLLMClient)

        system_message, user_message = client._build_instruction(
            agent_observations=[
                {
                    "agent_id": "agent0",
                    "current_viewpoint_index": 7,
                    "visible_viewpoints": [{"viewpoint_index": 8, "distance": 1.2}],
                    "horizon_depths": [0] * 48,
                },
                {
                    "agent_id": "agent1",
                    "current_viewpoint_index": 9,
                    "visible_viewpoints": [{"viewpoint_index": 10, "distance": 2.0}],
                    "horizon_depths": [0] * 48,
                },
            ],
            targets=[
                {"id": "plant", "description": "green plant on the table"},
                {"id": "glass", "description": "glass on the dining table"},
            ],
            graph_summary=_FakeGraph().get_mllm_summary(),
        )

        self.assertIn("Image i always corresponds to the agent", system_message)
        self.assertIn('"agent_id": "agent0"', user_message)
        self.assertIn('"image_index": 0', user_message)
        self.assertIn('"agent_id": "agent1"', user_message)
        self.assertIn('"image_index": 1', user_message)

    def test_propose_semantic_nodes_sends_exactly_one_panorama_per_agent(self):
        client = MLLMClient.__new__(MLLMClient)
        client.save_debug_images = False
        client._image_to_data_url = lambda image: "data:image/png;base64,test"

        captured_messages = {}

        def _fake_request_completion(messages):
            captured_messages["messages"] = messages
            return """
            {
              "agents": [
                {
                  "agent_id": "agent0",
                  "current_region_node": {
                    "id": 100,
                    "label": "living room",
                    "exist_prob": 1.0,
                    "target_probs": {"plant": 0.6, "glass": 0.4}
                  },
                  "viewpoint_target_probs": [
                    {"id": 8, "target_probs": {"plant": 0.6, "glass": 0.4}}
                  ],
                  "viewpoint_node_assigns": [
                    {"id": 8, "assign_region_node_id": 100}
                  ],
                  "detections": [
                    {"target_id": "plant", "found": true, "confidence": 0.9, "strip_index": 7},
                    {"target_id": "glass", "found": false, "confidence": 0.0, "strip_index": -1}
                  ]
                },
                {
                  "agent_id": "agent1",
                  "current_region_node": {
                    "id": 101,
                    "label": "kitchen",
                    "exist_prob": 1.0,
                    "target_probs": {"plant": 0.3, "glass": 0.7}
                  },
                  "viewpoint_target_probs": [
                    {"id": 10, "target_probs": {"plant": 0.3, "glass": 0.7}}
                  ],
                  "viewpoint_node_assigns": [
                    {"id": 10, "assign_region_node_id": 101}
                  ],
                  "detections": [
                    {"target_id": "plant", "found": false, "confidence": 0.0, "strip_index": -1},
                    {"target_id": "glass", "found": true, "confidence": 0.8, "strip_index": 5}
                  ]
                }
              ],
              "new_visible_region_nodes": [],
              "new_invisible_region_nodes": [],
              "new_arcs": [],
              "region_merges": []
            }
            """

        client._request_completion = _fake_request_completion

        payload = client.propose_semantic_nodes(
            agent_observations=[
                {
                    "agent_id": "agent0",
                    "current_viewpoint_index": 7,
                    "visible_viewpoints": [{"viewpoint_index": 8, "distance": 1.2}],
                    "horizon_depths": [0] * 48,
                    "annotated_panorama": 11 * np.ones((2, 3, 3), dtype=np.uint8),
                },
                {
                    "agent_id": "agent1",
                    "current_viewpoint_index": 9,
                    "visible_viewpoints": [{"viewpoint_index": 10, "distance": 2.0}],
                    "horizon_depths": [0] * 48,
                    "annotated_panorama": 22 * np.ones((2, 3, 3), dtype=np.uint8),
                },
            ],
            targets=[
                {"id": "plant", "description": "green plant on the table"},
                {"id": "glass", "description": "glass on the dining table"},
            ],
            graph=_FakeGraph(),
        )

        user_content = captured_messages["messages"][1]["content"]
        image_items = [item for item in user_content if item["type"] == "image_url"]
        self.assertEqual(len(image_items), 2)
        self.assertEqual(payload["agents"][0]["detections"][0]["strip_index"], 7)
        self.assertEqual(payload["agents"][1]["detections"][1]["target_id"], "glass")


if __name__ == "__main__":
    unittest.main()
