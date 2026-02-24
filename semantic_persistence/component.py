"""
component.py

High-level wrapper that runs the full loop per time step:

  proposals (MLLM)
      -> grounding (retrieval)
          -> match/merge (deterministic + optional MLLM verifier)
              -> persistent semantic graph update

Then, after a viewpoint is visited, you call update_after_visit to update beliefs.
"""


from typing import Dict, List, Optional, Set
import numpy as np

from .interfaces import MLLMClient, TextEmbedder
from .data_structures import ViewpointBank
from .grounding import RetrievalGrounder
from .matching import MatchConfig, SemanticGraph
from .beliefs import BeliefUpdater


class SemanticPersistenceComponent:
    def __init__(
        self,
        mllm: MLLMClient,
        text_embedder: TextEmbedder,
        grounder: RetrievalGrounder,
        match_cfg: Optional[MatchConfig] = None,
    ):
        """
        Parameters:
          mllm:
            Used for proposals and rare equivalence checks.

          text_embedder:
            Used for grounding and matching.

          grounder:
            Computes Omega_s for a semantic label.

          match_cfg:
            Thresholds and weights for merge decisions.
        """
        self.mllm = mllm
        self.graph = SemanticGraph(
            text_embedder=text_embedder, mllm=mllm, match_cfg=match_cfg
        )
        self.grounder = grounder
        self.beliefs = BeliefUpdater()

    def step(
        self,
        t: int,
        scan_id: str,
        vp_bank: ViewpointBank,
        instruction: str,
        observation_images: List[np.ndarray],
        memory_summary: str,
        max_proposals: int = 6,
    ) -> List[str]:
        """
        Run one semantic update step.

        Returns:
          List of node_id that were created or merged this step.
        """
        proposals = self.mllm.propose_semantic_nodes(
            instruction=instruction,
            observation_images=observation_images,
            memory_summary=memory_summary,
            max_proposals=max_proposals,
        )

        touched: List[str] = []
        for p in proposals:
            name = str(p.get("name", "")).strip()
            if not name:
                continue

            # Ground proposal label into a viewpoint set Omega_s
            omega, scores = self.grounder.ground(vp_bank, text=name)

            # Merge into persistent graph (or create new node)
            node_id = self.graph.match_and_merge(
                proposal=p,
                proposal_omega=omega,
                t=t,
                proposal_text_emb=None,
                scores_hint=scores,
            )
            touched.append(node_id)

        return touched

    def update_after_visit(
        self,
        t: int,
        scan_id: str,
        visited_vp_id: str,
        found_target: bool,
        membership_scores: Optional[Dict[str, float]] = None,
        contradict_nodes: Optional[Set[str]] = None,
    ) -> None:
        """
        Call after the agent visits a viewpoint.

        membership_scores:
          node_id -> how much this visited viewpoint supports that node.

        found_target:
          If True, p_target will jump to 1.0 for all nodes you update,
          unless you decide to update only specific nodes.

        contradict_nodes:
          node_ids that you consider refuted by the current observation.
        """
        self.beliefs.batch_update_after_visit(
            nodes=self.graph.nodes,
            t=t,
            scan_id=scan_id,
            visited_vp_id=visited_vp_id,
            found_target=found_target,
            membership_scores=membership_scores,
            contradict_nodes=contradict_nodes,
        )
