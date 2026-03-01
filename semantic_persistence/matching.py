"""
matching.py

Match newly proposed semantic nodes to existing persistent nodes, then merge or create.

Deterministic similarity:
  sim = lam_text * sim_text + (1 - lam_text) * sim_iou

Where:
  - sim_text is cosine similarity between text embeddings
  - sim_iou is IoU between grounded viewpoint sets Omega

Decision:
  - if sim >= auto_merge_threshold -> merge automatically
  - if sim in a gray zone -> optionally ask the MLLM verifier
  - else -> create a new node
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple
import json
import numpy as np

from .interfaces import TextEmbedder, MLLMClient
from .data_structures import SemanticNode, new_node_id
from .utils import cosine_sim, iou_sets


@dataclass
class MatchConfig:
    """
    lam_text:
      Weight on text similarity. (1-lam_text) is weight on region overlap.
    """

    lam_text: float = 0.6
    top_candidates: int = 3
    auto_merge_threshold: float = 0.80
    use_mllm_gray_zone: Tuple[float, float] = (0.55, 0.80)
    min_iou_for_merge: float = 0.05


class SemanticGraph:
    """
    Holds persistent semantic nodes keyed by stable node_id.
    """

    def __init__(
        self,
        text_embedder: TextEmbedder,
        mllm: Optional[MLLMClient] = None,
        match_cfg: Optional[MatchConfig] = None,
    ):
        self.text_embedder = text_embedder
        self.mllm = mllm
        self.cfg = match_cfg or MatchConfig()
        self.nodes: Dict[str, SemanticNode] = {}

    def add_node(self, node: SemanticNode) -> None:
        """
        Add a new node to the graph and ensure it has a cached embedding.
        """
        if node.text_emb is None:
            node.text_emb = self.text_embedder.embed(self._node_text(node))
        self.nodes[node.node_id] = node

    def get_nodes(self) -> List[SemanticNode]:
        return list(self.nodes.values())

    def _node_text(self, node: SemanticNode) -> str:
        """
        Canonical text used to embed a node for matching.
        """
        parts = [node.label.strip()]
        if node.desc.strip():
            parts.append(node.desc.strip())
        if node.synonyms:
            parts.append("synonyms: " + ", ".join(node.synonyms[:8]))
        return " | ".join(parts)

    def _proposal_text(self, proposal: Dict[str, Any]) -> str:
        """
        Canonical text used to embed a proposal for matching.
        """
        name = str(proposal.get("name", "")).strip()
        why = str(proposal.get("why", "")).strip()
        syn = proposal.get("syn", []) or []
        syn = [str(x) for x in syn][:8]
        parts = [name]
        if why:
            parts.append(why)
        if syn:
            parts.append("synonyms: " + ", ".join(syn))
        return " | ".join(parts)

    def match_and_merge(
        self,
        proposal: Dict[str, Any],
        proposal_omega: Set[str],
        t: int,
        proposal_text_emb: Optional[np.ndarray] = None,
        scores_hint: Optional[Dict[str, float]] = None,
    ) -> str:
        """
        Match a proposal to an existing node, then merge or create.

        Returns:
          node_id of the merged node or the newly created node.
        """
        if proposal_text_emb is None:
            proposal_text_emb = self.text_embedder.embed(self._proposal_text(proposal))

        candidates: List[Tuple[float, float, float, str]] = []
        for node in self.nodes.values():
            if node.text_emb is None:
                node.text_emb = self.text_embedder.embed(self._node_text(node))
            sim_text = cosine_sim(proposal_text_emb, node.text_emb)
            sim_iou = iou_sets(proposal_omega, node.omega)
            sim = self.cfg.lam_text * sim_text + (1.0 - self.cfg.lam_text) * sim_iou
            candidates.append((sim, sim_text, sim_iou, node.node_id))

        candidates.sort(reverse=True, key=lambda x: x[0])
        best = candidates[0] if candidates else None
        best_sim = best[0] if best else 0.0

        merge_node_id: Optional[str] = None

        # Case 1: no existing nodes
        if best is None:
            merge_node_id = None

        # Case 2: strong match
        elif (
            best_sim >= self.cfg.auto_merge_threshold
            and best[2] >= self.cfg.min_iou_for_merge
        ):
            merge_node_id = best[3]

        # Case 3: ambiguous match, ask verifier if available
        else:
            gray_lo, gray_hi = self.cfg.use_mllm_gray_zone
            if (
                self.mllm is not None
                and gray_lo <= best_sim < gray_hi
                and candidates[0][2] >= self.cfg.min_iou_for_merge
            ):
                node_id = candidates[0][3]
                node = self.nodes[node_id]
                evidence = self._format_equiv_evidence(
                    proposal=proposal,
                    proposal_omega=proposal_omega,
                    node=node,
                    candidates=candidates,
                    scores_hint=scores_hint,
                )
                v = self.mllm.verify_equivalence(
                    new_label=str(proposal.get("name", "")),
                    new_syn=[str(x) for x in (proposal.get("syn", []) or [])],
                    old_label=node.label,
                    old_syn=node.synonyms,
                    evidence=evidence,
                )
                if bool(v.get("same", False)) and float(v.get("conf", 0.0)) >= 0.6:
                    merge_node_id = node_id
                    canonical = str(v.get("canonical", "")).strip()
                    if canonical:
                        proposal = dict(proposal)
                        proposal["name"] = canonical

        # Create new node
        if merge_node_id is None:
            node = SemanticNode(
                node_id=new_node_id(),
                label=str(proposal.get("name", "")).strip() or "unknown",
                desc="",
                synonyms=[str(x) for x in (proposal.get("syn", []) or [])],
                text_emb=proposal_text_emb,
                omega=set(proposal_omega),
                r_exist=float(proposal.get("conf", 0.5)),
                p_target=0.0,
                last_seen_t=t,
            )
            self.add_node(node)
            return node.node_id

        # Merge into existing node
        self._merge_into(
            node_id=merge_node_id,
            proposal=proposal,
            proposal_omega=proposal_omega,
            t=t,
        )
        return merge_node_id

    def _merge_into(
        self,
        node_id: str,
        proposal: Dict[str, Any],
        proposal_omega: Set[str],
        t: int,
    ) -> None:
        """
        Merge the new proposal into an existing node.
        We do not overwrite labels aggressively to avoid semantic drift.
        """
        node = self.nodes[node_id]

        # Update synonyms conservatively
        new_label = str(proposal.get("name", "")).strip()
        if new_label and new_label.lower() != node.label.lower():
            if new_label not in node.synonyms:
                node.synonyms.append(new_label)

        for s in proposal.get("syn", []) or []:
            s = str(s).strip()
            if s and s.lower() != node.label.lower() and s not in node.synonyms:
                node.synonyms.append(s)

        # Refresh node embedding after synonym updates
        node.text_emb = self.text_embedder.embed(self._node_text(node))

        # Update Omega using union. Replace with decay if needed.
        node.omega |= set(proposal_omega)

        # Smooth update for existence confidence
        prop_conf = float(proposal.get("conf", 0.5))
        node.r_exist = float(np.clip(0.8 * node.r_exist + 0.2 * prop_conf, 0.0, 1.0))

        node.last_seen_t = t

    def _format_equiv_evidence(
        self,
        proposal: Dict[str, Any],
        proposal_omega: Set[str],
        node: SemanticNode,
        candidates: List[Tuple[float, float, float, str]],
        scores_hint: Optional[Dict[str, float]],
    ) -> str:
        """
        Provide short evidence to the MLLM verifier so it can decide "same vs different"
        without seeing the whole world state.

        Evidence is returned as a JSON string so your MLLM prompt can include it directly.
        """
        best_sim, best_text, best_iou, _ = candidates[0]
        evidence: Dict[str, Any] = {
            "best_similarity": {
                "combined": best_sim,
                "text": best_text,
                "iou": best_iou,
            },
            "proposal_name": str(proposal.get("name", "")),
            "proposal_syn": proposal.get("syn", []) or [],
            "old_name": node.label,
            "old_syn": node.synonyms[:8],
            "omega_overlap_size": len(set(proposal_omega) & set(node.omega)),
            "omega_proposal_size": len(proposal_omega),
            "omega_old_size": len(node.omega),
        }
        if scores_hint:
            top_vps = sorted(
                scores_hint.keys(), key=lambda k: scores_hint[k], reverse=True
            )[:5]
            evidence["proposal_top_viewpoints"] = [
                (vp, float(scores_hint[vp])) for vp in top_vps
            ]
        return json.dumps(evidence)
