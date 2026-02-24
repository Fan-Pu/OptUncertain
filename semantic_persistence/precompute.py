"""
precompute.py

Utilities to build ViewpointBank:

  - render_fn(vp_id, view_index) returns an RGB image for a fixed camera heading
  - image_embedder.embed(image) returns an embedding for that view

This is usually done once per scan and cached to disk.
"""


from typing import Callable, Iterable, Optional, Dict
import numpy as np

from .interfaces import ImageEmbedder
from .data_structures import ViewpointBank


def precompute_viewpoint_embeddings(
    scan_id: str,
    viewpoint_ids: Iterable[str],
    render_fn: Callable[[str, int], np.ndarray],
    image_embedder: ImageEmbedder,
    num_views: int = 12,
    vp_xyz: Optional[Dict] = None,
) -> ViewpointBank:
    """
    Parameters:
      scan_id:
        Scene identifier.

      viewpoint_ids:
        Iterable of viewpoint IDs for this scan.

      render_fn:
        Function that renders the k-th view at a viewpoint ID.
        You define the camera ring policy (for example 12 headings).

      image_embedder:
        Image encoder to turn each rendered view into an embedding.

      num_views:
        Number of headings/views per viewpoint to embed.

      vp_xyz:
        Optional coordinates for each viewpoint.

    Returns:
      ViewpointBank with embeddings vp_view_embs[vp] shaped (K, D).
    """
    vp_view_embs = {}

    for vp in viewpoint_ids:
        embs = []
        for k in range(int(num_views)):
            img = render_fn(vp, k)
            e = image_embedder.embed(img)
            embs.append(e.astype(np.float32))
        vp_view_embs[vp] = np.stack(embs, axis=0)

    return ViewpointBank(scan_id=scan_id, vp_view_embs=vp_view_embs, vp_xyz=vp_xyz)
