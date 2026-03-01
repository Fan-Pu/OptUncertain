"""
grounding.py

Ground a semantic label to candidate viewpoint sets.

We score each viewpoint v by best-view retrieval:
  score(v, s) = max_k cosine( g(v,k), f(s) )

Selection:
  - either TopK viewpoints by score, or all viewpoints above a threshold

Spatial clustering (recommended for region labels):
  - if coordinates exist, we cluster the selected viewpoints with DBSCAN
  - we return one or more clusters, each treated as a region instance
"""

from typing import Dict, List, Optional, Set, Tuple, Literal
import numpy as np

from .interfaces import TextEmbedder
from .data_structures import ViewpointBank
from .utils import cosine_sim

try:
    from sklearn.cluster import DBSCAN
except Exception:
    DBSCAN = None


ClusterMode = Literal["none", "all", "largest"]


class RetrievalGrounder:
    def __init__(
        self,
        text_embedder: TextEmbedder,
        topk: int = 12,
        score_threshold: Optional[float] = None,
        # spatial clustering
        cluster_mode: ClusterMode = "all",
        spatial_cluster_eps: float = 2.0,
        spatial_cluster_min_samples: int = 2,
        max_clusters: int = 3,
    ):
        """
        Parameters:
          topk:
            If score_threshold is None, keep topk viewpoints as Omega.

          score_threshold:
            If set, keep viewpoints with score >= threshold (overrides TopK).

          cluster_mode:
            "none"   : return a single set (no clustering)
            "all"    : return up to max_clusters DBSCAN clusters (by size), dropping noise
            "largest" : return only the largest DBSCAN cluster

          spatial_cluster_*:
            DBSCAN parameters, only used when vp_xyz exists and sklearn is installed.

          max_clusters:
            Only used for cluster_mode="all". Keeps the largest max_clusters clusters.
        """
        self.text_embedder = text_embedder
        self.topk = int(topk)
        self.score_threshold = score_threshold

        self.cluster_mode = cluster_mode
        self.spatial_cluster_eps = float(spatial_cluster_eps)
        self.spatial_cluster_min_samples = int(spatial_cluster_min_samples)
        self.max_clusters = int(max_clusters)

    def ground(
        self, vp_bank: ViewpointBank, text: str
    ) -> Tuple[Set[str], Dict[str, float]]:
        """
        Backward-compatible: returns a single Omega set.
        Omega is the set of viewpoint ids whose view embeddings best match the text embedding.
        """
        clusters, scores = self.ground_clusters(vp_bank, text=text)
        omega: Set[str] = set()
        for c in clusters:
            omega |= set(c)
        return omega, scores

    def ground_clusters(
        self, vp_bank: ViewpointBank, text: str
    ) -> Tuple[List[Set[str]], Dict[str, float]]:
        """
        Returns:
          - clusters: list of viewpoint-id sets (each is one region instance)
          - scores: dict vp_id -> retrieval score
        """
        f = self.text_embedder.embed(text)
        scores: Dict[str, float] = {}

        for vp_id, view_embs in vp_bank.vp_view_embs.items():
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

        if self.cluster_mode == "none":
            return [omega], scores

        clusters = self._clusterize(vp_bank, omega)
        if not clusters:
            return [omega], scores

        if self.cluster_mode == "largest":
            clusters = [max(clusters, key=lambda s: len(s))]

        elif self.cluster_mode == "all":
            clusters = sorted(clusters, key=lambda s: len(s), reverse=True)[
                : max(1, self.max_clusters)
            ]

        return clusters, scores

    def _clusterize(self, vp_bank: ViewpointBank, omega: Set[str]) -> List[Set[str]]:
        """
        Cluster Omega spatially using DBSCAN.

        Returns a list of clusters (each a set of vp_ids), excluding noise.
        If conditions are not met, returns an empty list.
        """
        if not omega or vp_bank.vp_xyz is None or DBSCAN is None:
            return []

        pts = []
        ids = []
        for vp_id in omega:
            xyz = vp_bank.vp_xyz.get(vp_id)
            if xyz is None:
                continue
            ids.append(vp_id)
            pts.append(xyz.astype(np.float32))

        if len(pts) < max(3, self.spatial_cluster_min_samples):
            return []

        X = np.vstack(pts)
        clustering = DBSCAN(
            eps=self.spatial_cluster_eps, min_samples=self.spatial_cluster_min_samples
        ).fit(X)
        labels = clustering.labels_

        lab_to_ids: Dict[int, Set[str]] = {}
        for i, lab in enumerate(labels.tolist()):
            lab = int(lab)
            if lab == -1:
                continue
            lab_to_ids.setdefault(lab, set()).add(ids[i])

        return list(lab_to_ids.values())
