"""
Minimal persistent graph storage for MLLM region hypotheses.

This graph matches the current MLLM schema:
  - region nodes: current_region_node / new_visible_region_nodes /
    new_invisible_region_nodes
  - viewpoint assignments: viewpoint_node_assigns
  - structural edges: new_arcs
  - optional merges: region_merges
"""

from __future__ import annotations


class GraphNode:
    def __init__(
        self,
        node_id: int,
        label: str,
        type: int,
        exist_prob: float,
        target_prob: float,
        grounded: bool = False,
    ):
        self.node_id = int(node_id)
        self.label = str(label)
        self.type = int(type)  # 0 for region, 1 for viewpoint
        self.exist_prob = float(exist_prob)
        self.target_prob = float(target_prob)
        self.grounded = bool(grounded)


class GraphEdge:
    def __init__(
        self,
        source_node_id: int,
        target_node_id: int,
        exist_prob: float,
        distance: float,
        grounded: bool = False,
    ):
        i, j = sorted((int(source_node_id), int(target_node_id)))
        self.source_node_id = i
        self.target_node_id = j
        self.exist_prob = float(exist_prob)
        self.distance = float(distance)
        self.grounded = bool(grounded)

    @property
    def edge_id(self) -> tuple[int, int]:
        return (self.source_node_id, self.target_node_id)


class HypothesisGraph:
    def __init__(self):
        self.nodes = {}
        self.edges = {}
        self.region_to_viewpoints = {}
        self.viewpoint_to_region = {}
        self.scan_id = None
        self.observation_step = 0

    @staticmethod
    def _clamp_prob(value, default: float = 0.0) -> float:
        try:
            value = float(value)
        except (TypeError, ValueError):
            value = float(default)
        return max(0.0, min(1.0, value))

    @staticmethod
    def _safe_distance(value, default: float = 0.0) -> float:
        try:
            value = float(value)
        except (TypeError, ValueError):
            value = float(default)
        return max(0.0, value)

    @staticmethod
    def _safe_int(value) -> int | None:
        try:
            value = int(value)
        except (TypeError, ValueError):
            return None
        return value if value > 0 else None

    @staticmethod
    def _normalize_pair(i: int, j: int) -> tuple[int, int]:
        return tuple(sorted((int(i), int(j))))

    def _ensure_viewpoint_node(
        self,
        node_id: int,
        viewpoint_label: str | None = None,
        grounded: bool = False,
    ) -> bool:
        node_id = int(node_id)
        node = self.nodes.get(node_id)

        if node is None:
            label = str(viewpoint_label or f"viewpoint-{node_id}")
            self.nodes[node_id] = GraphNode(
                node_id=node_id,
                label=label,
                type=1,
                exist_prob=1.0,
                target_prob=0.0,
                grounded=grounded,
            )
            return True

        if node.type != 1:
            node.type = 1
        if viewpoint_label:
            node.label = str(viewpoint_label)
        node.exist_prob = max(node.exist_prob, 1.0)
        node.grounded = node.grounded or grounded
        return False

    def _upsert_region_node(
        self,
        node_id: int,
        label: str,
        exist_prob: float,
        target_prob: float,
        grounded: bool = False,
    ) -> bool:
        node_id = int(node_id)
        label = str(label or "").strip()
        if not label:
            label = f"region-{node_id}"

        exist_prob = self._clamp_prob(exist_prob, 1.0)
        target_prob = self._clamp_prob(target_prob, 0.0)

        node = self.nodes.get(node_id)
        if node is None:
            self.nodes[node_id] = GraphNode(
                node_id=node_id,
                label=label,
                type=0,
                exist_prob=exist_prob,
                target_prob=target_prob,
                grounded=grounded,
            )
            self.region_to_viewpoints.setdefault(node_id, set())
            return True

        node.type = 0
        node.label = label
        node.exist_prob = max(node.exist_prob, exist_prob)
        node.target_prob = target_prob
        node.grounded = node.grounded or grounded
        self.region_to_viewpoints.setdefault(node_id, set())
        return False

    def _upsert_edge(
        self,
        source_node_id: int,
        target_node_id: int,
        exist_prob: float,
        distance: float,
    ) -> bool:
        pair = self._normalize_pair(source_node_id, target_node_id)
        if pair[0] == pair[1]:
            return False

        exist_prob = self._clamp_prob(exist_prob, 0.0)
        distance = self._safe_distance(distance, 0.0)
        if distance <= 0.0:
            return False

        grounded = bool(
            self.nodes.get(pair[0]) is not None
            and self.nodes.get(pair[1]) is not None
            and self.nodes[pair[0]].grounded
            and self.nodes[pair[1]].grounded
        )

        edge = self.edges.get(pair)
        if edge is None:
            self.edges[pair] = GraphEdge(
                source_node_id=pair[0],
                target_node_id=pair[1],
                exist_prob=exist_prob,
                distance=distance,
                grounded=grounded,
            )
            return True

        edge.exist_prob = max(edge.exist_prob, exist_prob)
        edge.distance = min(edge.distance, distance)
        edge.grounded = grounded
        return False

    def _assign_viewpoint_to_region(self, viewpoint_node_id: int, region_node_id: int):
        viewpoint_node_id = int(viewpoint_node_id)
        region_node_id = int(region_node_id)

        previous_region_id = self.viewpoint_to_region.get(viewpoint_node_id)
        if previous_region_id is not None and previous_region_id != region_node_id:
            old_assignments = self.region_to_viewpoints.get(previous_region_id, set())
            old_assignments.discard(viewpoint_node_id)

        self.viewpoint_to_region[viewpoint_node_id] = region_node_id
        self.region_to_viewpoints.setdefault(region_node_id, set()).add(viewpoint_node_id)

        region = self.nodes.get(region_node_id)
        if region is not None:
            region.grounded = True

    def _merge_region_nodes(self, keep_region_id: int, drop_region_id: int):
        if keep_region_id == drop_region_id:
            return

        keep_node = self.nodes.get(keep_region_id)
        drop_node = self.nodes.get(drop_region_id)
        if keep_node is None or drop_node is None:
            return
        if keep_node.type != 0 or drop_node.type != 0:
            return

        keep_node.exist_prob = max(keep_node.exist_prob, drop_node.exist_prob)
        keep_node.target_prob = max(keep_node.target_prob, drop_node.target_prob)
        keep_node.grounded = keep_node.grounded or drop_node.grounded

        for viewpoint_node_id in list(self.region_to_viewpoints.get(drop_region_id, set())):
            self._assign_viewpoint_to_region(viewpoint_node_id, keep_region_id)
        self.region_to_viewpoints.pop(drop_region_id, None)

        rewritten_edges = {}
        for edge in self.edges.values():
            source_id = keep_region_id if edge.source_node_id == drop_region_id else edge.source_node_id
            target_id = keep_region_id if edge.target_node_id == drop_region_id else edge.target_node_id
            if source_id == target_id:
                continue
            pair = self._normalize_pair(source_id, target_id)
            existing = rewritten_edges.get(pair)
            grounded = bool(
                self.nodes.get(pair[0]) is not None
                and self.nodes.get(pair[1]) is not None
                and self.nodes[pair[0]].grounded
                and self.nodes[pair[1]].grounded
            )
            if existing is None:
                rewritten_edges[pair] = GraphEdge(
                    source_node_id=pair[0],
                    target_node_id=pair[1],
                    exist_prob=edge.exist_prob,
                    distance=edge.distance,
                    grounded=grounded,
                )
                continue
            existing.exist_prob = max(existing.exist_prob, edge.exist_prob)
            existing.distance = min(existing.distance, edge.distance)
            existing.grounded = existing.grounded or grounded
        self.edges = rewritten_edges

        self.nodes.pop(drop_region_id, None)

    def _refresh_grounding(self):
        for region_id, viewpoint_ids in self.region_to_viewpoints.items():
            node = self.nodes.get(region_id)
            if node is not None and node.type == 0:
                node.grounded = bool(viewpoint_ids) or node.grounded

        for edge in self.edges.values():
            source_node = self.nodes.get(edge.source_node_id)
            target_node = self.nodes.get(edge.target_node_id)
            edge.grounded = bool(
                source_node is not None
                and target_node is not None
                and source_node.grounded
                and target_node.grounded
            )

    def _renormalize_region_target_probs(self):
        region_nodes = [node for node in self.nodes.values() if node.type == 0]
        if not region_nodes:
            return

        total = sum(max(0.0, node.target_prob) for node in region_nodes)
        if total <= 0.0:
            uniform_prob = 1.0 / float(len(region_nodes))
            for node in region_nodes:
                node.target_prob = uniform_prob
            return

        for node in region_nodes:
            node.target_prob = max(0.0, node.target_prob) / total

    def get_MLLM_summary(self):
        node_indices = []
        node_grounding_list = []
        node_existence_list = []
        node_target_list = []
        node_type_list = []
        node_assign_dict = {}

        arc_indices = []
        arc_grounding_list = []
        arc_existence_list = []
        arc_distance_list = []

        for node_id in sorted(self.nodes.keys()):
            node = self.nodes[node_id]
            node_indices.append(node.node_id)
            node_grounding_list.append(1 if node.grounded else 0)
            node_existence_list.append(node.exist_prob)
            node_target_list.append(node.target_prob)
            node_type_list.append(node.type)

            if node.type == 0:
                node_assign_dict[node.node_id] = sorted(
                    int(vp_id)
                    for vp_id in self.region_to_viewpoints.get(node.node_id, set())
                )

        for pair in sorted(self.edges.keys()):
            edge = self.edges[pair]
            arc_indices.append((edge.source_node_id, edge.target_node_id))
            arc_grounding_list.append(1 if edge.grounded else 0)
            arc_existence_list.append(edge.exist_prob)
            arc_distance_list.append(edge.distance)

        return {
            "node_indices": node_indices,
            "node_grounding_list": node_grounding_list,
            "node_existence_list": node_existence_list,
            "node_target_list": node_target_list,
            "node_type_list": node_type_list,
            "node_assign_dict": node_assign_dict,
            "arc_indices": arc_indices,
            "arc_grounding_list": arc_grounding_list,
            "arc_existence_list": arc_existence_list,
            "arc_distance_list": arc_distance_list,
        }

    def update_from_mllm(
        self,
        scan_id: str,
        current_vp: str,
        mllm_output: dict,
        observation_step: int,
    ):
        self.scan_id = str(scan_id)
        self.observation_step = int(observation_step)

        import Helper

        updated_node_ids = set()
        updated_edge_ids = set()

        current_vp_node_id = Helper.viewpoint_index_by_vp.get(str(current_vp))
        if current_vp_node_id is not None:
            self._ensure_viewpoint_node(
                node_id=current_vp_node_id,
                viewpoint_label=str(current_vp),
                grounded=True,
            )
            updated_node_ids.add(int(current_vp_node_id))

        current_region = (mllm_output or {}).get("current_region_node", {}) or {}
        current_region_id = self._safe_int(current_region.get("id"))
        if current_region_id is not None:
            self._upsert_region_node(
                node_id=current_region_id,
                label=current_region.get("label", ""),
                exist_prob=1.0,
                target_prob=current_region.get("target_prob", 0.0),
                grounded=current_vp_node_id is not None,
            )
            updated_node_ids.add(current_region_id)

        for key in ("new_visible_region_nodes", "new_invisible_region_nodes"):
            for region in (mllm_output or {}).get(key, []) or []:
                region_id = self._safe_int(region.get("id"))
                if region_id is None:
                    continue
                self._upsert_region_node(
                    node_id=region_id,
                    label=region.get("label", ""),
                    exist_prob=region.get("exist_prob", 0.0),
                    target_prob=region.get("target_prob", 0.0),
                    grounded=False,
                )
                updated_node_ids.add(region_id)

        for assignment in (mllm_output or {}).get("viewpoint_node_assigns", []) or []:
            viewpoint_node_id = self._safe_int(assignment.get("id"))
            region_node_id = self._safe_int(assignment.get("assign_region_node_id"))
            if viewpoint_node_id is None or region_node_id is None:
                continue

            viewpoint_label = (
                str(current_vp) if viewpoint_node_id == current_vp_node_id else None
            )
            self._ensure_viewpoint_node(
                node_id=viewpoint_node_id,
                viewpoint_label=viewpoint_label,
                grounded=viewpoint_node_id == current_vp_node_id,
            )
            updated_node_ids.add(viewpoint_node_id)

            if region_node_id not in self.nodes:
                self._upsert_region_node(
                    node_id=region_node_id,
                    label=f"region-{region_node_id}",
                    exist_prob=1.0,
                    target_prob=0.0,
                    grounded=True,
                )
                updated_node_ids.add(region_node_id)

            self._assign_viewpoint_to_region(viewpoint_node_id, region_node_id)

        for edge in (mllm_output or {}).get("new_arcs", []) or []:
            source_node_id = self._safe_int(edge.get("i"))
            target_node_id = self._safe_int(edge.get("j"))
            if source_node_id is None or target_node_id is None:
                continue

            if source_node_id not in self.nodes:
                self._ensure_viewpoint_node(node_id=source_node_id, grounded=False)
                updated_node_ids.add(source_node_id)
            if target_node_id not in self.nodes:
                self._ensure_viewpoint_node(node_id=target_node_id, grounded=False)
                updated_node_ids.add(target_node_id)

            created = self._upsert_edge(
                source_node_id=source_node_id,
                target_node_id=target_node_id,
                exist_prob=edge.get("exist_prob", 0.0),
                distance=edge.get("dist", 0.0),
            )
            pair = self._normalize_pair(source_node_id, target_node_id)
            if created or pair in self.edges:
                updated_edge_ids.add(pair)

        merged_region_ids = []
        for merge in (mllm_output or {}).get("region_merges", []) or []:
            if isinstance(merge, dict):
                keep_region_id = self._safe_int(merge.get("i"))
                drop_region_id = self._safe_int(merge.get("j"))
            elif isinstance(merge, (list, tuple)) and len(merge) >= 2:
                keep_region_id = self._safe_int(merge[0])
                drop_region_id = self._safe_int(merge[1])
            else:
                continue
            if keep_region_id is None or drop_region_id is None:
                continue
            self._merge_region_nodes(keep_region_id, drop_region_id)
            merged_region_ids.append((keep_region_id, drop_region_id))
            updated_node_ids.add(keep_region_id)

        self._refresh_grounding()
        self._renormalize_region_target_probs()

        return {
            "updated_node_ids": sorted(updated_node_ids),
            "updated_edge_ids": sorted(updated_edge_ids),
            "merged_region_ids": merged_region_ids,
        }

    def format_summary(self) -> str:
        region_nodes = []
        viewpoint_nodes = []
        for node_id in sorted(self.nodes.keys()):
            node = self.nodes[node_id]
            if node.type == 0:
                assignments = sorted(self.region_to_viewpoints.get(node_id, set()))
                region_nodes.append(
                    f"R{node_id} grounded={int(node.grounded)} exist={node.exist_prob:.2f} "
                    f"target={node.target_prob:.2f} assigns={assignments} label='{node.label}'"
                )
            else:
                viewpoint_nodes.append(
                    f"V{node_id} grounded={int(node.grounded)} label='{node.label}'"
                )

        edge_lines = []
        for pair in sorted(self.edges.keys()):
            edge = self.edges[pair]
            edge_lines.append(
                f"({edge.source_node_id},{edge.target_node_id}) grounded={int(edge.grounded)} "
                f"exist={edge.exist_prob:.2f} dist={edge.distance:.2f}"
            )

        lines = [
            f"Graph summary: regions={len(region_nodes)} viewpoints={len(viewpoint_nodes)} edges={len(edge_lines)} step={self.observation_step}",
        ]
        if region_nodes:
            lines.append("  Regions:")
            lines.extend(f"    {line}" for line in region_nodes)
        if viewpoint_nodes:
            lines.append("  Viewpoints:")
            lines.extend(f"    {line}" for line in viewpoint_nodes)
        if edge_lines:
            lines.append("  Edges:")
            lines.extend(f"    {line}" for line in edge_lines)
        return "\n".join(lines)
