import importlib.util
import pathlib
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
cv2_stub.getTextSize = lambda *args, **kwargs: ((0, 0), 0)

matter_sim_stub = types.ModuleType("MatterSim")
matter_sim_stub.Simulator = object

_original_cv2 = sys.modules.get("cv2")
_original_matter_sim = sys.modules.get("MatterSim")
sys.modules["cv2"] = cv2_stub
sys.modules["MatterSim"] = matter_sim_stub

module_path = pathlib.Path(__file__).resolve().parent / "Helper.py"
spec = importlib.util.spec_from_file_location("helper_under_test_batch", module_path)
helper_under_test = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper_under_test)


def tearDownModule():
    if _original_cv2 is None:
        sys.modules.pop("cv2", None)
    else:
        sys.modules["cv2"] = _original_cv2
    if _original_matter_sim is None:
        sys.modules.pop("MatterSim", None)
    else:
        sys.modules["MatterSim"] = _original_matter_sim


class _FakeLocation:
    def __init__(self, viewpoint_id, rel_heading, rel_distance):
        self.viewpointId = viewpoint_id
        self.rel_heading = rel_heading
        self.rel_elevation = 0.0
        self.rel_distance = rel_distance


class _FakeState:
    def __init__(self, viewpoint_id, heading, rgb_value, depth_value):
        self.location = types.SimpleNamespace(viewpointId=viewpoint_id)
        self.heading = heading
        self.rgb = rgb_value * np.ones((4, 64, 3), dtype=np.uint8)
        self.depth = depth_value * np.ones((4, 64, 1), dtype=np.float32)
        self.navigableLocations = [
            types.SimpleNamespace(viewpointId=viewpoint_id, rel_heading=0.0, rel_elevation=0.0, rel_distance=0.0),
            _FakeLocation("vp-a", 0.0, 1.0),
            _FakeLocation("vp-b", 0.2, 1.5),
        ]


class _FakeSim:
    def __init__(self):
        self.actions = []
        self.states = [
            _FakeState("vp-root-0", 0.0, 11, 1.0),
            _FakeState("vp-root-1", 0.1, 22, 2.0),
        ]

    def getState(self):
        return self.states

    def makeAction(self, locations, headings, elevations):
        self.actions.append((list(locations), list(headings), list(elevations)))


class HorizonPanoramaBatchTest(unittest.TestCase):
    def test_batch_horizon_scan_returns_one_panorama_per_agent(self):
        helper_under_test.viewpoint_index_by_vp_label.clear()
        helper_under_test.viewpoint_vp_label_by_index.clear()
        helper_under_test.viewpoint_index_by_vp_label.update(
            {
                "vp-root-0": 0,
                "vp-root-1": 1,
                "vp-a": 2,
                "vp-b": 3,
            }
        )
        helper_under_test.viewpoint_vp_label_by_index.update(
            {0: "vp-root-0", 1: "vp-root-1", 2: "vp-a", 3: "vp-b"}
        )
        sim = _FakeSim()

        observations = helper_under_test.horizon_scan_batch_return(
            sim=sim,
            agent_ids=["agent0", "agent1"],
            viewpoint_index_by_vp=helper_under_test.viewpoint_index_by_vp_label,
        )

        strip_width = int(
            round(64 * helper_under_test.DELTA_HEADING_RAD / helper_under_test.HFOV)
        )
        self.assertEqual(len(observations), 2)
        self.assertEqual(observations[0]["agent_id"], "agent0")
        self.assertEqual(observations[1]["agent_id"], "agent1")
        self.assertEqual(
            observations[0]["annotated_panorama"].shape,
            (4, helper_under_test.HORIZON_LEN * strip_width, 3),
        )
        self.assertEqual(
            observations[1]["raw_panorama"].shape,
            (4, helper_under_test.HORIZON_LEN * strip_width, 3),
        )
        self.assertEqual(len(sim.actions), helper_under_test.HORIZON_LEN)

    def test_execute_batched_first_hops_uses_one_move_action_per_agent(self):
        sim = _FakeSim()
        sim.states[0].navigableLocations = [
            types.SimpleNamespace(viewpointId="vp-root-0", rel_heading=0.0, rel_elevation=0.0, rel_distance=0.0),
            _FakeLocation("vp-a", 0.0, 1.0),
        ]
        sim.states[1].navigableLocations = [
            types.SimpleNamespace(viewpointId="vp-root-1", rel_heading=0.0, rel_elevation=0.0, rel_distance=0.0),
            _FakeLocation("vp-a", 0.0, 1.0),
            _FakeLocation("vp-b", 0.1, 1.5),
        ]

        helper_under_test.execute_batched_first_hops(
            sim=sim,
            move_specs=[
                {"target_heading": 0.0, "target_viewpoint_id": "vp-a"},
                {"target_heading": 0.0, "target_viewpoint_id": "vp-b"},
            ],
        )

        self.assertEqual(sim.actions[-1][0], [1, 2])


if __name__ == "__main__":
    unittest.main()
