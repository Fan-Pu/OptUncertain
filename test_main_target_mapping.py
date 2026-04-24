import importlib.util
import pathlib
import sys
import types
import unittest


_original_helper = sys.modules.get("Helper")
sys.modules["Helper"] = types.ModuleType("Helper")

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


class MainDetectionMappingTest(unittest.TestCase):
    def test_select_detection_observation_maps_strip_index_to_heading_frame_and_depth(self):
        agent_observation = {
            "horizon_headings": [0.1, 0.2, 0.3],
            "horizon_rgb_frames": ["frame-0", "frame-1", "frame-2"],
            "horizon_depths": ["depth-0", "depth-1", "depth-2"],
        }
        detection = {"found": True, "strip_index": 1}

        target_heading, target_rgb_image, target_depth_image = (
            main_under_test.select_detection_observation(agent_observation, detection)
        )

        self.assertEqual(target_heading, 0.2)
        self.assertEqual(target_rgb_image, "frame-1")
        self.assertEqual(target_depth_image, "depth-1")


if __name__ == "__main__":
    unittest.main()
