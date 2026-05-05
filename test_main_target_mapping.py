import importlib.util
import pathlib
import sys
import types
import unittest


_original_helper = sys.modules.get("Helper")
helper_stub = types.ModuleType("Helper")
helper_stub.TYPE_VP = 1
sys.modules["Helper"] = helper_stub

module_path = pathlib.Path(__file__).resolve().parent / "main.py"
spec = importlib.util.spec_from_file_location("main_under_test_detection", module_path)
main_under_test = importlib.util.module_from_spec(spec)
spec.loader.exec_module(main_under_test)


def tearDownModule():
    sys.modules.pop("main_under_test_detection", None)
    if _original_helper is None:
        sys.modules.pop("Helper", None)
    else:
        sys.modules["Helper"] = _original_helper


class _FakeGraph:
    def __init__(self):
        self.target_found = {"0": False}

    def mark_target_found(self, target_id):
        self.target_found[target_id] = True


class MainDetectionMappingTest(unittest.TestCase):
    def test_found_detection_marks_target_and_preserves_panorama_center(self):
        completed_targets = main_under_test._collect_completed_targets(
            mllm_output={
                "detections": [
                    {
                        "agent_id": "agent0",
                        "target_indices": ["0"],
                        "founds": [True],
                        "target_center_xs": [0.25],
                    }
                ]
            },
            agent_observations=[{"agent_id": "agent0"}],
            targets=[{"target_id": "0", "description": "green plant"}],
            hypothesis_graph=_FakeGraph(),
        )

        detection = completed_targets[0]
        self.assertEqual(detection["target_id"], "0")
        self.assertEqual(detection["agent_id"], "agent0")
        self.assertEqual(detection["target_center_x"], 0.25)
        self.assertAlmostEqual(detection["target_heading"], -0.5 * 3.141592653589793)


if __name__ == "__main__":
    unittest.main()
