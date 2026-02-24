"""semantic_persistence.vpbank_manager

Utilities to load or build a ViewpointBank (vp bank).

Behavior:
  - Look for a saved bank file under the folder `vpbanks/`.
  - If missing, build it using Matterport3DSimulator rendering + an ImageEmbedder.

This project sets dataset/connectivity paths inside the container (MP_ROOT).
So we do not rely on environment variables.

The saved file format is the same as semantic_persistence.matterport_adapter.save_viewpoint_bank_npz.
"""


import os
from typing import Optional

from .matterport_adapter import (
    build_viewpoint_bank_from_matterport,
    load_viewpoint_bank_npz,
    save_viewpoint_bank_npz,
)


def get_or_create_vp_bank(
    scan_id: str,
    vpbanks_dir: str = "vpbanks",
    bank_filename: Optional[str] = None,
    dataset_path: Optional[str] = None,
    connectivity_dir: Optional[str] = None,
    image_embedder=None,
    num_views: int = 12,
    elevation_degrees: float = 0.0,
    image_width: int = 640,
    image_height: int = 480,
    vfov_degrees: float = 60.0,
):
    """Load a vp bank from disk; build and save it if missing.

    Parameters:
      scan_id:
        Matterport scan ID.

      vpbanks_dir:
        Folder where vp bank .npz files are stored.

      bank_filename:
        If None, defaults to f"{scan_id}_vpbank.npz".

      dataset_path/connectivity_dir:
        Only required when building (bank file does not exist).
        If None, will read from MP3D_DATASET_PATH / MP3D_CONNECTIVITY_DIR.

      image_embedder:
        Must provide embed(image_rgb)->np.ndarray.
        Required when building.

    Returns:
      ViewpointBank
    """

    os.makedirs(vpbanks_dir, exist_ok=True)

    if bank_filename is None:
        bank_filename = f"{scan_id}_vpbank.npz"

    vp_bank_path = os.path.join(vpbanks_dir, bank_filename)

    if os.path.exists(vp_bank_path):
        print(f"[VPBANK] Loading: {vp_bank_path}")
        return load_viewpoint_bank_npz(vp_bank_path)

    # Need to build. dataset_path/connectivity_dir must be provided by caller.
    if not dataset_path or not connectivity_dir:
        raise RuntimeError(
            "VP bank file is missing and dataset_path/connectivity_dir were not provided.\n"
            "In this project, set MP_ROOT in main.py and pass:\n"
            "  dataset_path=os.path.join(MP_ROOT, 'data/v1/scans')\n"
            "  connectivity_dir=os.path.join(MP_ROOT, 'connectivity')\n"
        )

    if image_embedder is None:
        raise RuntimeError("image_embedder is required to build vp bank")

    print(f"[VPBANK] Not found. Building: {vp_bank_path} (this can be slow)")

    vp_bank = build_viewpoint_bank_from_matterport(
        scan_id=scan_id,
        dataset_path=dataset_path,
        connectivity_dir=connectivity_dir,
        image_embedder=image_embedder,
        num_views=num_views,
        elevation_degrees=elevation_degrees,
        image_width=image_width,
        image_height=image_height,
        vfov_degrees=vfov_degrees,
        rendering_enabled=True,
    )

    save_viewpoint_bank_npz(vp_bank, vp_bank_path)
    print(f"[VPBANK] Saved: {vp_bank_path}")

    return vp_bank
