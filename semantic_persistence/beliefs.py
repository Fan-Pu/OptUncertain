"""
beliefs.py

Online updates for:
  - r_exist: confidence that a semantic node exists in the environment
  - p_target: probability that the target is in that region

This file is intentionally simple. You can swap in Bayesian updates later.
"""


from typing import Dict, Optional, Set
import numpy as np

from .data_structures import SemanticNode


class BeliefUpdater:
    def __init__(
        self,
        r_support_gain: float = 0.15,
        r_contradict_drop: float = 0.30,
        min_r: float = 0.0,
        max_r: float = 1.0,
    ):
        self.r_support_gain = float(r_support_gain)
        self.r_contradict_drop = float(r_contradict_drop)
        self.min_r = float(min_r)
        self.max_r = float(max_r)

    def update_with_visit(
        self,
        node: SemanticNode,
        t: int,
        scan_id: str,
        vp_id: str,
        membership_score: float,
        found_target: bool,
        contradicts: bool = False,
    ) -> None:
        """
        Update one node after visiting a viewpoint.

        membership_score:
          A soft support score in [0,1] (or any non-negative scale)
          that indicates how consistent the viewpoint is with the node concept.
          You can compute this by retrieval: score(visited_vp, node.label).

        found_target:
          Whether your detector confirmed the target is present.
        """
        if contradicts:
            node.r_exist = float(
                np.clip(node.r_exist - self.r_contradict_drop, self.min_r, self.max_r)
            )
        else:
            if membership_score >= 0.0:
                node.r_exist = float(
                    np.clip(
                        node.r_exist + self.r_support_gain * float(membership_score),
                        self.min_r,
                        self.max_r,
                    )
                )

        if found_target:
            node.p_target = 1.0
        else:
            # Simple decay when you keep searching and do not find it.
            node.p_target = float(np.clip(node.p_target * 0.9, 0.0, 1.0))

        node.last_seen_t = t
        node.evidence_log.append(
            {
                "t": int(t),
                "scan": scan_id,
                "vp": vp_id,
                "membership_score": float(membership_score),
                "found_target": bool(found_target),
                "contradicts": bool(contradicts),
                "r_exist": float(node.r_exist),
                "p_target": float(node.p_target),
            }
        )

    def batch_update_after_visit(
        self,
        nodes: Dict[str, SemanticNode],
        t: int,
        scan_id: str,
        visited_vp_id: str,
        found_target: bool,
        membership_scores: Optional[Dict[str, float]] = None,
        contradict_nodes: Optional[Set[str]] = None,
    ) -> None:
        """
        Update all nodes after a visit.

        membership_scores:
          Optional node_id -> membership_score for the visited viewpoint.

        contradict_nodes:
          Optional set of node_id that are contradicted by vision evidence.
        """
        membership_scores = membership_scores or {}
        contradict_nodes = contradict_nodes or set()

        for node in nodes.values():
            ms = float(membership_scores.get(node.node_id, 0.0))
            contradicts = node.node_id in contradict_nodes
            self.update_with_visit(
                node=node,
                t=t,
                scan_id=scan_id,
                vp_id=visited_vp_id,
                membership_score=ms,
                found_target=found_target,
                contradicts=contradicts,
            )
