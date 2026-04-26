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
    def test_found_detection_uses_full_aligned_panorama_images(self):
        found_detections = main_under_test._found_detections_by_target(
            mllm_output={
                "detections": [
                    {
                        "agent_id": "agent0",
                        "target": "green plant on the table",
                        "found": True,
                    }
                ]
            },
            agent_observations=[
                {
                    "agent_id": "agent0",
                    "raw_panorama": "rgb-panorama",
                    "depth_panorama": "depth-panorama",
                }
            ],
            unfound_target_descriptions={"green plant on the table"},
        )

        detection = found_detections["green plant on the table"][0]
        self.assertEqual(detection["target_rgb_image"], "rgb-panorama")
        self.assertEqual(detection["target_depth_image"], "depth-panorama")


if __name__ == "__main__":
    unittest.main()
