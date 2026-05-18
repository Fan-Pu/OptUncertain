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
            }
        )

    return annotated_rgb, visible_viewpoints


def render_sim_state(state_list, viewpoint_index_by_vp=None):
    for batch_index, state in enumerate(state_list):
        rgb_image, _ = annotate_rgb_with_viewpoints(
            state.rgb,
            state.navigableLocations,
            viewpoint_index_by_vp=viewpoint_index_by_vp,
        )
        cv2.imshow("Agent %s" % batch_index, rgb_image)
    cv2.waitKey(1)


def build_truncated_panorama(horizon_frames):
    strip_width = int(round(horizon_frames[0].shape[1] * DELTA_HEADING_RAD / HFOV))
    center_x = horizon_frames[0].shape[1] // 2
    start_x = center_x - strip_width // 2
    end_x = start_x + strip_width
    strips = [frame[:, start_x:end_x].copy() for frame in horizon_frames]
    return np.concatenate(strips, axis=1)


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
        "annotated_panorama": build_truncated_panorama(horizon_mllm_frames),
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
        raw_rgb = np.array(state.rgb, copy=True)
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


def execute_individual_rotations(sims, target_headings, PAUSE_TIME=0.05):
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
        )


def execute_batched_first_hops(sim, move_specs, PAUSE_TIME=0.0):
    states = list(sim.getState())
    step_plans = []
    for batch_index, spec in enumerate(move_specs):
        direction, step_count = compute_rotation(
            math.degrees(states[batch_index].heading),
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

    max_step_count = max(plan["step_count"] for plan in step_plans)
    for step_index in range(max_step_count):
        sim.makeAction(
            [0 for _ in step_plans],
            [
                (
                    plan["direction"] * DELTA_HEADING_RAD
                    if step_index < plan["step_count"]
                    else 0.0
                )
                for plan in step_plans
            ],
            [0 for _ in step_plans],
        )
        if PAUSE_TIME > 0.0:
            time.sleep(PAUSE_TIME)

    rotated_states = list(sim.getState())
    move_actions = []
    for batch_index, state in enumerate(rotated_states):
        target_viewpoint_id = step_plans[batch_index]["target_viewpoint_id"]
        location_index = [
            index
            for index, location in enumerate(state.navigableLocations)
            if str(location.viewpointId) == target_viewpoint_id
        ][0]
        move_actions.append(location_index)

    sim.makeAction(
        move_actions,
        [0.0 for _ in step_plans],
        [0.0 for _ in step_plans],
    )
    if PAUSE_TIME > 0.0:
        time.sleep(PAUSE_TIME)


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


def explore_world(sim, location=0, heading=0, elevation=0):
    while True:
        sim.makeAction([location], [heading], [elevation])
        location = 0
        heading = 0
        elevation = 0

        state = sim.getState()[0]
        rgb = np.array(state.rgb, copy=False)
        for index, location in enumerate(state.navigableLocations[1:], start=1):
            font_scale = 3.0 / location.rel_distance
            x_coord = int(WIDTH / 2 + location.rel_heading / HFOV * WIDTH)
            y_coord = int(HEIGHT / 2 - location.rel_elevation / VFOV * HEIGHT)
            cv2.putText(
                rgb,
                str(index),
                (x_coord, y_coord),
                cv2.FONT_HERSHEY_SIMPLEX,
                font_scale,
                TEXT_COLOR,
                thickness=3,
            )
        cv2.imshow("Agent 0", rgb)
        key_code = cv2.waitKey(1)
        if key_code == -1:
            continue
        key_code &= 255
        if key_code == ord("q"):
            break
        if ord("1") <= key_code <= ord("9"):
            location = key_code - ord("0")
            if location >= len(state.navigableLocations):
                location = 0
        elif key_code == 81 or key_code == ord("a"):
            heading = -DELTA_HEADING_RAD
        elif key_code == 82 or key_code == ord("w"):
            elevation = DELTA_HEADING_RAD
        elif key_code == 83 or key_code == ord("d"):
            heading = DELTA_HEADING_RAD
        elif key_code == 84 or key_code == ord("s"):
            elevation = -DELTA_HEADING_RAD
