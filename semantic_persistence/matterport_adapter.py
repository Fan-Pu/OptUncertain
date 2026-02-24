"""
matterport_adapter.py

Adapter utilities for Matterport3DSimulator (MatterSim).

This file helps you connect the semantic persistence component to Matterport by providing:
  - connectivity loading (viewpoint IDs + coordinates)
  - a render_fn(vp_id, view_index) -> RGB image
  - a convenience function to build ViewpointBank with vp_xyz

Assumptions:
  - You have Matterport3DSimulator installed and importable as `MatterSim`.
  - You have downloaded the Matterport3D connectivity files (the JSON graphs).

Typical folder structure (common in the repo tutorials):
  <MP_DATASET_PATH>/
    scans/
    connectivity/
      <scan_id>_connectivity.json
"""

from dataclasses import dataclass
from typing import Callable, Dict, List, Tuple, Optional
import json
import math
import os

import numpy as np

from .interfaces import ImageEmbedder
from .data_structures import ViewpointBank


@dataclass
class ConnectivityInfo:
    """
    Parsed connectivity for one scan.

    viewpoint_ids:
      List of viewpoint IDs (image_id in the connectivity JSON).

    vp_xyz:
      Map viewpoint_id -> (x, y, z) coordinates (float32).
    """

    scan_id: str
    viewpoint_ids: List[str]
    vp_xyz: Dict[str, np.ndarray]


def load_connectivity(connectivity_dir: str, scan_id: str) -> ConnectivityInfo:
    """
    Load Matterport connectivity JSON for a scan and extract viewpoint IDs and coordinates.

    Parameters:
      connectivity_dir:
        Path to the folder containing "<scan_id>_connectivity.json".

      scan_id:
        Matterport scan ID, for example "17DRP5sb8fy".

    Returns:
      ConnectivityInfo with viewpoint_ids and vp_xyz.

    Notes:
      Each JSON entry typically has:
        - "image_id"
        - "included" (bool)
        - "pose" (length 16 list, a 4x4 matrix flattened row-major)
      The position is commonly read from pose[3], pose[7], pose[11].
    """
    path = os.path.join(connectivity_dir, f"{scan_id}_connectivity.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Connectivity file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    viewpoint_ids: List[str] = []
    vp_xyz: Dict[str, np.ndarray] = {}

    for item in data:
        if not bool(item.get("included", False)):
            continue

        vp_id = str(item["image_id"])
        pose = item.get("pose", None)
        if pose is None or len(pose) < 16:
            continue

        # Pose is a 4x4 matrix flattened row-major.
        # Translation components are usually at indices 3, 7, 11.
        x = float(pose[3])
        y = float(pose[7])
        z = float(pose[11])

        viewpoint_ids.append(vp_id)
        vp_xyz[vp_id] = np.array([x, y, z], dtype=np.float32)

    if not viewpoint_ids:
        raise RuntimeError(f"No included viewpoints found in: {path}")

    return ConnectivityInfo(scan_id=scan_id, viewpoint_ids=viewpoint_ids, vp_xyz=vp_xyz)


def make_simulator(
    dataset_path: str,
    connectivity_dir: str,
    image_width: int = 640,
    image_height: int = 480,
    vfov_degrees: float = 60.0,
    rendering_enabled: bool = True,
    discretized_view_angles: bool = False,
):
    """
    Create and initialize a MatterSim.Simulator with standard settings.

    Parameters:
      dataset_path:
        Root path to Matterport3D scans (often the folder containing "scans/").

      connectivity_dir:
        Path to the connectivity graphs folder.

      image_width/image_height:
        Output render resolution.

      vfov_degrees:
        Vertical field-of-view in degrees.

      rendering_enabled:
        If False, the simulator will not render RGB.

      discretized_view_angles:
        If True, simulator may restrict view angles; for precompute, False is usually better.
    """
    try:
        import MatterSim
    except Exception as e:
        raise ImportError(
            "Cannot import MatterSim. Make sure Matterport3DSimulator is installed and built."
        ) from e

    sim = MatterSim.Simulator()

    # Dataset and graph paths
    sim.setDatasetPath(dataset_path)
    sim.setNavGraphPath(connectivity_dir)

    # Rendering controls
    sim.setRenderingEnabled(bool(rendering_enabled))
    sim.setDiscretizedViewingAngles(bool(discretized_view_angles))

    # Camera controls
    sim.setCameraResolution(int(image_width), int(image_height))
    sim.setCameraVFOV(math.radians(float(vfov_degrees)))

    sim.initialize()
    return sim


def make_render_fn(
    sim,
    scan_id: str,
    num_views: int = 12,
    elevation_degrees: float = 0.0,
) -> Callable[[str, int], np.ndarray]:
    """
    Build a render function with the signature:
      render_fn(viewpoint_id, view_index) -> RGB np.ndarray (H, W, 3), dtype uint8

    It renders a fixed ring of headings:
      heading_k = 2*pi * k / num_views

    Implementation detail:
      We use sim.newEpisode(...) to set viewpoint + heading + elevation directly.
      This is slower than incremental turning, but is simple and reliable for offline precompute.

    Parameters:
      sim:
        A MatterSim.Simulator instance.

      scan_id:
        Current scan.

      num_views:
        Number of headings per viewpoint.

      elevation_degrees:
        Camera elevation in degrees (0 is horizontal).
    """
    elev = math.radians(float(elevation_degrees))
    K = int(num_views)

    def render_fn(viewpoint_id: str, view_index: int) -> np.ndarray:
        k = int(view_index) % K
        heading = 2.0 * math.pi * (k / K)

        # newEpisode takes lists; this is the standard usage pattern in MatterSim examples
        sim.newEpisode([scan_id], [viewpoint_id], [heading], [elev])

        state = sim.getState()[0]
        # In MatterSim, state.rgb is typically an HxWx3 uint8 array.
        rgb = state.rgb
        if rgb is None:
            raise RuntimeError(
                "Rendering returned None. Did you enable rendering in the simulator?"
            )
        return np.array(rgb, copy=True)

    return render_fn


def build_viewpoint_bank_from_matterport(
    scan_id: str,
    dataset_path: str,
    connectivity_dir: str,
    image_embedder: ImageEmbedder,
    num_views: int = 12,
    elevation_degrees: float = 0.0,
    image_width: int = 640,
    image_height: int = 480,
    vfov_degrees: float = 60.0,
    rendering_enabled: bool = True,
) -> ViewpointBank:
    """
    Convenience function:
      - load connectivity (viewpoint IDs + xyz)
      - create simulator
      - render K views per viewpoint
      - embed each view and produce ViewpointBank

    Returns:
      ViewpointBank(scan_id, vp_view_embs, vp_xyz)

    Practical tip:
      This can be slow. Usually you run it once per scan and save to disk using np.savez.
    """
    conn = load_connectivity(connectivity_dir=connectivity_dir, scan_id=scan_id)

    sim = make_simulator(
        dataset_path=dataset_path,
        connectivity_dir=connectivity_dir,
        image_width=image_width,
        image_height=image_height,
        vfov_degrees=vfov_degrees,
        rendering_enabled=rendering_enabled,
        discretized_view_angles=False,
    )

    render_fn = make_render_fn(
        sim=sim,
        scan_id=scan_id,
        num_views=num_views,
        elevation_degrees=elevation_degrees,
    )

    vp_view_embs: Dict[str, np.ndarray] = {}

    for vp_id in conn.viewpoint_ids:
        embs = []
        for k in range(int(num_views)):
            img = render_fn(vp_id, k)
            e = image_embedder.embed(img)  # 1D vector
            embs.append(e.astype(np.float32))
        vp_view_embs[vp_id] = np.stack(embs, axis=0)  # (K, D)

    return ViewpointBank(scan_id=scan_id, vp_view_embs=vp_view_embs, vp_xyz=conn.vp_xyz)


def save_viewpoint_bank_npz(
    vp_bank: ViewpointBank,
    out_path: str,
) -> None:
    """
    Save a ViewpointBank to an .npz file.

    Storage format:
      - vp_ids: (N,) array of strings
      - embs:   (N, K, D) float32
      - xyz:    (N, 3) float32 (or omitted if vp_xyz is None)
      - scan_id: string

    This makes loading fast later.
    """
    vp_ids = np.array(sorted(vp_bank.vp_view_embs.keys()), dtype=object)
    embs = np.stack([vp_bank.vp_view_embs[vp] for vp in vp_ids], axis=0)

    if vp_bank.vp_xyz is not None:
        xyz = np.stack([vp_bank.vp_xyz[vp] for vp in vp_ids], axis=0)
        np.savez_compressed(
            out_path, scan_id=vp_bank.scan_id, vp_ids=vp_ids, embs=embs, xyz=xyz
        )
    else:
        np.savez_compressed(out_path, scan_id=vp_bank.scan_id, vp_ids=vp_ids, embs=embs)


def load_viewpoint_bank_npz(path: str) -> ViewpointBank:
    """
    Load a ViewpointBank saved by save_viewpoint_bank_npz.
    """
    z = np.load(path, allow_pickle=True)
    scan_id = str(z["scan_id"])
    vp_ids = list(z["vp_ids"])
    embs = z["embs"]

    vp_view_embs: Dict[str, np.ndarray] = {}
    for i, vp in enumerate(vp_ids):
        vp_view_embs[str(vp)] = embs[i]

    vp_xyz: Optional[Dict[str, np.ndarray]] = None
    if "xyz" in z:
        xyz = z["xyz"]
        vp_xyz = {str(vp_ids[i]): xyz[i].astype(np.float32) for i in range(len(vp_ids))}

    return ViewpointBank(scan_id=scan_id, vp_view_embs=vp_view_embs, vp_xyz=vp_xyz)
