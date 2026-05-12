import importlib.util
import json
import os
import pathlib
import sys
import tempfile
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
mllm_client_under_test.debugpy.breakpoint = lambda: None


def tearDownModule():
    if _original_openai is None:
        sys.modules.pop("openai", None)
    else:
        sys.modules["openai"] = _original_openai


class _FakeGraph:
    def __init__(self, target_found=None):
        self.target_found = dict(
            target_found
            or {
                "0": False,
                "1": False,
            }
        )

    def get_mllm_summary(self):
        return {
            "observation_step": 3,
            "targets": _targets(),
            "target_found": dict(self.target_found),
            "agent_current_vp_ids": {"agent0": 7, "agent1": 9},
            "nodes": [],
            "edges": [],
            "viewpoint_to_region": {},
        }


def _targets():
    return [
        {"target_id": "0", "description": "green plant on the table"},
        {"target_id": "1", "description": "glass on the dining table"},
    ]


def _agent_observations():
    return [
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
    ]


def _valid_payload():
    return {
        "agents": [
            {"agent_id": "agent0", "current_region_node_id": 100},
            {"agent_id": "agent1", "current_region_node_id": 101},
        ],
        "visible_region_nodes": [
            {
                "id": 100,
                "label": "living room near sofa",
                "exist_prob": 1.0,
                "target_probs": {"0": 0.6, "1": 0.4},
            },
            {
                "id": 101,
                "label": "kitchen beside dining table",
                "exist_prob": 1.0,
                "target_probs": {"0": 0.3, "1": 0.7},
            },
        ],
        "invisible_region_nodes": [],
        "viewpoint_target_probs": [
            {"id": 7, "target_probs": {"0": 0.0, "1": 0.0}},
            {"id": 8, "target_probs": {"0": 0.6, "1": 0.4}},
            {"id": 9, "target_probs": {"0": 0.0, "1": 0.0}},
            {"id": 10, "target_probs": {"0": 0.3, "1": 0.7}},
        ],
        "viewpoint_node_assigns": [
            {"region_node_id": 100, "assigned_viewpoint_node_indices": [7, 8]},
            {"region_node_id": 101, "assigned_viewpoint_node_indices": [9, 10]},
        ],
        "new_edges": [],
        "edge_distance_variances": {
            "viewpoint_region": 3.5,
            "viewpoint_viewpoint": 1.5,
        },
        "detections": [
            {"agent_id": "agent0", "target_indices": ["0", "1"], "founds": [False, False]},
            {"agent_id": "agent1", "target_indices": ["0", "1"], "founds": [False, False]},
        ],
    }


def _valid_payload_text():
    return json.dumps(_valid_payload(), indent=2, sort_keys=True)


def _valid_detection_payload():
    return {
        "detections": [
            {
                "agent_id": "agent0",
                "target_indices": ["0", "1"],
                "founds": [False, False],
                "target_center_xs": [None, None],
            },
            {
                "agent_id": "agent1",
                "target_indices": ["0", "1"],
                "founds": [False, False],
                "target_center_xs": [None, None],
            },
        ]
    }


def _valid_detection_payload_text():
    return json.dumps(_valid_detection_payload(), indent=2, sort_keys=True)


def _found_one_detection_payload():
    return {
        "detections": [
            {
                "agent_id": "agent0",
                "target_indices": ["0", "1"],
                "founds": [True, False],
                "target_center_xs": [0.25, None],
            },
            {
                "agent_id": "agent1",
                "target_indices": ["0", "1"],
                "founds": [False, False],
                "target_center_xs": [None, None],
            },
        ]
    }


def _target_one_detection_payload():
    return {
        "detections": [
            {
                "agent_id": "agent0",
                "target_indices": ["1"],
                "founds": [False],
                "target_center_xs": [None],
            },
            {
                "agent_id": "agent1",
                "target_indices": ["1"],
                "founds": [False],
                "target_center_xs": [None],
            },
        ]
    }


def _target_one_payload():
    payload = _valid_payload()

    for region in payload["visible_region_nodes"]:
        region["target_probs"] = {"1": region["target_probs"]["1"]}

    payload["viewpoint_target_probs"] = []
    for item in _valid_payload()["viewpoint_target_probs"]:
        value = 0.0 if item["id"] in {7, 9} else item["target_probs"]["1"]
        payload["viewpoint_target_probs"].append(
            {"id": item["id"], "target_probs": {"1": value}}
        )

    payload["detections"] = [
        {"agent_id": "agent0", "target_indices": ["1"], "founds": [False]},
        {"agent_id": "agent1", "target_indices": ["1"], "founds": [False]},
    ]

    return payload


def _target_one_payload_text():
    return json.dumps(_target_one_payload(), indent=2, sort_keys=True)


def _found_all_detection_payload():
    return {
        "detections": [
            {
                "agent_id": "agent0",
                "target_indices": ["0", "1"],
                "founds": [True, False],
                "target_center_xs": [0.25, None],
            },
            {
                "agent_id": "agent1",
                "target_indices": ["0", "1"],
                "founds": [False, True],
                "target_center_xs": [None, 0.75],
            },
        ]
    }


class JointMLLMClientTest(unittest.TestCase):
    def test_replay_mode_constructor_does_not_require_api_key(self):
        old_token = os.environ.pop("HF_TOKEN", None)
        try:
            client = MLLMClient(read_saved_raw_outputs=True)
        finally:
            if old_token is not None:
                os.environ["HF_TOKEN"] = old_token

        self.assertIsNone(client.client)
        self.assertTrue(client.read_saved_raw_outputs)

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
            targets=_targets(),
            graph_summary=_FakeGraph().get_mllm_summary(),
            fixed_detections=MLLMClient._strip_detection_localization(
                _valid_detection_payload()["detections"]
            ),
        )

        self.assertIn("one annotated RGB panorama per agent", system_message)
        self.assertIn("Region labels must be room or area labels", system_message)
        self.assertIn("Use at most 5 current-step region nodes", system_message)
        self.assertIn("Current step request:", user_message)
        self.assertIn("Current-step interpretation note:", user_message)
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

        captured_messages = []
        responses = iter([_valid_detection_payload_text(), _valid_payload_text()])

        def _fake_request_completion(messages, model_name):
            captured_messages.append(messages)
            return next(responses)

        client._request_completion = _fake_request_completion

        with tempfile.TemporaryDirectory() as tmp_dir:
            client.raw_output_dir = tmp_dir
            payload = client.propose_semantic_nodes(
                agent_observations=_agent_observations(),
                targets=_targets(),
                graph=_FakeGraph(),
            )

        user_content = captured_messages[1][1]["content"]
        image_items = [item for item in user_content if item["type"] == "image_url"]
        self.assertEqual(len(image_items), 2)
        self.assertEqual(payload["detections"][0]["target_indices"], ["0", "1"])
        self.assertFalse(payload["detections"][1]["founds"][1])
        self.assertEqual(client.last_direct_detections[0]["target_center_xs"][0], None)

    def test_validate_detection_payload_requires_target_center_xs(self):
        client = MLLMClient.__new__(MLLMClient)
        detections = client._validate_detection_payload(
            payload=_valid_detection_payload(),
            agent_observations=_agent_observations(),
            targets=_targets(),
        )

        self.assertEqual(detections[0]["target_center_xs"], [None, None])

    def test_propose_semantic_nodes_saves_generated_raw_outputs(self):
        client = MLLMClient.__new__(MLLMClient)
        client.save_debug_images = False
        client._image_to_data_url = lambda image: "data:image/png;base64,test"
        detection_decoded = _valid_detection_payload_text()
        graph_decoded = _valid_payload_text()
        responses = iter([detection_decoded, graph_decoded])
        client._request_completion = lambda messages, model_name: next(responses)

        with tempfile.TemporaryDirectory() as tmp_dir:
            client.raw_output_dir = tmp_dir
            payload = client.propose_semantic_nodes(
                agent_observations=_agent_observations(),
                targets=_targets(),
                graph=_FakeGraph(),
            )
            detection_saved_path = pathlib.Path(tmp_dir) / "detection_step_0000.json"
            saved_path = pathlib.Path(tmp_dir) / "semantic_step_0000.json"
            agent0_image_path = (
                pathlib.Path(tmp_dir) / "observation_step_0000_agent_agent0.jpg"
            )
            agent1_image_path = (
                pathlib.Path(tmp_dir) / "observation_step_0000_agent_agent1.jpg"
            )
            self.assertEqual(
                detection_saved_path.read_text(encoding="utf-8"),
                detection_decoded,
            )
            self.assertEqual(saved_path.read_text(encoding="utf-8"), graph_decoded)
            self.assertEqual(agent0_image_path.read_bytes()[:2], b"\xff\xd8")
            self.assertEqual(agent1_image_path.read_bytes()[:2], b"\xff\xd8")

        self.assertEqual(payload["agents"][0]["current_region_node_id"], 100)
        self.assertEqual(client.semantic_raw_output_index, 1)

    def test_propose_semantic_nodes_replays_saved_raw_output_without_request(self):
        client = MLLMClient.__new__(MLLMClient)
        client.save_debug_images = False
        client.read_saved_raw_outputs = True
        client._image_to_data_url = lambda image: "data:image/png;base64,test"

        def _unexpected_request(messages, model_name):
            raise AssertionError("_request_completion should not be called")

        client._request_completion = _unexpected_request

        with tempfile.TemporaryDirectory() as tmp_dir:
            client.raw_output_dir = tmp_dir
            detection_saved_path = pathlib.Path(tmp_dir) / "detection_step_0000.json"
            detection_saved_path.write_text(
                _valid_detection_payload_text(),
                encoding="utf-8",
            )
            saved_path = pathlib.Path(tmp_dir) / "semantic_step_0000.json"
            saved_path.write_text(_valid_payload_text(), encoding="utf-8")
            payload = client.propose_semantic_nodes(
                agent_observations=_agent_observations(),
                targets=_targets(),
                graph=_FakeGraph(),
            )

        self.assertEqual(payload["agents"][1]["current_region_node_id"], 101)
        self.assertEqual(client.last_direct_detections[1]["target_center_xs"][1], None)
        self.assertEqual(client.semantic_raw_output_index, 1)

    def test_previously_found_target_is_omitted_from_detection_prompt(self):
        client = MLLMClient.__new__(MLLMClient)
        client.save_debug_images = False
        client._image_to_data_url = lambda image: "data:image/png;base64,test"

        captured_messages = []
        responses = iter(
            [
                json.dumps(_target_one_detection_payload()),
                _target_one_payload_text(),
            ]
        )

        def _fake_request_completion(messages, model_name):
            captured_messages.append(messages)
            return next(responses)

        client._request_completion = _fake_request_completion

        with tempfile.TemporaryDirectory() as tmp_dir:
            client.raw_output_dir = tmp_dir
            client.propose_semantic_nodes(
                agent_observations=_agent_observations(),
                targets=_targets(),
                graph=_FakeGraph(target_found={"0": True, "1": False}),
            )

        detection_text = MLLMClient._message_to_text(
            captured_messages[0][1]["content"]
        )
        self.assertNotIn('"target_id": "0"', detection_text)
        self.assertNotIn("green plant on the table", detection_text)
        self.assertIn('"target_id": "1"', detection_text)

    def test_current_step_found_target_is_omitted_from_graph_prompt(self):
        client = MLLMClient.__new__(MLLMClient)
        client.save_debug_images = False
        client._image_to_data_url = lambda image: "data:image/png;base64,test"

        captured_messages = []
        responses = iter(
            [
                json.dumps(_found_one_detection_payload()),
                _target_one_payload_text(),
            ]
        )

        def _fake_request_completion(messages, model_name):
            captured_messages.append(messages)
            return next(responses)

        client._request_completion = _fake_request_completion

        with tempfile.TemporaryDirectory() as tmp_dir:
            client.raw_output_dir = tmp_dir
            payload = client.propose_semantic_nodes(
                agent_observations=_agent_observations(),
                targets=_targets(),
                graph=_FakeGraph(),
            )

        graph_text = MLLMClient._message_to_text(captured_messages[1][1]["content"])
        self.assertNotIn('"target_id": "0"', graph_text)
        self.assertNotIn('"0":', graph_text)
        self.assertNotIn("green plant on the table", graph_text)
        self.assertEqual(payload["detections"][0]["target_indices"], ["1"])
        self.assertEqual(payload["viewpoint_target_probs"][0]["target_probs"], {"1": 0.0})
        self.assertEqual(client.last_direct_detections[0]["target_center_xs"][0], 0.25)

    def test_graph_generation_is_skipped_when_detection_finds_all_active_targets(self):
        client = MLLMClient.__new__(MLLMClient)
        client.save_debug_images = False
        client._image_to_data_url = lambda image: "data:image/png;base64,test"

        captured_messages = []

        def _fake_request_completion(messages, model_name):
            captured_messages.append(messages)
            return json.dumps(_found_all_detection_payload())

        client._request_completion = _fake_request_completion

        with tempfile.TemporaryDirectory() as tmp_dir:
            client.raw_output_dir = tmp_dir
            payload = client.propose_semantic_nodes(
                agent_observations=_agent_observations(),
                targets=_targets(),
                graph=_FakeGraph(),
            )

        self.assertIsNone(payload)
        self.assertEqual(len(captured_messages), 1)
        self.assertEqual(client.semantic_raw_output_index, 1)
        self.assertEqual(client.last_direct_detections[1]["target_center_xs"][1], 0.75)

    def test_validate_payload_accepts_only_active_target_prob_keys(self):
        client = MLLMClient.__new__(MLLMClient)

        client._validate_payload(
            payload=_target_one_payload(),
            agent_observations=_agent_observations(),
            targets=[_targets()[1]],
            graph_summary=_FakeGraph().get_mllm_summary(),
            fixed_detections=MLLMClient._strip_detection_localization(
                _target_one_detection_payload()["detections"]
            ),
        )

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
