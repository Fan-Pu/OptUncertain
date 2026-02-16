import json
import os
import debugpy
import numpy as np
import cv2
import math
import MatterSim
from collections import defaultdict
import time

WIDTH = 800
HEIGHT = 600
VFOV = math.radians(60)
HFOV = VFOV * WIDTH / HEIGHT
TEXT_COLOR = [230, 40, 40]
MP_ROOT = "/root/mount/Matterport3DSimulator"  # repo root inside container
depth_enabled = False
HORIZON_LEN = 48
DELTA_HEADING_DEG = 360 / HORIZON_LEN
DELTA_HEADING_RAD = math.radians(DELTA_HEADING_DEG)
pause_time = 0.15  # smooth rendering
decision_pause = 1.5


def init_render():
    cv2.namedWindow("Python RGB")
    if depth_enabled:
        cv2.namedWindow("Python Depth")

    sim = MatterSim.Simulator()
    sim.setCameraResolution(WIDTH, HEIGHT)
    sim.setCameraVFOV(VFOV)
    sim.setDepthEnabled(depth_enabled)
    sim.setDiscretizedViewingAngles(False)

    sim.setDatasetPath(os.path.join(MP_ROOT, "data/v1/scans"))
    sim.setNavGraphPath(os.path.join(MP_ROOT, "connectivity"))
    sim.setPreloadingEnabled(True)
    sim.setBatchSize(1)
    sim.setCacheSize(
        2
    )  # cacheSize 200 uses about 1.2GB of GPU memory for caching pano textures

    return sim


def get_viewpoints(scan_id):
    conn_file = os.path.join(
        "/root/mount/Matterport3DSimulator/connectivity", f"{scan_id}_connectivity.json"
    )

    with open(conn_file, "r") as f:
        data = json.load(f)

    # Only include included viewpoints
    vp_ids = [item["image_id"] for item in data if item["included"]]

    return vp_ids


def render_sim_state(state):
    locations = state.navigableLocations
    rgb = np.array(state.rgb, copy=False)
    for idx, loc in enumerate(locations[1:]):
        # Draw actions on the screen
        fontScale = 3.0 / loc.rel_distance
        x = int(WIDTH / 2 + loc.rel_heading / HFOV * WIDTH)
        y = int(HEIGHT / 2 - loc.rel_elevation / VFOV * HEIGHT)
        cv2.putText(
            rgb,
            str(loc.ix),
            (x, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            fontScale,
            TEXT_COLOR,
            thickness=3,
        )
    cv2.imshow("Python RGB", rgb)

    if depth_enabled:
        depth = np.array(state.depth, copy=False)
        cv2.imshow("Python Depth", depth)
    cv2.waitKey(1)


def horizon_scan_return(sim):
    """
    Full 360 horizon scan (12 discrete headings) at current viewpoint,
    but returns to the EXACT starting viewIndex at the end.

    Returns:
      best_heading_for_vp: dict vp_id -> horizon_idx (0..11), where 0 means "starting heading"
      start_state: the state at the beginning (for debugging)
    """
    start_state = sim.getState()[0]
    start_view_index = start_state.viewIndex  # absolute 0..35 in discretized mode

    best_heading_for_vp = {}
    best_score_for_vp = defaultdict(lambda: 1e18)

    for horizon_idx in range(HORIZON_LEN):
        state = sim.getState()[0]
        locations = state.navigableLocations
        cur_heading = state.heading

        # record best "in-front" heading for each neighbor
        for loc in locations[1:]:
            score = abs(loc.rel_heading) + 0.5 * abs(loc.rel_elevation)
            if score < best_score_for_vp[loc.viewpointId]:
                best_score_for_vp[loc.viewpointId] = score
                best_heading_for_vp[loc.viewpointId] = cur_heading

        # rotate right by one discrete step for next view (except after last)
        if horizon_idx != HORIZON_LEN - 1:
            sim.makeAction([0], [DELTA_HEADING_RAD], [0])

    # rotate back to the exact starting viewIndex
    sim.makeAction([0], [DELTA_HEADING_RAD], [0])

    # sanity check (optional)
    final_view_index = sim.getState()[0].viewIndex
    if final_view_index != start_view_index:
        print(
            f"[WARN] viewIndex mismatch: start={start_view_index}, end={final_view_index}"
        )

    return best_heading_for_vp, start_state


def compute_rotation(current_heading_deg, target_heading_deg, step_size_deg):
    """
    Returns:
        direction: -1 (counterclockwise) or 1 (clockwise)
        steps: integer number of discrete rotation steps
    """

    if step_size_deg <= 0:
        raise ValueError("step_size_deg must be positive")

    # Normalize to [0, 360)
    current_heading_deg %= 360.0
    target_heading_deg %= 360.0

    # Angular distance
    clockwise_distance = (target_heading_deg - current_heading_deg) % 360.0
    counterclockwise_distance = (current_heading_deg - target_heading_deg) % 360.0

    # Choose shortest direction
    if counterclockwise_distance <= clockwise_distance:
        direction = -1  # left / counterclockwise
        distance = counterclockwise_distance
    else:
        direction = 1  # right / clockwise
        distance = clockwise_distance

    # Number of discrete steps (closest integer)
    steps = int(round(distance / step_size_deg))

    return direction, steps


def rotate_to_target_heading_mov2vp(sim, selected_heading, target_vp_id):
    """
    smoothly move to the selected heading and move to the target vp with rendering
    """
    start_state = sim.getState()[0]
    start_heading = start_state.heading
    direction, steps = compute_rotation(
        math.degrees(start_heading),
        math.degrees(selected_heading),
        DELTA_HEADING_DEG,
    )

    for i in range(steps):
        sim.makeAction([0], [direction * DELTA_HEADING_RAD], [0])
        state = sim.getState()[0]  # current state
        render_sim_state(state)
        time.sleep(pause_time)

    current_state = sim.getState()[0]
    current_heading = current_state.heading
    print(f"Selected_heading: {math.degrees(selected_heading):.2f} degrees")
    print(f"Current heading: {math.degrees(current_heading):.2f} degrees")

    locations = current_state.navigableLocations
    location_id = [i for i, x in enumerate(locations) if x.viewpointId == target_vp_id][
        0
    ]
    # move to the target viewpoint (after rotation, it should be in the current navigableLocations)
    time.sleep(decision_pause)
    sim.makeAction([location_id], [0], [0])
    render_sim_state(sim.getState()[0])
