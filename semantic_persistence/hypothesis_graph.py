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
from doctest import debug
from platform import node
from tarfile import tar_filter

import debugpy
from numpy import source
from sympy import N

import Helper
from Helper import TYPE_REGION, TYPE_VP


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
        self.region_to_viewpoints: dict[int, set[int]] = (
            {}
        )  # region_node_id -> set of assigned viewpoint_node_ids
        self.viewpoint_to_region: dict[int, int] = (
            {}
        )  # viewpoint_node_id -> assigned region_node_id
        self.observation_step = 0
        self.current_vp_id = None
        self.node_visit_times: dict[int, int] = (
            {}
        )  # node_id -> count of visits (i.e., times included in MLLM input)
        self.region_connect_nodes: dict[int, set[int]] = (
            {}
        )  # region_node_id -> set of connected node_ids (for efficient edge updates during merges)

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
        viewpoint_assigns_info.append(
            {
                "id": mllm_output["current_vp_id"],
                "assign_region_node_id": current_region_info.get("id"),
            }
        )  # add the viewpoint assignment for the current viewpoint and region
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
        # -------------------------------------- update nodes ---------------------------------------
        # for the current viewpoint node. No targets here, set target_prob=0.0.
        self.add_or_update_a_node(
            node_id=self.current_vp_id,
            label=Helper.viewpoint_vp_label_by_index[self.current_vp_id],
            type=1,
            exist_prob=1.0,
            target_prob=0.0,
            grounded=True,
        )
        # add neighbor viewpoints
        for id, vp_id in enumerate(neighbor_vp_node_ids):
            self.add_or_update_a_node(
                node_id=vp_id,
                label=Helper.viewpoint_vp_label_by_index[vp_id],
                type=1,
                exist_prob=1.0,
                target_prob=viewpoint_target_probs_info[vp_id],
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

        # ------------------------------- update viewpoint-region assignments ---------------------------------------
        # It also affects whether the region node is grounded.
        for assign_info in viewpoint_assigns_info:
            vp_id = assign_info["id"]
            current_node = self.nodes.get(vp_id)
            # sanity check: the assigned viewpoint node must be of TYPE_VP (viewpoint)
            if current_node.type != TYPE_VP:
                raise ValueError(
                    f"Assigned viewpoint node {vp_id} is not of TYPE_VP (viewpoint)"
                )
            region_id = assign_info["assign_region_node_id"]
            # remove old assignment if exists. The old region node is not grounded if no assigned viewpoint nodes after the update.
            if vp_id in self.viewpoint_to_region:
                old_region_id = self.viewpoint_to_region[vp_id]
                self.region_to_viewpoints[old_region_id].discard(vp_id)
                # Check if the old region node is still grounded
                if not self.region_to_viewpoints[
                    old_region_id
                ]:  # no assigned viewpoint nodes after the update
                    self.nodes[old_region_id].grounded = False
                    # the connected edges of the ungrounded region node are also ungrounded
                    for node_id in self.region_connect_nodes.get(old_region_id, []):
                        edge_id = tuple(sorted((old_region_id, node_id)))
                        self.edges[edge_id].grounded = False
            # new assignment
            self.viewpoint_to_region[vp_id] = region_id
            if region_id not in self.region_to_viewpoints:
                self.region_to_viewpoints[region_id] = set()
            self.region_to_viewpoints[region_id].add(vp_id)
            # grounding. The region node is grounded if it has at least one assigned viewpoint (grounded) node after the update
            if any(
                [
                    vp_id
                    for vp_id in self.region_to_viewpoints[region_id]
                    if self.nodes[vp_id].grounded
                ]
            ):
                self.nodes[region_id].grounded = True
            # the connected edges of the grounded region node to another grounded node are also grounded
            for node_id in self.region_connect_nodes.get(region_id, []):
                edge_id = tuple(sorted((region_id, node_id)))
                if self.nodes[node_id].grounded:
                    self.edges[edge_id].grounded = True

        # --------------------------------------- update edges ---------------------------------------
        for arc_info in new_arcs_info:
            source_id, target_id = sorted((arc_info["i"], arc_info["j"]))
            edge_id = tuple([source_id, target_id])
            self.add_or_update_an_edge(
                source_node=self.nodes[source_id],
                target_node=self.nodes[target_id],
                exist_prob=arc_info["exist_prob"],
                distance=arc_info["dist"],
            )
        for id, vp_id in enumerate(neighbor_vp_node_ids):
            # generate edge between current viewpoint and neighbor viewpoint
            edge_id = tuple(sorted((self.current_vp_id, vp_id)))
            source_id, target_id = edge_id
            self.add_or_update_an_edge(
                source_node=self.nodes[source_id],
                target_node=self.nodes[target_id],
                exist_prob=1.0,
                distance=neighbor_vp_distances[id],
            )

        # for region merges
        for source_id, target_id in region_merges_info:
            debugpy.breakpoint()
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
                for node_id in self.region_connect_nodes[old_region_id]:
                    # existing edge
                    origin_edge_id = tuple(sorted((old_region_id, node_id)))
                    new_edge_id = tuple(sorted((new_region_id, node_id)))
                    # reassign edge to new_region_id
                    self.edges[new_edge_id] = self.edges.pop(origin_edge_id)
                    new_edge = self.edges[new_edge_id]
                    new_edge.source_node_id = min(new_region_id, node_id)
                    new_edge.target_node_id = max(new_region_id, node_id)
                    # update region_connect_edges
                    self.region_connect_nodes[new_region_id].add(node_id)
                    self.region_connect_nodes[old_region_id].discard(node_id)
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
        # a new edge
        if edge_id not in self.edges.keys():
            # if this edge is a viewpoint-region edge, check whether there is an associated viewpoint-viewpoint 2 edge such that viewpoint 2 is assigned to the region. If yes, do not add this edge.
            if source_node.type == TYPE_REGION or target_node.type == TYPE_REGION:
                region_node = (
                    source_node if source_node.type == TYPE_REGION else target_node
                )
                viewpoint_node = (
                    target_node if source_node.type == TYPE_REGION else source_node
                )
                if any(
                    tuple(sorted((viewpoint_node.node_id, nid))) in self.edges
                    for nid in self.region_to_viewpoints[region_node.node_id]
                ):
                    return

            self.edges[edge_id] = GraphEdge(
                source_node_id=source_node.node_id,
                target_node_id=target_node.node_id,
                exist_prob=exist_prob,
                distance=distance,
                grounded=False,
            )
            # check if this new edge is grounded based on the grounding status of the connected nodes
            if source_node.grounded and target_node.grounded:
                self.edges[edge_id].grounded = True
            # if this edge is a viewpoint-viewpoint edge, check whether there are associated viewpoint-region edges and delete them
            if source_node.type == TYPE_VP and target_node.type == TYPE_VP:
                vp1_id, vp2_id = source_node.node_id, target_node.node_id
                region1_id = self.viewpoint_to_region.get(vp1_id)
                region2_id = self.viewpoint_to_region.get(vp2_id)
                edge1_id = tuple(sorted((vp1_id, region2_id)))
                edge2_id = tuple(sorted((vp2_id, region1_id)))
                if edge1_id in self.edges:
                    self.remove_an_edge(source_node, self.nodes[region2_id])
                if edge2_id in self.edges:
                    self.remove_an_edge(target_node, self.nodes[region1_id])
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
        if source_node.type == TYPE_REGION:  # region node
            self.region_connect_nodes.setdefault(source_node.node_id, set()).add(
                target_node.node_id
            )
        if target_node.type == TYPE_REGION:
            self.region_connect_nodes.setdefault(target_node.node_id, set()).add(
                source_node.node_id
            )

    def remove_an_edge(self, source_node: GraphNode, target_node: GraphNode):
        edge_id = tuple(sorted((source_node.node_id, target_node.node_id)))
        # update self.edges and the connected_node_ids of the source and target nodes
        if edge_id in self.edges:
            del self.edges[edge_id]
            source_node.connected_node_ids.discard(target_node.node_id)
            target_node.connected_node_ids.discard(source_node.node_id)
        # update self.region_connect_nodes if the removed edge connects to a region node
        for current_node in (source_node, target_node):
            if current_node.type == TYPE_REGION:
                self.region_connect_nodes[current_node.node_id].discard(
                    target_node.node_id
                    if current_node == source_node
                    else source_node.node_id
                )

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

            if node.type == TYPE_REGION:
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
