import math
from types import SimpleNamespace

import numpy as np

import Helper


def _candidate(
    viewpoint_index,
    rel_heading,
    rel_elevation=0.0,
    horizon_index=0,
    elevation_band_index=0,
):
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
        "elevation_band_index": int(elevation_band_index),
        "elevation_band_count": len(Helper.ELEVATION_BAND_DEGS),
    }


def _frame(color, height=100, width=800):
    return np.full((height, width, 3), color, dtype=np.uint8)


def _frame_rows():
    return [
        [_frame([200, 0, 0]) for _ in range(4)],
        [_frame([0, 200, 0]) for _ in range(4)],
        [_frame([0, 0, 200]) for _ in range(4)],
    ]


def _frame_pose_rows():
    heading_rows = [
        [index * Helper.DELTA_HEADING_RAD for index in range(4)]
        for _ in Helper.ELEVATION_BAND_RADS
    ]
    elevation_rows = [
        [elevation for _ in range(4)]
        for elevation in Helper.ELEVATION_BAND_RADS
    ]
    return heading_rows, elevation_rows


def _analytic_frame(heading, elevation, height=100, width=800):
    x_coords = np.arange(width, dtype=np.float32)[None, :]
    y_coords = np.arange(height, dtype=np.float32)[:, None]
    tan_half_hfov = math.tan(Helper.HFOV / 2.0)
    tan_half_vfov = math.tan(Helper.VFOV / 2.0)
    camera_x = (2.0 * x_coords / float(width - 1) - 1.0) * tan_half_hfov
    camera_y = (1.0 - 2.0 * y_coords / float(height - 1)) * tan_half_vfov
    camera_z = np.ones((height, width), dtype=np.float32)

    forward, right, up = Helper._camera_axes(heading, elevation)
    ray_x = (
        camera_x * right[0]
        + camera_y * up[0]
        + camera_z * forward[0]
    )
    ray_y = (
        camera_x * right[1]
        + camera_y * up[1]
        + camera_z * forward[1]
    )
    ray_z = (
        camera_x * right[2]
        + camera_y * up[2]
        + camera_z * forward[2]
    )

    global_heading = np.mod(np.arctan2(ray_x, ray_z), 2.0 * math.pi)
    horizontal_norm = np.sqrt(ray_x * ray_x + ray_z * ray_z)
    global_pitch = np.arctan2(ray_y, horizontal_norm)
    red = global_heading / (2.0 * math.pi) * 255.0
    green = (global_pitch + math.pi / 2.0) / math.pi * 255.0
    blue = np.zeros((height, width), dtype=np.float32)
    return np.clip(np.stack([red, green, blue], axis=2), 0, 255).astype(np.uint8)


def _analytic_frame_rows():
    heading_rows, elevation_rows = _frame_pose_rows()
    return [
        [
            _analytic_frame(
                heading=heading,
                elevation=elevation_rows[elevation_band_index][horizon_index],
            )
            for horizon_index, heading in enumerate(heading_row)
        ]
        for elevation_band_index, heading_row in enumerate(heading_rows)
    ], heading_rows, elevation_rows


def test_multi_elevation_panorama_projects_rows_to_smooth_pitch_canvas():
    rows = _frame_rows()
    panorama = Helper.build_multi_elevation_panorama(rows)
    strip_width = Helper._panorama_strip_width(rows[0][0])
    expected_strip_width = int(
        round(
            (rows[0][0].shape[1] - 1)
            * math.tan(Helper.DELTA_HEADING_RAD / 2.0)
            / math.tan(Helper.HFOV / 2.0)
        )
    )

    assert strip_width == expected_strip_width
    assert panorama.shape == (200, strip_width * 4, 3)
    assert panorama[10, 10, 0] > 180
    assert panorama[100, 10, 1] > 180
    assert panorama[190, 10, 2] > 180


def test_multi_elevation_panorama_uses_single_source_in_overlap_regions():
    rows = _frame_rows()
    panorama = Helper.build_multi_elevation_panorama(rows)

    upper_middle_overlap = panorama[75, 10]
    lower_middle_overlap = panorama[125, 10]

    assert upper_middle_overlap[0] < 10
    assert upper_middle_overlap[1] > 180
    assert upper_middle_overlap[2] < 10
    assert lower_middle_overlap[0] < 10
    assert lower_middle_overlap[1] < 10
    assert lower_middle_overlap[2] > 180


def test_multi_elevation_panorama_keeps_yaw_boundaries_continuous():
    rows, heading_rows, elevation_rows = _analytic_frame_rows()
    panorama = Helper.build_multi_elevation_panorama(
        rows,
        heading_rows=heading_rows,
        elevation_rows=elevation_rows,
    )
    strip_width = Helper._panorama_strip_width(rows[0][0])
    center_y = panorama.shape[0] // 2

    for boundary_x in (strip_width, 2 * strip_width, 3 * strip_width):
        seam_delta = np.abs(
            panorama[center_y, boundary_x - 1].astype(np.int16)
            - panorama[center_y, boundary_x].astype(np.int16)
        )
        assert np.max(seam_delta) <= 4


def test_smooth_multi_elevation_panorama_draws_heading_guides_and_pitch_labels():
    rows = [[_frame([0, 0, 0]) for _ in range(4)] for _ in range(3)]
    panorama = Helper.build_multi_elevation_panorama(rows, add_guides=True)

    assert np.any(np.all(panorama[:, 0:2] == [255, 255, 255], axis=2))
    assert np.any(panorama[40:60, 2:180] != 0)
    assert np.any(panorama[90:110, 2:180] != 0)
    assert np.any(panorama[140:160, 2:180] != 0)


def test_panorama_marker_origin_uses_absolute_pitch_not_row_band():
    rows = _frame_rows()
    panorama = Helper.build_multi_elevation_panorama(rows)
    strip_width = Helper._panorama_strip_width(rows[0][0])
    panorama_height, panorama_width = panorama.shape[:2]

    _, upper_pitch_y = Helper._panorama_marker_origin(
        candidate=_candidate(7, rel_heading=0.0, elevation_band_index=0),
        panorama_width=panorama_width,
        panorama_height=panorama_height,
        strip_width=strip_width,
    )
    _, middle_pitch_y = Helper._panorama_marker_origin(
        candidate=_candidate(8, rel_heading=0.0, elevation_band_index=1),
        panorama_width=panorama_width,
        panorama_height=panorama_height,
        strip_width=strip_width,
    )
    _, lower_pitch_y = Helper._panorama_marker_origin(
        candidate=_candidate(8, rel_heading=0.0, elevation_band_index=2),
        panorama_width=panorama_width,
        panorama_height=panorama_height,
        strip_width=strip_width,
    )

    assert 40 <= upper_pitch_y <= 60
    assert 90 <= middle_pitch_y <= 110
    assert 140 <= lower_pitch_y <= 160


def test_panorama_center_x_to_heading_stays_horizontal_axis_only():
    headings = [index * Helper.DELTA_HEADING_RAD for index in range(4)]

    assert math.isclose(
        Helper.panorama_center_x_to_heading(0.5, headings),
        1.5 * Helper.DELTA_HEADING_RAD,
    )


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
