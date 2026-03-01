import json
import os
import debugpy
import numpy as np
import cv2
import math
import MatterSim
from collections import defaultdict
import time

from semantic_persistence.utils import cosine_sim

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
DELTA_HEADING_DEG = 360 / HORIZON_LEN
DELTA_HEADING_RAD = math.radians(DELTA_HEADING_DEG)
pause_time = 0.15  # smooth rendering
decision_pause = 1.5


def init_render():
    cv2.namedWindow("Python RGB")
    cv2.namedWindow("Python Depth")
    cv2.namedWindow("MLLM RGB")

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

    depth = np.array(state.depth, copy=False)
    cv2.imshow("Python Depth", depth)
    cv2.waitKey(1)


def horizon_scan_return(
    sim,
    goal_text=None,
    text_embedder=None,
    image_embedder=None,
    similarity_threshold=0.25,
    distance_threshold=1.5,
    owl_detector=None,
):
    """
    Perform a full 360 horizon scan at the current viewpoint, returning to the exact starting viewIndex at the end.

    Args:
        sim: initialized MatterSim.Simulator with an active episode.
        goal_text: target text description (optional).
        text_embedder: CLIPTextEmbedder instance (optional).
        image_embedder: CLIPImageEmbedder instance (optional).
        similarity_threshold: CLIP similarity threshold to consider object as found.
        distance_threshold: maximum distance in meters to consider target reachable.

    Returns:
        best_heading_for_vp: dict mapping each reachable neighboring viewpoint ID to the best heading (in radians) that faces it during the horizon scan.
        start_state: the initial simulator state before performing any rotations.
        target_found: bool, True if target object found and within distance threshold.
        best_heading: float, the heading (in radians) where target was best observed (or None).
        best_distance: float, the minimum distance at which target was found (or None).
        horizon_images: list of RGB images (as numpy arrays) captured during the horizon scan, in order of increasing heading.
    """
    start_state = sim.getState()[0]

    best_heading_for_vp = (
        {}
    )  # key: neighboring vp_id, value: best heading in radians to face that vp during the horizon scan
    # record the best (lowest) score for each neighboring vp across the horizon scan, where score reflects how well the neighbor is centered in the view (lower is better)
    best_score_for_vp = defaultdict(
        lambda: 1e18
    )  # key: neighboring vp_id, value: best score (lower is better)
    heading_info_list_contain_target = (
        []
    )  # list of (heading, rgb, box, distance) for each heading where target is detected

    target_found = False

    enable_target_check = (
        goal_text is not None
        and text_embedder is not None
        and image_embedder is not None
    )

    horizon_images = []  # for MLLM visual context (full 360 horizontal scan)

    # horizon scan loop
    for horizon_idx in range(HORIZON_LEN):
        state = sim.getState()[0]
        locations = state.navigableLocations
        cur_heading = state.heading
        horizon_images.append(np.array(state.rgb, copy=False))

        # record best "in-front" heading for each neighbor
        for loc in locations[1:]:
            # score reflects how well the neighbor is centered in the view (lower is better)
            score = abs(loc.rel_heading) + 0.5 * abs(loc.rel_elevation)
            if score < best_score_for_vp[loc.viewpointId]:
                best_score_for_vp[loc.viewpointId] = score
                best_heading_for_vp[loc.viewpointId] = cur_heading

        # target check
        if enable_target_check:
            rgb = np.array(state.rgb, copy=False)  # RGB
            depth = np.array(state.depth, copy=False)
            target_found, dist_m, box, _ = owl_detector.detect_and_distance(
                rgb,
                depth,
                text_query=goal_text,
                score_thresh=similarity_threshold,
                dist_thresh_m=distance_threshold,
                percentile=10,
            )

            if target_found:
                print(
                    f"✓ Target found at heading {math.degrees(cur_heading):.1f}°, distance {dist_m:.2f}m, score {score:.3f}"
                )
                heading_info_list_contain_target.append((cur_heading, rgb, box, dist_m))

        # rotate right by one discrete step for next view (except after last)
        if horizon_idx != HORIZON_LEN - 1:
            sim.makeAction([0], [DELTA_HEADING_RAD], [0])

        if enable_target_check:
            time.sleep(pause_time / 4)

    # rotate back to the exact starting viewIndex
    sim.makeAction([0], [DELTA_HEADING_RAD], [0])

    # determine the best heading where the target was observed (if any) based on the lowest distance (most reachable)
    if heading_info_list_contain_target:
        target_heading, _, _, target_distance = min(
            heading_info_list_contain_target, key=lambda x: x[3]
        )
    else:
        target_heading = None
        target_distance = None

    return (
        best_heading_for_vp,
        start_state,
        target_found,
        target_heading,
        target_distance,
        horizon_images,
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


def select_next_viewpoint_by_retrieval(
    candidate_vps,
    goal_text,
    vp_bank,
    text_embedder,
):
    """
    Choose the candidate viewpoint that best matches the goal text. The matching score is computed using the provided text_embedder and the pre-computed view embeddings in vp_bank. Specifically, for each candidate viewpoint v, we compute:
    score(v) = max_k cosine( view_emb(v, k), text_emb(goal_text) ), where view_emb(v, k) is the embedding of the k-th view of viewpoint v, and text_emb(goal_text) is the embedding of the goal text. We return the viewpoint with the highest score.

    Returns:
      best_vp_id, best_score
    """
    q = text_embedder.embed(goal_text)

    best_vp_id = None
    best_score = -1e9

    for vp_id in candidate_vps:
        view_embs = vp_bank.vp_view_embs.get(vp_id)
        if view_embs is None:
            continue

        # view_embs shape: (K, D)
        s = -1e9
        for k in range(view_embs.shape[0]):
            s = max(s, cosine_sim(view_embs[k], q))

        if s > best_score:
            best_score = s
            best_vp_id = vp_id

    if best_vp_id is None:
        # Fallback: deterministic first candidate (avoid randomness)
        return candidate_vps[0], float("nan")

    return best_vp_id, float(best_score)


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
