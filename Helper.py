import json
import os
import numpy as np
import cv2
import math
import MatterSim

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

# for node type definition in the hypothesis graph
TYPE_REGION = 0
TYPE_VP = 1

viewpoint_index_by_vp_label = (
    {}
)  # key: viewpoint_id (str), value: stable integer index for exploration labels
viewpoint_vp_label_by_index = (
    {}
)  # key: stable integer index for exploration labels, value: viewpoint_id (str)


def init_render():
    cv2.namedWindow("Python RGB")

    sim = MatterSim.Simulator()
    sim.setCameraResolution(WIDTH, HEIGHT)
    sim.setCameraVFOV(VFOV)
    sim.setDiscretizedViewingAngles(False)

    sim.setDatasetPath(os.path.join(MP_ROOT, "data/v1/scans"))
    sim.setNavGraphPath(os.path.join(MP_ROOT, "connectivity"))
    sim.setPreloadingEnabled(False)
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
    viewpoint_index_by_vp_label.clear()
    viewpoint_vp_label_by_index.clear()
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
    cv2.waitKey(1)


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
        current_vp_id = viewpoint_index_by_vp_label[str(state.location.viewpointId)]
        navigable_vp_ids = [
            viewpoint_index_by_vp_label[str(loc.viewpointId)] for loc in locations[1:]
        ]
        print(
            f"current vp id: {current_vp_id}, long id: {state.location.viewpointId}, elevation: {math.degrees(state.elevation):.1f} deg, heading: {math.degrees(state.heading):.1f} deg"
        )
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
