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
from platform import node
from tarfile import tar_filter

from numpy import source
from sympy import N

import Helper


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
        """type: 0 for region, 1 for viewpoint"""
        self.node_id = int(node_id)
        self.label = str(label)
        self.type = int(type)  # 0 for region, 1 for viewpoint
        self.exist_prob = float(exist_prob)
        self.target_prob = float(target_prob)
        self.grounded = bool(grounded)
        self.connected_node_ids: set[int] = set()


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
        return sorted((self.source_node_id, self.target_node_id))


class HypothesisGraph:
    def __init__(self):
        self.nodes: dict[int, GraphNode] = {}  # node_id -> GraphNode
        self.edges: dict[tuple[int, int], GraphEdge] = (
            {}
        )  # edge_id (tuple of sorted node_ids) -> GraphEdge
        self.region_to_viewpoints = dict[int, set[int]] = (
            {}
        )  # region_node_id -> set of assigned viewpoint_node_ids
        self.viewpoint_to_region: dict[int, int] = (
            {}
        )  # viewpoint_node_id -> assigned region_node_id
        self.scan_id = None
        self.observation_step = 0
        self.current_vp_id = None
        self.node_visit_times: dict[int, int] = (
            {}
        )  # node_id -> count of visits (i.e., times included in MLLM input)
        self.region_connect_edges: dict[int, set[int]] = (
            {}
        )  # region_node_id -> set of connected node_ids (for quick lookup during merges)

    def update_from_mllm(
        self,
        mllm_output: dict,
    ) -> dict:
        """
        Update the hypothesis graph based on the MLLM output for the current scan and viewpoint.
        Returns a summary of the graph update, including counts of updated nodes and edges.
        """
        self.observation_step += 1
        # get info from MLLM output
        current_region_info = mllm_output.get("current_region_node", {})
        new_visible_regions_info = mllm_output.get("new_visible_region_nodes", [])
        new_invisible_regions_info = mllm_output.get("new_invisible_region_nodes", [])
        viewpoint_target_probs_info = {}
        for info in mllm_output.get("viewpoint_target_probs", []):
            viewpoint_target_probs_info[info["id"]] = info["target_prob"]
        viewpoint_assigns_info = mllm_output.get("viewpoint_node_assigns", [])
        new_arcs_info = mllm_output.get("new_arcs", [])
        region_merges_info = mllm_output.get("region_merges", [])

        neighbor_vp_node_ids = mllm_output.get("neighbor_vp_ids", [])
        neighbor_vp_distances = mllm_output.get("neighbor_vp_distances", [])

        new_region_ids = [
            info["id"] for info in new_visible_regions_info + new_invisible_regions_info
        ]
        # update
        self.current_vp_id = mllm_output["current_vp_id"]
        for node_id in neighbor_vp_node_ids + [self.current_vp_id] + new_region_ids:
            if node_id not in self.node_visit_times:
                self.node_visit_times[node_id] = 0
        # for the current viewpoint node
        self.add_or_update_a_node(
            node_id=self.current_vp_id,
            label=Helper.viewpoint_vp_label_by_index[self.current_vp_id],
            type=1,
            exist_prob=1.0,
            target_prob=current_region_info["target_prob"],
            grounded=True,
        )
        # add neighbor viewpoints
        for vp_id in neighbor_vp_node_ids:
            self.add_or_update_a_node(
                node_id=vp_id,
                label=Helper.viewpoint_vp_label_by_index[vp_id],
                type=1,
                exist_prob=1.0,
                target_prob=viewpoint_target_probs_info[vp_id],
            )
            # generate edge between current viewpoint and neighbor viewpoint
            edge_id = tuple(sorted((self.current_vp_id, vp_id)))
            source_id, target_id = edge_id
            self.add_or_update_an_edge(
                source_node=self.nodes[source_id],
                target_node=self.nodes[target_id],
                exist_prob=1.0,
                distance=neighbor_vp_distances[vp_id],
            )

        # for current region node
        current_region_id = current_region_info.get("id")
        self.add_or_update_a_node(
            node_id=current_region_id,
            label=current_region_info["label"],
            type=0,
            exist_prob=1.0,
            target_prob=current_region_info["target_prob"],
            grounded=True,
        )

        # for new region nodes
        for node_info in new_visible_regions_info + new_invisible_regions_info:
            node_id = node_info["id"]
            self.add_or_update_a_node(
                node_id=node_id,
                label=node_info["label"],
                type=0,
                exist_prob=node_info["exist_prob"],
                target_prob=node_info["target_prob"],
            )

        # for new arcs
        for arc_info in new_arcs_info:
            source_id, target_id = sorted((arc_info["i"], arc_info["j"]))
            edge_id = tuple(source_id, target_id)
            self.add_or_update_an_edge(
                source_node=self.nodes[source_id],
                target_node=self.nodes[target_id],
                exist_prob=arc_info["exist_prob"],
                distance=arc_info["distance"],
            )

        # for viewpoint assignments. It also affects whether the region node is grounded.
        for assign_info in viewpoint_assigns_info:
            vp_id = assign_info["id"]
            current_node = self.nodes.get(vp_id)
            if (
                current_node.type != 1
            ):  # sanity check: the assigned viewpoint node must be of type 1 (viewpoint)
                raise ValueError(
                    f"Assigned viewpoint node {vp_id} is not of type 1 (viewpoint)"
                )
            region_id = assign_info["assign_region_node_id"]
            # remove old assignment if exists. The old region node is not grounded if no assigned viewpoint nodes after the update.
            if vp_id in self.viewpoint_to_region:
                old_region_id = self.viewpoint_to_region[vp_id]
                self.region_to_viewpoints[old_region_id].discard(vp_id)
                # Check if the old region node is still grounded
                if not self.region_to_viewpoints[old_region_id]:
                    self.nodes[old_region_id].grounded = False
                    # the connected edges of the ungrounded region node are also ungrounded
                    for node_id in self.region_connect_edges.get(old_region_id, []):
                        edge_id = tuple(sorted((old_region_id, node_id)))
                        self.edges[edge_id].grounded = False
            # new assignment
            self.viewpoint_to_region[vp_id] = region_id
            if region_id not in self.region_to_viewpoints:
                self.region_to_viewpoints[region_id] = set()
            self.region_to_viewpoints[region_id].add(vp_id)
            # grounding
            self.nodes[region_id].grounded = True
            # the connected edges of the grounded region node to another grounded node are also grounded
            for node_id in self.region_connect_edges.get(region_id, []):
                edge_id = tuple(sorted((region_id, node_id)))
                if self.nodes[node_id].grounded:
                    self.edges[edge_id].grounded = True

        # for region merges
        for source_id, target_id in region_merges_info:
            new_region_id, old_region_id = sorted((source_id, target_id))
            # merge
            if source_id in self.nodes and target_id in self.nodes:
                # update node info (e.g., take max exist_prob and target_prob)
                self.nodes[target_id].exist_prob = max(
                    self.nodes[target_id].exist_prob, self.nodes[source_id].exist_prob
                )
                self.nodes[target_id].target_prob = max(
                    self.nodes[target_id].target_prob, self.nodes[source_id].target_prob
                )
                # merge old region edges into new region
                for node_id in self.region_connect_edges[old_region_id]:
                    # existing edge
                    origin_edge_id = tuple(sorted((old_region_id, node_id)))
                    new_edge_id = tuple(sorted((new_region_id, node_id)))
                    # reassign edge to new_region_id
                    self.edges[new_edge_id] = self.edges.pop(origin_edge_id)
                    new_edge = self.edges[new_edge_id]
                    new_edge.source_node_id = min(new_region_id, node_id)
                    new_edge.target_node_id = max(new_region_id, node_id)
                    # update region_connect_edges
                    self.region_connect_edges[new_region_id].add(node_id)
                    self.region_connect_edges[old_region_id].discard(node_id)
                    # reassign viewpoint assignments
                    for vp_id in self.region_to_viewpoints[old_region_id]:
                        self.viewpoint_to_region[vp_id] = new_region_id
                        self.region_to_viewpoints[new_region_id].add(vp_id)
                    # remove old_region_id from self.region_to_viewpoints
                    del self.region_to_viewpoints[old_region_id]

        # check whether any edge connects to any existing region nodes for region_connect_edges

    def add_or_update_a_node(
        self,
        node_id: int,
        label: str,
        type: int,
        exist_prob: float = None,
        target_prob: float = None,
        grounded: bool = None,
    ):
        if node_id not in self.nodes:
            self.nodes[node_id] = GraphNode(
                node_id=node_id,
                label=label,
                type=type,
                exist_prob=exist_prob,
                target_prob=target_prob,
                grounded=grounded if grounded is not None else False,
            )
        else:
            self.nodes[node_id].exist_prob = (
                exist_prob if exist_prob is not None else self.nodes[node_id].exist_prob
            )
            self.nodes[node_id].target_prob = (
                target_prob
                if target_prob is not None
                else self.nodes[node_id].target_prob
            )
            self.nodes[node_id].grounded = (
                grounded if grounded is not None else self.nodes[node_id].grounded
            )

    def add_or_update_an_edge(
        self,
        source_node: GraphNode,
        target_node: GraphNode,
        exist_prob: float = None,
        distance: float = None,
        grounded: bool = None,
    ):
        edge_id = tuple(sorted((source_node.node_id, target_node.node_id)))
        if edge_id not in self.edges:
            self.edges[edge_id] = GraphEdge(
                source_node_id=source_node.node_id,
                target_node_id=target_node.node_id,
                exist_prob=exist_prob,
                distance=distance,
                grounded=False,
            )
        else:
            self.edges[edge_id].exist_prob = (
                exist_prob if exist_prob is not None else self.edges[edge_id].exist_prob
            )
            self.edges[edge_id].distance = (
                distance if distance is not None else self.edges[edge_id].distance
            )
            self.edges[edge_id].grounded = (
                grounded if grounded is not None else self.edges[edge_id].grounded
            )
        source_node.connected_node_ids.add(target_node.node_id)
        target_node.connected_node_ids.add(source_node.node_id)
        if source_node.type == 0:  # region node
            self.region_connect_edges.setdefault(source_node.node_id, set()).add(
                target_node.node_id
            )
        if target_node.type == 0:
            self.region_connect_edges.setdefault(target_node.node_id, set()).add(
                source_node.node_id
            )

    def remove_an_edge(self, source_node: GraphNode, target_node: GraphNode):
        edge_id = tuple(sorted((source_node.node_id, target_node.node_id)))
        if edge_id in self.edges:
            del self.edges[edge_id]
            source_node.connected_node_ids.discard(target_node.node_id)
            target_node.connected_node_ids.discard(source_node.node_id)
        if source_node.type == 0:  # region node
            self.region_connect_edges[source_node.node_id].discard(target_node.node_id)
        if target_node.type == 0:
            self.region_connect_edges[target_node.node_id].discard(source_node.node_id)
