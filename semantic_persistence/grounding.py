"""
grounding.py

Ground a semantic region label s to candidate viewpoint sets Ω_s.

This implementation supports a hybrid, more stable grounding pipeline:

  (1) Text-to-view retrieval using a shared embedding space (CLIP):
        raw_score(v, s) = max_{k in K_sel} cosine( g(v,k), f(s) )

      where K_sel can be restricted by MLLM-provided support views.

  (2) Graph smoothing on the known Matterport navigation graph:
        score <- alpha * score + (1-alpha) * mean_neighbor(score)

      This suppresses isolated false positives and favors spatially consistent regions.

  (3) Selection:
        - either TopK viewpoints by (smoothed) score, or all viewpoints above a threshold

  (4) Spatial clustering (recommended for region labels):
        - DBSCAN over viewpoint coordinates, returning one or more region instances
"""

from typing import Dict, List, Optional, Set, Tuple, Literal, Iterable
import numpy as np

from .interfaces import TextEmbedder
from .data_structures import ViewpointBank
from .utils import cosine_sim

try:
    from sklearn.cluster import DBSCAN
except Exception:
    DBSCAN = None


ClusterMode = Literal["none", "all", "largest"]


def map_support_views_to_view_indices(
    support_views: Iterable[int],
    num_obs_images: int,
    num_views_per_vp: int,
) -> List[int]:
    """
    Map indices referring to the MLLM's observation image list (length = num_obs_images)
    into indices of the viewpoint-bank per-view embeddings (length = num_views_per_vp).

    We assume both are approximately uniform samples over 360 degrees, so we use
    proportional binning:
        k = floor(i * num_views_per_vp / num_obs_images)

    Returns unique sorted indices within [0, num_views_per_vp-1].
    """
    if num_obs_images <= 0 or num_views_per_vp <= 0:
        return []
    out: Set[int] = set()
    for i in support_views:
        try:
            ii = int(i)
        except Exception:
            continue
        if ii < 0 or ii >= num_obs_images:
            continue
        k = int(np.floor(ii * float(num_views_per_vp) / float(num_obs_images)))
        k = max(0, min(num_views_per_vp - 1, k))
        out.add(k)
    return sorted(out)


class RetrievalGrounder:
    def __init__(
        self,
        text_embedder: TextEmbedder,
        topk: int = 12,
        score_threshold: Optional[float] = None,
        # graph smoothing
        adjacency: Optional[Dict[str, List[str]]] = None,
        smooth_alpha: float = 0.65,
        smooth_steps: int = 2,
        # spatial clustering
        cluster_mode: ClusterMode = "all",
        spatial_cluster_eps: float = 2.0,
        spatial_cluster_min_samples: int = 2,
        max_clusters: int = 3,
    ):
        """
        Parameters
        ----------
        topk:
          If score_threshold is None, keep topk viewpoints as Ω_s.

        score_threshold:
          If set, keep viewpoints with score >= threshold (overrides TopK).

        adjacency / smooth_*:
          If adjacency is provided and smooth_steps>0, apply simple diffusion-style
          smoothing to the retrieval scores on the nav graph.

        cluster_mode:
          "none"    : return a single set (no clustering)
          "all"     : return up to max_clusters DBSCAN clusters (by size), dropping noise
          "largest" : return only the largest DBSCAN cluster

        spatial_cluster_*:
          DBSCAN parameters, only used when vp_xyz exists and sklearn is installed.

        max_clusters:
          Only used for cluster_mode="all". Keeps the largest max_clusters clusters.
        """
        self.text_embedder = text_embedder
        self.topk = int(topk)
        self.score_threshold = score_threshold

        self.adjacency = adjacency
        self.smooth_alpha = float(smooth_alpha)
        self.smooth_steps = int(smooth_steps)

        self.cluster_mode = cluster_mode
        self.spatial_cluster_eps = float(spatial_cluster_eps)
        self.spatial_cluster_min_samples = int(spatial_cluster_min_samples)
        self.max_clusters = int(max_clusters)

    def ground(
        self,
        vp_bank: ViewpointBank,
        text: str,
        support_views: Optional[List[int]] = None,
        num_obs_images: Optional[int] = None,
    ) -> Tuple[Set[str], Dict[str, float]]:
        """
        Backward-compatible: returns a single Ω set and a score dict.

        support_views / num_obs_images:
          Optional. If provided, restrict view indices used for each viewpoint's score
          to the mapped indices corresponding to the MLLM's supporting views.
        """
        clusters, scores = self.ground_clusters(
            vp_bank, text=text, support_views=support_views, num_obs_images=num_obs_images
        )
        omega: Set[str] = set()
        for c in clusters:
            omega |= set(c)
        return omega, scores

    def ground_clusters(
        self,
        vp_bank: ViewpointBank,
        text: str,
        support_views: Optional[List[int]] = None,
        num_obs_images: Optional[int] = None,
    ) -> Tuple[List[Set[str]], Dict[str, float]]:
        """
        Returns:
          - clusters: list of viewpoint-id sets (each is one region instance)
          - scores: dict vp_id -> (smoothed) retrieval score
        """
        f = self.text_embedder.embed(text)
        scores: Dict[str, float] = {}

        # Restrict per-view indices if MLLM gave supporting views.
        view_indices: Optional[List[int]] = None
        if support_views is not None and num_obs_images is not None and len(vp_bank.vp_view_embs) > 0:
            any_vp = next(iter(vp_bank.vp_view_embs.values()))
            num_views = int(any_vp.shape[0])
            view_indices = map_support_views_to_view_indices(
                support_views=support_views,
                num_obs_images=int(num_obs_images),
                num_views_per_vp=num_views,
            )
            if not view_indices:
                view_indices = None  # fall back to all views

        # (1) retrieval scoring
        for vp_id, view_embs in vp_bank.vp_view_embs.items():
            best = -1e9
            if view_indices is None:
                for k in range(view_embs.shape[0]):
                    best = max(best, cosine_sim(view_embs[k], f))
            else:
                for k in view_indices:
                    if 0 <= k < view_embs.shape[0]:
                        best = max(best, cosine_sim(view_embs[k], f))
            scores[vp_id] = float(best)

        # (2) nav-graph smoothing (optional)
        if self.adjacency is not None and self.smooth_steps > 0:
            scores = self._smooth_scores(scores)

        # (3) select Ω
        if self.score_threshold is not None:
            omega = {vp for vp, sc in scores.items() if sc >= float(self.score_threshold)}
        else:
            omega = set(sorted(scores.keys(), key=lambda v: scores[v], reverse=True)[: self.topk])

        # (4) clusterize Ω (optional)
        if self.cluster_mode == "none":
            return [omega], scores

        clusters = self._clusterize(vp_bank, omega)
        if not clusters:
            return [omega], scores

        if self.cluster_mode == "largest":
            clusters = [max(clusters, key=lambda s: len(s))]
        elif self.cluster_mode == "all":
            clusters = sorted(clusters, key=lambda s: len(s), reverse=True)[: max(1, self.max_clusters)]

        return clusters, scores

    def _smooth_scores(self, scores: Dict[str, float]) -> Dict[str, float]:
        """
        Simple diffusion smoothing on the navigation graph.
        score_{t+1}(v) = alpha * score_t(v) + (1-alpha) * mean_{u in N(v)} score_t(u)

        Notes:
          - Uses only neighbors present in the score dict.
          - Keeps nodes with no neighbors unchanged (no-op).
        """
        alpha = self.smooth_alpha
        adjacency = self.adjacency or {}
        cur = dict(scores)

        for _ in range(self.smooth_steps):
            nxt: Dict[str, float] = {}
            for v, sv in cur.items():
                nbrs = adjacency.get(v, [])
                if not nbrs:
                    nxt[v] = sv
                    continue
                vals = [cur.get(u) for u in nbrs if u in cur]
                if not vals:
                    nxt[v] = sv
                    continue
                mean_n = float(np.mean(vals))
                nxt[v] = alpha * float(sv) + (1.0 - alpha) * mean_n
            cur = nxt
        return cur

    def _clusterize(self, vp_bank: ViewpointBank, omega: Set[str]) -> List[Set[str]]:
        """
        Cluster Ω spatially using DBSCAN.

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
            eps=self.spatial_cluster_eps,
            min_samples=self.spatial_cluster_min_samples,
        ).fit(X)
        labels = clustering.labels_

        lab_to_ids: Dict[int, Set[str]] = {}
        for i, lab in enumerate(labels.tolist()):
            lab = int(lab)
            if lab == -1:
                continue
            lab_to_ids.setdefault(lab, set()).add(ids[i])

        return list(lab_to_ids.values())
