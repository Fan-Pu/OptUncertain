import importlib.util
import pathlib
import sys
import types
import unittest


helper_stub = types.ModuleType("Helper")
helper_stub.TYPE_VP = 1
helper_stub.panorama_center_x_to_heading = lambda target_center_x, horizon_headings: target_center_x
_original_helper = sys.modules.get("Helper")
sys.modules["Helper"] = helper_stub

module_path = pathlib.Path(__file__).resolve().parent / "main.py"
spec = importlib.util.spec_from_file_location("main_under_test_targets", module_path)
main_under_test = importlib.util.module_from_spec(spec)
spec.loader.exec_module(main_under_test)


def tearDownModule():
    if _original_helper is None:
        sys.modules.pop("Helper", None)
    else:
        sys.modules["Helper"] = _original_helper


class _FakeMLLMClient:
    def __init__(self, distance_by_target=None, distance_by_rgb=None):
        self.distance_by_target = dict(distance_by_target or {})
        self.distance_by_rgb = dict(distance_by_rgb or {})
        self.calls = []

    def estimate_target_distance(self, rgb_image, depth_image, target_object):
        self.calls.append((rgb_image, depth_image, target_object))
        if rgb_image in self.distance_by_rgb:
            return {"distance_m": self.distance_by_rgb[rgb_image]}
        return {"distance_m": self.distance_by_target[target_object]}


class _FakeGraph:
    def __init__(self):
        self.target_found = {
            "0": False,
            "1": False,
        }

    def mark_target_found(self, target_id):
        self.target_found[target_id] = True


class MultiTargetDetectionTest(unittest.TestCase):
    def _observations(self):
        return [
            {
                "agent_id": "agent0",
                "horizon_headings": [0.1, 0.2],
                "horizon_rgb_frames": ["rgb-a0-0", "rgb-a0-1"],
                "horizon_depths": ["depth-a0-0", "depth-a0-1"],
                "raw_panorama": "rgb-a0-panorama",
                "depth_panorama": "depth-a0-panorama",
            },
            {
                "agent_id": "agent1",
                "horizon_headings": [0.3, 0.4],
                "horizon_rgb_frames": ["rgb-a1-0", "rgb-a1-1"],
                "horizon_depths": ["depth-a1-0", "depth-a1-1"],
                "raw_panorama": "rgb-a1-panorama",
                "depth_panorama": "depth-a1-panorama",
            },
        ]

    def _mllm_output(self):
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
            ],
            "agents": [
                {"agent_id": "agent0"},
                {"agent_id": "agent1"},
            ]
        }

    def test_found_detections_are_grouped_per_target_description(self):
        found_detections = main_under_test._found_detections_by_target(
            mllm_output=self._mllm_output(),
            agent_observations=self._observations(),
            unfound_target_ids={"0", "1"},
        )

        self.assertEqual(
            found_detections["0"][0]["agent_id"], "agent0"
        )
        self.assertEqual(
            found_detections["0"][0]["target_rgb_image"],
            "rgb-a0-panorama",
        )
        self.assertEqual(
            found_detections["1"][0]["agent_id"], "agent1"
        )
        self.assertEqual(
            found_detections["1"][0]["target_depth_image"],
            "depth-a1-panorama",
        )

    def test_multiple_targets_can_complete_in_same_step(self):
        hypothesis_graph = _FakeGraph()
        completed_target_ids = main_under_test._mark_completed_targets(
            mllm_client=_FakeMLLMClient(
                {"green plant on the table": 0.8, "glass on the dining table": 0.9}
            ),
            mllm_output=self._mllm_output(),
            agent_observations=self._observations(),
            targets=[
                {
                    "target_id": "0",
                    "description": "green plant on the table",
                    "distance_threshold_m": 1.0,
                },
                {
                    "target_id": "1",
                    "description": "glass on the dining table",
                    "distance_threshold_m": 1.0,
                },
            ],
            hypothesis_graph=hypothesis_graph,
        )

        self.assertEqual(
            [item["target_id"] for item in completed_target_ids],
            ["0", "1"],
        )
        self.assertTrue(hypothesis_graph.target_found["0"])
        self.assertTrue(hypothesis_graph.target_found["1"])

    def test_multiple_agent_detections_for_same_target_are_distance_checked(self):
        hypothesis_graph = _FakeGraph()
        mllm_output = {
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
                    "founds": [True, False],
                    "target_center_xs": [0.75, None],
                },
            ],
            "agents": [{"agent_id": "agent0"}, {"agent_id": "agent1"}],
        }
        mllm_client = _FakeMLLMClient(
            distance_by_rgb={"rgb-a0-panorama": 2.0, "rgb-a1-panorama": 0.5}
        )

        completed_target_ids = main_under_test._mark_completed_targets(
            mllm_client=mllm_client,
            mllm_output=mllm_output,
            agent_observations=self._observations(),
            targets=[
                {
                    "target_id": "0",
                    "description": "green plant on the table",
                    "distance_threshold_m": 1.0,
                },
                {
                    "target_id": "1",
                    "description": "glass on the dining table",
                    "distance_threshold_m": 1.0,
                },
            ],
            hypothesis_graph=hypothesis_graph,
        )

        self.assertEqual(
            [item["target_id"] for item in completed_target_ids],
            ["0"],
        )
        self.assertEqual(
            [call[0] for call in mllm_client.calls],
            ["rgb-a0-panorama", "rgb-a1-panorama"],
        )


if __name__ == "__main__":
    unittest.main()
