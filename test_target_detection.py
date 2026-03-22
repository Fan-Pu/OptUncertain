import inspect
import sys
import types
import unittest
from unittest import mock


cv2_stub = types.ModuleType("cv2")
cv2_stub.FONT_HERSHEY_SIMPLEX = 0
cv2_stub.namedWindow = lambda *args, **kwargs: None
cv2_stub.imshow = lambda *args, **kwargs: None
cv2_stub.waitKey = lambda *args, **kwargs: -1
cv2_stub.putText = lambda *args, **kwargs: None
cv2_stub.rectangle = lambda *args, **kwargs: None
cv2_stub.getTextSize = lambda *args, **kwargs: ((0, 0), 0)
sys.modules.setdefault("cv2", cv2_stub)

matter_sim_stub = types.ModuleType("MatterSim")
matter_sim_stub.Simulator = object
sys.modules.setdefault("MatterSim", matter_sim_stub)

debugpy_stub = types.ModuleType("debugpy")
debugpy_stub.breakpoint = lambda: None
debugpy_stub.listen = lambda *args, **kwargs: None
debugpy_stub.wait_for_client = lambda: None
sys.modules.setdefault("debugpy", debugpy_stub)

import Helper


class _FakeSim:
    def getState(self):
        return [object()]


class TargetDetectionTest(unittest.TestCase):
    def test_returns_false_when_target_not_found(self):
        sim = _FakeSim()

        with mock.patch.object(Helper, "rotate_to_target_heading_mov2vp") as rotate_mock:
            result = Helper.target_detection(
                {"found": False, "view_id": -1},
                "plant",
                None,
                None,
                None,
                1.0,
                sim,
            )

        self.assertFalse(result)
        rotate_mock.assert_not_called()

    def test_terminates_when_distance_within_threshold(self):
        sim = _FakeSim()

        with mock.patch.object(Helper, "rotate_to_target_heading_mov2vp") as rotate_mock:
            with mock.patch.object(Helper, "render_sim_state") as render_mock:
                result = Helper.target_detection(
                    {"found": True, "view_id": 7},
                    "plant",
                    1.25,
                    object(),
                    object(),
                    3.0,
                    sim,
                )

        self.assertTrue(result)
        rotate_mock.assert_called_once_with(sim, 1.25, None)
        render_mock.assert_called_once()

    def test_continues_when_distance_exceeds_threshold(self):
        sim = _FakeSim()

        with mock.patch.object(Helper, "rotate_to_target_heading_mov2vp") as rotate_mock:
            with mock.patch.object(Helper, "render_sim_state") as render_mock:
                result = Helper.target_detection(
                    {"found": True, "view_id": 7},
                    "plant",
                    1.25,
                    object(),
                    object(),
                    2.0,
                    sim,
                )

        self.assertFalse(result)
        rotate_mock.assert_not_called()
        render_mock.assert_not_called()

    def test_missing_view_id_crashes_when_found(self):
        sim = _FakeSim()

        with self.assertRaises(KeyError):
            Helper.target_detection(
                {"found": True},
                "plant",
                1.25,
                object(),
                object(),
                3.0,
                sim,
            )

    def test_target_detection_no_longer_uses_legacy_plural_fields(self):
        source = inspect.getsource(Helper.target_detection)

        self.assertNotIn("view_confidences", source)
        self.assertNotIn("target_views", source)


if __name__ == "__main__":
    unittest.main()
