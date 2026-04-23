import sys
import types
import unittest
import numpy as np


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


class HorizonPanoramaTest(unittest.TestCase):
    def test_build_truncated_panorama_stitches_center_strips_in_order(self):
        frame_width = 64
        strip_width = int(round(frame_width * Helper.DELTA_HEADING_RAD / Helper.HFOV))

        raw_frames = [
            (index * np.ones((3, frame_width, 3), dtype=np.uint8))
            for index in range(Helper.HORIZON_LEN)
        ]
        annotated_frames = [
            ((100 + index) * np.ones((3, frame_width, 3), dtype=np.uint8))
            for index in range(Helper.HORIZON_LEN)
        ]

        raw_panorama = Helper.build_truncated_panorama(raw_frames)
        annotated_panorama = Helper.build_truncated_panorama(annotated_frames)

        self.assertEqual(
            raw_panorama.shape,
            (3, Helper.HORIZON_LEN * strip_width, 3),
        )
        self.assertEqual(
            annotated_panorama.shape,
            (3, Helper.HORIZON_LEN * strip_width, 3),
        )

        for index in range(Helper.HORIZON_LEN):
            start = index * strip_width
            end = start + strip_width
            self.assertTrue(np.all(raw_panorama[:, start:end] == index))
            self.assertTrue(np.all(annotated_panorama[:, start:end] == 100 + index))


if __name__ == "__main__":
    unittest.main()
