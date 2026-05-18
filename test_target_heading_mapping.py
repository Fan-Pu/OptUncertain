import importlib.util
import math
import sys
import types
from types import SimpleNamespace

import numpy as np
import pytest


if importlib.util.find_spec("MatterSim") is None:
    mattersim_stub = types.ModuleType("MatterSim")

    class _Simulator:
        pass

    mattersim_stub.Simulator = _Simulator
    sys.modules["MatterSim"] = mattersim_stub

if importlib.util.find_spec("cv2") is None:
    sys.modules["cv2"] = types.ModuleType("cv2")

if importlib.util.find_spec("openai") is None:
    openai_stub = types.ModuleType("openai")

    class _BadRequestError(Exception):
        pass

    class _OpenAI:
        pass

    openai_stub.BadRequestError = _BadRequestError
    openai_stub.OpenAI = _OpenAI
    sys.modules["openai"] = openai_stub


import Helper
from main import _center_completed_targets, _collect_completed_targets
from semantic_persistence.mllm_client import MLLMClient


class _Graph:
    def __init__(self):
        self.target_found = {"0": False}

    def mark_target_found(self, target_id):
        self.target_found[str(target_id)] = True


def _horizon_headings(start_heading=0.0):
    return [
        (start_heading + index * Helper.DELTA_HEADING_RAD) % (2.0 * math.pi)
        for index in range(Helper.HORIZON_LEN)
    ]


@pytest.mark.parametrize("target_center_x", [0.0, 0.41, 0.999])
def test_panorama_center_x_to_heading_uses_scan_strip_geometry(target_center_x):
    horizon_headings = _horizon_headings(start_heading=0.37)
    panorama_position = target_center_x * len(horizon_headings)
    frame_index = int(math.floor(panorama_position))
    if frame_index == len(horizon_headings):
        frame_index = len(horizon_headings) - 1
    strip_fraction = panorama_position - frame_index
    expected_heading = (
        horizon_headings[frame_index]
        + (strip_fraction - 0.5) * Helper.DELTA_HEADING_RAD
    ) % (2.0 * math.pi)

    assert Helper.panorama_center_x_to_heading(
        target_center_x,
        horizon_headings,
    ) == pytest.approx(expected_heading)


def test_collect_completed_targets_maps_center_x_through_agent_horizon_headings():
    horizon_headings = _horizon_headings(start_heading=1.25)
    completed_targets = _collect_completed_targets(
        mllm_output={
            "detections": [
                {
                    "agent_id": "agent0",
                    "target_indices": ["0"],
                    "founds": [True],
                    "target_center_xs": [0.41],
                }
            ]
        },
        agent_observations=[
            {
                "agent_id": "agent0",
                "horizon_headings": horizon_headings,
            }
        ],
        targets=[
            {
                "target_id": "0",
                "description": "the long bathrobe in the bathroom",
            }
        ],
        hypothesis_graph=_Graph(),
    )

    assert len(completed_targets) == 1
    assert completed_targets[0]["target_id"] == "0"
    assert completed_targets[0]["description"] == "the long bathrobe in the bathroom"
    assert completed_targets[0]["agent_id"] == "agent0"
    assert completed_targets[0]["target_heading"] == pytest.approx(
        Helper.panorama_center_x_to_heading(0.41, horizon_headings)
    )


def test_center_completed_targets_passes_agent_window_and_notification(monkeypatch):
    calls = []

    def fake_execute_individual_rotations(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(
        Helper,
        "execute_individual_rotations",
        fake_execute_individual_rotations,
    )

    _center_completed_targets(
        agent_sims=["sim0", "sim1"],
        agent_ids=["agent0", "agent1"],
        completed_targets=[
            {
                "target_id": "0",
                "description": "the long bathrobe in the bathroom",
                "agent_id": "agent1",
                "target_center_x": 0.41,
                "target_heading": 1.5,
            }
        ],
    )

    assert calls == [
        {
            "sims": ["sim1"],
            "target_headings": [1.5],
            "PAUSE_TIME": Helper.PAUSE_TIME,
            "window_names": ["Agent 1"],
            "notifications": [
                "Target 0 (the long bathrobe in the bathroom) is found."
            ],
        }
    ]


def test_render_sim_state_draws_notification(monkeypatch):
    calls = []

    monkeypatch.setattr(Helper.cv2, "FONT_HERSHEY_SIMPLEX", 0, raising=False)
    monkeypatch.setattr(
        Helper.cv2,
        "getTextSize",
        lambda text, font, font_scale, thickness: ((len(text) * 10, 20), 5),
        raising=False,
    )
    monkeypatch.setattr(
        Helper.cv2,
        "rectangle",
        lambda image, start, end, color, thickness: calls.append(
            ("rectangle", start, end, color, thickness)
        ),
        raising=False,
    )
    monkeypatch.setattr(
        Helper.cv2,
        "putText",
        lambda image, text, origin, font, font_scale, color, thickness: calls.append(
            ("putText", text, origin, font, font_scale, color, thickness)
        ),
        raising=False,
    )
    monkeypatch.setattr(
        Helper.cv2,
        "imshow",
        lambda window_name, image: calls.append(("imshow", window_name)),
        raising=False,
    )
    monkeypatch.setattr(
        Helper.cv2,
        "waitKey",
        lambda delay: calls.append(("waitKey", delay)),
        raising=False,
    )

    state = SimpleNamespace(
        rgb=np.zeros((60, 80, 3), dtype=np.uint8),
        navigableLocations=[],
    )

    Helper.render_sim_state(
        [state],
        window_names=["Agent 1"],
        notifications=["Target 0 (the long bathrobe in the bathroom) is found."],
    )

    assert (
        "putText",
        "Target 0 (the long bathrobe in the bathroom) is found.",
        (16, 36),
        0,
        0.9,
        (255, 255, 255),
        2,
    ) in calls
    assert ("imshow", "Agent 1") in calls


def test_mllm_found_targets_maps_center_x_through_agent_horizon_headings():
    horizon_headings = _horizon_headings(start_heading=2.0)

    found_targets = MLLMClient._found_targets_from_detections(
        detections=[
            {
                "agent_id": "agent0",
                "target_indices": ["0"],
                "founds": [True],
                "target_center_xs": [0.41],
            }
        ],
        agent_observations=[
            {
                "agent_id": "agent0",
                "horizon_headings": horizon_headings,
            }
        ],
    )

    assert found_targets["0"][0]["target_heading"] == pytest.approx(
        Helper.panorama_center_x_to_heading(0.41, horizon_headings)
    )
