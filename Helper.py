from doctest import debug
import json
import os
from pydoc import Helper
from unittest import result
import debugpy
import numpy as np
import cv2
import math
import MatterSim
from collections import defaultdict
import time

WIDTH = 800
HEIGHT = 600
VFOV = math.radians(
    60
)  # Vertical field of view of the camera in radians (Matterport default is 60 degrees)
HFOV = (
    VFOV * WIDTH / HEIGHT
)  # Horizontal field of view in radians, computed from vertical FOV and aspect ratio
TEXT_COLOR = [230, 40, 40]
MP_ROOT = "/root/mount/Matterport3DSimulator"  # repo root inside container
HORIZON_LEN = 48
# Each horizon scan rotates right by this many degrees (360 / HORIZON_LEN) for the next view, so smaller values mean finer-grained scans but more time spent rotating and rendering.
DELTA_HEADING_DEG = 360 / HORIZON_LEN
DELTA_HEADING_RAD = math.radians(DELTA_HEADING_DEG)
pause_time = 0.15  # smooth rendering
decision_pause = 1.5

# for node type definition in the hypothesis graph
TYPE_REGION = 0
TYPE_VP = 1

viewpoint_index_by_vp_label = (
    {}
)  # key: viewpoint_id (str), value: stable integer index for MLLM marker labels
viewpoint_vp_label_by_index = (
    {}
)  # key: stable integer index for MLLM marker labels, value: viewpoint_id (str)


def init_render():
    cv2.namedWindow("Python RGB")
    cv2.namedWindow("Python Depth")

    sim = MatterSim.Simulator()
    sim.setCameraResolution(WIDTH, HEIGHT)
    sim.setCameraVFOV(VFOV)
    sim.setDepthEnabled(True)
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


def build_viewpoint_index(scan_id):
    """Create a stable scan-level integer marker for each viewpoint id."""
    for idx, vp_id in enumerate(get_viewpoints(scan_id)):
        viewpoint_index_by_vp_label[vp_id] = idx
        viewpoint_vp_label_by_index[idx] = vp_id


def annotate_rgb_with_viewpoints(rgb, locations, viewpoint_index_by_vp=None):
    """
    Draw stable `vp-N` markers for all visible navigable viewpoints in one frame.

    Returns:
        annotated_rgb: RGB copy with overlayed viewpoint markers.
        visible_viewpoints: list of dicts with viewpoint ids and their stable indices.
    """
    annotated_rgb = np.array(rgb, copy=True)
    image_height, image_width = annotated_rgb.shape[:2]
    visible_viewpoints = []

    for idx, loc in enumerate(locations[1:]):
        marker_index = None
        if viewpoint_index_by_vp is not None:
            marker_index = viewpoint_index_by_vp.get(loc.viewpointId)
        if marker_index is None:
            marker_index = idx + 1

        font_scale = 2.0
        thickness = 3

        x = int(image_width / 2 + loc.rel_heading / HFOV * image_width)
        y = int(image_height / 2 - loc.rel_elevation / VFOV * image_height)
        marker_text = f"{int(marker_index)}"
        (text_width, text_height), baseline = cv2.getTextSize(
            marker_text,
            cv2.FONT_HERSHEY_SIMPLEX,
            font_scale,
            thickness,
        )

        # Skip labels that would be clipped by the image boundary.
        if (
            x < 0
            or x + text_width > image_width
            or y - text_height < 0
            or y + baseline > image_height
        ):
            continue

        cv2.putText(
            annotated_rgb,
            marker_text,
            (x, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            font_scale,
            TEXT_COLOR,
            thickness=thickness,
        )
        visible_viewpoints.append(
            {
                "viewpoint_id": str(loc.viewpointId),
                "viewpoint_index": int(marker_index),
                "distance": float(loc.rel_distance),
            }
        )

    return annotated_rgb, visible_viewpoints


def render_sim_state(state, viewpoint_index_by_vp=None):
    locations = state.navigableLocations
    rgb, _ = annotate_rgb_with_viewpoints(
        state.rgb,
        locations,
        viewpoint_index_by_vp=viewpoint_index_by_vp,
    )
    cv2.imshow("Python RGB", rgb)

    depth = np.array(state.depth, copy=False)
    cv2.imshow("Python Depth", depth)
    cv2.waitKey(1)


def build_truncated_panorama(horizon_frames):
    """
    Convert a full set of overlapping horizon frames into a stitched 360 panorama
    by keeping only the central strip that corresponds to one scan step.
    """
    strip_width = int(round(horizon_frames[0].shape[1] * DELTA_HEADING_RAD / HFOV))
    center_x = horizon_frames[0].shape[1] // 2
    start_x = center_x - strip_width // 2
    end_x = start_x + strip_width
    strips = [frame[:, start_x:end_x].copy() for frame in horizon_frames]
    return np.concatenate(strips, axis=1)


def horizon_scan_return(sim, viewpoint_index_by_vp=None):
    """
    Perform a full 360 horizon scan at the current viewpoint and return to the
    exact starting heading at the end.

    This function is intentionally "perception-only": it does NOT perform any
    target detection. It only collects:
      1) the locally observable moveable neighbors (from navigableLocations)
      2) a list of raw RGB frames for the full horizon scan
      3) a list of annotated RGB frames with visible `vp-N` markers
      4) stitched raw and annotated panoramas built from the scan
      5) the heading (radians) associated with each frame

    Args:
        sim: initialized MatterSim.Simulator with an active episode.

    Returns:
        best_heading_for_vp: dict mapping each reachable neighboring viewpoint ID
            to the best heading (radians) that faces it during the horizon scan.
        start_state: the initial simulator state before performing any rotations.
        horizon_rgb_frames: list of raw RGB frames (numpy arrays) captured during the scan.
        horizon_mllm_frames: list of RGB frames with stable viewpoint markers.
        horizon_rgb_panorama: raw stitched panorama built from horizon_rgb_frames.
        horizon_mllm_panorama: annotated stitched panorama built from horizon_mllm_frames.
        horizon_headings: list of headings (radians) aligned with horizon_rgb_frames.
        horizon_depths: list of depth maps (numpy arrays) captured during the scan.
        observation_context: dict containing: current viewpoint id/index, list of visible viewpoints with their ids and indices, and list of visible viewpoint indices for each frame in the horizon scan.
    """
    start_state = sim.getState()[0]

    best_heading_for_vp = {}
    best_score_for_vp = defaultdict(lambda: 1e18)

    horizon_rgb_frames = []
    horizon_mllm_frames = []
    horizon_headings = []
    horizon_depths = []
    frame_visible_viewpoint_indices = []
    visible_viewpoints_by_index = {}

    for horizon_idx in range(HORIZON_LEN):
        state = sim.getState()[0]
        locations = state.navigableLocations
        cur_heading = float(state.heading)

        raw_rgb = np.array(state.rgb, copy=True)
        annotated_rgb, visible_viewpoints = annotate_rgb_with_viewpoints(
            raw_rgb,
            locations,
            viewpoint_index_by_vp=viewpoint_index_by_vp,
        )

        horizon_rgb_frames.append(raw_rgb)
        horizon_mllm_frames.append(annotated_rgb)
        horizon_headings.append(cur_heading)
        horizon_depths.append(np.array(state.depth, copy=True))
        frame_visible_viewpoint_indices.append(
            [
                int(item["viewpoint_index"])
                for item in visible_viewpoints
                if item.get("viewpoint_index") is not None
            ]
        )

        for item in visible_viewpoints:
            visible_viewpoints_by_index[int(item["viewpoint_index"])] = {
                "viewpoint_id": str(item["viewpoint_id"]),
                "viewpoint_index": int(item["viewpoint_index"]),
                "distance": round(float(item["distance"]), 3),
            }

        # record best "in-front" heading for each neighbor
        for loc in locations[1:]:
            score = abs(loc.rel_heading) + 0.5 * abs(loc.rel_elevation)
            if score < best_score_for_vp[loc.viewpointId]:
                best_score_for_vp[loc.viewpointId] = score
                best_heading_for_vp[loc.viewpointId] = cur_heading

        # rotate right for next view (except after last)
        if horizon_idx != HORIZON_LEN - 1:
            sim.makeAction([0], [DELTA_HEADING_RAD], [0])

    # rotate back to the exact starting heading
    sim.makeAction([0], [DELTA_HEADING_RAD], [0])

    current_vp_id = str(start_state.location.viewpointId)
    current_viewpoint_index = None
    if viewpoint_index_by_vp is not None:
        current_viewpoint_index = viewpoint_index_by_vp.get(current_vp_id)

    observation_context = {
        "current_viewpoint_id": current_vp_id,
        "current_viewpoint_index": current_viewpoint_index,
        "visible_viewpoints": [
            visible_viewpoints_by_index[idx]
            for idx in sorted(visible_viewpoints_by_index.keys())
        ],
        "frame_visible_viewpoint_indices": frame_visible_viewpoint_indices,
    }
    horizon_rgb_panorama = build_truncated_panorama(horizon_rgb_frames)
    horizon_mllm_panorama = build_truncated_panorama(horizon_mllm_frames)

    return (
        best_heading_for_vp,
        start_state,
        horizon_rgb_frames,
        horizon_mllm_frames,
        horizon_rgb_panorama,
        horizon_mllm_panorama,
        horizon_headings,
        horizon_depths,
        observation_context,
    )


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

    # move to the target viewpoint (after rotation, it should be in the current navigableLocations)
    if target_vp_id is not None:
        locations = current_state.navigableLocations
        location_id = [
            i for i, x in enumerate(locations) if x.viewpointId == target_vp_id
        ][0]
        time.sleep(decision_pause)
        sim.makeAction([location_id], [0], [0])
        render_sim_state(sim.getState()[0])


def explore_world(sim, location=0, heading=0, elevation=0):
    """Explore the world by using keyboard input to move around and look for objects. This is a manual mode for testing and debugging."""

    while True:
        sim.makeAction([location], [heading], [elevation])
        location = 0
        heading = 0
        elevation = 0

        state = sim.getState()[0]
        locations = state.navigableLocations
        rgb = np.array(state.rgb, copy=False)
        print(f"current vp: {state.location.viewpointId}")
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

        depth = np.array(state.depth, copy=False)
        cv2.imshow("Python Depth", depth)
        k = cv2.waitKey(1)
        if k == -1:
            continue
        else:
            k = k & 255
        if k == ord("q"):
            break
        elif ord("1") <= k <= ord("9"):
            location = k - ord("0")
            if location >= len(locations):
                location = 0
        elif k == 81 or k == ord("a"):
            heading = -DELTA_HEADING_RAD
        elif k == 82 or k == ord("w"):
            elevation = DELTA_HEADING_RAD
        elif k == 83 or k == ord("d"):
            heading = DELTA_HEADING_RAD
        elif k == 84 or k == ord("s"):
            elevation = -DELTA_HEADING_RAD


def target_detection(
    tgt: dict,
    target_object: str,
    target_heading,
    target_rgb_image,
    target_depth_image,
    distance_threshold_m,
    sim,
):
    """Process the MLLM output for target detection and distance estimation, and decide whether to terminate or continue exploring."""
    if not bool(tgt["found"]):
        return False

    target_strip_index = int(tgt["strip_index"])
    print(
        f"Target '{target_object}' detected by MLLM in panorama strip "
        f"{target_strip_index}."
    )
    depth_start_time = time.perf_counter()
    distance_out = {"distance_m": 2.375}
    # distance_out = mllm.estimate_target_distance(
    #     rgb_image=target_rgb_image,
    #     depth_image=target_depth_image,
    #     target_object=target_object,
    # )
    depth_runtime = time.perf_counter() - depth_start_time
    print(f"[MLLM distance] runtime: {depth_runtime:.2f} seconds")

    distance_m = distance_out.get("distance_m")

    if distance_m is not None:
        print(
            f"Target '{target_object}' distance estimate: {distance_m:.2f} m "
            f"(threshold: {distance_threshold_m:.2f} m)."
        )
        if distance_m <= distance_threshold_m:
            rotate_to_target_heading_mov2vp(sim, target_heading, None)
            render_sim_state(
                sim.getState()[0],
                viewpoint_index_by_vp=viewpoint_index_by_vp_label,
            )
            debugpy.breakpoint()
            return True
        print(
            f"[CONTINUE] Target detected but distance {distance_m:.2f} m exceeds "
            f"threshold {distance_threshold_m:.2f} m."
        )
        return False

    print(
        f"[CONTINUE] Target '{target_object}' detected, but distance could not be estimated."
    )
    return False
