"""
data_structures.py

Data classes for:
  - SemanticNode: a persistent semantic hypothesis (stable ID across time)
  - ViewpointBank: precomputed image embeddings for each viewpoint in a scan

Key idea:
  We store semantics as tracked nodes, not raw strings, so the planner sees stable IDs.
"""


from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
import time
import uuid
import numpy as np


def new_node_id(prefix: str = "S") -> str:
    """
    Create a stable-ish unique ID for a semantic node.
    Prefix is useful for debugging (for example "S_...").
    """
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


@dataclass
class SemanticNode:
    """
    A persistent semantic hypothesis.

    label/synonyms:
      Human-readable description and alternative names.

    omega:
      Set of viewpoint IDs that are likely to contain this region/concept.
      This is used by your planner to choose candidate viewpoints.

    r_exist:
      Existence confidence. How sure you are this semantic region is real in this scan.

    p_target:
      Probability the target (for example "glass") is in this region.
      This is optional but useful for search planning.
    """

    node_id: str
    label: str
    desc: str = ""
    synonyms: List[str] = field(default_factory=list)

    # Cached embedding for matching and retrieval (computed from label + synonyms).
    text_emb: Optional[np.ndarray] = None

    # Grounded region in the navigation graph.
    omega: Set[str] = field(default_factory=set)

    # Beliefs.
    r_exist: float = 0.5
    p_target: float = 0.0

    # Time bookkeeping.
    last_seen_t: int = 0
    created_ts: float = field(default_factory=time.time)

    # Optional evidence log for debugging and analysis.
    evidence_log: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ViewpointBank:
    """
    Precomputed viewpoint embeddings for a scan.

    vp_view_embs:
      Map vp_id -> array of view embeddings with shape (K, D)
      K is the number of camera headings per viewpoint (for example 12).

    vp_xyz:
      Optional map vp_id -> coordinates (x,y,z) or (x,y).
      Used to keep Omega compact using spatial clustering.

    scan_id:
      Identifier of the scan/scene.
    """

    scan_id: str
    vp_view_embs: Dict[str, np.ndarray]
    vp_xyz: Optional[Dict[str, np.ndarray]] = None

    def viewpoint_ids(self) -> List[str]:
        """Convenience helper."""
        return list(self.vp_view_embs.keys())
