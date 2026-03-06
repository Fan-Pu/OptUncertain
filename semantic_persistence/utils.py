"""
utils.py

Small utilities used across the package:
  - iou_sets: overlap measure for Omega sets (region overlap)
"""

from typing import Set
import numpy as np


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
