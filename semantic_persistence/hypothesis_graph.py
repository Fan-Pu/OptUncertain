"""
Minimal persistent graph storage for MLLM region hypotheses.

This class keeps only the graph context that the MLLM prompt needs and offers
basic helpers to update, summarize, save, and load that graph.
"""

from __future__ import annotations

import json
import re
from pathlib import Path


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
        self.node_id = node_id
        self.label = label
        self.type = type  # 0 for region, 1 for object
        self.exist_prob = exist_prob
        self.target_prob = target_prob
        self.grounded = grounded


class GraphEdge:
    def __init__(
        self,
        edge_id: int,
        source_node_id: int,
        target_node_id: int,
        exist_prob: float,
        distance: float,
        grounded: bool = False,
    ):
        self.edge_id = edge_id
        self.source_node_id = source_node_id
        self.target_node_id = target_node_id
        self.exist_prob = exist_prob
        self.distance = distance
        self.grounded = grounded


class HypothesisGraph:
    def __init__(self):
        self.nodes = dict[int, GraphNode]()
        self.edges = dict[int, GraphEdge]()
        self.observation_step = 0

    def get_MLLM_summary(self):
        # node information
        node_indices = []
        node_grounding_list = []
        node_existence_list = []
        node_target_list = []
        node_type_list = []
        node_assign_dict = {}

        # arc information
        arc_indices = []
        arc_grounding_list = []
        arc_existence_list = []
        arc_distance_list = []

        for node_id, node in self.nodes.items():
            node_indices.append(node_id)
            node_grounding_list.append(0 if not node.grounded else 1)
            node_existence_list.append(node.exist_prob)
            node_target_list.append(node.target_prob)
            node_type_list.append(node.type)
            node_assign_dict[node_id] = len(node_indices) - 1

        for edge_id, edge in self.edges.items():
            arc_indices.append(edge_id)
            arc_grounding_list.append(0 if not edge.grounded else 1)
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
