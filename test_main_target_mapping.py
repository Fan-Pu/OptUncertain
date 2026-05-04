import importlib.util
import pathlib
import sys
import types
import unittest


_original_helper = sys.modules.get("Helper")
helper_stub = types.ModuleType("Helper")
helper_stub.TYPE_VP = 1
helper_stub.panorama_center_x_to_heading = lambda target_center_x, horizon_headings: target_center_x
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


class MainDetectionMappingTest(unittest.TestCase):
    def test_found_detection_uses_full_aligned_panorama_images(self):
        found_detections = main_under_test._found_detections_by_target(
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
            agent_observations=[
                {
                    "agent_id": "agent0",
                    "horizon_headings": [0.1, 0.2],
                    "raw_panorama": "rgb-panorama",
                    "depth_panorama": "depth-panorama",
                }
            ],
            unfound_target_ids={"0"},
        )

        detection = found_detections["0"][0]
        self.assertEqual(detection["target_rgb_image"], "rgb-panorama")
        self.assertEqual(detection["target_depth_image"], "depth-panorama")
        self.assertEqual(detection["target_heading"], 0.25)


if __name__ == "__main__":
    unittest.main()
