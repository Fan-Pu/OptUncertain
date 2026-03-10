"""
hypothesis_graph.py

Persistent hypothesis graph built from repeated MLLM semantic proposals.

The graph is intentionally lightweight:
  - each node is a hypothesized semantic region
  - each edge is a hypothesized connection between two regions
  - repeated observations update probabilities instead of replacing them

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
    Normalize a label so repeated mentions map to the same persistent node.

    The MLLM prompt already restricts the label space, so a simple normalization
    step is enough here and avoids over-engineering semantic matching logic.
    """
    label = str(label or "").strip().lower()
    label = re.sub(r"[^a-z0-9\s]+", " ", label)
    label = re.sub(r"\s+", " ", label)
    return label.strip()


def _edge_key(node_a_id: str, node_b_id: str) -> Tuple[str, str]:
    """Store edges with an order-invariant key because region links are symmetric."""
    if node_a_id <= node_b_id:
        return (node_a_id, node_b_id)
    return (node_b_id, node_a_id)


@dataclass
class HypothesisNode:
    """
    Persistent semantic-region hypothesis.

    `label` keeps the most recently preferred surface form.
    `canonical_label` is the deduplication key.
    """

    node_id: str
    label: str
    canonical_label: str
    aliases: Set[str] = field(default_factory=set)
    existence_prob: float = 0.5
    target_prob: float = 0.0
    observation_count: int = 0
    grounded_viewpoints: Set[str] = field(default_factory=set)
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
      - persistent semantic region nodes
      - probabilistic region-to-region edges
      - current viewpoint grounding for the active region
    """

    def __init__(self, target_object: str = ""):
        self.target_object = str(target_object or "").strip()
        self.nodes: Dict[str, HypothesisNode] = {}
        self.edges: Dict[Tuple[str, str], HypothesisEdge] = {}
        self._label_to_node_id: Dict[str, str] = {}
        self.observation_step: int = 0
        self.visited_viewpoints: Set[str] = set()
        self.last_current_node_id: Optional[str] = None

    @staticmethod
    def _running_average(previous: float, new_value: float, previous_count: int) -> float:
        """
        Update a belief with a simple count-based average.

        This keeps the graph stable over time while still letting fresh evidence
        move the estimate when the node has only been observed a few times.
        """
        if previous_count <= 0:
            return float(new_value)
        return float(((previous * previous_count) + new_value) / (previous_count + 1))

    def _get_or_create_node(self, label: str) -> Optional[HypothesisNode]:
        canonical_label = _canonicalize_label(label)
        if not canonical_label:
            return None

        node_id = self._label_to_node_id.get(canonical_label)
        if node_id is None:
            node = HypothesisNode(
                node_id=new_node_id("HGN"),
                label=str(label).strip(),
                canonical_label=canonical_label,
                aliases={str(label).strip()},
            )
            self.nodes[node.node_id] = node
            self._label_to_node_id[canonical_label] = node.node_id
            return node

        node = self.nodes[node_id]
        surface_label = str(label).strip()
        if surface_label:
            node.aliases.add(surface_label)
            node.label = surface_label
        return node

    def _observe_node(
        self,
        label: str,
        existence_prob: float,
        target_prob: Optional[float],
        scan_id: str,
        observed_from_vp: str,
        observation_step: int,
        grounded_viewpoint: Optional[str] = None,
        direct_target_detection: bool = False,
    ) -> Optional[HypothesisNode]:
        """
        Create/update one node belief from one MLLM observation.

        `grounded_viewpoint` should only be used for the current region because the
        neighbors are semantic hypotheses, not confirmed robot poses.
        """
        node = self._get_or_create_node(label)
        if node is None:
            return None

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

        if grounded_viewpoint:
            node.grounded_viewpoints.add(str(grounded_viewpoint))

        node.evidence_log.append(
            {
                "step": int(observation_step),
                "scan_id": str(scan_id or ""),
                "observed_from_vp": str(observed_from_vp or ""),
                "grounded_viewpoint": str(grounded_viewpoint or ""),
                "existence_prob": float(_clamp(existence_prob)),
                "target_prob": None if target_prob is None else float(target_prob),
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
        """Create/update one symmetric edge hypothesis."""
        if node_a.node_id == node_b.node_id:
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

        travel_distance = _safe_float(travel_distance, default=-1.0)
        if travel_distance >= 0.0:
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
            "current_region": {"label": ..., "confidence": ...},
            "neighbor_regions": [{"label": ..., "existence_prob": ..., "target_prob": ...}],
            "region_connections": [{"region_a": ..., "region_b": ..., "connection_prob": ..., "travel_distance": ...}],
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

        known_nodes_by_label: Dict[str, HypothesisNode] = {}
        updated_node_ids: List[str] = []
        updated_edge_ids: List[str] = []

        current_label = str(current_region.get("label", "")).strip()
        current_confidence = _clamp(
            _safe_float(current_region.get("confidence", 0.0), 0.0)
        )
        current_node = self._observe_node(
            label=current_label,
            existence_prob=current_confidence,
            target_prob=direct_target_prob if direct_target_prob > 0.0 else None,
            scan_id=scan_id,
            observed_from_vp=current_vp,
            observation_step=step,
            grounded_viewpoint=current_vp,
            direct_target_detection=direct_target_prob > 0.0,
        )
        if current_node is not None:
            known_nodes_by_label[current_node.canonical_label] = current_node
            updated_node_ids.append(current_node.node_id)
            self.last_current_node_id = current_node.node_id

        # Neighbor regions are not directly grounded to the current viewpoint. They
        # remain hypotheses until the robot physically reaches supporting viewpoints.
        for neighbor in neighbor_regions:
            label = str(neighbor.get("label", "")).strip()
            neighbor_node = self._observe_node(
                label=label,
                existence_prob=_safe_float(neighbor.get("existence_prob", 0.0), 0.0),
                target_prob=_safe_float(neighbor.get("target_prob", 0.0), 0.0),
                scan_id=scan_id,
                observed_from_vp=current_vp,
                observation_step=step,
            )
            if neighbor_node is None:
                continue
            known_nodes_by_label[neighbor_node.canonical_label] = neighbor_node
            updated_node_ids.append(neighbor_node.node_id)

        # Connections may mention labels that did not survive neighbor filtering. In
        # that case we still create the corresponding nodes because the edge itself
        # is evidence that those semantic regions are part of the hypothesis graph.
        for connection in region_connections:
            region_a = str(connection.get("region_a", "")).strip()
            region_b = str(connection.get("region_b", "")).strip()
            canonical_a = _canonicalize_label(region_a)
            canonical_b = _canonicalize_label(region_b)
            if not canonical_a or not canonical_b or canonical_a == canonical_b:
                continue

            node_a = known_nodes_by_label.get(canonical_a) or self._get_or_create_node(
                region_a
            )
            node_b = known_nodes_by_label.get(canonical_b) or self._get_or_create_node(
                region_b
            )
            if node_a is None or node_b is None:
                continue

            known_nodes_by_label[node_a.canonical_label] = node_a
            known_nodes_by_label[node_b.canonical_label] = node_b

            edge = self._observe_edge(
                node_a=node_a,
                node_b=node_b,
                connection_prob=_safe_float(connection.get("connection_prob", 0.0), 0.0),
                travel_distance=_safe_float(connection.get("travel_distance", -1.0), -1.0),
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
                    "aliases": sorted(node.aliases),
                    "existence_prob": float(node.existence_prob),
                    "target_prob": float(node.target_prob),
                    "observation_count": int(node.observation_count),
                    "grounded_viewpoints": sorted(node.grounded_viewpoints),
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
            "nodes": nodes,
            "edges": edges,
        }

    def format_summary(self, max_nodes: int = 8, max_edges: int = 8) -> str:
        """
        Build a compact text summary for debugging in the main navigation loop.

        The formatting is intentionally plain because this is mainly meant for
        terminal inspection while the simulator is running.
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
                node.target_prob,
                node.existence_prob,
                node.observation_count,
            ),
            reverse=True,
        )
        for node in sorted_nodes[:max_nodes]:
            lines.append(
                "  "
                + (
                    f"NODE {node.node_id} | {node.label} | exist={node.existence_prob:.2f} "
                    f"| target={node.target_prob:.2f} | obs={node.observation_count} "
                    f"| grounded={len(node.grounded_viewpoints)}"
                )
            )

        sorted_edges = sorted(
            self.edges.values(),
            key=lambda edge: (
                edge.connection_prob,
                -edge.travel_distance if edge.travel_distance >= 0 else -1e9,
            ),
            reverse=True,
        )
        for edge in sorted_edges[:max_edges]:
            node_a = self.nodes.get(edge.node_a_id)
            node_b = self.nodes.get(edge.node_b_id)
            label_a = node_a.label if node_a is not None else edge.node_a_id
            label_b = node_b.label if node_b is not None else edge.node_b_id
            distance_text = (
                f"{edge.travel_distance:.2f}m"
                if edge.travel_distance >= 0
                else "unknown"
            )
            lines.append(
                "  "
                + (
                    f"EDGE {edge.edge_id} | {label_a} <-> {label_b} "
                    f"| conn={edge.connection_prob:.2f} | dist={distance_text} "
                    f"| obs={edge.observation_count}"
                )
            )

        return "\n".join(lines)
