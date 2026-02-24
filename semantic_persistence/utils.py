"""
utils.py

Small utilities used across the package:
  - cosine_sim: compare embeddings
  - iou_sets: overlap measure for Omega sets (region overlap)
"""


from typing import Set
import numpy as np


def cosine_sim(a: np.ndarray, b: np.ndarray, eps: float = 1e-12) -> float:
    """
    Cosine similarity in [-1, 1].

    The embedder output should be float vectors.
    We cast to float32 for speed and consistent behavior.
    """
    a = a.astype(np.float32)
    b = b.astype(np.float32)
    denom = (np.linalg.norm(a) * np.linalg.norm(b)) + eps
    return float(np.dot(a, b) / denom)


def iou_sets(a: Set[str], b: Set[str]) -> float:
    """
    Intersection-over-union between two sets of viewpoint IDs.

    Used to measure region overlap between an existing semantic node Omega and
    a newly grounded proposal Omega.
    """
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return float(inter / union) if union > 0 else 0.0
