import importlib.util
import pathlib
import sys
import types
import unittest


helper_stub = types.ModuleType("Helper")
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
    def __init__(self, distance_by_target):
        self.distance_by_target = dict(distance_by_target)

    def estimate_target_distance(self, rgb_image, depth_image, target_object):
        return {"distance_m": self.distance_by_target[target_object]}


class _FakeGraph:
    def __init__(self):
        self.target_found = {"plant": False, "glass": False}

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
            },
            {
                "agent_id": "agent1",
                "horizon_headings": [0.3, 0.4],
                "horizon_rgb_frames": ["rgb-a1-0", "rgb-a1-1"],
                "horizon_depths": ["depth-a1-0", "depth-a1-1"],
            },
        ]

    def _mllm_output(self):
        return {
            "agents": [
                {
                    "agent_id": "agent0",
                    "detections": [
                        {"target_id": "plant", "found": True, "confidence": 0.95, "strip_index": 1},
                        {"target_id": "glass", "found": False, "confidence": 0.0, "strip_index": -1},
                    ],
                },
                {
                    "agent_id": "agent1",
                    "detections": [
                        {"target_id": "plant", "found": False, "confidence": 0.0, "strip_index": -1},
                        {"target_id": "glass", "found": True, "confidence": 0.92, "strip_index": 0},
                    ],
                },
            ]
        }

    def test_best_detections_are_selected_per_target(self):
        best_detections = main_under_test._best_detections_by_target(
            mllm_output=self._mllm_output(),
            agent_observations=self._observations(),
            unfound_target_ids={"plant", "glass"},
        )

        self.assertEqual(best_detections["plant"]["agent_id"], "agent0")
        self.assertEqual(best_detections["plant"]["target_rgb_image"], "rgb-a0-1")
        self.assertEqual(best_detections["glass"]["agent_id"], "agent1")
        self.assertEqual(best_detections["glass"]["target_depth_image"], "depth-a1-0")

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
                    "id": "plant",
                    "description": "green plant on the table",
                    "distance_threshold_m": 1.0,
                },
                {
                    "id": "glass",
                    "description": "glass on the dining table",
                    "distance_threshold_m": 1.0,
                },
            ],
            hypothesis_graph=hypothesis_graph,
        )

        self.assertEqual(sorted(completed_target_ids), ["glass", "plant"])
        self.assertTrue(hypothesis_graph.target_found["plant"])
        self.assertTrue(hypothesis_graph.target_found["glass"])


if __name__ == "__main__":
    unittest.main()
