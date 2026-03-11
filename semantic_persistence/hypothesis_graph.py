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


def _surface_region_label(label: str) -> str:
    """Drop the grounded viewpoint suffix while preserving the region instance id."""
    label = str(label or "").strip()
    label = re.sub(r"\s*-vp-\d+\s*$", "", label, flags=re.IGNORECASE)
    label = re.sub(r"\s+", " ", label)
    return label.strip()


def _canonicalize_label(label: str) -> str:
    """
    Normalize a region-instance label for matching while keeping node ids stable.

    Grounded labels like `dining area-1-vp-17` and ungrounded hypotheses like
    `dining area-1` should match the same semantic region instance.
    """
    label = _surface_region_label(label).lower()
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
    region_label: str
    canonical_label: str
    note: str = ""
    aliases: Set[str] = field(default_factory=set)
    existence_prob: float = 0.5
    target_prob: float = 0.0
    observation_count: int = 0  # of times observed as current or neighbor
    grounded_viewpoints: Set[str] = field(
        default_factory=set
    )  # viewpoints that have validated this node as current_region
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
        self.graph_context: Dict[str, Any] = self._empty_graph_context()

    @staticmethod
    def _empty_graph_context() -> Dict[str, Any]:
        return {
            "label_names": [],
            "label_existence_probs": [],
            "label_target_probs": [],
            "label_connection_ajacent_matrix": [],
            "label_distance_ajacent_matrix": [],
            "label_assigns": {},
            "viewpoints_target_confidences": {},
        }

    @classmethod
    def _normalize_graph_context(cls, raw_context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not isinstance(raw_context, dict):
            return cls._empty_graph_context()

        raw_labels = raw_context.get("label_names", []) or []
        raw_existence = raw_context.get("label_existence_probs", []) or []
        raw_target = raw_context.get("label_target_probs", []) or []
        raw_connection = raw_context.get("label_connection_ajacent_matrix", []) or []
        raw_distance = raw_context.get("label_distance_ajacent_matrix", []) or []
        raw_assigns = raw_context.get("label_assigns", {}) or {}
        raw_view_confidences = raw_context.get("viewpoints_target_confidences", {}) or {}

        canonical_to_label: Dict[str, str] = {}
        raw_index_by_key: Dict[str, int] = {}
        for idx, raw_label in enumerate(raw_labels):
            label = _surface_region_label(raw_label)
            key = _canonicalize_label(label)
            if not key or key in canonical_to_label:
                continue
            canonical_to_label[key] = label
            raw_index_by_key[key] = idx

        label_names = sorted(canonical_to_label.values(), key=lambda item: item.lower())
        label_lookup = {_canonicalize_label(label): label for label in label_names}

        existence_map: Dict[str, float] = {}
        target_map: Dict[str, float] = {}
        for label in label_names:
            key = _canonicalize_label(label)
            raw_idx = raw_index_by_key.get(key, -1)
            raw_exist = raw_existence[raw_idx] if 0 <= raw_idx < len(raw_existence) else 0.5
            raw_tgt = raw_target[raw_idx] if 0 <= raw_idx < len(raw_target) else 0.0
            existence_map[label] = _clamp(_safe_float(raw_exist, 0.5))
            target_map[label] = _clamp(_safe_float(raw_tgt, 0.0))

        label_assigns: Dict[str, List[int]] = {label: [] for label in label_names}
        assigned_viewpoints: Set[int] = set()
        for raw_label, raw_values in raw_assigns.items():
            label = label_lookup.get(_canonicalize_label(raw_label), "")
            if not label:
                continue
            candidates = raw_values if isinstance(raw_values, list) else [raw_values]
            cleaned: List[int] = []
            for value in candidates:
                try:
                    viewpoint_index = int(value)
                except (TypeError, ValueError):
                    continue
                if viewpoint_index <= 0 or viewpoint_index in assigned_viewpoints:
                    continue
                cleaned.append(viewpoint_index)
                assigned_viewpoints.add(viewpoint_index)
            label_assigns[label] = sorted(cleaned)

        edge_map: Dict[Tuple[str, str], float] = {}
        distance_map: Dict[Tuple[str, str], float] = {}
        for label_a in label_names:
            idx_a = raw_index_by_key.get(_canonicalize_label(label_a), -1)
            if idx_a < 0:
                continue
            for label_b in label_names:
                idx_b = raw_index_by_key.get(_canonicalize_label(label_b), -1)
                if idx_b < 0 or label_a == label_b:
                    continue
                pair_key = tuple(sorted((label_a, label_b), key=lambda item: item.lower()))
                prob = 0.0
                dist = 0.0
                if (
                    isinstance(raw_connection, list)
                    and idx_a < len(raw_connection)
                    and isinstance(raw_connection[idx_a], list)
                    and idx_b < len(raw_connection[idx_a])
                ):
                    prob = _clamp(_safe_float(raw_connection[idx_a][idx_b], 0.0))
                if (
                    isinstance(raw_distance, list)
                    and idx_a < len(raw_distance)
                    and isinstance(raw_distance[idx_a], list)
                    and idx_b < len(raw_distance[idx_a])
                ):
                    dist = max(0.0, _safe_float(raw_distance[idx_a][idx_b], 0.0))
                if prob > 0.0 and dist > 0.0:
                    edge_map[pair_key] = max(edge_map.get(pair_key, 0.0), prob)
                    previous_dist = distance_map.get(pair_key, 0.0)
                    distance_map[pair_key] = dist if previous_dist <= 0.0 else min(previous_dist, dist)

        viewpoint_owner = {}
        for label, assignments in label_assigns.items():
            for viewpoint_index in assignments:
                viewpoint_owner[int(viewpoint_index)] = label

        viewpoints_target_confidences: Dict[str, float] = {}
        for raw_key, raw_value in raw_view_confidences.items():
            try:
                viewpoint_index = int(raw_key)
            except (TypeError, ValueError):
                continue
            if viewpoint_index <= 0 or viewpoint_index not in viewpoint_owner:
                continue
            owner_label = viewpoint_owner[viewpoint_index]
            viewpoints_target_confidences[str(viewpoint_index)] = min(
                _clamp(_safe_float(raw_value, 0.0)),
                target_map.get(owner_label, 0.0),
            )

        label_index = {label: idx for idx, label in enumerate(label_names)}
        size = len(label_names)
        connection_matrix = [[0.0 for _ in range(size)] for _ in range(size)]
        distance_matrix = [[0.0 for _ in range(size)] for _ in range(size)]
        for (label_a, label_b), prob in edge_map.items():
            dist = distance_map.get((label_a, label_b), 0.0)
            if prob <= 0.0 or dist <= 0.0:
                continue
            idx_a = label_index[label_a]
            idx_b = label_index[label_b]
            connection_matrix[idx_a][idx_b] = prob
            connection_matrix[idx_b][idx_a] = prob
            distance_matrix[idx_a][idx_b] = dist
            distance_matrix[idx_b][idx_a] = dist

        return {
            "label_names": label_names,
            "label_existence_probs": [float(existence_map.get(label, 0.5)) for label in label_names],
            "label_target_probs": [float(target_map.get(label, 0.0)) for label in label_names],
            "label_connection_ajacent_matrix": connection_matrix,
            "label_distance_ajacent_matrix": distance_matrix,
            "label_assigns": {label: list(label_assigns.get(label, [])) for label in label_names},
            "viewpoints_target_confidences": {
                key: viewpoints_target_confidences[key]
                for key in sorted(viewpoints_target_confidences.keys(), key=lambda item: int(item))
            },
        }

    @staticmethod
    def _graph_edge_records(graph_context: Dict[str, Any]) -> List[Dict[str, Any]]:
        labels = graph_context.get("label_names", []) or []
        connection_matrix = graph_context.get("label_connection_ajacent_matrix", []) or []
        distance_matrix = graph_context.get("label_distance_ajacent_matrix", []) or []
        records: List[Dict[str, Any]] = []
        for idx_a, label_a in enumerate(labels):
            for idx_b in range(idx_a + 1, len(labels)):
                label_b = labels[idx_b]
                prob = 0.0
                dist = 0.0
                if (
                    idx_a < len(connection_matrix)
                    and isinstance(connection_matrix[idx_a], list)
                    and idx_b < len(connection_matrix[idx_a])
                ):
                    prob = _clamp(_safe_float(connection_matrix[idx_a][idx_b], 0.0))
                if (
                    idx_a < len(distance_matrix)
                    and isinstance(distance_matrix[idx_a], list)
                    and idx_b < len(distance_matrix[idx_a])
                ):
                    dist = max(0.0, _safe_float(distance_matrix[idx_a][idx_b], 0.0))
                if prob > 0.0 and dist > 0.0:
                    records.append(
                        {
                            "A": label_a,
                            "B": label_b,
                            "prob": prob,
                            "dist": dist,
                        }
                    )
        records.sort(
            key=lambda item: (item["prob"], -item["dist"], item["A"].lower(), item["B"].lower()),
            reverse=True,
        )
        return records

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
            region_label=_surface_region_label(surface_label) or surface_label,
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
            node.region_label = _surface_region_label(surface_label) or surface_label
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
            (
                1.0
                if preferred_source_vp
                and preferred_source_vp in node.proposed_from_viewpoints
                else 0.0
            ),
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
                if (
                    other_node.mapped_viewpoint
                    and other_node.mapped_viewpoint != current_vp
                ):
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

    def _resolve_grounded_viewpoint_node(
        self,
        current_node: Optional[HypothesisNode],
        viewpoint_id: str,
        label: str,
        note: str = "",
        requested_node_id: str = "",
    ) -> Optional[HypothesisNode]:
        """
        Resolve one visible physical viewpoint into a dedicated grounded node.

        This mirrors current-region grounding: the physical viewpoint identity wins,
        while ungrounded hypotheses with the same region instance may still be reused.
        """
        viewpoint_id = str(viewpoint_id or "").strip()
        if not viewpoint_id:
            return None
        if viewpoint_id in self._vp_to_node_id:
            return self._get_node(self._vp_to_node_id[viewpoint_id])

        canonical_label = _canonicalize_label(label)
        if not canonical_label:
            return None

        if requested_node_id:
            hinted_node = self._get_node(requested_node_id)
            if (
                hinted_node is not None
                and hinted_node.canonical_label == canonical_label
                and (
                    not hinted_node.mapped_viewpoint
                    or hinted_node.mapped_viewpoint == viewpoint_id
                )
            ):
                return hinted_node

        anchor_node_id = None if current_node is None else current_node.node_id
        preferred_source_vp = "" if current_node is None else current_node.mapped_viewpoint

        adjacent_candidates: List[HypothesisNode] = []
        if current_node is not None:
            for _, other_node_id in self._iter_adjacent_edges(current_node.node_id):
                other_node = self._get_node(other_node_id)
                if other_node is None:
                    continue
                if other_node.canonical_label != canonical_label:
                    continue
                if other_node.mapped_viewpoint and other_node.mapped_viewpoint != viewpoint_id:
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
                    preferred_source_vp=preferred_source_vp,
                    note=note,
                ),
            )

        ungrounded_candidates = self._nodes_with_canonical_label(
            canonical_label,
            grounded=False,
        )
        if len(ungrounded_candidates) == 1:
            return ungrounded_candidates[0]
        if ungrounded_candidates:
            return max(
                ungrounded_candidates,
                key=lambda node: self._candidate_rank(
                    node=node,
                    anchor_node_id=anchor_node_id,
                    preferred_source_vp=preferred_source_vp,
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
                and (
                    current_node is None or hinted_node.node_id != current_node.node_id
                )
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
        self,
        node: Optional[HypothesisNode],
        viewpoint_index_by_vp: Optional[Dict[str, int]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Build the compact node payload injected into the MLLM prompt."""
        if node is None:
            return None
        mapped_viewpoint_index = None
        if viewpoint_index_by_vp is not None and node.mapped_viewpoint:
            mapped_viewpoint_index = viewpoint_index_by_vp.get(node.mapped_viewpoint)
        return {
            "node_id": node.node_id,
            "label": node.label,
            "region_label": node.region_label,
            "note": node.note,
            "mapped_viewpoint": node.mapped_viewpoint,
            "mapped_viewpoint_index": mapped_viewpoint_index,
            "is_grounded": bool(node.mapped_viewpoint),
            "existence_prob": float(node.existence_prob),
            "target_prob": float(node.target_prob),
        }

    def build_mllm_context(
        self,
        current_vp: str,
        viewpoint_index_by_vp: Optional[Dict[str, int]] = None,
        max_grounded_nodes: int = 12,
        max_neighbor_candidates: int = 8,
    ) -> Dict[str, Any]:
        current_vp = str(current_vp or "").strip()
        if current_vp:
            self.visited_viewpoints.add(current_vp)
        self.graph_context = self._normalize_graph_context(self.graph_context)
        return self.graph_context

    def update_from_mllm(
        self,
        scan_id: str,
        current_vp: str,
        mllm_output: Dict[str, Any],
        observation_step: Optional[int] = None,
    ) -> Dict[str, Any]:
        if observation_step is None:
            self.observation_step += 1
        else:
            self.observation_step = max(self.observation_step, int(observation_step))

        step = self.observation_step
        current_vp = str(current_vp or "")
        if current_vp:
            self.visited_viewpoints.add(current_vp)

        previous_graph_context = self._normalize_graph_context(self.graph_context)
        updated_graph_context = self._normalize_graph_context(
            mllm_output.get("updated_graph_context", previous_graph_context)
        )
        if not updated_graph_context["label_names"] and previous_graph_context["label_names"]:
            updated_graph_context = previous_graph_context
        self.graph_context = updated_graph_context

        current_region = mllm_output.get("current_region", {}) or {}
        current_label = _surface_region_label(current_region.get("label", ""))
        if current_label:
            self.last_current_node_id = current_label

        previous_labels = set(previous_graph_context.get("label_names", []))
        current_labels = set(updated_graph_context.get("label_names", []))
        mentioned_labels = set()
        if current_label:
            mentioned_labels.add(current_label)
        for region in mllm_output.get("neighbor_regions", []) or []:
            label = _surface_region_label(region.get("label", ""))
            if label:
                mentioned_labels.add(label)

        previous_edges = {
            f"{edge['A']}|{edge['B']}" for edge in self._graph_edge_records(previous_graph_context)
        }
        current_edges = {
            f"{edge['A']}|{edge['B']}" for edge in self._graph_edge_records(updated_graph_context)
        }
        mentioned_edges = {
            f"{_surface_region_label(edge.get('A', ''))}|{_surface_region_label(edge.get('B', ''))}"
            for edge in mllm_output.get("region_connections", []) or []
            if _surface_region_label(edge.get("A", ""))
            and _surface_region_label(edge.get("B", ""))
            and _surface_region_label(edge.get("A", ""))
            != _surface_region_label(edge.get("B", ""))
        }

        return {
            "step": step,
            "current_node_id": current_label or None,
            "updated_node_ids": sorted(
                mentioned_labels | (current_labels - previous_labels),
                key=lambda item: item.lower(),
            ),
            "updated_edge_ids": sorted(
                mentioned_edges if mentioned_edges else (current_edges - previous_edges),
                key=lambda item: item.lower(),
            ),
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_object": self.target_object,
            "observation_step": int(self.observation_step),
            "visited_viewpoints": sorted(self.visited_viewpoints),
            "last_current_node_id": self.last_current_node_id,
            "graph_context": self._normalize_graph_context(self.graph_context),
        }

    def format_summary(self, max_nodes: int = 8, max_edges: int = 8) -> str:
        graph_context = self._normalize_graph_context(self.graph_context)
        edges = self._graph_edge_records(graph_context)
        lines = [
            (
                f"[HypothesisGraph] step={self.observation_step} "
                f"labels={len(graph_context['label_names'])} edges={len(edges)} "
                f"visited_vps={len(self.visited_viewpoints)}"
            )
        ]

        label_records = []
        for idx, label in enumerate(graph_context.get("label_names", [])):
            label_records.append(
                {
                    "label": label,
                    "exist": float(graph_context["label_existence_probs"][idx]),
                    "target": float(graph_context["label_target_probs"][idx]),
                    "assigns": list(graph_context["label_assigns"].get(label, [])),
                }
            )
        label_records.sort(
            key=lambda item: (item["target"], item["exist"], len(item["assigns"]), item["label"].lower()),
            reverse=True,
        )

        for record in label_records[:max_nodes]:
            assign_text = ",".join(str(item) for item in record["assigns"]) or "-"
            lines.append(
                "  "
                + (
                    f"LABEL {record['label']} | exist={record['exist']:.2f} "
                    f"| target={record['target']:.2f} | assigns=[{assign_text}]"
                )
            )

        for edge in edges[:max_edges]:
            lines.append(
                "  "
                + (
                    f"EDGE {edge['A']} <-> {edge['B']} | conn={edge['prob']:.2f} "
                    f"| dist={edge['dist']:.2f}m"
                )
            )

        viewpoint_confidences = graph_context.get("viewpoints_target_confidences", {}) or {}
        if viewpoint_confidences:
            conf_text = ", ".join(
                f"{key}:{value:.2f}" for key, value in viewpoint_confidences.items()
            )
            lines.append(f"  TARGET_VPS {conf_text}")

        return "\n".join(lines)
