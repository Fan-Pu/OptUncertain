import json
import os
import numpy as np
import cv2
import math
import MatterSim
from collections import defaultdict

WIDTH = 800
HEIGHT = 600
VFOV = math.radians(60)
HFOV = VFOV * WIDTH / HEIGHT
TEXT_COLOR = [230, 40, 40]
MP_ROOT = "/root/mount/Matterport3DSimulator"  # repo root inside container
depth_enabled = False
HORIZON_START = 12  # viewIndex 12..23 is horizon band
HORIZON_LEN = 12


def init_render():
    cv2.namedWindow("Python RGB")
    if depth_enabled:
        cv2.namedWindow("Python Depth")

    sim = MatterSim.Simulator()
    sim.setCameraResolution(WIDTH, HEIGHT)
    sim.setCameraVFOV(VFOV)
    sim.setDepthEnabled(depth_enabled)
    sim.setDiscretizedViewingAngles(True)

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
            str(idx + 1),
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

    # Define horizon_idx=0 as the starting heading.
    for horizon_idx in range(HORIZON_LEN):
        state = sim.getState()[0]
        locations = state.navigableLocations

        # record best "in-front" heading for each neighbor
        for loc in locations[1:]:
            score = abs(loc.rel_heading) + 0.5 * abs(loc.rel_elevation)
            if score < best_score_for_vp[loc.viewpointId]:
                best_score_for_vp[loc.viewpointId] = score
                best_heading_for_vp[loc.viewpointId] = horizon_idx

        # rotate right by one discrete step for next view (except after last)
        if horizon_idx != HORIZON_LEN - 1:
            sim.makeAction([0], [1], [0])

    # rotate back to the exact starting viewIndex
    sim.makeAction([0], [1], [0])

    # sanity check (optional)
    final_view_index = sim.getState()[0].viewIndex
    if final_view_index != start_view_index:
        print(
            f"[WARN] viewIndex mismatch: start={start_view_index}, end={final_view_index}"
        )

    return best_heading_for_vp, start_state
