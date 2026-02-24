"""
grounding.py

Ground a semantic label to a set of candidate viewpoints Omega_s.

We use retrieval scoring:
  score(v, s) = max_k cosine( g(v,k), f(s) )

Where:
  - g(v,k) is the embedding for the k-th view of viewpoint v
  - f(s) is the embedding for semantic text s

Selection:
  - either TopK viewpoints by score, or all viewpoints above a threshold

Optional:
  - if coordinates exist, keep Omega compact using DBSCAN clustering
"""

from typing import Dict, Optional, Set, Tuple
import numpy as np

from .interfaces import TextEmbedder
from .data_structures import ViewpointBank
from .utils import cosine_sim

try:
    from sklearn.cluster import DBSCAN
except Exception:
    DBSCAN = None


class RetrievalGrounder:
    def __init__(
        self,
        text_embedder: TextEmbedder,
        topk: int = 12,
        score_threshold: Optional[float] = None,
        spatial_cluster_eps: float = 2.0,
        spatial_cluster_min_samples: int = 2,
    ):
        """
        Parameters:
          topk:
            If score_threshold is None, keep topk viewpoints as Omega.

          score_threshold:
            If set, keep viewpoints with score >= threshold (overrides TopK).

          spatial_cluster_*:
            If vp_xyz exists and sklearn is installed, keep Omega compact
            by taking the largest spatial cluster.
        """
        self.text_embedder = text_embedder
        self.topk = int(topk)
        self.score_threshold = score_threshold
        self.spatial_cluster_eps = float(spatial_cluster_eps)
        self.spatial_cluster_min_samples = int(spatial_cluster_min_samples)

    def ground(
        self, vp_bank: ViewpointBank, text: str
    ) -> Tuple[Set[str], Dict[str, float]]:
        """
        Returns:
          - omega: set of viewpoint IDs
          - scores: dict vp_id -> retrieval score
        """
        f = self.text_embedder.embed(text)
        scores: Dict[str, float] = {}

        for vp_id, view_embs in vp_bank.vp_view_embs.items():
            # view_embs: (K, D)
            best = -1e9
            for k in range(view_embs.shape[0]):
                best = max(best, cosine_sim(view_embs[k], f))
            scores[vp_id] = float(best)

        if self.score_threshold is not None:
            omega = {
                vp for vp, sc in scores.items() if sc >= float(self.score_threshold)
            }
        else:
            omega = set(
                sorted(scores.keys(), key=lambda v: scores[v], reverse=True)[
                    : self.topk
                ]
            )

        omega = self._compactify(vp_bank, omega)
        return omega, scores

    def _compactify(self, vp_bank: ViewpointBank, omega: Set[str]) -> Set[str]:
        """
        Keep Omega spatially compact by selecting the largest DBSCAN cluster.
        If conditions are not met, return Omega unchanged.
        """
        if not omega or vp_bank.vp_xyz is None or DBSCAN is None:
            return omega

        pts = []
        ids = []
        for vp_id in omega:
            xyz = vp_bank.vp_xyz.get(vp_id)
            if xyz is None:
                continue
            ids.append(vp_id)
            pts.append(xyz.astype(np.float32))

        if len(pts) < max(3, self.spatial_cluster_min_samples):
            return omega

        X = np.vstack(pts)
        clustering = DBSCAN(
            eps=self.spatial_cluster_eps, min_samples=self.spatial_cluster_min_samples
        ).fit(X)
        labels = clustering.labels_

        # Ignore noise label -1. Keep largest valid cluster.
        unique = [lab for lab in set(labels.tolist()) if lab != -1]
        if not unique:
            return omega

        best_lab = None
        best_count = -1
        for lab in unique:
            c = int(np.sum(labels == lab))
            if c > best_count:
                best_count = c
                best_lab = lab

        kept = {ids[i] for i in range(len(ids)) if int(labels[i]) == int(best_lab)}
        return kept if kept else omega
