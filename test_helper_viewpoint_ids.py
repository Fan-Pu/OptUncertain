import sys
import types
import unittest
from unittest.mock import patch

import numpy as np


cv2_stub = types.ModuleType("cv2")
cv2_stub.FONT_HERSHEY_SIMPLEX = 0
cv2_stub.namedWindow = lambda *args, **kwargs: None
cv2_stub.imshow = lambda *args, **kwargs: None
cv2_stub.waitKey = lambda *args, **kwargs: ord("q")
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


class HelperViewpointIdsTest(unittest.TestCase):
    def setUp(self):
        self.original_get_viewpoints = Helper.get_viewpoints

    def tearDown(self):
        Helper.get_viewpoints = self.original_get_viewpoints
        Helper.viewpoint_index_by_vp_label.clear()
        Helper.viewpoint_vp_label_by_index.clear()

    def test_build_viewpoint_index_clears_stale_entries(self):
        Helper.viewpoint_index_by_vp_label["stale-vp"] = 99
        Helper.viewpoint_vp_label_by_index[99] = "stale-vp"
        Helper.get_viewpoints = lambda scan_id: ["vp-a", "vp-b"]

        Helper.build_viewpoint_index("scan-1")

        self.assertEqual(Helper.viewpoint_index_by_vp_label, {"vp-a": 0, "vp-b": 1})
        self.assertEqual(Helper.viewpoint_vp_label_by_index, {0: "vp-a", 1: "vp-b"})

    def test_explore_world_prints_short_current_viewpoint_id(self):
        raw_viewpoint_id = "f6cbc0517fc14f129f5456e59dc66c76"
        Helper.viewpoint_index_by_vp_label[raw_viewpoint_id] = 50
        state = types.SimpleNamespace(
            location=types.SimpleNamespace(viewpointId=raw_viewpoint_id),
            elevation=0.0,
            heading=0.0,
            navigableLocations=[types.SimpleNamespace(viewpointId=raw_viewpoint_id)],
            rgb=np.zeros((Helper.HEIGHT, Helper.WIDTH, 3), dtype=np.uint8),
            depth=np.zeros((Helper.HEIGHT, Helper.WIDTH), dtype=np.float32),
        )
        sim = types.SimpleNamespace(
            makeAction=lambda *args, **kwargs: None,
            getState=lambda: [state],
        )

        with patch("builtins.print") as print_mock:
            Helper.explore_world(sim)

        print_mock.assert_any_call(
            "current vp: 50, elevation: 0.0 deg, heading: 0.0 deg"
        )


if __name__ == "__main__":
    unittest.main()
