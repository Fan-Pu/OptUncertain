"""
Persistent shared hypothesis graph for many-to-many cooperative VLN.

The graph follows the paper's two-layer representation:
  - viewpoint nodes: physically executable poses
  - region nodes: semantic zones proposed by the MLLM

Target probabilities are maintained separately on the viewpoint and region
layers, and uncertain region existence / edge distance / edge existence are
updated with the paper's Bayesian rules.
"""

from __future__ import annotations

from calendar import c
import copy
import json
from logging import debug
import math
import os
from typing import Dict, Iterable, List, Optional, Set, Tuple

import debugpy

import Helper
from Helper import TYPE_REGION, TYPE_VP


class GraphNode:
    def __init__(
        self,
        node_id: int,
        label: str,
        node_type: int,
        exist_prob: float,
        grounded: bool,
        target_probs: Dict[str, float],
        node_visit_times: int = 0,
    ):
        self.node_id = int(node_id)
        self.label = str(label)
        self.type = int(node_type)
        self.exist_prob = float(exist_prob)
        self.grounded = bool(grounded)
        self.target_probs = {
            str(target_id): float(value) for target_id, value in target_probs.items()
        }
        self.node_visit_times = int(node_visit_times)
        self.connected_node_ids: Set[int] = set()


class GraphEdge:
    def __init__(
        self,
        source_node_id: int,
        target_node_id: int,
        distance_mean: float,
        distance_var: float,
        cond_exist_prob: float,
        exist_prob: float,
        grounded: bool,
    ):
        i, j = sorted((int(source_node_id), int(target_node_id)))
        self.source_node_id = i
        self.target_node_id = j
        self.distance_mean = float(distance_mean)
        self.distance_var = float(distance_var)
        self.cond_exist_prob = float(cond_exist_prob)
        self.exist_prob = float(exist_prob)
        self.grounded = bool(grounded)

    @property
    def edge_id(self) -> Tuple[int, int]:
        return (self.source_node_id, self.target_node_id)


class HypothesisGraph:
    def __init__(
        self,
        targets: List[Dict[str, object]],
        bayes_config: Optional[Dict[str, float]] = None,
    ):
        defaults = {
            "eta_goal": 5.0,
            "eta_exist": 5.0,
            "sigma_vv2": 4.0,
            "sigma_vz2": 9.0,
            "kappa_vv": 1.0,
            "kappa_vz": 1.0,
            "varrho": 0.75,
            "omega_vz": 0.7,
            "eta_vz": 5.0,
            "epsilon": 1e-6,
        }

        self.bayes_config = copy.deepcopy(defaults)
        if bayes_config is not None:
            self.bayes_config.update(bayes_config)

        if not isinstance(targets, list) or len(targets) == 0:
            raise ValueError("targets must be a non-empty list of target records.")

        self.target_records: List[Dict[str, str]] = []
        for target in targets:
            if not isinstance(target, dict):
                raise TypeError(
                    "Each target must be a dictionary with target_id and description."
                )

            if "target_id" not in target or "description" not in target:
                raise KeyError("Each target must contain target_id and description.")

            self.target_records.append(
                {
                    "target_id": str(target["target_id"]),
                    "description": str(target["description"]),
                }
            )

        self.target_ids = [record["target_id"] for record in self.target_records]

        if len(self.target_ids) != len(set(self.target_ids)):
            raise ValueError("Target ids must be unique.")

        self.target_id_to_description = {
            record["target_id"]: record["description"] for record in self.target_records
        }

        self.target_found = {target_id: False for target_id in self.target_ids}

        self.nodes: Dict[int, GraphNode] = {}
        self.edges: Dict[Tuple[int, int], GraphEdge] = {}
        self.viewpoint_to_region: Dict[int, int] = {}
        self.region_to_viewpoints: Dict[int, Set[int]] = {}
        self.agent_current_vp_ids: Dict[str, int] = {}
        self.viewpoint_rgb_evidence: Dict[int, List[object]] = {}
        self.observation_step = 0

    def sync_agent_current_viewpoints(
        self,
        agent_observations: List[Dict[str, object]],
    ) -> None:
        """Sync current agent viewpoint ids before the MLLM call.

        This method is intentionally light-weight. It only updates
        self.agent_current_vp_ids so that get_mllm_summary() can report the
        current agent locations even before update_from_mllm() is called.

        It does not create graph nodes, semantic regions, viewpoint assignments,
        or edges. Those updates still happen after the MLLM returns its graph
        hypotheses.
        """

        self.agent_current_vp_ids = {
            str(observation["agent_id"]): int(observation["current_viewpoint_index"])
            for observation in agent_observations
        }

    def mark_target_found(self, target_id: str) -> None:
        target_id = str(target_id)
        if target_id not in self.target_found:
            raise KeyError("Unknown target_id: %s" % target_id)
        self.target_found[target_id] = True

    def add_or_update_node(
        self,
        node_id: int,
        label: str,
        node_type: int,
        exist_prob: Optional[float] = None,
        grounded: Optional[bool] = None,
        target_probs: Optional[Dict[str, float]] = None,
        node_visit_times: Optional[int] = None,
    ) -> GraphNode:
        node_id = int(node_id)

        if target_probs is None:
            target_probs = {}

        normalized_target_probs = {
            target_id: float(target_probs.get(target_id, 0.0))
            for target_id in self.target_ids
        }

        if node_id not in self.nodes:
            self.nodes[node_id] = GraphNode(
                node_id=node_id,
                label=label,
                node_type=node_type,
                exist_prob=1.0 if exist_prob is None else float(exist_prob),
                grounded=False if grounded is None else bool(grounded),
                target_probs=normalized_target_probs,
                node_visit_times=(
                    0 if node_visit_times is None else int(node_visit_times)
                ),
            )
            return self.nodes[node_id]

        node = self.nodes[node_id]
        node.label = str(label)
        node.type = int(node_type)

        if exist_prob is not None:
            node.exist_prob = float(exist_prob)

        if grounded is not None:
            node.grounded = bool(grounded)

        if target_probs is not None:
            for target_id in self.target_ids:
                node.target_probs[target_id] = float(normalized_target_probs[target_id])

        if node_visit_times is not None:
            node.node_visit_times = int(node_visit_times)

        return node

    def add_or_update_edge(
        self,
        source_node_id: int,
        target_node_id: int,
        distance_mean: Optional[float] = None,
        distance_var: Optional[float] = None,
        cond_exist_prob: Optional[float] = None,
        exist_prob: Optional[float] = None,
        grounded: Optional[bool] = None,
    ) -> GraphEdge:
        source_node_id = int(source_node_id)
        target_node_id = int(target_node_id)
        edge_id = tuple(sorted((source_node_id, target_node_id)))

        if edge_id not in self.edges:
            if distance_mean is None:
                raise ValueError("distance_mean is required for a new edge")
            if distance_var is None:
                raise ValueError("distance_var is required for a new edge")
            if cond_exist_prob is None:
                raise ValueError("cond_exist_prob is required for a new edge")
            if exist_prob is None:
                raise ValueError("exist_prob is required for a new edge")
            if grounded is None:
                raise ValueError("grounded is required for a new edge")
            self.edges[edge_id] = GraphEdge(
                source_node_id=source_node_id,
                target_node_id=target_node_id,
                distance_mean=distance_mean,
                distance_var=distance_var,
                cond_exist_prob=cond_exist_prob,
                exist_prob=exist_prob,
                grounded=grounded,
            )
        else:
            edge = self.edges[edge_id]
            if distance_mean is not None:
                edge.distance_mean = float(distance_mean)
            if distance_var is not None:
                edge.distance_var = float(distance_var)
            if cond_exist_prob is not None:
                edge.cond_exist_prob = float(cond_exist_prob)
            if exist_prob is not None:
                edge.exist_prob = float(exist_prob)
            if grounded is not None:
                edge.grounded = bool(grounded)

        self.nodes[source_node_id].connected_node_ids.add(target_node_id)
        self.nodes[target_node_id].connected_node_ids.add(source_node_id)
        return self.edges[edge_id]

    def remove_edge(self, edge_id: Tuple[int, int]) -> None:
        source_node_id, target_node_id = tuple(sorted(edge_id))
        if (source_node_id, target_node_id) not in self.edges:
            return
        del self.edges[(source_node_id, target_node_id)]
        self.nodes[source_node_id].connected_node_ids.discard(target_node_id)
        self.nodes[target_node_id].connected_node_ids.discard(source_node_id)

    def update_from_mllm(
        self,
        mllm_output: Dict[str, object],
        agent_observations: List[Dict[str, object]],
        scorer,
    ) -> None:
        self.observation_step += 1

        existing_node_ids = set(self.nodes)

        previous_target_probs = {
            node_id: dict(node.target_probs) for node_id, node in self.nodes.items()
        }
        previous_exist_probs = {
            node_id: float(node.exist_prob) for node_id, node in self.nodes.items()
        }
        previous_grounded = {
            node_id: bool(node.grounded) for node_id, node in self.nodes.items()
        }
        previous_distance_means = {
            edge_id: float(edge.distance_mean) for edge_id, edge in self.edges.items()
        }
        previous_distance_vars = {
            edge_id: float(edge.distance_var) for edge_id, edge in self.edges.items()
        }
        previous_cond_exist_probs = {
            edge_id: float(edge.cond_exist_prob) for edge_id, edge in self.edges.items()
        }

        alias_map = self._build_region_alias_map(mllm_output.get("region_merges", []))
        payload = self._apply_region_alias_map(mllm_output, alias_map)
        self._merge_existing_regions(alias_map)

        observation_by_agent = {
            str(observation["agent_id"]): observation
            for observation in agent_observations
        }

        self.agent_current_vp_ids = {}

        region_initial_probs: Dict[int, Dict[str, float]] = {}
        region_initial_exist_probs: Dict[int, float] = {}
        viewpoint_initial_probs: Dict[int, Dict[str, float]] = {}
        current_region_for_agent: Dict[str, int] = {}
        newly_grounded_viewpoints: Set[int] = set()
        candidate_viewpoint_ids: Set[int] = set()

        region_info_by_id: Dict[int, Dict[str, object]] = {}

        for region_key in ("visible_region_nodes", "invisible_region_nodes"):
            for region_info in payload[region_key]:
                region_id = int(region_info["id"])
                region_info_by_id[region_id] = region_info

                region_initial_probs[region_id] = self._normalize_target_dict(
                    region_info["target_probs"]
                )
                region_initial_exist_probs[region_id] = float(region_info["exist_prob"])

                self.add_or_update_node(
                    node_id=region_id,
                    label=region_info["label"],
                    node_type=TYPE_REGION,
                    exist_prob=region_initial_exist_probs[region_id],
                    grounded=False,
                    target_probs=self._zero_target_probs(),
                )

        for agent_payload in payload["agents"]:
            agent_id = str(agent_payload["agent_id"])
            if agent_id not in observation_by_agent:
                raise KeyError("Missing observation for agent %s" % agent_id)

            observation = observation_by_agent[agent_id]
            current_vp_id = int(observation["current_viewpoint_index"])
            current_region_id = int(agent_payload["current_region_node_id"])

            if current_region_id not in region_info_by_id:
                raise KeyError(
                    "current_region_node_id %s is not included in "
                    "visible_region_nodes or invisible_region_nodes."
                    % current_region_id
                )

            current_region_for_agent[agent_id] = current_region_id
            self.agent_current_vp_ids[agent_id] = current_vp_id

            current_vp_label = Helper.viewpoint_vp_label_by_index[current_vp_id]
            current_vp_node = self.add_or_update_node(
                node_id=current_vp_id,
                label=current_vp_label,
                node_type=TYPE_VP,
                exist_prob=1.0,
                grounded=True,
                target_probs=self._zero_target_probs(),
            )
            current_vp_node.node_visit_times += 1

            self.viewpoint_rgb_evidence[current_vp_id] = [observation["raw_panorama"]]

            if not previous_grounded.get(current_vp_id, False):
                newly_grounded_viewpoints.add(current_vp_id)

            candidate_viewpoint_ids.add(current_vp_id)

            for visible_viewpoint in observation["visible_viewpoints"]:
                visible_vp_id = int(visible_viewpoint["viewpoint_index"])
                visible_label = Helper.viewpoint_vp_label_by_index[visible_vp_id]

                already_grounded = (
                    self.nodes[visible_vp_id].grounded
                    if visible_vp_id in self.nodes
                    else False
                )

                self.add_or_update_node(
                    node_id=visible_vp_id,
                    label=visible_label,
                    node_type=TYPE_VP,
                    exist_prob=1.0,
                    grounded=already_grounded,
                    target_probs=self._zero_target_probs(),
                )

                candidate_viewpoint_ids.add(visible_vp_id)

                self.add_or_update_edge(
                    source_node_id=current_vp_id,
                    target_node_id=visible_vp_id,
                    distance_mean=float(visible_viewpoint["distance"]),
                    distance_var=0.0,
                    cond_exist_prob=1.0,
                    exist_prob=1.0,
                    grounded=True,
                )

        for target_prob_info in payload["viewpoint_target_probs"]:
            vp_id = int(target_prob_info["id"])
            viewpoint_initial_probs[vp_id] = self._normalize_target_dict(
                target_prob_info["target_probs"]
            )

        self._refresh_region_to_viewpoints()

        proposed_assignments: Dict[int, int] = {}

        for assign_info in payload["viewpoint_node_assigns"]:
            region_id = int(assign_info["region_node_id"])

            for viewpoint_id in assign_info["assigned_viewpoint_node_indices"]:
                viewpoint_id = int(viewpoint_id)

                if viewpoint_id in proposed_assignments:
                    raise ValueError(
                        "Viewpoint %s appears in more than one assignment group."
                        % viewpoint_id
                    )

                proposed_assignments[viewpoint_id] = region_id

        for agent_id, current_vp_id in self.agent_current_vp_ids.items():
            self._set_viewpoint_region(
                current_vp_id,
                current_region_for_agent[agent_id],
            )

        for viewpoint_id in sorted(candidate_viewpoint_ids):
            if viewpoint_id in self.agent_current_vp_ids.values():
                continue

            if (
                viewpoint_id in existing_node_ids
                and viewpoint_id not in newly_grounded_viewpoints
                and viewpoint_id in self.viewpoint_to_region
            ):
                continue

            if viewpoint_id not in proposed_assignments:
                raise KeyError(
                    "Missing region assignment for viewpoint %s." % viewpoint_id
                )

            self._set_viewpoint_region(
                viewpoint_id,
                proposed_assignments[viewpoint_id],
            )

        self._refresh_region_grounding()

        edge_distance_variances = payload["edge_distance_variances"]
        vv_distance_var = float(edge_distance_variances["viewpoint_viewpoint"])
        vz_distance_var = float(edge_distance_variances["viewpoint_region"])

        for edge_info in payload["new_edges"]:
            source_id = int(edge_info["i"])
            target_id = int(edge_info["j"])
            edge_type = str(edge_info["edge_type"])

            if source_id == target_id:
                raise ValueError("Self-loop is not allowed.")

            if edge_type not in {"VV", "VZ"}:
                raise ValueError("Invalid edge_type: %s" % edge_type)

            if source_id not in self.nodes:
                raise KeyError("Edge source node %s is not in graph." % source_id)
            if target_id not in self.nodes:
                raise KeyError("Edge target node %s is not in graph." % target_id)

            edge_id = tuple(sorted((source_id, target_id)))
            if edge_id in self.edges:
                continue

            actual_edge_type = self._edge_type_for_ids(source_id, target_id)

            if edge_type == "VV" and actual_edge_type != "vv":
                raise ValueError(
                    "edge_type VV does not match endpoint node types for edge %s."
                    % (edge_id,)
                )

            if edge_type == "VZ" and actual_edge_type != "vz":
                raise ValueError(
                    "edge_type VZ does not match endpoint node types for edge %s."
                    % (edge_id,)
                )

            if actual_edge_type == "vz":
                region_id = (
                    source_id
                    if self.nodes[source_id].type == TYPE_REGION
                    else target_id
                )

                if self.region_to_viewpoints.get(region_id):
                    continue

                distance_var = vz_distance_var
            else:
                distance_var = vv_distance_var

            self.add_or_update_edge(
                source_node_id=source_id,
                target_node_id=target_id,
                distance_mean=float(edge_info["dist"]),
                distance_var=distance_var,
                cond_exist_prob=float(edge_info["exist_prob"]),
                exist_prob=float(edge_info["exist_prob"]),
                grounded=False,
            )

        for detection in payload["detections"]:
            target_indices = detection["target_indices"]
            founds = detection["founds"]

            for target_id, found in zip(target_indices, founds):
                if bool(found):
                    self.mark_target_found(str(target_id))

        self._drop_invalid_vz_edges()

        self._update_target_posteriors(
            previous_target_probs=previous_target_probs,
            existing_node_ids=existing_node_ids,
            region_initial_probs=region_initial_probs,
            viewpoint_initial_probs=viewpoint_initial_probs,
            scorer=scorer,
        )

        # Remove all found targets from every node's target_probs.
        # This must be after _update_target_posteriors, because that update may
        # otherwise add the found target keys back.
        self._remove_found_target_probs_from_nodes()

        self._update_region_existence_posteriors(
            previous_exist_probs=previous_exist_probs,
            existing_node_ids=existing_node_ids,
            region_initial_exist_probs=region_initial_exist_probs,
            scorer=scorer,
        )
        self._update_edge_distance_posteriors(
            previous_distance_means=previous_distance_means,
            previous_distance_vars=previous_distance_vars,
            previous_cond_exist_probs=previous_cond_exist_probs,
            scorer=scorer,
        )
        self._update_edge_existence_posteriors(
            previous_distance_means=previous_distance_means,
            previous_cond_exist_probs=previous_cond_exist_probs,
            scorer=scorer,
        )

        self.target_found

    def _remove_found_target_probs_from_nodes(self) -> None:
        found_target_ids = {
            str(target_id)
            for target_id, found in self.target_found.items()
            if bool(found)
        }

        if not found_target_ids:
            return

        for node in self.nodes.values():
            node.target_probs = {
                str(target_id): prob
                for target_id, prob in node.target_probs.items()
                if str(target_id) not in found_target_ids
            }

    def get_mllm_summary(self) -> Dict[str, object]:
        nodes = []

        for node_id in sorted(self.nodes):
            node = self.nodes[node_id]

            node_summary = {
                "id": node.node_id,
                "label": node.label,
                "type": "region" if node.type == TYPE_REGION else "viewpoint",
                "grounded": 1 if node.grounded else 0,
                "exist_prob": node.exist_prob,
                "target_probs": dict(node.target_probs),
                "node_visit_times": node.node_visit_times,
            }

            if node.type == TYPE_REGION:
                node_summary["assigned_viewpoint_ids"] = sorted(
                    self.region_to_viewpoints.get(node.node_id, set())
                )

            nodes.append(node_summary)

        edges = []
        for edge_id in sorted(self.edges):
            edge = self.edges[edge_id]
            edges.append(
                {
                    "i": edge.source_node_id,
                    "j": edge.target_node_id,
                    "type": self._edge_type(edge),
                    "distance_mean": edge.distance_mean,
                    "distance_var": edge.distance_var,
                    "cond_exist_prob": edge.cond_exist_prob,
                    "exist_prob": edge.exist_prob,
                    "grounded": 1 if edge.grounded else 0,
                }
            )

        return {
            "observation_step": self.observation_step,
            "targets": copy.deepcopy(self.target_records),
            "target_found": copy.deepcopy(self.target_found),
            "agent_current_vp_ids": copy.deepcopy(self.agent_current_vp_ids),
            "nodes": nodes,
            "edges": edges,
            "viewpoint_to_region": copy.deepcopy(self.viewpoint_to_region),
        }

    get_MLLM_summary = get_mllm_summary

    def get_graph_layout_snapshot(self) -> Dict[str, object]:
        nodes = []
        for node_id in sorted(self.nodes):
            node = self.nodes[node_id]
            node_record = {
                "id": node.node_id,
                "label": node.label,
                "type": "region" if node.type == TYPE_REGION else "viewpoint",
                "grounded": bool(node.grounded),
                "node_visit_times": node.node_visit_times,
                "connected_node_ids": sorted(node.connected_node_ids),
            }
            if node.type == TYPE_REGION:
                node_record["assigned_viewpoint_ids"] = sorted(
                    self.region_to_viewpoints.get(node.node_id, set())
                )
            nodes.append(node_record)

        edges = []
        for edge_id in sorted(self.edges):
            edge = self.edges[edge_id]
            edges.append(
                {
                    "i": edge.source_node_id,
                    "j": edge.target_node_id,
                    "type": self._edge_type(edge),
                    "grounded": bool(edge.grounded),
                }
            )

        return {
            "observation_step": self.observation_step,
            "agent_current_vp_ids": copy.deepcopy(self.agent_current_vp_ids),
            "nodes": nodes,
            "edges": edges,
            "viewpoint_to_region": copy.deepcopy(self.viewpoint_to_region),
            "region_to_viewpoints": {
                region_id: sorted(viewpoint_ids)
                for region_id, viewpoint_ids in sorted(
                    self.region_to_viewpoints.items()
                )
            },
        }

    def get_hypothesis_snapshot(self) -> Dict[str, object]:
        nodes = []
        for node_id in sorted(self.nodes):
            node = self.nodes[node_id]
            nodes.append(
                {
                    "id": node.node_id,
                    "label": node.label,
                    "type": "region" if node.type == TYPE_REGION else "viewpoint",
                    "grounded": bool(node.grounded),
                    "exist_prob": node.exist_prob,
                    "target_probs": dict(node.target_probs),
                    "node_visit_times": node.node_visit_times,
                }
            )

        edges = []
        for edge_id in sorted(self.edges):
            edge = self.edges[edge_id]
            edges.append(
                {
                    "i": edge.source_node_id,
                    "j": edge.target_node_id,
                    "type": self._edge_type(edge),
                    "distance_mean": edge.distance_mean,
                    "distance_var": edge.distance_var,
                    "cond_exist_prob": edge.cond_exist_prob,
                    "exist_prob": edge.exist_prob,
                    "grounded": bool(edge.grounded),
                }
            )

        return {
            "observation_step": self.observation_step,
            "targets": copy.deepcopy(self.target_records),
            "target_found": copy.deepcopy(self.target_found),
            "bayes_config": copy.deepcopy(self.bayes_config),
            "nodes": nodes,
            "edges": edges,
        }

    def export_debug_snapshot(self, output_dir: str, step_index: int) -> None:
        os.makedirs(output_dir, exist_ok=True)

        layout_path = os.path.join(
            output_dir,
            "graph_layout_step_%04d.json" % int(step_index),
        )
        hypothesis_path = os.path.join(
            output_dir,
            "hypothesis_step_%04d.json" % int(step_index),
        )

        with open(layout_path, "w", encoding="utf-8") as file_handle:
            json.dump(
                self.get_graph_layout_snapshot(),
                file_handle,
                indent=2,
                sort_keys=True,
            )

        with open(hypothesis_path, "w", encoding="utf-8") as file_handle:
            json.dump(
                self.get_hypothesis_snapshot(),
                file_handle,
                indent=2,
                sort_keys=True,
            )

    def _zero_target_probs(self) -> Dict[str, float]:
        return {target_id: 0.0 for target_id in self.target_ids}

    def _normalize_target_dict(
        self,
        target_probs: Dict[str, float],
    ) -> Dict[str, float]:
        return {
            target_id: float(target_probs.get(target_id, 0.0))
            for target_id in self.target_ids
        }

    def _target_text(self, target_id: str) -> str:
        target_id = str(target_id)
        if target_id not in self.target_id_to_description:
            raise KeyError("Unknown target_id: %s" % target_id)
        return self.target_id_to_description[target_id]

    def _build_region_alias_map(
        self, region_merges: Iterable[Iterable[int]]
    ) -> Dict[int, int]:
        alias_map = {}
        for raw_pair in region_merges:
            source_id, target_id = [int(value) for value in raw_pair]
            canonical_id = min(source_id, target_id)
            merged_id = max(source_id, target_id)
            alias_map[merged_id] = canonical_id
            alias_map.setdefault(canonical_id, canonical_id)
        return alias_map

    def _resolve_alias(self, node_id: int, alias_map: Dict[int, int]) -> int:
        resolved = int(node_id)
        while resolved in alias_map and alias_map[resolved] != resolved:
            resolved = alias_map[resolved]
        return resolved

    def _apply_region_alias_map(
        self, payload: Dict[str, object], alias_map: Dict[int, int]
    ) -> Dict[str, object]:
        if not alias_map:
            return copy.deepcopy(payload)

        updated = copy.deepcopy(payload)

        for region_list_key in ("visible_region_nodes", "invisible_region_nodes"):
            for region_info in updated.get(region_list_key, []):
                region_info["id"] = self._resolve_alias(region_info["id"], alias_map)

        for agent_info in updated.get("agents", []):
            agent_info["current_region_node_id"] = self._resolve_alias(
                agent_info["current_region_node_id"],
                alias_map,
            )

        for assign_info in updated.get("viewpoint_node_assigns", []):
            assign_info["region_node_id"] = self._resolve_alias(
                assign_info["region_node_id"],
                alias_map,
            )

        for edge_info in updated.get("new_edges", []):
            if int(edge_info["i"]) in alias_map:
                edge_info["i"] = self._resolve_alias(edge_info["i"], alias_map)
            if int(edge_info["j"]) in alias_map:
                edge_info["j"] = self._resolve_alias(edge_info["j"], alias_map)

        normalized_region_merges = []
        for merged_id, canonical_id in alias_map.items():
            if merged_id == canonical_id:
                continue
            normalized_region_merges.append([canonical_id, merged_id])

        if normalized_region_merges:
            updated["region_merges"] = normalized_region_merges

        return updated

    def _merge_existing_regions(self, alias_map: Dict[int, int]) -> None:
        for merged_id in sorted(alias_map):
            canonical_id = self._resolve_alias(merged_id, alias_map)
            if merged_id == canonical_id:
                continue
            if canonical_id not in self.nodes or merged_id not in self.nodes:
                continue
            self._merge_region_nodes(canonical_id, merged_id)

    def _merge_region_nodes(self, canonical_id: int, merged_id: int) -> None:
        canonical_node = self.nodes[canonical_id]
        merged_node = self.nodes[merged_id]
        canonical_node.exist_prob = max(
            canonical_node.exist_prob, merged_node.exist_prob
        )
        canonical_node.grounded = canonical_node.grounded or merged_node.grounded
        for target_id in self.target_ids:
            canonical_node.target_probs[target_id] = max(
                canonical_node.target_probs[target_id],
                merged_node.target_probs[target_id],
            )
        canonical_node.node_visit_times = max(
            canonical_node.node_visit_times, merged_node.node_visit_times
        )

        for viewpoint_id in list(self.region_to_viewpoints.get(merged_id, set())):
            self.viewpoint_to_region[viewpoint_id] = canonical_id
            self.region_to_viewpoints.setdefault(canonical_id, set()).add(viewpoint_id)
        self.region_to_viewpoints.pop(merged_id, None)

        affected_edges = [
            edge_id for edge_id in list(self.edges) if merged_id in edge_id
        ]
        for edge_id in affected_edges:
            edge = self.edges.pop(edge_id)
            other_id = (
                edge.source_node_id
                if edge.target_node_id == merged_id
                else edge.target_node_id
            )
            if other_id == canonical_id:
                continue
            new_edge_id = tuple(sorted((canonical_id, other_id)))
            if new_edge_id in self.edges:
                existing_edge = self.edges[new_edge_id]
                existing_edge.distance_mean = min(
                    existing_edge.distance_mean, edge.distance_mean
                )
                existing_edge.distance_var = min(
                    existing_edge.distance_var, edge.distance_var
                )
                existing_edge.cond_exist_prob = max(
                    existing_edge.cond_exist_prob, edge.cond_exist_prob
                )
                existing_edge.exist_prob = max(
                    existing_edge.exist_prob, edge.exist_prob
                )
                existing_edge.grounded = existing_edge.grounded or edge.grounded
            else:
                edge.source_node_id, edge.target_node_id = new_edge_id
                self.edges[new_edge_id] = edge
                self.nodes[new_edge_id[0]].connected_node_ids.add(new_edge_id[1])
                self.nodes[new_edge_id[1]].connected_node_ids.add(new_edge_id[0])

        self.nodes.pop(merged_id)
        for node in self.nodes.values():
            node.connected_node_ids.discard(merged_id)
        self.nodes[canonical_id].connected_node_ids.discard(canonical_id)

    def _refresh_region_to_viewpoints(self) -> None:
        self.region_to_viewpoints = {}
        for viewpoint_id, region_id in self.viewpoint_to_region.items():
            self.region_to_viewpoints.setdefault(region_id, set()).add(viewpoint_id)

    def _set_viewpoint_region(self, viewpoint_id: int, region_id: int) -> None:
        viewpoint_id = int(viewpoint_id)
        region_id = int(region_id)
        if viewpoint_id in self.viewpoint_to_region:
            old_region_id = self.viewpoint_to_region[viewpoint_id]
            if old_region_id == region_id:
                return
            self.region_to_viewpoints.setdefault(old_region_id, set()).discard(
                viewpoint_id
            )
        self.viewpoint_to_region[viewpoint_id] = region_id
        self.region_to_viewpoints.setdefault(region_id, set()).add(viewpoint_id)

    def _refresh_region_grounding(self) -> None:
        for node in self.nodes.values():
            if node.type != TYPE_REGION:
                continue
            assigned_viewpoints = self.region_to_viewpoints.get(node.node_id, set())
            node.grounded = node.grounded or any(
                self.nodes[viewpoint_id].grounded
                for viewpoint_id in assigned_viewpoints
            )
            if node.grounded:
                node.exist_prob = 1.0

    def _drop_invalid_vz_edges(self) -> None:
        invalid_edges = []
        for edge_id, edge in self.edges.items():
            if self._edge_type(edge) != "vz":
                continue
            region_id = (
                edge.source_node_id
                if self.nodes[edge.source_node_id].type == TYPE_REGION
                else edge.target_node_id
            )
            if self.region_to_viewpoints.get(region_id):
                invalid_edges.append(edge_id)
        for edge_id in invalid_edges:
            self.remove_edge(edge_id)

    def _agent_for_current_viewpoint(self, viewpoint_id: int) -> str:
        for agent_id, current_vp_id in self.agent_current_vp_ids.items():
            if current_vp_id == viewpoint_id:
                return agent_id
        raise KeyError("No agent is currently at viewpoint %s" % viewpoint_id)

    def _target_visual_score(
        self,
        node_id: int,
        target_id: str,
        scorer,
    ) -> float:
        node = self.nodes[node_id]
        target_text = self._target_text(target_id)

        if node.type == TYPE_VP:
            images = self.viewpoint_rgb_evidence.get(node_id, [])
            if not images:
                return 0.0
            return float(scorer.score_images_text(images, target_text))

        assigned_viewpoints = self.region_to_viewpoints.get(node_id, set())
        if not assigned_viewpoints:
            return 0.0

        return max(
            self._target_visual_score(viewpoint_id, target_id, scorer)
            for viewpoint_id in assigned_viewpoints
        )

    def _update_target_posteriors(
        self,
        previous_target_probs: Dict[int, Dict[str, float]],
        existing_node_ids: Set[int],
        region_initial_probs: Dict[int, Dict[str, float]],
        viewpoint_initial_probs: Dict[int, Dict[str, float]],
        scorer,
    ) -> None:
        eta_goal = float(self.bayes_config["eta_goal"])

        viewpoint_node_ids = [
            node_id for node_id, node in self.nodes.items() if node.type == TYPE_VP
        ]
        region_node_ids = [
            node_id for node_id, node in self.nodes.items() if node.type == TYPE_REGION
        ]

        for target_id in self.target_ids:
            if self.target_found.get(target_id, False):
                continue

            viewpoint_scores = {}

            for node_id in viewpoint_node_ids:
                # Grounded viewpoints are assumed to have already verified existence of their targets
                if self.nodes[node_id].grounded:
                    viewpoint_scores[node_id] = 0.0
                    continue
                if node_id in existing_node_ids:
                    prior_prob = previous_target_probs[node_id].get(target_id, 0.0)
                else:
                    prior_prob = viewpoint_initial_probs.get(node_id, {}).get(
                        target_id, 0.0
                    )

                likelihood = math.exp(
                    eta_goal * self._target_visual_score(node_id, target_id, scorer)
                )
                viewpoint_scores[node_id] = prior_prob * likelihood

            viewpoint_norm = sum(viewpoint_scores.values())

            if viewpoint_node_ids:
                if viewpoint_norm > 0.0:
                    for node_id in viewpoint_node_ids:
                        self.nodes[node_id].target_probs[target_id] = (
                            viewpoint_scores[node_id] / viewpoint_norm
                        )
                else:
                    uniform_prob = 1.0 / float(len(viewpoint_node_ids))
                    for node_id in viewpoint_node_ids:
                        self.nodes[node_id].target_probs[target_id] = uniform_prob

            region_scores = {}

            for node_id in region_node_ids:
                if node_id in existing_node_ids:
                    prior_prob = previous_target_probs[node_id].get(target_id, 0.0)
                else:
                    prior_prob = region_initial_probs.get(node_id, {}).get(
                        target_id, 0.0
                    )

                likelihood = math.exp(
                    eta_goal * self._target_visual_score(node_id, target_id, scorer)
                )
                region_scores[node_id] = prior_prob * likelihood

            region_norm = sum(region_scores.values())

            if region_node_ids:
                if region_norm > 0.0:
                    for node_id in region_node_ids:
                        self.nodes[node_id].target_probs[target_id] = (
                            region_scores[node_id] / region_norm
                        )
                else:
                    uniform_prob = 1.0 / float(len(region_node_ids))
                    for node_id in region_node_ids:
                        self.nodes[node_id].target_probs[target_id] = uniform_prob

    def _update_region_existence_posteriors(
        self,
        previous_exist_probs: Dict[int, float],
        existing_node_ids: Set[int],
        region_initial_exist_probs: Dict[int, float],
        scorer,
    ) -> None:
        eta_exist = float(self.bayes_config["eta_exist"])
        for node_id, node in self.nodes.items():
            if node.type != TYPE_REGION:
                node.exist_prob = 1.0
                continue
            if node.grounded:
                node.exist_prob = 1.0
                continue
            if node_id in existing_node_ids:
                prior_prob = previous_exist_probs.get(node_id, node.exist_prob)
            else:
                prior_prob = region_initial_exist_probs.get(node_id, node.exist_prob)
            assigned_viewpoints = self.region_to_viewpoints.get(node_id, set())
            scored_viewpoints = [
                viewpoint_id
                for viewpoint_id in assigned_viewpoints
                if self.viewpoint_rgb_evidence.get(viewpoint_id)
            ]
            if scored_viewpoints:
                zone_visual_score = max(
                    float(
                        scorer.score_images_text(
                            self.viewpoint_rgb_evidence[viewpoint_id], node.label
                        )
                    )
                    for viewpoint_id in scored_viewpoints
                )
            else:
                zone_visual_score = 0.0
            exist_likelihood = math.exp(eta_exist * zone_visual_score)
            non_exist_likelihood = math.exp(-eta_exist * zone_visual_score)
            denominator = exist_likelihood * prior_prob + non_exist_likelihood * (
                1.0 - prior_prob
            )
            if denominator <= 0.0:
                node.exist_prob = prior_prob
            else:
                node.exist_prob = exist_likelihood * prior_prob / denominator

    def _empirical_grounded_vv_stats(self) -> Tuple[float, float]:
        epsilon = float(self.bayes_config["epsilon"])
        grounded_vv_edges = [
            edge
            for edge in self.edges.values()
            if self._edge_type(edge) == "vv" and edge.grounded
        ]

        if not grounded_vv_edges:
            return 1.0, 1.0 + epsilon

        mean_distance = sum(edge.distance_mean for edge in grounded_vv_edges) / float(
            len(grounded_vv_edges)
        )
        variance = (
            sum((edge.distance_mean - mean_distance) ** 2 for edge in grounded_vv_edges)
            / float(len(grounded_vv_edges))
        ) + epsilon
        return mean_distance, variance

    def _vp_assignment_indicator(self, source_id: int, target_id: int) -> int:
        if self.viewpoint_to_region.get(source_id) == self.viewpoint_to_region.get(
            target_id
        ):
            return 1
        return 0

    def _vz_semantic_score(self, edge: GraphEdge, scorer) -> float:
        viewpoint_id = (
            edge.source_node_id
            if self.nodes[edge.source_node_id].type == TYPE_VP
            else edge.target_node_id
        )
        region_id = (
            edge.source_node_id
            if self.nodes[edge.source_node_id].type == TYPE_REGION
            else edge.target_node_id
        )
        images = self.viewpoint_rgb_evidence.get(viewpoint_id, [])
        if not images:
            return 0.0
        return float(scorer.score_images_text(images, self.nodes[region_id].label))

    def _update_edge_distance_posteriors(
        self,
        previous_distance_means: Dict[Tuple[int, int], float],
        previous_distance_vars: Dict[Tuple[int, int], float],
        previous_cond_exist_probs: Dict[Tuple[int, int], float],
        scorer,
    ) -> None:
        epsilon = float(self.bayes_config["epsilon"])
        sigma_vz2 = float(self.bayes_config["sigma_vz2"])
        sigma_vv2 = float(self.bayes_config["sigma_vv2"])
        kappa_vv = float(self.bayes_config["kappa_vv"])
        kappa_vz = float(self.bayes_config["kappa_vz"])
        empirical_mean, empirical_var = self._empirical_grounded_vv_stats()
        empirical_var = max(empirical_var, epsilon)

        for edge_id, edge in self.edges.items():
            edge_type = self._edge_type(edge)
            if edge_type == "vv" and edge.grounded:
                edge.distance_var = 0.0
                edge.cond_exist_prob = 1.0
                edge.exist_prob = 1.0
                continue

            prior_mean = previous_distance_means.get(edge_id, edge.distance_mean)
            prior_var = previous_distance_vars.get(
                edge_id, sigma_vv2 if edge_type == "vv" else sigma_vz2
            )
            prior_var = max(float(prior_var), epsilon)

            if edge_type == "vv":
                assignment_indicator = self._vp_assignment_indicator(
                    edge.source_node_id, edge.target_node_id
                )
                cue_mean = empirical_mean
                cue_var = empirical_var / (1.0 + kappa_vv * assignment_indicator)
            else:
                semantic_score = self._vz_semantic_score(edge, scorer)
                cue_mean = prior_mean * (1.0 - semantic_score)
                cue_var = sigma_vz2 / (1.0 + kappa_vz * ((1.0 + semantic_score) / 2.0))

            cue_var = max(float(cue_var), epsilon)

            posterior_var = 1.0 / ((1.0 / prior_var) + (1.0 / cue_var))
            posterior_mean = posterior_var * (
                (prior_mean / prior_var) + (cue_mean / cue_var)
            )
            edge.distance_var = posterior_var
            edge.distance_mean = posterior_mean
            edge.cond_exist_prob = previous_cond_exist_probs.get(
                edge_id, edge.cond_exist_prob
            )

    def _gaussian_density(self, x: float, mean: float, variance: float) -> float:
        epsilon = float(self.bayes_config["epsilon"])
        variance = max(float(variance), epsilon)
        return (1.0 / math.sqrt(2.0 * math.pi * variance)) * math.exp(
            -((x - mean) ** 2) / (2.0 * variance)
        )

    def _update_edge_existence_posteriors(
        self,
        previous_distance_means: Dict[Tuple[int, int], float],
        previous_cond_exist_probs: Dict[Tuple[int, int], float],
        scorer,
    ) -> None:
        epsilon = float(self.bayes_config["epsilon"])
        varrho = float(self.bayes_config["varrho"])
        omega_vz = float(self.bayes_config["omega_vz"])
        eta_vz = float(self.bayes_config["eta_vz"])
        empirical_mean, empirical_var = self._empirical_grounded_vv_stats()
        empirical_var = max(empirical_var, epsilon)

        for edge_id, edge in self.edges.items():
            edge_type = self._edge_type(edge)
            if edge_type == "vv" and edge.grounded:
                edge.cond_exist_prob = 1.0
                edge.exist_prob = 1.0
                edge.grounded = True
                continue

            prior_cond_exist_prob = previous_cond_exist_probs.get(
                edge_id, edge.cond_exist_prob
            )

            if edge_type == "vv":
                assignment_indicator = self._vp_assignment_indicator(
                    edge.source_node_id, edge.target_node_id
                )
                gaussian_term = self._gaussian_density(
                    edge.distance_mean, empirical_mean, empirical_var
                )
                exist_likelihood = gaussian_term * (
                    (varrho**assignment_indicator)
                    * ((1.0 - varrho) ** (1 - assignment_indicator))
                )
                non_exist_likelihood = (
                    gaussian_term
                    * (
                        1.0
                        - math.exp(
                            -((edge.distance_mean - empirical_mean) ** 2)
                            / (2.0 * empirical_var)
                        )
                    )
                    * (
                        ((1.0 - varrho) ** assignment_indicator)
                        * (varrho ** (1 - assignment_indicator))
                    )
                )
            else:
                semantic_score = self._vz_semantic_score(edge, scorer)
                previous_distance = previous_distance_means.get(
                    edge_id, edge.distance_mean
                )
                approach_effort = math.tanh(
                    (previous_distance - edge.distance_mean)
                    / (empirical_mean + epsilon)
                )
                edge_comp_score = (
                    omega_vz * semantic_score + (1.0 - omega_vz) * approach_effort
                )
                exist_likelihood = math.exp(eta_vz * edge_comp_score)
                non_exist_likelihood = math.exp(-eta_vz * edge_comp_score)

            denominator = (
                exist_likelihood * prior_cond_exist_prob
                + non_exist_likelihood * (1.0 - prior_cond_exist_prob)
            )
            if denominator <= 0.0:
                edge.cond_exist_prob = prior_cond_exist_prob
            else:
                edge.cond_exist_prob = (
                    exist_likelihood * prior_cond_exist_prob / denominator
                )

            source_exist = self.nodes[edge.source_node_id].exist_prob
            target_exist = self.nodes[edge.target_node_id].exist_prob
            edge.exist_prob = edge.cond_exist_prob * source_exist * target_exist
            edge.grounded = False

    def _edge_type(self, edge: GraphEdge) -> str:
        return self._edge_type_for_ids(edge.source_node_id, edge.target_node_id)

    def _edge_type_for_ids(self, source_node_id: int, target_node_id: int) -> str:
        source_type = self.nodes[source_node_id].type
        target_type = self.nodes[target_node_id].type
        if source_type == TYPE_VP and target_type == TYPE_VP:
            return "vv"
        if source_type == TYPE_REGION and target_type == TYPE_REGION:
            raise ValueError("Region-region edges are not allowed")
        return "vz"
