import importlib.util
import pathlib
import sys
import types
import unittest


helper_stub = types.ModuleType("Helper")
helper_stub.TYPE_VP = 1
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
            {"agent_id": "agent0"},
            {"agent_id": "agent1"},
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
            ]
        }

    def test_multiple_targets_can_complete_in_same_step(self):
        hypothesis_graph = _FakeGraph()
        completed_targets = main_under_test._collect_completed_targets(
            mllm_output=self._mllm_output(),
            agent_observations=self._observations(),
            targets=[
                {"target_id": "0", "description": "green plant on the table"},
                {"target_id": "1", "description": "glass on the dining table"},
            ],
            hypothesis_graph=hypothesis_graph,
        )

        self.assertEqual(
            [item["target_id"] for item in completed_targets],
            ["0", "1"],
        )
        self.assertEqual(completed_targets[0]["agent_id"], "agent0")
        self.assertEqual(completed_targets[1]["agent_id"], "agent1")
        self.assertTrue(hypothesis_graph.target_found["0"])
        self.assertTrue(hypothesis_graph.target_found["1"])

    def test_multiple_agent_detections_for_same_target_use_first_detection(self):
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
            ]
        }

        completed_targets = main_under_test._collect_completed_targets(
            mllm_output=mllm_output,
            agent_observations=self._observations(),
            targets=[
                {"target_id": "0", "description": "green plant on the table"},
                {"target_id": "1", "description": "glass on the dining table"},
            ],
            hypothesis_graph=hypothesis_graph,
        )

        self.assertEqual([item["target_id"] for item in completed_targets], ["0"])
        self.assertEqual(completed_targets[0]["agent_id"], "agent0")
        self.assertAlmostEqual(completed_targets[0]["target_heading"], -0.5 * 3.141592653589793)


if __name__ == "__main__":
    unittest.main()
