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
HFOV = VFOV * WIDTH / HEIGHT
TEXT_COLOR = [230, 40, 40]
MP_ROOT = "/root/mount/Matterport3DSimulator"
HORIZON_LEN = 48 * 4
DELTA_HEADING_DEG = 360 / HORIZON_LEN
DELTA_HEADING_RAD = math.radians(DELTA_HEADING_DEG)
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
    sim.setDepthEnabled(True)
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


def annotate_rgb_with_viewpoints(rgb, locations, viewpoint_index_by_vp=None):
    annotated_rgb = np.array(rgb, copy=True)
    image_height, image_width = annotated_rgb.shape[:2]
    visible_viewpoints = []

    for fallback_index, location in enumerate(locations[1:], start=1):
        viewpoint_index = fallback_index
        if (
            viewpoint_index_by_vp is not None
            and location.viewpointId in viewpoint_index_by_vp
        ):
            viewpoint_index = int(viewpoint_index_by_vp[location.viewpointId])

        x_coord = int(image_width / 2 + location.rel_heading / HFOV * image_width)
        y_coord = int(image_height / 2 - location.rel_elevation / VFOV * image_height)
        marker_text = str(viewpoint_index)
        font_scale = 2.0
        thickness = 3
        (text_width, text_height), baseline = cv2.getTextSize(
            marker_text,
            cv2.FONT_HERSHEY_SIMPLEX,
            font_scale,
            thickness,
        )
        if (
            x_coord < 0
            or x_coord + text_width > image_width
            or y_coord - text_height < 0
            or y_coord + baseline > image_height
        ):
            continue

        cv2.putText(
            annotated_rgb,
            marker_text,
            (x_coord, y_coord),
            cv2.FONT_HERSHEY_SIMPLEX,
            font_scale,
            TEXT_COLOR,
            thickness=thickness,
        )
        visible_viewpoints.append(
            {
                "viewpoint_id": str(location.viewpointId),
                "viewpoint_index": int(viewpoint_index),
                "distance": float(location.rel_distance),
                "xy": [float(location.x), float(location.y)],
            }
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


def build_truncated_panorama(horizon_frames, add_guides=False):
    strip_width = int(round(horizon_frames[0].shape[1] * DELTA_HEADING_RAD / HFOV))
    center_x = horizon_frames[0].shape[1] // 2
    start_x = center_x - strip_width // 2
    end_x = start_x + strip_width

    strips = [frame[:, start_x:end_x].copy() for frame in horizon_frames]
    panorama = np.concatenate(strips, axis=1)

    if add_guides:
        image_height = panorama.shape[0]

        for horizon_index in range(0, len(horizon_frames), 12):
            x_coord = int(horizon_index * strip_width)
            heading_deg = int(round(horizon_index * DELTA_HEADING_DEG))

            cv2.line(
                panorama,
                (x_coord, 0),
                (x_coord, image_height - 1),
                (255, 255, 255),
                thickness=2,
            )

            cv2.putText(
                panorama,
                "%d deg" % heading_deg,
                (x_coord + 4, 28),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (255, 255, 255),
                thickness=2,
            )

    return panorama


def _scan_state_to_observation(
    agent_id,
    start_state,
    best_heading_for_vp,
    best_score_for_vp,
    horizon_rgb_frames,
    horizon_mllm_frames,
    horizon_headings,
    horizon_depths,
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
        "horizon_rgb_frames": horizon_rgb_frames,
        "horizon_mllm_frames": horizon_mllm_frames,
        "horizon_headings": horizon_headings,
        "horizon_depths": horizon_depths,
        "raw_panorama": build_truncated_panorama(horizon_rgb_frames),
        "depth_panorama": build_truncated_panorama(horizon_depths),
        "annotated_panorama": build_truncated_panorama(
            horizon_mllm_frames,
            add_guides=True,
        ),
    }


def horizon_scan_return(sim, agent_id, viewpoint_index_by_vp=None):
    start_state = sim.getState()[0]
    record = {
        "agent_id": str(agent_id),
        "start_state": start_state,
        "best_heading_for_vp": {},
        "best_score_for_vp": defaultdict(lambda: 1e18),
        "horizon_rgb_frames": [],
        "horizon_mllm_frames": [],
        "horizon_headings": [],
        "horizon_depths": [],
        "frame_visible_viewpoint_indices": [],
        "visible_viewpoints_by_index": {},
    }

    for horizon_index in range(HORIZON_LEN):
        state = sim.getState()[0]
        raw_rgb = simulator_frame_to_rgb(state.rgb)
        annotated_rgb, visible_viewpoints = annotate_rgb_with_viewpoints(
            raw_rgb,
            state.navigableLocations,
            viewpoint_index_by_vp=viewpoint_index_by_vp,
        )

        record["horizon_rgb_frames"].append(raw_rgb)
        record["horizon_mllm_frames"].append(annotated_rgb)
        record["horizon_headings"].append(float(state.heading))
        record["horizon_depths"].append(np.array(state.depth, copy=True))
        record["frame_visible_viewpoint_indices"].append(
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
        for location in state.navigableLocations[1:]:
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

    sim.makeAction(
        [0],
        [DELTA_HEADING_RAD],
        [0],
    )

    observations = _scan_state_to_observation(
        agent_id=record["agent_id"],
        start_state=record["start_state"],
        best_heading_for_vp=record["best_heading_for_vp"],
        best_score_for_vp=record["best_score_for_vp"],
        horizon_rgb_frames=record["horizon_rgb_frames"],
        horizon_mllm_frames=record["horizon_mllm_frames"],
        horizon_headings=record["horizon_headings"],
        horizon_depths=record["horizon_depths"],
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


def execute_individual_rotations(
    sims,
    target_headings,
    PAUSE_TIME=0.05,
    window_names=None,
    notifications=None,
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
        if PAUSE_TIME > 0.0:
            time.sleep(PAUSE_TIME)
        render_sim_state(
            [sim.getState()[0] for sim in sims],
            viewpoint_index_by_vp=viewpoint_index_by_vp_label,
            window_names=window_names,
        )

    if notifications is not None:
        render_sim_state(
            [sim.getState()[0] for sim in sims],
            viewpoint_index_by_vp=viewpoint_index_by_vp_label,
            window_names=window_names,
            notifications=notifications,
        )
        if PAUSE_TIME > 0.0:
            time.sleep(2)


def execute_individual_first_hops(sims, move_specs, PAUSE_TIME=0.05):
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
        if PAUSE_TIME > 0.0:
            time.sleep(0.3 * PAUSE_TIME)
        render_sim_state(
            [sim.getState()[0] for sim in sims],
            viewpoint_index_by_vp=viewpoint_index_by_vp_label,
        )

    # Update the states after rotation
    rotated_states = [sim.getState()[0] for sim in sims]
    if PAUSE_TIME > 0.0:
        time.sleep(10 * PAUSE_TIME)
    for sim, state, plan in zip(sims, rotated_states, step_plans):
        target_viewpoint_id = plan["target_viewpoint_id"]
        location_index = [
            index
            for index, location in enumerate(state.navigableLocations)
            if str(location.viewpointId) == target_viewpoint_id
        ][0]
        sim.makeAction([location_index], [0.0], [0.0])
    render_sim_state(
        [sim.getState()[0] for sim in sims],
        viewpoint_index_by_vp=viewpoint_index_by_vp_label,
    )
