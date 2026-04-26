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
            "targets": ["green plant on the table", "glass on the dining table"],
            "target_found": {
                "green plant on the table": False,
                "glass on the dining table": False,
            },
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
                {"description": "green plant on the table"},
                {"description": "glass on the dining table"},
            ],
            graph_summary=_FakeGraph().get_mllm_summary(),
        )

        self.assertIn("Image i corresponds to the agent", system_message)
        self.assertIn("Region labels must be room or area labels only", system_message)
        self.assertIn("A maximum of 5 current-step semantic regions", system_message)
        self.assertIn("Generation priority:", user_message)
        self.assertIn("Grounding rules:", user_message)
        self.assertIn('"agent_id": "agent0"', user_message)
        self.assertIn('"image_index": 0', user_message)
        self.assertIn('"agent_id": "agent1"', user_message)
        self.assertIn('"image_index": 1', user_message)
        self.assertNotIn("region_merges", system_message)
        self.assertNotIn("region_merges", user_message)

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
                    "target_probs": {"green plant on the table": 0.6, "glass on the dining table": 0.4}
                  },
                  "viewpoint_target_probs": [
                    {"id": 8, "target_probs": {"green plant on the table": 0.6, "glass on the dining table": 0.4}}
                  ],
                  "viewpoint_node_assigns": [
                    {"id": 8, "assign_region_node_id": 100}
                  ]
                },
                {
                  "agent_id": "agent1",
                  "current_region_node": {
                    "id": 101,
                    "label": "kitchen",
                    "exist_prob": 1.0,
                    "target_probs": {"green plant on the table": 0.3, "glass on the dining table": 0.7}
                  },
                  "viewpoint_target_probs": [
                    {"id": 10, "target_probs": {"green plant on the table": 0.3, "glass on the dining table": 0.7}}
                  ],
                  "viewpoint_node_assigns": [
                    {"id": 10, "assign_region_node_id": 101}
                  ]
                }
              ],
              "detections": [
                {"agent_id": "agent0", "target": "green plant on the table", "found": true},
                {"agent_id": "agent0", "target": "glass on the dining table", "found": false},
                {"agent_id": "agent1", "target": "green plant on the table", "found": false},
                {"agent_id": "agent1", "target": "glass on the dining table", "found": true}
              ],
              "new_visible_region_nodes": [],
              "new_invisible_region_nodes": [],
              "new_arcs": []
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
                {"description": "green plant on the table"},
                {"description": "glass on the dining table"},
            ],
            graph=_FakeGraph(),
        )

        user_content = captured_messages["messages"][1]["content"]
        image_items = [item for item in user_content if item["type"] == "image_url"]
        self.assertEqual(len(image_items), 2)
        self.assertEqual(payload["detections"][0]["target"], "green plant on the table")
        self.assertTrue(payload["detections"][3]["found"])

    def test_validate_payload_rejects_stale_target_id_detection_shape(self):
        client = MLLMClient.__new__(MLLMClient)
        payload = {
            "agents": [
                {
                    "agent_id": "agent0",
                    "current_region_node": {
                        "id": 100,
                        "label": "living room",
                        "exist_prob": 1.0,
                        "target_probs": {"green plant on the table": 0.6},
                    },
                    "viewpoint_target_probs": [
                        {
                            "id": 8,
                            "target_probs": {"green plant on the table": 0.6},
                        }
                    ],
                    "viewpoint_node_assigns": [
                        {"id": 8, "assign_region_node_id": 100}
                    ],
                }
            ],
            "detections": [
                {
                    "agent_id": "agent0",
                    "target_id": "plant",
                    "found": True,
                    "confidence": 0.9,
                    "strip_index": 7,
                }
            ],
            "new_visible_region_nodes": [],
            "new_invisible_region_nodes": [],
            "new_arcs": [],
        }

        with self.assertRaises(KeyError):
            client._validate_payload(
                payload=payload,
                agent_observations=[
                    {
                        "agent_id": "agent0",
                        "visible_viewpoints": [
                            {"viewpoint_index": 8, "distance": 1.2}
                        ],
                    }
                ],
                targets=[{"description": "green plant on the table"}],
            )


if __name__ == "__main__":
    unittest.main()
