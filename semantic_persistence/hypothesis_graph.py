"""
hypothesis_graph.py

Persistent hypothesis graph built from repeated MLLM semantic proposals.

The graph is intentionally lightweight:
  - each node is a hypothesized semantic region / future viewpoint
  - each edge is a hypothesized direct connection between two regions
  - repeated observations update probabilities instead of replacing them

Important modeling rule:
  - one grounded node corresponds to one physical viewpoint
  - ungrounded neighbor proposals remain separate hypotheses until a future
    current observation validates one of them

This keeps the online state easy to inspect and easy to feed into a planner later.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from .data_structures import new_node_id


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    """Clamp a scalar into a closed interval."""
    return max(low, min(high, float(value)))


def _safe_float(value: Any, default: float = 0.0) -> float:
    """Convert arbitrary values to float without throwing."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _canonicalize_label(label: str) -> str:
    """
    Normalize a label for matching while keeping node ids stable.

    We still canonicalize labels to compare semantic classes, but node identity is
    no longer derived from the label alone because multiple viewpoints may share
    the same room category.
    """
    label = str(label or "").strip().lower()
    label = re.sub(r"[^a-z0-9\s]+", " ", label)
    label = re.sub(r"\s+", " ", label)
    return label.strip()


def _clean_note(note: Any) -> str:
    """Normalize a short free-form note emitted by the MLLM."""
    note = str(note or "").strip()
    note = re.sub(r"\s+", " ", note)
    return note[:160]


def _edge_key(node_a_id: str, node_b_id: str) -> Tuple[str, str]:
    """Store edges with an order-invariant key because region links are symmetric."""
    if node_a_id <= node_b_id:
        return (node_a_id, node_b_id)
    return (node_b_id, node_a_id)


@dataclass
class HypothesisNode:
    """
    Persistent semantic-region hypothesis.

    `mapped_viewpoint` is the decisive grounding field. It stays empty for pure
    hypotheses and becomes a single viewpoint id once the node is validated as a
    current region at that physical location.
    """

    node_id: str
    label: str
    canonical_label: str
    note: str = ""
    aliases: Set[str] = field(default_factory=set)
    existence_prob: float = 0.5
    target_prob: float = 0.0
    observation_count: int = 0
    grounded_viewpoints: Set[str] = field(default_factory=set)
    mapped_viewpoint: str = ""
    proposed_from_viewpoints: Set[str] = field(default_factory=set)
    last_observed_step: int = 0
    last_observed_scan: str = ""
    last_observed_from_vp: str = ""
    evidence_log: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class HypothesisEdge:
    """Persistent connectivity hypothesis between two semantic nodes."""

    edge_id: str
    node_a_id: str
    node_b_id: str
    connection_prob: float = 0.0
    travel_distance: float = -1.0
    observation_count: int = 0
    distance_observation_count: int = 0
    last_observed_step: int = 0
    evidence_log: List[Dict[str, Any]] = field(default_factory=list)


class HypothesisGraph:
    """
    Online graph memory for structural uncertainty.

    The graph consumes one MLLM response at a time and incrementally maintains:
      - persistent semantic nodes for both grounded viewpoints and ungrounded guesses
      - probabilistic region-to-region edges
      - a strict viewpoint -> node binding for validated current regions
    """

    def __init__(self, target_object: str = ""):
        self.target_object = str(target_object or "").strip()
        self.nodes: Dict[str, HypothesisNode] = {}
        self.edges: Dict[Tuple[str, str], HypothesisEdge] = {}
        self._vp_to_node_id: Dict[str, str] = {}
        self.observation_step: int = 0
        self.visited_viewpoints: Set[str] = set()
        self.last_current_node_id: Optional[str] = None

    @staticmethod
    def _running_average(
        previous: float, new_value: float, previous_count: int
    ) -> float:
        """
        Update a belief with a simple count-based average.

        This keeps the graph stable over time while still letting fresh evidence
        move the estimate when the node has only been observed a few times.
        """
        if previous_count <= 0:
            return float(new_value)
        return float(((previous * previous_count) + new_value) / (previous_count + 1))

    def _create_node(self, label: str, note: str = "") -> Optional[HypothesisNode]:
        """
        Allocate a brand-new node instead of deduplicating globally by label.

        This is the core change that lets multiple viewpoints share the same
        semantic label without being collapsed into a single node.
        """
        surface_label = str(label or "").strip()
        canonical_label = _canonicalize_label(surface_label)
        if not canonical_label:
            return None

        node = HypothesisNode(
            node_id=new_node_id("HGN"),
            label=surface_label,
            canonical_label=canonical_label,
            note=_clean_note(note),
            aliases={surface_label},
        )
        self.nodes[node.node_id] = node
        return node

    def _get_node(self, node_id: str) -> Optional[HypothesisNode]:
        """Small helper so all id lookups stay uniform."""
        return self.nodes.get(str(node_id or "").strip())

    def _touch_node_surface(
        self,
        node: HypothesisNode,
        label: str,
        note: str = "",
    ) -> None:
        """
        Refresh the user-facing label/note while keeping the stable node id.

        We update the surface form because the model may provide a cleaner label or
        a more useful short note after seeing the viewpoint again.
        """
        surface_label = str(label or "").strip()
        if surface_label:
            node.label = surface_label
            node.aliases.add(surface_label)
            canonical_label = _canonicalize_label(surface_label)
            if canonical_label:
                node.canonical_label = canonical_label

        cleaned_note = _clean_note(note)
        if cleaned_note:
            node.note = cleaned_note

    def _bind_node_to_viewpoint(self, node: HypothesisNode, viewpoint_id: str) -> bool:
        """
        Enforce the 1:1 relationship between a grounded node and a physical viewpoint.

        A node may remain ungrounded for many steps, but once grounded it must never
        silently migrate to another viewpoint.
        """
        viewpoint_id = str(viewpoint_id or "").strip()
        if not viewpoint_id:
            return False

        existing_node_id = self._vp_to_node_id.get(viewpoint_id)
        if existing_node_id and existing_node_id != node.node_id:
            return False

        if node.mapped_viewpoint and node.mapped_viewpoint != viewpoint_id:
            return False

        node.mapped_viewpoint = viewpoint_id
        node.grounded_viewpoints = {viewpoint_id}
        self._vp_to_node_id[viewpoint_id] = node.node_id
        return True

    def _get_edge(
        self, node_a_id: Optional[str], node_b_id: Optional[str]
    ) -> Optional[HypothesisEdge]:
        """Return the symmetric edge between two nodes if it already exists."""
        if not node_a_id or not node_b_id:
            return None
        return self.edges.get(_edge_key(node_a_id, node_b_id))

    def _iter_adjacent_edges(self, node_id: str) -> List[Tuple[HypothesisEdge, str]]:
        """
        Collect all edges adjacent to one node.

        Returning both the edge and the opposite node id keeps the caller logic
        simple when building prompt context or matching a prior hypothesis.
        """
        adjacent: List[Tuple[HypothesisEdge, str]] = []
        for edge in self.edges.values():
            if edge.node_a_id == node_id:
                adjacent.append((edge, edge.node_b_id))
            elif edge.node_b_id == node_id:
                adjacent.append((edge, edge.node_a_id))
        return adjacent

    def _nodes_with_canonical_label(
        self,
        canonical_label: str,
        grounded: Optional[bool] = None,
    ) -> List[HypothesisNode]:
        """
        Return nodes that share a canonical label.

        The optional `grounded` filter lets the caller explicitly choose between
        future hypothesis nodes and already validated viewpoint nodes.
        """
        candidates: List[HypothesisNode] = []
        for node in self.nodes.values():
            if node.canonical_label != canonical_label:
                continue
            if grounded is None:
                candidates.append(node)
                continue
            if bool(node.mapped_viewpoint) == bool(grounded):
                candidates.append(node)
        return candidates

    def _candidate_rank(
        self,
        node: HypothesisNode,
        anchor_node_id: Optional[str] = None,
        preferred_source_vp: str = "",
        note: str = "",
    ) -> Tuple[float, ...]:
        """
        Rank node-reuse candidates using local structural evidence first.

        The ranking is intentionally simple and deterministic:
          1. directly adjacent to the previous/current node
          2. previously proposed from the same source viewpoint
          3. matching note text if available
          4. stronger connectivity / existence / recency
        """
        edge = self._get_edge(anchor_node_id, node.node_id)
        cleaned_note = _clean_note(note)
        note_match = (
            1.0
            if cleaned_note and node.note and node.note.lower() == cleaned_note.lower()
            else 0.0
        )
        return (
            1.0 if edge is not None else 0.0,
            1.0
            if preferred_source_vp and preferred_source_vp in node.proposed_from_viewpoints
            else 0.0,
            note_match,
            edge.connection_prob if edge is not None else -1.0,
            node.existence_prob,
            node.target_prob,
            float(node.observation_count),
            float(node.last_observed_step),
        )

    def _resolve_current_node(
        self,
        current_vp: str,
        label: str,
        note: str = "",
        requested_node_id: str = "",
    ) -> Optional[HypothesisNode]:
        """
        Resolve the current_region node using viewpoint identity first.

        Resolution order:
          1. reuse the node already bound to this viewpoint
          2. reuse an explicit model-selected node id if it is still ungrounded
          3. reuse an adjacent ungrounded hypothesis from the previous current node
          4. reuse the single remaining ungrounded node with the same label
          5. create a fresh grounded node for this viewpoint
        """
        current_vp = str(current_vp or "").strip()
        if current_vp and current_vp in self._vp_to_node_id:
            return self._get_node(self._vp_to_node_id[current_vp])

        canonical_label = _canonicalize_label(label)
        if not canonical_label:
            return None

        # If the prompt returned a node id, trust it only when that node is still
        # compatible with this viewpoint. A node already grounded elsewhere must not
        # be reused for a new viewpoint.
        if requested_node_id:
            hinted_node = self._get_node(requested_node_id)
            if (
                hinted_node is not None
                and hinted_node.canonical_label == canonical_label
                and (
                    not hinted_node.mapped_viewpoint
                    or hinted_node.mapped_viewpoint == current_vp
                )
            ):
                return hinted_node

        previous_node = self._get_node(self.last_current_node_id or "")
        previous_vp = "" if previous_node is None else previous_node.mapped_viewpoint

        # The most important merge rule: if the new current label matches a prior
        # neighbor hypothesis reachable from the previous current node, bind this new
        # viewpoint to that hypothesis node instead of creating a duplicate.
        adjacent_candidates: List[HypothesisNode] = []
        if previous_node is not None:
            for edge, other_node_id in self._iter_adjacent_edges(previous_node.node_id):
                other_node = self._get_node(other_node_id)
                if other_node is None:
                    continue
                if other_node.canonical_label != canonical_label:
                    continue
                if other_node.mapped_viewpoint and other_node.mapped_viewpoint != current_vp:
                    continue
                adjacent_candidates.append(other_node)

        if adjacent_candidates:
            return max(
                adjacent_candidates,
                key=lambda node: self._candidate_rank(
                    node=node,
                    anchor_node_id=previous_node.node_id if previous_node else None,
                    preferred_source_vp=previous_vp,
                    note=note,
                ),
            )

        ungrounded_candidates = self._nodes_with_canonical_label(
            canonical_label, grounded=False
        )
        if len(ungrounded_candidates) == 1:
            return ungrounded_candidates[0]
        if ungrounded_candidates:
            return max(
                ungrounded_candidates,
                key=lambda node: self._candidate_rank(
                    node=node,
                    anchor_node_id=self.last_current_node_id,
                    preferred_source_vp=previous_vp,
                    note=note,
                ),
            )

        return self._create_node(label=label, note=note)

    def _resolve_neighbor_node(
        self,
        current_node: Optional[HypothesisNode],
        label: str,
        note: str = "",
        requested_node_id: str = "",
    ) -> Optional[HypothesisNode]:
        """
        Resolve one neighbor hypothesis without forcing a new viewpoint binding.

        Unlike current_region, a neighbor is allowed to match an already grounded
        node because the current observation may be looking toward a known place.
        If no safe match exists, we allocate a new ungrounded hypothesis node.
        """
        canonical_label = _canonicalize_label(label)
        if not canonical_label:
            return None

        if requested_node_id:
            hinted_node = self._get_node(requested_node_id)
            if (
                hinted_node is not None
                and hinted_node.canonical_label == canonical_label
                and (current_node is None or hinted_node.node_id != current_node.node_id)
            ):
                return hinted_node

        current_vp = "" if current_node is None else current_node.mapped_viewpoint
        anchor_node_id = None if current_node is None else current_node.node_id

        # First try to reuse a node already connected to the current node. This helps
        # the graph stay stable across revisits and loop closures.
        adjacent_candidates: List[HypothesisNode] = []
        if current_node is not None:
            for edge, other_node_id in self._iter_adjacent_edges(current_node.node_id):
                other_node = self._get_node(other_node_id)
                if other_node is None:
                    continue
                if other_node.canonical_label != canonical_label:
                    continue
                if other_node.node_id == current_node.node_id:
                    continue
                adjacent_candidates.append(other_node)

        if adjacent_candidates:
            return max(
                adjacent_candidates,
                key=lambda node: self._candidate_rank(
                    node=node,
                    anchor_node_id=anchor_node_id,
                    preferred_source_vp=current_vp,
                    note=note,
                ),
            )

        # Next reuse hypotheses proposed from the same source viewpoint. This keeps
        # repeated scans from cloning the same unseen neighbor again and again.
        label_matches = self._nodes_with_canonical_label(canonical_label, grounded=None)
        source_matches = [
            node
            for node in label_matches
            if node.node_id != (current_node.node_id if current_node else "")
            and current_vp
            and current_vp in node.proposed_from_viewpoints
        ]
        if source_matches:
            return max(
                source_matches,
                key=lambda node: self._candidate_rank(
                    node=node,
                    anchor_node_id=anchor_node_id,
                    preferred_source_vp=current_vp,
                    note=note,
                ),
            )

        ungrounded_matches = [
            node
            for node in label_matches
            if node.node_id != (current_node.node_id if current_node else "")
            and not node.mapped_viewpoint
        ]
        if len(ungrounded_matches) == 1:
            return ungrounded_matches[0]

        return self._create_node(label=label, note=note)

    def _update_node_observation(
        self,
        node: HypothesisNode,
        label: str,
        note: str,
        existence_prob: float,
        target_prob: Optional[float],
        scan_id: str,
        observed_from_vp: str,
        observation_step: int,
        grounded_viewpoint: Optional[str] = None,
        proposed_from_viewpoint: Optional[str] = None,
        direct_target_detection: bool = False,
    ) -> HypothesisNode:
        """
        Update one node once its identity has already been resolved.

        Splitting resolution from belief updates keeps the viewpoint-matching logic
        readable and makes the node update itself easy to inspect.
        """
        self._touch_node_surface(node=node, label=label, note=note)

        node.existence_prob = _clamp(
            self._running_average(
                previous=node.existence_prob,
                new_value=_clamp(existence_prob),
                previous_count=node.observation_count,
            )
        )

        if target_prob is not None:
            target_prob = _clamp(target_prob)
            if direct_target_detection:
                # A direct detection in the current region is stronger evidence than
                # a neighbor prior, so do not average it down immediately.
                node.target_prob = max(node.target_prob, target_prob)
            else:
                node.target_prob = _clamp(
                    self._running_average(
                        previous=node.target_prob,
                        new_value=target_prob,
                        previous_count=node.observation_count,
                    )
                )

        node.observation_count += 1
        node.last_observed_step = int(observation_step)
        node.last_observed_scan = str(scan_id or "")
        node.last_observed_from_vp = str(observed_from_vp or "")

        if proposed_from_viewpoint:
            node.proposed_from_viewpoints.add(str(proposed_from_viewpoint))

        if grounded_viewpoint:
            self._bind_node_to_viewpoint(node, grounded_viewpoint)

        node.evidence_log.append(
            {
                "step": int(observation_step),
                "scan_id": str(scan_id or ""),
                "observed_from_vp": str(observed_from_vp or ""),
                "grounded_viewpoint": str(grounded_viewpoint or ""),
                "proposed_from_viewpoint": str(proposed_from_viewpoint or ""),
                "existence_prob": float(_clamp(existence_prob)),
                "target_prob": None if target_prob is None else float(target_prob),
                "note": _clean_note(note),
                "direct_target_detection": bool(direct_target_detection),
            }
        )
        return node

    def _observe_edge(
        self,
        node_a: HypothesisNode,
        node_b: HypothesisNode,
        connection_prob: float,
        travel_distance: float,
        observation_step: int,
        source_labels: Tuple[str, str],
    ) -> Optional[HypothesisEdge]:
        """
        Create/update one symmetric edge hypothesis.

        We now keep only direct edges with valid positive distances. This removes the
        earlier "unknown distance" clutter that came from forcing all pairwise links
        in the prompt output.
        """
        if node_a.node_id == node_b.node_id:
            return None

        travel_distance = _safe_float(travel_distance, default=-1.0)
        if travel_distance <= 0.0:
            return None

        key = _edge_key(node_a.node_id, node_b.node_id)
        edge = self.edges.get(key)
        if edge is None:
            edge = HypothesisEdge(
                edge_id=new_node_id("HGE"),
                node_a_id=key[0],
                node_b_id=key[1],
            )
            self.edges[key] = edge

        edge.connection_prob = _clamp(
            self._running_average(
                previous=edge.connection_prob,
                new_value=_clamp(connection_prob),
                previous_count=edge.observation_count,
            )
        )

        edge.travel_distance = self._running_average(
            previous=(
                edge.travel_distance
                if edge.distance_observation_count > 0
                else travel_distance
            ),
            new_value=travel_distance,
            previous_count=edge.distance_observation_count,
        )
        edge.distance_observation_count += 1

        edge.observation_count += 1
        edge.last_observed_step = int(observation_step)
        edge.evidence_log.append(
            {
                "step": int(observation_step),
                "source_labels": [str(source_labels[0]), str(source_labels[1])],
                "connection_prob": float(_clamp(connection_prob)),
                "travel_distance": float(travel_distance),
            }
        )
        return edge

    def _node_prompt_record(
        self, node: Optional[HypothesisNode]
    ) -> Optional[Dict[str, Any]]:
        """Build the compact node payload injected into the MLLM prompt."""
        if node is None:
            return None
        return {
            "node_id": node.node_id,
            "label": node.label,
            "note": node.note,
            "mapped_viewpoint": node.mapped_viewpoint,
            "is_grounded": bool(node.mapped_viewpoint),
            "existence_prob": float(node.existence_prob),
            "target_prob": float(node.target_prob),
        }

    def build_mllm_context(
        self,
        current_vp: str,
        max_grounded_nodes: int = 12,
        max_neighbor_candidates: int = 8,
    ) -> Dict[str, Any]:
        """
        Export compact graph context for the next MLLM call.

        The prompt only needs the current viewpoint binding, the previously active
        node, and a small set of reusable nodes/edges. Keeping this summary short
        makes the prompt more stable and avoids wasting tokens on the full graph.
        """
        current_vp = str(current_vp or "").strip()
        known_current_node = (
            self._get_node(self._vp_to_node_id[current_vp])
            if current_vp and current_vp in self._vp_to_node_id
            else None
        )
        previous_current_node = self._get_node(self.last_current_node_id or "")

        grounded_nodes = sorted(
            [node for node in self.nodes.values() if node.mapped_viewpoint],
            key=lambda node: (
                node.last_observed_step,
                node.target_prob,
                node.existence_prob,
            ),
            reverse=True,
        )

        neighbor_candidates: List[Dict[str, Any]] = []
        if previous_current_node is not None:
            adjacent = sorted(
                self._iter_adjacent_edges(previous_current_node.node_id),
                key=lambda item: (
                    item[0].connection_prob,
                    item[0].travel_distance,
                    self.nodes[item[1]].last_observed_step if item[1] in self.nodes else -1,
                ),
                reverse=True,
            )
            for edge, other_node_id in adjacent[:max_neighbor_candidates]:
                other_node = self._get_node(other_node_id)
                if other_node is None:
                    continue
                neighbor_candidates.append(
                    {
                        "node": self._node_prompt_record(other_node),
                        "connection_prob": float(edge.connection_prob),
                        "travel_distance": float(edge.travel_distance),
                    }
                )

        return {
            "current_viewpoint": current_vp,
            "known_current_node": self._node_prompt_record(known_current_node),
            "previous_current_node": self._node_prompt_record(previous_current_node),
            "grounded_nodes": [
                self._node_prompt_record(node)
                for node in grounded_nodes[:max_grounded_nodes]
            ],
            "neighbor_candidates": neighbor_candidates,
        }

    def update_from_mllm(
        self,
        scan_id: str,
        current_vp: str,
        mllm_output: Dict[str, Any],
        observation_step: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Ingest one normalized MLLM payload and update the persistent graph.

        Expected input shape:
          {
            "current_region": {
                "node_id": "...",
                "label": "...",
                "confidence": ...,
                "note": "..."
            },
            "neighbor_regions": [
                {
                    "node_id": "...",
                    "label": "...",
                    "existence_prob": ...,
                    "target_prob": ...,
                    "note": "..."
                }
            ],
            "region_connections": [
                {
                    "region_a": "...",
                    "region_b": "...",
                    "connection_prob": ...,
                    "travel_distance": ...
                }
            ],
            "target": {"found": ..., "confidence": [...]}
          }
        """
        if observation_step is None:
            self.observation_step += 1
        else:
            self.observation_step = max(self.observation_step, int(observation_step))

        step = self.observation_step
        current_vp = str(current_vp or "")
        if current_vp:
            self.visited_viewpoints.add(current_vp)

        current_region = mllm_output.get("current_region", {}) or {}
        neighbor_regions = mllm_output.get("neighbor_regions", []) or []
        region_connections = mllm_output.get("region_connections", []) or []
        target = mllm_output.get("target", {}) or {}

        direct_target_prob = 0.0
        if bool(target.get("found", False)):
            confidence_values = target.get("confidence", [])
            if isinstance(confidence_values, list) and confidence_values:
                direct_target_prob = max(
                    _safe_float(value, 0.0) for value in confidence_values
                )

        # We key this local lookup by the surface label emitted in the current MLLM
        # payload because region_connections refer to the labels from the same output.
        local_nodes_by_label: Dict[str, HypothesisNode] = {}
        updated_node_ids: List[str] = []
        updated_edge_ids: List[str] = []

        current_label = str(current_region.get("label", "")).strip()
        current_note = _clean_note(current_region.get("note", ""))
        current_node = self._resolve_current_node(
            current_vp=current_vp,
            label=current_label,
            note=current_note,
            requested_node_id=str(current_region.get("node_id", "")).strip(),
        )

        if current_node is not None:
            current_confidence = _clamp(
                _safe_float(current_region.get("confidence", 0.0), 0.0)
            )
            current_node = self._update_node_observation(
                node=current_node,
                label=current_label,
                note=current_note,
                existence_prob=current_confidence,
                target_prob=direct_target_prob if direct_target_prob > 0.0 else None,
                scan_id=scan_id,
                observed_from_vp=current_vp,
                observation_step=step,
                grounded_viewpoint=current_vp,
                direct_target_detection=direct_target_prob > 0.0,
            )
            local_nodes_by_label[current_label] = current_node
            updated_node_ids.append(current_node.node_id)
            self.last_current_node_id = current_node.node_id

        # Neighbor regions stay ungrounded until a future current observation lands
        # on them, but we still try to reuse existing hypotheses or loop-closure nodes.
        for neighbor in neighbor_regions:
            label = str(neighbor.get("label", "")).strip()
            note = _clean_note(neighbor.get("note", ""))
            neighbor_node = self._resolve_neighbor_node(
                current_node=current_node,
                label=label,
                note=note,
                requested_node_id=str(neighbor.get("node_id", "")).strip(),
            )
            if neighbor_node is None:
                continue

            neighbor_node = self._update_node_observation(
                node=neighbor_node,
                label=label,
                note=note,
                existence_prob=_safe_float(neighbor.get("existence_prob", 0.0), 0.0),
                target_prob=_safe_float(neighbor.get("target_prob", 0.0), 0.0),
                scan_id=scan_id,
                observed_from_vp=current_vp,
                observation_step=step,
                proposed_from_viewpoint=current_vp,
            )
            local_nodes_by_label[label] = neighbor_node
            updated_node_ids.append(neighbor_node.node_id)

        # Connections now describe direct links only, so we no longer create nodes
        # solely from orphan edge labels. An edge is useful only if both endpoints are
        # already present in the current local proposal set.
        for connection in region_connections:
            region_a = str(connection.get("region_a", "")).strip()
            region_b = str(connection.get("region_b", "")).strip()
            if not region_a or not region_b or region_a == region_b:
                continue

            node_a = local_nodes_by_label.get(region_a)
            node_b = local_nodes_by_label.get(region_b)
            if node_a is None or node_b is None:
                continue

            edge = self._observe_edge(
                node_a=node_a,
                node_b=node_b,
                connection_prob=_safe_float(
                    connection.get("connection_prob", 0.0), 0.0
                ),
                travel_distance=_safe_float(
                    connection.get("travel_distance", -1.0), -1.0
                ),
                observation_step=step,
                source_labels=(region_a, region_b),
            )
            if edge is not None:
                updated_edge_ids.append(edge.edge_id)

        return {
            "step": step,
            "current_node_id": None if current_node is None else current_node.node_id,
            "updated_node_ids": list(dict.fromkeys(updated_node_ids)),
            "updated_edge_ids": list(dict.fromkeys(updated_edge_ids)),
        }

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the graph into a planner/debug-friendly dictionary."""
        nodes = []
        for node in self.nodes.values():
            nodes.append(
                {
                    "node_id": node.node_id,
                    "label": node.label,
                    "canonical_label": node.canonical_label,
                    "note": node.note,
                    "aliases": sorted(node.aliases),
                    "existence_prob": float(node.existence_prob),
                    "target_prob": float(node.target_prob),
                    "observation_count": int(node.observation_count),
                    "grounded_viewpoints": sorted(node.grounded_viewpoints),
                    "mapped_viewpoint": node.mapped_viewpoint,
                    "proposed_from_viewpoints": sorted(node.proposed_from_viewpoints),
                    "last_observed_step": int(node.last_observed_step),
                    "last_observed_scan": node.last_observed_scan,
                    "last_observed_from_vp": node.last_observed_from_vp,
                }
            )

        edges = []
        for edge in self.edges.values():
            edges.append(
                {
                    "edge_id": edge.edge_id,
                    "node_a_id": edge.node_a_id,
                    "node_b_id": edge.node_b_id,
                    "connection_prob": float(edge.connection_prob),
                    "travel_distance": float(edge.travel_distance),
                    "observation_count": int(edge.observation_count),
                    "distance_observation_count": int(edge.distance_observation_count),
                    "last_observed_step": int(edge.last_observed_step),
                }
            )

        return {
            "target_object": self.target_object,
            "observation_step": int(self.observation_step),
            "visited_viewpoints": sorted(self.visited_viewpoints),
            "last_current_node_id": self.last_current_node_id,
            "viewpoint_to_node_id": dict(self._vp_to_node_id),
            "nodes": nodes,
            "edges": edges,
        }

    def format_summary(self, max_nodes: int = 8, max_edges: int = 8) -> str:
        """
        Build a compact text summary for debugging in the main navigation loop.

        The summary now explicitly shows whether a node is already bound to a
        viewpoint and carries the short note generated by the MLLM.
        """
        lines = [
            (
                f"[HypothesisGraph] step={self.observation_step} "
                f"nodes={len(self.nodes)} edges={len(self.edges)} "
                f"visited_vps={len(self.visited_viewpoints)}"
            )
        ]

        sorted_nodes = sorted(
            self.nodes.values(),
            key=lambda node: (
                bool(node.mapped_viewpoint),
                node.target_prob,
                node.existence_prob,
                node.observation_count,
            ),
            reverse=True,
        )

        # grounded={len(node.grounded_viewpoints)} behaves like a binary signal in
        # normal operation because each validated node maps to exactly one viewpoint.
        for node in sorted_nodes[:max_nodes]:
            vp_text = node.mapped_viewpoint if node.mapped_viewpoint else "unbound"
            note_text = f" | note={node.note}" if node.note else ""
            lines.append(
                "  "
                + (
                    f"NODE {node.node_id} | {node.label} | exist={node.existence_prob:.2f} "
                    f"| target={node.target_prob:.2f} | obs={node.observation_count} "
                    f"| grounded={len(node.grounded_viewpoints)} | vp={vp_text}"
                    f"{note_text}"
                )
            )

        sorted_edges = sorted(
            self.edges.values(),
            key=lambda edge: (
                edge.connection_prob,
                edge.travel_distance,
            ),
            reverse=True,
        )
        for edge in sorted_edges[:max_edges]:
            node_a = self.nodes.get(edge.node_a_id)
            node_b = self.nodes.get(edge.node_b_id)
            label_a = node_a.label if node_a is not None else edge.node_a_id
            label_b = node_b.label if node_b is not None else edge.node_b_id
            lines.append(
                "  "
                + (
                    f"EDGE {edge.edge_id} | {label_a} <-> {label_b} "
                    f"| conn={edge.connection_prob:.2f} | dist={edge.travel_distance:.2f}m "
                    f"| obs={edge.observation_count}"
                )
            )

        return "\n".join(lines)
