from doctest import debug
import json
import math
import os
import time
from collections import defaultdict

import debugpy

import cv2
import MatterSim
import numpy as np

WIDTH = 800
HEIGHT = 600
VFOV = math.radians(60)
HFOV = 2.0 * math.atan(math.tan(VFOV / 2.0) * WIDTH / HEIGHT)
TEXT_COLOR = [230, 40, 40]
VIEWPOINT_MARKER_FONT_SCALE = 2.0
VIEWPOINT_MARKER_THICKNESS = 3
MP_ROOT = "/root/mount/Matterport3DSimulator"
HORIZON_LEN = 48 * 4
DELTA_HEADING_DEG = 360 / HORIZON_LEN
DELTA_HEADING_RAD = math.radians(DELTA_HEADING_DEG)
ELEVATION_BAND_DEGS = (30.0, 0.0, -30.0)
ELEVATION_BAND_RADS = tuple(math.radians(value) for value in ELEVATION_BAND_DEGS)
PAUSE_TIME = 0.02

TYPE_REGION = 0
TYPE_VP = 1

viewpoint_index_by_vp_label = {}
viewpoint_vp_label_by_index = {}


def init_render(batch_size=1, enable_render=False):
    if enable_render:
        for batch_index in range(int(batch_size)):
            cv2.namedWindow("Agent %s" % batch_index)

    sim = MatterSim.Simulator()
    sim.setCameraResolution(WIDTH, HEIGHT)
    sim.setCameraVFOV(VFOV)
    sim.setDiscretizedViewingAngles(False)
    sim.setDatasetPath(os.path.join(MP_ROOT, "data/v1/scans"))
    sim.setNavGraphPath(os.path.join(MP_ROOT, "connectivity"))
    sim.setPreloadingEnabled(True)
    sim.setBatchSize(int(batch_size))
    sim.setCacheSize(2)
    return sim


def get_viewpoints(scan_id):
    connectivity_file = os.path.join(
        MP_ROOT, "connectivity", "%s_connectivity.json" % scan_id
    )
    with open(connectivity_file, "r", encoding="utf-8") as file_handle:
        data = json.load(file_handle)
    return [item["image_id"] for item in data if item["included"]]


def build_viewpoint_index(scan_id):
    viewpoint_index_by_vp_label.clear()
    viewpoint_vp_label_by_index.clear()
    for index, viewpoint_id in enumerate(get_viewpoints(scan_id)):
        viewpoint_index_by_vp_label[viewpoint_id] = index
        viewpoint_vp_label_by_index[index] = viewpoint_id


def simulator_frame_to_rgb(frame):
    return cv2.cvtColor(np.array(frame, copy=True), cv2.COLOR_BGR2RGB)


def _viewpoint_index_for_location(location, fallback_index, viewpoint_index_by_vp):
    viewpoint_index = fallback_index
    if (
        viewpoint_index_by_vp is not None
        and location.viewpointId in viewpoint_index_by_vp
    ):
        viewpoint_index = int(viewpoint_index_by_vp[location.viewpointId])
    return viewpoint_index


def _viewpoint_record_from_location(location, viewpoint_index):
    return {
        "viewpoint_id": str(location.viewpointId),
        "viewpoint_index": int(viewpoint_index),
        "distance": float(location.rel_distance),
        "xy": [float(location.x), float(location.y)],
    }


def _viewpoint_marker_text_size(marker_text):
    return cv2.getTextSize(
        str(marker_text),
        cv2.FONT_HERSHEY_SIMPLEX,
        VIEWPOINT_MARKER_FONT_SCALE,
        VIEWPOINT_MARKER_THICKNESS,
    )


def _constrain_marker_origin(
    x_coord,
    y_coord,
    text_width,
    text_height,
    baseline,
    image_width,
    image_height,
):
    x_coord = int(round(x_coord))
    y_coord = int(round(y_coord))
    x_coord = min(max(x_coord, 0), image_width - int(text_width))
    y_coord = min(max(y_coord, int(text_height)), image_height - int(baseline))
    return x_coord, y_coord


def _draw_viewpoint_marker(rgb_image, viewpoint_index, x_coord, y_coord):
    marker_text = str(viewpoint_index)
    cv2.putText(
        rgb_image,
        marker_text,
        (int(x_coord), int(y_coord)),
        cv2.FONT_HERSHEY_SIMPLEX,
        VIEWPOINT_MARKER_FONT_SCALE,
        TEXT_COLOR,
        thickness=VIEWPOINT_MARKER_THICKNESS,
    )


def _viewpoint_marker_candidate(
    location,
    viewpoint_index,
    current_heading,
    horizon_index,
    elevation_band_index=0,
):
    candidate = _viewpoint_record_from_location(location, viewpoint_index)
    candidate.update(
        {
            "heading": (float(current_heading) + float(location.rel_heading))
            % (2.0 * math.pi),
            "elevation": float(location.rel_elevation),
            "rel_heading": float(location.rel_heading),
            "rel_elevation": float(location.rel_elevation),
            "horizon_index": int(horizon_index),
            "elevation_band_index": int(elevation_band_index),
            "elevation_band_count": len(ELEVATION_BAND_DEGS),
        }
    )
    return candidate


def execute_individual_rotations(
    sims,
    target_headings,
    window_names=None,
    notifications=None,
    render=True,
):
    if len(sims) != len(target_headings):
        raise ValueError("sims and target_headings must have the same length.")

    states = [sim.getState()[0] for sim in sims]
    step_plans = []
    for state, target_heading in zip(states, target_headings):
        direction, step_count = compute_rotation(
            math.degrees(state.heading),
            math.degrees(float(target_heading)),
            DELTA_HEADING_DEG,
        )
        step_plans.append(
            {
                "direction": direction,
                "step_count": step_count,
            }
        )

    max_step_count = max(plan["step_count"] for plan in step_plans)
    for step_index in range(max_step_count):
        for sim, plan in zip(sims, step_plans):
            heading = (
                plan["direction"] * DELTA_HEADING_RAD
                if step_index < plan["step_count"]
                else 0.0
            )
            sim.makeAction([0], [heading], [0.0])
        if render and PAUSE_TIME > 0.0:
            time.sleep(PAUSE_TIME)
        if render:
            render_sim_state(
                [sim.getState()[0] for sim in sims],
                viewpoint_index_by_vp=viewpoint_index_by_vp_label,
                window_names=window_names,
            )

    if render and notifications is not None:
        render_sim_state(
            [sim.getState()[0] for sim in sims],
            viewpoint_index_by_vp=viewpoint_index_by_vp_label,
            window_names=window_names,
            notifications=notifications,
        )
        if PAUSE_TIME > 0.0:
            time.sleep(2)


def annotate_rgb_with_viewpoints(rgb, locations, viewpoint_index_by_vp=None):
    annotated_rgb = np.array(rgb, copy=True)
    image_height, image_width = annotated_rgb.shape[:2]
    visible_viewpoints = []

    for fallback_index, location in enumerate(locations[1:], start=1):
        viewpoint_index = _viewpoint_index_for_location(
            location,
            fallback_index,
            viewpoint_index_by_vp,
        )

        x_coord = int(image_width / 2 + location.rel_heading / HFOV * image_width)
        y_coord = int(image_height / 2 - location.rel_elevation / VFOV * image_height)
        marker_text = str(viewpoint_index)
        (text_width, text_height), baseline = cv2.getTextSize(
            marker_text,
            cv2.FONT_HERSHEY_SIMPLEX,
            VIEWPOINT_MARKER_FONT_SCALE,
            VIEWPOINT_MARKER_THICKNESS,
        )
        if not (
            x_coord < 0
            or x_coord + text_width > image_width
            or y_coord - text_height < 0
            or y_coord + baseline > image_height
        ):
            _draw_viewpoint_marker(
                annotated_rgb,
                viewpoint_index,
                x_coord,
                y_coord,
            )
        visible_viewpoints.append(
            _viewpoint_record_from_location(location, viewpoint_index)
        )

    return annotated_rgb, visible_viewpoints


def _draw_notification(rgb_image, notification):
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.9
    thickness = 2
    margin = 16
    padding = 10
    (text_width, text_height), baseline = cv2.getTextSize(
        notification,
        font,
        font_scale,
        thickness,
    )
    cv2.rectangle(
        rgb_image,
        (margin - padding, margin - padding),
        (margin + text_width + padding, margin + text_height + baseline + padding),
        (0, 0, 0),
        thickness=-1,
    )
    cv2.putText(
        rgb_image,
        notification,
        (margin, margin + text_height),
        font,
        font_scale,
        (255, 255, 255),
        thickness=thickness,
    )


def render_sim_state(
    state_list,
    viewpoint_index_by_vp=None,
    window_names=None,
    notifications=None,
):
    if window_names is None:
        window_names = [
            "Agent %s" % batch_index for batch_index in range(len(state_list))
        ]
    if notifications is None:
        notifications = [None for _ in state_list]

    for batch_index, state in enumerate(state_list):
        rgb_frame = simulator_frame_to_rgb(state.rgb)
        rgb_image, _ = annotate_rgb_with_viewpoints(
            rgb_frame,
            state.navigableLocations,
            viewpoint_index_by_vp=viewpoint_index_by_vp,
        )
        if notifications[batch_index]:
            _draw_notification(rgb_image, notifications[batch_index])
        cv2.imshow(
            window_names[batch_index],
            cv2.cvtColor(rgb_image, cv2.COLOR_RGB2BGR),
        )
    cv2.waitKey(1)


def _panorama_strip_width(frame):
    return int(
        round(
            (frame.shape[1] - 1)
            * math.tan(DELTA_HEADING_RAD / 2.0)
            / math.tan(HFOV / 2.0)
        )
    )


def _panorama_pitch_bounds():
    return (
        min(ELEVATION_BAND_RADS) - VFOV / 2.0,
        max(ELEVATION_BAND_RADS) + VFOV / 2.0,
    )


def _panorama_pitch_height(frame_height):
    pitch_min, pitch_max = _panorama_pitch_bounds()
    return int(round(float(frame_height) * (pitch_max - pitch_min) / VFOV))


def _pitch_to_panorama_y(pitch, panorama_height):
    pitch_min, pitch_max = _panorama_pitch_bounds()
    return (pitch_max - float(pitch)) / (pitch_max - pitch_min) * float(
        panorama_height
    )


def _draw_panorama_text(rgb_image, text, origin, font_scale=0.7, thickness=2):
    x_coord, y_coord = origin
    cv2.putText(
        rgb_image,
        str(text),
        (int(x_coord), int(y_coord)),
        cv2.FONT_HERSHEY_SIMPLEX,
        font_scale,
        (0, 0, 0),
        thickness=thickness + 2,
    )
    cv2.putText(
        rgb_image,
        str(text),
        (int(x_coord), int(y_coord)),
        cv2.FONT_HERSHEY_SIMPLEX,
        font_scale,
        (255, 255, 255),
        thickness=thickness,
    )


def _build_panorama_row(horizon_frames, add_guides=False, row_label=None):
    strip_width = _panorama_strip_width(horizon_frames[0])
    center_x = horizon_frames[0].shape[1] // 2
    start_x = center_x - strip_width // 2
    end_x = start_x + strip_width

    strips = [frame[:, start_x:end_x].copy() for frame in horizon_frames]
    panorama_row = np.concatenate(strips, axis=1)

    if add_guides:
        image_height = panorama_row.shape[0]

        for horizon_index in range(0, len(horizon_frames), 12):
            x_coord = int(horizon_index * strip_width)
            heading_deg = int(round(horizon_index * DELTA_HEADING_DEG))

            cv2.line(
                panorama_row,
                (x_coord, 0),
                (x_coord, image_height - 1),
                (255, 255, 255),
                thickness=2,
            )

            _draw_panorama_text(
                panorama_row,
                "%d deg" % heading_deg,
                (x_coord + 4, 28),
            )

        if row_label is not None:
            label_y = image_height - 16 if image_height >= 64 else image_height - 6
            _draw_panorama_text(
                panorama_row,
                row_label,
                (4, label_y),
                font_scale=0.7,
                thickness=2,
            )

    return panorama_row


def build_truncated_panorama(horizon_frames, add_guides=False):
    return _build_panorama_row(horizon_frames, add_guides=add_guides)


def _camera_axes(heading, elevation):
    sin_heading = math.sin(float(heading))
    cos_heading = math.cos(float(heading))
    sin_elevation = math.sin(float(elevation))
    cos_elevation = math.cos(float(elevation))
    forward = np.array(
        [
            cos_elevation * sin_heading,
            sin_elevation,
            cos_elevation * cos_heading,
        ],
        dtype=np.float32,
    )
    right = np.array([cos_heading, 0.0, -sin_heading], dtype=np.float32)
    up = np.cross(forward, right).astype(np.float32)
    return forward, right, up


def _angle_difference(angles, reference_angles):
    return (angles - reference_angles + math.pi) % (2.0 * math.pi) - math.pi


def _default_heading_rows(horizon_frame_rows):
    return [
        [
            float(horizon_index) * float(DELTA_HEADING_RAD)
            for horizon_index in range(len(horizon_frames))
        ]
        for horizon_frames in horizon_frame_rows
    ]


def _default_elevation_rows(horizon_frame_rows):
    return [
        [
            float(ELEVATION_BAND_RADS[elevation_band_index])
            for _ in horizon_frames
        ]
        for elevation_band_index, horizon_frames in enumerate(horizon_frame_rows)
    ]


def _panorama_output_headings(heading_axis, panorama_width, strip_width):
    panorama_positions = (
        np.arange(panorama_width, dtype=np.float32) + 0.5
    ) / float(strip_width)
    frame_indices = np.floor(panorama_positions).astype(np.int32)
    strip_fractions = panorama_positions - frame_indices.astype(np.float32)
    heading_axis_array = np.asarray(heading_axis, dtype=np.float32)
    return (
        heading_axis_array[frame_indices]
        + (strip_fractions - 0.5) * float(DELTA_HEADING_RAD)
    )


def _source_projection_maps(
    target_headings,
    target_pitches,
    source_heading,
    source_elevation,
    source_width,
    source_height,
):
    heading_delta = _angle_difference(target_headings, source_heading)
    sin_pitch = np.sin(target_pitches)
    cos_pitch = np.cos(target_pitches)
    sin_elevation = np.sin(source_elevation)
    cos_elevation = np.cos(source_elevation)
    camera_x = cos_pitch * np.sin(heading_delta)
    camera_y = (
        sin_pitch * cos_elevation
        - cos_pitch * sin_elevation * np.cos(heading_delta)
    )
    camera_z = (
        sin_pitch * sin_elevation
        + cos_pitch * cos_elevation * np.cos(heading_delta)
    )
    tan_half_hfov = math.tan(float(HFOV / 2.0))
    tan_half_vfov = math.tan(float(VFOV / 2.0))
    map_x = (
        (camera_x / camera_z / tan_half_hfov + 1.0)
        * 0.5
        * float(source_width - 1)
    ).astype(np.float32)
    map_y = (
        (1.0 - camera_y / camera_z / tan_half_vfov)
        * 0.5
        * float(source_height - 1)
    ).astype(np.float32)
    valid = (
        (camera_z > 0.0)
        & (map_x >= 0.0)
        & (map_x <= float(source_width - 1))
        & (map_y >= 0.0)
        & (map_y <= float(source_height - 1))
    )
    return map_x, map_y, valid


def _project_elevation_rows_to_pitch_canvas(
    horizon_frame_rows,
    heading_rows=None,
    elevation_rows=None,
):
    if heading_rows is None:
        heading_rows = _default_heading_rows(horizon_frame_rows)
    if elevation_rows is None:
        elevation_rows = _default_elevation_rows(horizon_frame_rows)

    source_height, source_width = horizon_frame_rows[0][0].shape[:2]
    horizon_frame_count = len(horizon_frame_rows[0])
    strip_width = _panorama_strip_width(horizon_frame_rows[0][0])
    panorama_width = int(strip_width * horizon_frame_count)
    output_height = _panorama_pitch_height(source_height)
    pitch_min, pitch_max = _panorama_pitch_bounds()
    pitch_span = pitch_max - pitch_min
    output_pitches = (
        pitch_max
        - (np.arange(output_height, dtype=np.float32) + 0.5)
        * float(pitch_span)
        / float(output_height)
    )
    output_headings = _panorama_output_headings(
        heading_rows[0],
        panorama_width,
        strip_width,
    )
    selected_horizon_by_band = []
    band_scores = []
    output_pitch_grid = output_pitches[:, None]

    for elevation_band_index in range(len(horizon_frame_rows)):
        source_headings = np.asarray(
            heading_rows[elevation_band_index],
            dtype=np.float32,
        )
        source_elevations = np.asarray(
            elevation_rows[elevation_band_index],
            dtype=np.float32,
        )
        heading_deltas = _angle_difference(
            output_headings[:, None],
            source_headings[None, :],
        )
        horizon_indices = np.argmax(np.cos(heading_deltas), axis=1).astype(np.int32)
        selected_horizon_by_band.append(horizon_indices)

        col_indices = np.arange(panorama_width)
        selected_heading_deltas = heading_deltas[col_indices, horizon_indices]
        selected_source_elevations = source_elevations[horizon_indices]

        source_elevation_grid = selected_source_elevations[None, :]
        _, _, valid = _source_projection_maps(
            output_headings[None, :],
            output_pitch_grid,
            source_headings[horizon_indices][None, :],
            source_elevation_grid,
            source_width,
            source_height,
        )
        score = (
            np.sin(output_pitch_grid) * np.sin(source_elevation_grid)
            + np.cos(output_pitch_grid)
            * np.cos(source_elevation_grid)
            * np.cos(selected_heading_deltas[None, :])
        )
        band_scores.append(np.where(valid, score, -np.inf))

    band_score_stack = np.stack(band_scores, axis=2)
    best_scores = np.max(band_score_stack, axis=2)
    if np.any(~np.isfinite(best_scores)):
        raise RuntimeError("multi-elevation reprojection produced an uncovered ray")
    selected_band_by_pixel = np.argmax(band_score_stack, axis=2).astype(np.int32)
    output = np.empty((output_height, panorama_width, 3), dtype=np.uint8)

    target_pitch_grid = output_pitches[:, None]
    for elevation_band_index in range(len(horizon_frame_rows)):
        selected_horizon_by_x = selected_horizon_by_band[elevation_band_index]
        for horizon_index in range(horizon_frame_count):
            cols = np.where(selected_horizon_by_x == horizon_index)[0]
            if len(cols) == 0:
                continue

            target_heading = output_headings[cols][None, :]
            map_x, map_y, valid = _source_projection_maps(
                target_heading,
                target_pitch_grid,
                float(heading_rows[elevation_band_index][horizon_index]),
                float(elevation_rows[elevation_band_index][horizon_index]),
                source_width,
                source_height,
            )
            selected_mask = selected_band_by_pixel[:, cols] == elevation_band_index
            if np.any(selected_mask & ~valid):
                raise RuntimeError("multi-elevation reprojection selected an invalid source view")

            sampled = cv2.remap(
                horizon_frame_rows[elevation_band_index][horizon_index],
                map_x,
                map_y,
                interpolation=cv2.INTER_LINEAR,
            )
            output_view = output[:, cols]
            output_view[selected_mask] = sampled[selected_mask]
            output[:, cols] = output_view

    return output


def _draw_smooth_panorama_guides(panorama, horizon_frame_count):
    image_height, image_width = panorama.shape[:2]
    strip_width = image_width / float(horizon_frame_count)
    for horizon_index in range(0, horizon_frame_count, 12):
        x_coord = int(round(horizon_index * strip_width))
        heading_deg = int(round(horizon_index * DELTA_HEADING_DEG))
        cv2.line(
            panorama,
            (x_coord, 0),
            (x_coord, image_height - 1),
            (255, 255, 255),
            thickness=2,
        )
        _draw_panorama_text(
            panorama,
            "%d deg" % heading_deg,
            (x_coord + 4, 28),
        )

    for elevation_deg, elevation_rad in zip(ELEVATION_BAND_DEGS, ELEVATION_BAND_RADS):
        y_coord = _pitch_to_panorama_y(elevation_rad, image_height)
        y_coord = int(round(min(max(y_coord, 28), image_height - 8)))
        _draw_panorama_text(
            panorama,
            "%+d deg pitch" % int(round(elevation_deg)),
            (4, y_coord),
            font_scale=0.7,
            thickness=2,
        )


def build_multi_elevation_panorama(
    horizon_frame_rows,
    add_guides=False,
    heading_rows=None,
    elevation_rows=None,
):
    panorama = _project_elevation_rows_to_pitch_canvas(
        horizon_frame_rows,
        heading_rows=heading_rows,
        elevation_rows=elevation_rows,
    )
    if add_guides:
        _draw_smooth_panorama_guides(panorama, len(horizon_frame_rows[0]))
    return panorama


def _select_viewpoint_marker_candidates(marker_candidates):
    candidates_by_viewpoint = {}
    for candidate in marker_candidates:
        viewpoint_index = int(candidate["viewpoint_index"])
        best_candidate = candidates_by_viewpoint.get(viewpoint_index)
        if best_candidate is None:
            candidates_by_viewpoint[viewpoint_index] = candidate
            continue

        candidate_key = (
            abs(float(candidate["rel_heading"])),
            abs(float(candidate["rel_elevation"])),
            int(candidate["horizon_index"]),
        )
        best_key = (
            abs(float(best_candidate["rel_heading"])),
            abs(float(best_candidate["rel_elevation"])),
            int(best_candidate["horizon_index"]),
        )
        if candidate_key < best_key:
            candidates_by_viewpoint[viewpoint_index] = candidate

    return [
        candidates_by_viewpoint[viewpoint_index]
        for viewpoint_index in sorted(candidates_by_viewpoint)
    ]


def _panorama_marker_origin(
    candidate,
    panorama_width,
    panorama_height,
    strip_width,
    heading_axis=None,
):
    marker_text = str(candidate["viewpoint_index"])
    (text_width, text_height), baseline = _viewpoint_marker_text_size(marker_text)
    if heading_axis is None:
        continuous_index = (
            float(candidate["horizon_index"])
            + float(candidate["rel_heading"]) / DELTA_HEADING_RAD
        )
    else:
        heading_axis_array = np.asarray(heading_axis, dtype=np.float32)
        heading_delta_by_axis = _angle_difference(
            float(candidate["heading"]),
            heading_axis_array,
        )
        horizon_index = int(np.argmin(np.abs(heading_delta_by_axis)))
        continuous_index = (
            float(horizon_index)
            + float(heading_delta_by_axis[horizon_index]) / DELTA_HEADING_RAD
        )
    x_coord = ((continuous_index + 0.5) * float(strip_width)) % float(panorama_width)
    elevation_band_index = int(candidate.get("elevation_band_index", 0))
    absolute_pitch = (
        float(ELEVATION_BAND_RADS[elevation_band_index])
        + float(candidate["rel_elevation"])
    )
    y_coord = _pitch_to_panorama_y(absolute_pitch, panorama_height)
    return _constrain_marker_origin(
        x_coord=x_coord,
        y_coord=y_coord,
        text_width=text_width,
        text_height=text_height,
        baseline=baseline,
        image_width=panorama_width,
        image_height=panorama_height,
    )


def build_annotated_panorama(
    horizon_rgb_frame_rows,
    marker_candidates,
    heading_rows=None,
    elevation_rows=None,
):
    panorama = build_multi_elevation_panorama(
        horizon_rgb_frame_rows,
        add_guides=True,
        heading_rows=heading_rows,
        elevation_rows=elevation_rows,
    )
    strip_width = _panorama_strip_width(horizon_rgb_frame_rows[0][0])
    panorama_height, panorama_width = panorama.shape[:2]

    for candidate in _select_viewpoint_marker_candidates(marker_candidates):
        x_coord, y_coord = _panorama_marker_origin(
            candidate=candidate,
            panorama_width=panorama_width,
            panorama_height=panorama_height,
            strip_width=strip_width,
            heading_axis=heading_rows[0] if heading_rows is not None else None,
        )
        _draw_viewpoint_marker(
            panorama,
            int(candidate["viewpoint_index"]),
            x_coord,
            y_coord,
        )

    return panorama


def _scan_state_to_observation(
    agent_id,
    start_state,
    best_heading_for_vp,
    best_score_for_vp,
    horizon_rgb_frames,
    horizon_headings,
    horizon_heading_rows,
    horizon_elevation_rows,
    viewpoint_marker_candidates,
    frame_visible_viewpoint_indices,
    visible_viewpoints_by_index,
    viewpoint_index_by_vp,
):
    current_viewpoint_id = str(start_state.location.viewpointId)
    current_viewpoint_index = None
    if viewpoint_index_by_vp is not None:
        current_viewpoint_index = viewpoint_index_by_vp.get(current_viewpoint_id)

    return {
        "agent_id": str(agent_id),
        "start_state": start_state,
        "current_viewpoint_id": current_viewpoint_id,
        "current_viewpoint_index": current_viewpoint_index,
        "current_xy": [
            float(start_state.location.x),
            float(start_state.location.y),
        ],
        "visible_viewpoints": [
            visible_viewpoints_by_index[index]
            for index in sorted(visible_viewpoints_by_index)
        ],
        "frame_visible_viewpoint_indices": frame_visible_viewpoint_indices,
        "best_heading_for_vp": dict(best_heading_for_vp),
        "best_score_for_vp": dict(best_score_for_vp),
        "horizon_headings": horizon_headings,
        "horizon_heading_rows": horizon_heading_rows,
        "horizon_elevation_rows": horizon_elevation_rows,
        "panorama_elevation_band_degs": [
            float(value) for value in ELEVATION_BAND_DEGS
        ],
        "raw_panorama": build_multi_elevation_panorama(
            horizon_rgb_frames,
            heading_rows=horizon_heading_rows,
            elevation_rows=horizon_elevation_rows,
        ),
        "annotated_panorama": build_annotated_panorama(
            horizon_rgb_frames,
            viewpoint_marker_candidates,
            heading_rows=horizon_heading_rows,
            elevation_rows=horizon_elevation_rows,
        ),
    }


def horizon_scan_return(sim, agent_id, viewpoint_index_by_vp=None):
    start_state = sim.getState()[0]
    start_elevation = float(start_state.elevation)
    record = {
        "agent_id": str(agent_id),
        "start_state": start_state,
        "best_heading_for_vp": {},
        "best_score_for_vp": defaultdict(lambda: 1e18),
        "horizon_rgb_frames": [],
        "horizon_headings": [],
        "horizon_heading_rows": [],
        "horizon_elevation_rows": [],
        "viewpoint_marker_candidates": [],
        "frame_visible_viewpoint_indices": [],
        "visible_viewpoints_by_index": {},
    }

    for elevation_band_index, elevation_offset in enumerate(ELEVATION_BAND_RADS):
        current_state = sim.getState()[0]
        sim.makeAction(
            [0],
            [0.0],
            [start_elevation + float(elevation_offset) - float(current_state.elevation)],
        )

        row_rgb_frames = []
        row_headings = []
        row_elevations = []
        row_visible_viewpoint_indices = []

        for horizon_index in range(HORIZON_LEN):
            state = sim.getState()[0]
            raw_rgb = simulator_frame_to_rgb(state.rgb)
            _, visible_viewpoints = annotate_rgb_with_viewpoints(
                raw_rgb,
                state.navigableLocations,
                viewpoint_index_by_vp=viewpoint_index_by_vp,
            )

            row_rgb_frames.append(raw_rgb)
            row_headings.append(float(state.heading))
            row_elevations.append(float(state.elevation))
            if elevation_band_index == 0:
                record["horizon_headings"].append(float(state.heading))
            row_visible_viewpoint_indices.append(
                [
                    int(item["viewpoint_index"])
                    for item in visible_viewpoints
                    if item.get("viewpoint_index") is not None
                ]
            )

            for visible_viewpoint in visible_viewpoints:
                record["visible_viewpoints_by_index"][
                    int(visible_viewpoint["viewpoint_index"])
                ] = {
                    "viewpoint_id": str(visible_viewpoint["viewpoint_id"]),
                    "viewpoint_index": int(visible_viewpoint["viewpoint_index"]),
                    "distance": round(float(visible_viewpoint["distance"]), 3),
                    "xy": [
                        float(visible_viewpoint["xy"][0]),
                        float(visible_viewpoint["xy"][1]),
                    ],
                }

            current_heading = float(state.heading)
            for fallback_index, location in enumerate(
                state.navigableLocations[1:],
                start=1,
            ):
                viewpoint_index = _viewpoint_index_for_location(
                    location,
                    fallback_index,
                    viewpoint_index_by_vp,
                )
                record["viewpoint_marker_candidates"].append(
                    _viewpoint_marker_candidate(
                        location=location,
                        viewpoint_index=viewpoint_index,
                        current_heading=current_heading,
                        horizon_index=horizon_index,
                        elevation_band_index=elevation_band_index,
                    )
                )
                score = abs(location.rel_heading) + 0.5 * abs(location.rel_elevation)
                if score < record["best_score_for_vp"][location.viewpointId]:
                    record["best_score_for_vp"][location.viewpointId] = score
                    record["best_heading_for_vp"][location.viewpointId] = current_heading

            if horizon_index != HORIZON_LEN - 1:
                sim.makeAction(
                    [0],
                    [DELTA_HEADING_RAD],
                    [0],
                )

        record["horizon_rgb_frames"].append(row_rgb_frames)
        record["horizon_heading_rows"].append(row_headings)
        record["horizon_elevation_rows"].append(row_elevations)
        record["frame_visible_viewpoint_indices"].append(row_visible_viewpoint_indices)

        sim.makeAction(
            [0],
            [DELTA_HEADING_RAD],
            [0],
        )

    current_state = sim.getState()[0]
    sim.makeAction(
        [0],
        [0.0],
        [start_elevation - float(current_state.elevation)],
    )

    observations = _scan_state_to_observation(
        agent_id=record["agent_id"],
        start_state=record["start_state"],
        best_heading_for_vp=record["best_heading_for_vp"],
        best_score_for_vp=record["best_score_for_vp"],
        horizon_rgb_frames=record["horizon_rgb_frames"],
        horizon_headings=record["horizon_headings"],
        horizon_heading_rows=record["horizon_heading_rows"],
        horizon_elevation_rows=record["horizon_elevation_rows"],
        viewpoint_marker_candidates=record["viewpoint_marker_candidates"],
        frame_visible_viewpoint_indices=record["frame_visible_viewpoint_indices"],
        visible_viewpoints_by_index=record["visible_viewpoints_by_index"],
        viewpoint_index_by_vp=viewpoint_index_by_vp,
    )

    return observations


def horizon_scan_individual_sims_return(sims, agent_ids, viewpoint_index_by_vp=None):
    if len(sims) != len(agent_ids):
        raise ValueError("sims and agent_ids must have the same length.")
    observations = []
    for sim, agent_id in zip(sims, agent_ids):
        scan_return = horizon_scan_return(
            sim=sim,
            agent_id=agent_id,
            viewpoint_index_by_vp=viewpoint_index_by_vp,
        )
        observations.append(scan_return)
    return observations


def compute_rotation(current_heading_deg, target_heading_deg, step_size_deg):
    if step_size_deg <= 0:
        raise ValueError("step_size_deg must be positive")
    current_heading_deg %= 360.0
    target_heading_deg %= 360.0
    clockwise_distance = (target_heading_deg - current_heading_deg) % 360.0
    counterclockwise_distance = (current_heading_deg - target_heading_deg) % 360.0
    if counterclockwise_distance <= clockwise_distance:
        return -1, int(round(counterclockwise_distance / step_size_deg))
    return 1, int(round(clockwise_distance / step_size_deg))


def panorama_center_x_to_heading(target_center_x, horizon_headings):
    panorama_position = float(target_center_x) * len(horizon_headings)
    frame_index = int(math.floor(panorama_position))
    if frame_index == len(horizon_headings):
        frame_index = len(horizon_headings) - 1
    strip_fraction = panorama_position - frame_index
    target_heading = (
        float(horizon_headings[frame_index])
        + (strip_fraction - 0.5) * DELTA_HEADING_RAD
    )
    return target_heading % (2.0 * math.pi)


def execute_individual_first_hops(sims, move_specs, render=True):
    if len(sims) != len(move_specs):
        raise ValueError("sims and move_specs must have the same length.")

    states = [sim.getState()[0] for sim in sims]
    step_plans = []
    for state, spec in zip(states, move_specs):
        direction, step_count = compute_rotation(
            math.degrees(state.heading),
            math.degrees(float(spec["target_heading"])),
            DELTA_HEADING_DEG,
        )
        step_plans.append(
            {
                "direction": direction,
                "step_count": step_count,
                "target_viewpoint_id": str(spec["target_viewpoint_id"]),
            }
        )

    # rotate all sims in sync, then move towards target viewpoint in sync
    max_step_count = max(plan["step_count"] for plan in step_plans)
    for step_index in range(max_step_count):
        for sim, plan in zip(sims, step_plans):
            heading = (
                plan["direction"] * DELTA_HEADING_RAD
                if step_index < plan["step_count"]
                else 0.0
            )
            sim.makeAction([0], [heading], [0.0])
        if render and PAUSE_TIME > 0.0:
            time.sleep(0.3 * PAUSE_TIME)
        if render:
            render_sim_state(
                [sim.getState()[0] for sim in sims],
                viewpoint_index_by_vp=viewpoint_index_by_vp_label,
            )

    # Update the states after rotation
    rotated_states = [sim.getState()[0] for sim in sims]
    if render and PAUSE_TIME > 0.0:
        time.sleep(10 * PAUSE_TIME)
    for sim, state, plan in zip(sims, rotated_states, step_plans):
        target_viewpoint_id = plan["target_viewpoint_id"]
        location_index = [
            index
            for index, location in enumerate(state.navigableLocations)
            if str(location.viewpointId) == target_viewpoint_id
        ][0]
        sim.makeAction([location_index], [0.0], [0.0])
    if render:
        render_sim_state(
            [sim.getState()[0] for sim in sims],
            viewpoint_index_by_vp=viewpoint_index_by_vp_label,
        )
