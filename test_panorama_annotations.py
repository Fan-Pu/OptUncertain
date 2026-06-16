import math
from types import SimpleNamespace

import numpy as np

import Helper


def _candidate(viewpoint_index, rel_heading, rel_elevation=0.0, horizon_index=0):
    return {
        "viewpoint_id": "vp%s" % viewpoint_index,
        "viewpoint_index": viewpoint_index,
        "distance": 1.0,
        "xy": [0.0, 0.0],
        "heading": float(rel_heading),
        "elevation": float(rel_elevation),
        "rel_heading": float(rel_heading),
        "rel_elevation": float(rel_elevation),
        "horizon_index": int(horizon_index),
    }


def test_panorama_marker_origin_constrains_left_and_right_boundaries():
    marker_text = "123"
    (text_width, _), _ = Helper._viewpoint_marker_text_size(marker_text)
    panorama_width = int(text_width) + 40
    panorama_height = 120
    strip_width = 20

    left_candidate = _candidate(
        viewpoint_index=int(marker_text),
        rel_heading=-0.5 * Helper.DELTA_HEADING_RAD,
    )
    left_x, _ = Helper._panorama_marker_origin(
        candidate=left_candidate,
        panorama_width=panorama_width,
        panorama_height=panorama_height,
        strip_width=strip_width,
    )
    assert left_x == 0

    right_candidate = _candidate(
        viewpoint_index=int(marker_text),
        rel_heading=-0.5 * Helper.DELTA_HEADING_RAD - 1e-6,
    )
    right_x, _ = Helper._panorama_marker_origin(
        candidate=right_candidate,
        panorama_width=panorama_width,
        panorama_height=panorama_height,
        strip_width=strip_width,
    )
    assert right_x == panorama_width - text_width


def test_select_viewpoint_marker_candidates_prefers_centered_observation():
    candidates = [
        _candidate(viewpoint_index=7, rel_heading=0.30, horizon_index=0),
        _candidate(viewpoint_index=7, rel_heading=-0.04, horizon_index=1),
        _candidate(viewpoint_index=7, rel_heading=0.10, horizon_index=2),
    ]

    selected = Helper._select_viewpoint_marker_candidates(candidates)

    assert len(selected) == 1
    assert selected[0]["horizon_index"] == 1


def test_annotate_rgb_with_viewpoints_preserves_metadata_for_clipped_label():
    image = np.zeros((80, 80, 3), dtype=np.uint8)
    current_location = SimpleNamespace(viewpointId="current")
    clipped_location = SimpleNamespace(
        viewpointId="neighbor",
        rel_heading=math.radians(60),
        rel_elevation=0.0,
        rel_distance=2.5,
        x=1.0,
        y=2.0,
    )

    _, visible_viewpoints = Helper.annotate_rgb_with_viewpoints(
        image,
        [current_location, clipped_location],
        viewpoint_index_by_vp={"neighbor": 42},
    )

    assert visible_viewpoints == [
        {
            "viewpoint_id": "neighbor",
            "viewpoint_index": 42,
            "distance": 2.5,
            "xy": [1.0, 2.0],
        }
    ]
