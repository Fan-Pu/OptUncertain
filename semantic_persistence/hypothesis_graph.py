"""
Persistent shared hypothesis graph for many-to-many cooperative VLN.

The graph follows the paper's two-layer representation:
  - viewpoint nodes: physically executable poses
  - region nodes: semantic zones proposed by the MLLM

Viewpoint target probabilities are inferred by the MLLM and normalized per
target across non-current viewpoint nodes. Region target probabilities are
derived from assigned viewpoints or MLLM region scores, then normalized per
target across region nodes. Uncertain region existence / edge distance / edge
existence are updated with the paper's Bayesian rules.
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
        raw_target_probs: Dict[str, float],
        node_visit_times: int = 0,
        latent_exist_prob: Optional[float] = None,
    ):
        self.node_id = int(node_id)
        self.label = str(label)
        self.type = int(node_type)
        self.exist_prob = float(exist_prob)
        self.latent_exist_prob = (
            float(exist_prob) if latent_exist_prob is None else float(latent_exist_prob)
        )
        self.grounded = bool(grounded)
        self.target_probs = {
            str(target_id): float(value) for target_id, value in target_probs.items()
        }
        self.raw_target_probs = {
            str(target_id): float(value)
            for target_id, value in raw_target_probs.items()
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
            "sigma_vv2": 4.0,
            "sigma_vz2": 9.0,
            "kappa_vv": 1.0,
            "kappa_vz": 1.0,
            "varrho": 0.75,
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
        self.viewpoint_target_score_basis: Dict[int, Dict[str, str]] = {}
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
        raw_target_probs: Optional[Dict[str, float]] = None,
        node_visit_times: Optional[int] = None,
        latent_exist_prob: Optional[float] = None,
    ) -> GraphNode:
        node_id = int(node_id)

        target_probs_provided = target_probs is not None
        raw_target_probs_provided = raw_target_probs is not None

        if target_probs is None:
            target_probs = {}

        materialized_target_probs = self._materialize_target_probs(target_probs)
        materialized_raw_target_probs = self._materialize_target_probs(
            {} if raw_target_probs is None else raw_target_probs
        )

        if node_id not in self.nodes:
            self.nodes[node_id] = GraphNode(
                node_id=node_id,
                label=label,
                node_type=node_type,
                exist_prob=1.0 if exist_prob is None else float(exist_prob),
                grounded=False if grounded is None else bool(grounded),
                target_probs=materialized_target_probs,
                raw_target_probs=materialized_raw_target_probs,
                node_visit_times=(
                    0 if node_visit_times is None else int(node_visit_times)
                ),
                latent_exist_prob=(
                    1.0
                    if node_type == TYPE_VP
                    else (
                        float(exist_prob)
                        if latent_exist_prob is None
                        else float(latent_exist_prob)
                    )
                ),
            )
            return self.nodes[node_id]

        node = self.nodes[node_id]
        node.label = str(label)
        node.type = int(node_type)

        if exist_prob is not None:
            node.exist_prob = float(exist_prob)
            node.latent_exist_prob = 1.0 if node.type == TYPE_VP else float(exist_prob)

        if latent_exist_prob is not None:
            node.latent_exist_prob = (
                1.0 if node.type == TYPE_VP else float(latent_exist_prob)
            )

        if grounded is not None:
            node.grounded = bool(grounded)

        if target_probs_provided:
            for target_id in self._active_target_ids():
                node.target_probs[target_id] = float(
                    materialized_target_probs[target_id]
                )

        if raw_target_probs_provided:
            for target_id in self._active_target_ids():
                node.raw_target_probs[target_id] = float(
                    materialized_raw_target_probs[target_id]
                )

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

        existing_edge_ids = set(self.edges)
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
        region_target_scores: Dict[int, Dict[str, float]] = {}
        viewpoint_initial_probs: Dict[int, Dict[str, float]] = {}
        current_region_for_agent: Dict[str, int] = {}
        newly_grounded_viewpoints: Set[int] = set()
        candidate_viewpoint_ids: Set[int] = set()
        previous_type1_region_ids = {
            region_id
            for region_id, viewpoint_ids in self.region_to_viewpoints.items()
            if viewpoint_ids
        }

        region_info_by_id: Dict[int, Dict[str, object]] = {}
        visible_region_ids: Set[int] = set()

        for region_key in ("visible_region_nodes", "invisible_region_nodes"):
            for region_info in payload[region_key]:
                region_id = int(region_info["id"])
                region_info_by_id[region_id] = region_info
                if region_key == "visible_region_nodes":
                    visible_region_ids.add(region_id)

                region_initial_probs[region_id] = self._materialize_target_probs(
                    region_info["target_probs"]
                )
                region_initial_exist_probs[region_id] = float(region_info["exist_prob"])

                self.add_or_update_node(
                    node_id=region_id,
                    label=region_info["label"],
                    node_type=TYPE_REGION,
                    exist_prob=region_initial_exist_probs[region_id],
                    grounded=False,
                    target_probs=region_initial_probs[region_id],
                    raw_target_probs=region_initial_probs[region_id],
                )

        for item in payload.get("region_target_scores", []):
            region_id = int(item["id"])
            region_target_scores[region_id] = self._materialize_target_probs(
                item["target_scores"]
            )

        for observation in agent_observations:
            agent_id = str(observation["agent_id"])
            if agent_id not in observation_by_agent:
                raise KeyError("Missing observation for agent %s" % agent_id)

            current_vp_id = int(observation["current_viewpoint_index"])

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
                    target_probs=None,
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
            raw_target_probs = self._materialize_target_probs(
                target_prob_info.get(
                    "raw_target_probs",
                    target_prob_info["target_probs"],
                )
            )
            viewpoint_initial_probs[vp_id] = raw_target_probs
            self.add_or_update_node(
                node_id=vp_id,
                label=Helper.viewpoint_vp_label_by_index[vp_id],
                node_type=TYPE_VP,
                target_probs=self._materialize_target_probs(
                    target_prob_info["target_probs"]
                ),
                raw_target_probs=raw_target_probs,
            )

        for item in payload["viewpoint_target_score_basis"]:
            viewpoint_id = int(item["id"])
            self.viewpoint_target_score_basis[viewpoint_id] = {
                str(target_id): str(basis)
                for target_id, basis in item["score_basis"].items()
            }

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

        reassigned_current_viewpoint_to_region: Dict[int, int] = {}
        for item in payload["current_viewpoints_reassignment"]:
            viewpoint_id = int(item["viewpoint_id"])
            new_region_id = int(item["new_assigned_region_id"])
            if viewpoint_id in reassigned_current_viewpoint_to_region:
                raise ValueError(
                    "Duplicated current_viewpoints_reassignment item for viewpoint %s."
                    % viewpoint_id
                )
            reassigned_current_viewpoint_to_region[viewpoint_id] = new_region_id

        for agent_id, current_vp_id in self.agent_current_vp_ids.items():
            if current_vp_id in proposed_assignments:
                current_region_id = proposed_assignments[current_vp_id]
            elif current_vp_id in reassigned_current_viewpoint_to_region:
                current_region_id = reassigned_current_viewpoint_to_region[
                    current_vp_id
                ]
            else:
                if current_vp_id not in self.viewpoint_to_region:
                    raise KeyError(
                        "Current viewpoint %s has no region in viewpoint_node_assigns, "
                        "current_viewpoints_reassignment, or graph viewpoint_to_region."
                        % current_vp_id
                    )
                current_region_id = self.viewpoint_to_region[current_vp_id]

            if (
                current_vp_id in proposed_assignments
                and current_vp_id in reassigned_current_viewpoint_to_region
                and proposed_assignments[current_vp_id]
                != reassigned_current_viewpoint_to_region[current_vp_id]
            ):
                raise ValueError(
                    "Current viewpoint %s has conflicting regions in "
                    "viewpoint_node_assigns and current_viewpoints_reassignment."
                    % current_vp_id
                )

            if (
                current_region_id not in visible_region_ids
                and current_region_id not in existing_node_ids
            ):
                raise KeyError(
                    "Derived current region %s for agent %s viewpoint %s is not "
                    "included in visible_region_nodes or the existing graph."
                    % (current_region_id, agent_id, current_vp_id)
                )
            if current_region_id not in self.nodes:
                raise KeyError(
                    "Derived current region %s for agent %s viewpoint %s is not "
                    "present in the graph."
                    % (current_region_id, agent_id, current_vp_id)
                )
            if self.nodes[current_region_id].type != TYPE_REGION:
                raise ValueError(
                    "Derived current region %s for agent %s viewpoint %s is not a "
                    "region node." % (current_region_id, agent_id, current_vp_id)
                )

            current_region_for_agent[agent_id] = current_region_id

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

        self._drop_invalid_vz_edges()
        self._drop_invalid_hypothesized_vv_edges()

        self._apply_mllm_viewpoint_target_probabilities(
            viewpoint_initial_probs=viewpoint_initial_probs,
            current_viewpoint_ids=set(self.agent_current_vp_ids.values()),
        )
        self._apply_region_target_probabilities(
            region_target_scores=region_target_scores,
            previous_type1_region_ids=previous_type1_region_ids,
        )

        # Remove all found targets from every node's target_probs.
        # This must be after MLLM viewpoint target normalization, because that
        # update may otherwise add the found target keys back.
        self._remove_found_target_probs_from_nodes()

        self._refresh_region_grounding()
        self._update_edge_distance_posteriors(
            existing_edge_ids=existing_edge_ids,
            previous_distance_means=previous_distance_means,
            previous_distance_vars=previous_distance_vars,
            previous_cond_exist_probs=previous_cond_exist_probs,
            scorer=scorer,
        )
        self._update_edge_existence_posteriors(
            existing_edge_ids=existing_edge_ids,
            previous_distance_means=previous_distance_means,
            previous_cond_exist_probs=previous_cond_exist_probs,
            scorer=scorer,
        )

        self.target_found

    def update_without_mllm(
        self,
        agent_observations: List[Dict[str, object]],
    ) -> None:
        """Update observation-driven graph states when no MLLM call is made.

        This function is intended for cases such as the final step, where all
        targets have already been found and therefore no MLLM output is requested.

        It updates:
        - observation_step
        - current agent viewpoint ids
        - grounding status of current viewpoints
        - visit counts of current viewpoints
        - RGB evidence for current viewpoints
        - grounded VV edges from each current viewpoint to its visible neighbors
        - grounding status of assigned region nodes
        - removal of invalid VZ edges
        - removal of target probabilities for targets already marked as found

        It does not:
        - create or revise semantic region hypotheses
        - revise viewpoint-region assignments
        - add MLLM-proposed uncertain edges
        - preserve target probabilities
        """

        self.observation_step += 1

        self.agent_current_vp_ids = {}

        for observation in agent_observations:
            agent_id = str(observation["agent_id"])
            current_vp_id = int(observation["current_viewpoint_index"])

            self.agent_current_vp_ids[agent_id] = current_vp_id

            current_vp_label = Helper.viewpoint_vp_label_by_index[current_vp_id]

            # Preserve existing target_probs if the node already exists.
            # For a new viewpoint node, add_or_update_node() initializes them to zero.
            current_vp_node = self.add_or_update_node(
                node_id=current_vp_id,
                label=current_vp_label,
                node_type=TYPE_VP,
                exist_prob=1.0,
                grounded=True,
                target_probs=None,
            )

            current_vp_node.node_visit_times += 1

            self.viewpoint_rgb_evidence[current_vp_id] = [observation["raw_panorama"]]

            for visible_viewpoint in observation["visible_viewpoints"]:
                visible_vp_id = int(visible_viewpoint["viewpoint_index"])
                visible_label = Helper.viewpoint_vp_label_by_index[visible_vp_id]

                already_grounded = (
                    self.nodes[visible_vp_id].grounded
                    if visible_vp_id in self.nodes
                    else False
                )

                # Preserve existing target_probs if the node already exists.
                self.add_or_update_node(
                    node_id=visible_vp_id,
                    label=visible_label,
                    node_type=TYPE_VP,
                    exist_prob=1.0,
                    grounded=already_grounded,
                    target_probs=None,
                )

                # This VV edge is directly observed from the simulator, so it is grounded.
                self.add_or_update_edge(
                    source_node_id=current_vp_id,
                    target_node_id=visible_vp_id,
                    distance_mean=float(visible_viewpoint["distance"]),
                    distance_var=0.0,
                    cond_exist_prob=1.0,
                    exist_prob=1.0,
                    grounded=True,
                )

        # If a region already has this viewpoint assigned, grounding the viewpoint
        # should also ground that region.
        self._refresh_region_grounding()
        self._apply_region_target_probabilities(
            region_target_scores={},
            previous_type1_region_ids=set(),
        )

        # Remove VZ edges whose region now has assigned viewpoints.
        self._drop_invalid_vz_edges()
        self._drop_invalid_hypothesized_vv_edges()

        # If target_found has already been updated elsewhere, remove those found
        # targets from every node's target probability dictionary.
        self._remove_found_target_probs_from_nodes()

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
            node.raw_target_probs = {
                str(target_id): prob
                for target_id, prob in node.raw_target_probs.items()
                if str(target_id) not in found_target_ids
            }

        for viewpoint_id, target_score_basis in list(
            self.viewpoint_target_score_basis.items()
        ):
            self.viewpoint_target_score_basis[viewpoint_id] = {
                str(target_id): basis
                for target_id, basis in target_score_basis.items()
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
                "latent_exist_prob": node.latent_exist_prob,
                "target_probs": dict(node.target_probs),
                "raw_target_probs": dict(node.raw_target_probs),
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
                "exist_prob": node.exist_prob,
                "latent_exist_prob": node.latent_exist_prob,
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
                    "latent_exist_prob": node.latent_exist_prob,
                    "target_probs": dict(node.target_probs),
                    "raw_target_probs": dict(node.raw_target_probs),
                    "target_score_basis": copy.deepcopy(
                        self.viewpoint_target_score_basis.get(node.node_id, {})
                    ),
                    "node_visit_times": node.node_visit_times,
                }
            )
            if node.type == TYPE_REGION:
                nodes[-1]["assigned_viewpoint_ids"] = sorted(
                    self.region_to_viewpoints.get(node.node_id, set())
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

        # check if layout_path and hypothesis_path already exist, and if so, skip writing to avoid overwriting existing debug snapshots
        if os.path.exists(layout_path) or os.path.exists(hypothesis_path):
            debug(
                "Debug snapshot for step %d already exists, skipping export."
                % int(step_index)
            )
            return

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
        return {target_id: 0.0 for target_id in self._active_target_ids()}

    def _active_target_ids(self) -> List[str]:
        return [
            target_id
            for target_id in self.target_ids
            if not self.target_found.get(target_id, False)
        ]

    def _materialize_target_probs(
        self,
        target_probs: Dict[str, float],
    ) -> Dict[str, float]:
        return {
            target_id: float(target_probs.get(target_id, 0.0))
            for target_id in self._active_target_ids()
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
        canonical_node.latent_exist_prob = max(
            canonical_node.latent_exist_prob,
            merged_node.latent_exist_prob,
        )
        canonical_node.exist_prob = max(
            canonical_node.exist_prob, merged_node.exist_prob
        )
        for target_id in self._active_target_ids():
            canonical_node.target_probs[target_id] = max(
                canonical_node.target_probs[target_id],
                merged_node.target_probs[target_id],
            )
            canonical_node.raw_target_probs[target_id] = max(
                canonical_node.raw_target_probs[target_id],
                merged_node.raw_target_probs[target_id],
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
                node.exist_prob = 1.0
                node.latent_exist_prob = 1.0
                continue
            assigned_viewpoints = self.region_to_viewpoints.get(node.node_id, set())
            node.grounded = any(
                self.nodes[viewpoint_id].grounded
                for viewpoint_id in assigned_viewpoints
            )
            node.exist_prob = 1.0 if node.grounded else node.latent_exist_prob

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

    def _drop_invalid_hypothesized_vv_edges(self) -> None:
        invalid_edges = []
        for edge_id, edge in self.edges.items():
            if self._edge_type(edge) != "vv" or edge.grounded:
                continue
            if (
                self.nodes[edge.source_node_id].grounded
                or self.nodes[edge.target_node_id].grounded
            ):
                invalid_edges.append(edge_id)
        for edge_id in invalid_edges:
            self.remove_edge(edge_id)

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

    def _apply_mllm_viewpoint_target_probabilities(
        self,
        viewpoint_initial_probs: Dict[int, Dict[str, float]],
        current_viewpoint_ids: Set[int],
    ) -> None:
        viewpoint_node_ids = [
            node_id for node_id, node in self.nodes.items() if node.type == TYPE_VP
        ]
        detection_fixed_viewpoint_node_ids = {
            node_id
            for node_id in viewpoint_node_ids
            if (
                node_id in current_viewpoint_ids
                or self.nodes[node_id].grounded
                or self.nodes[node_id].node_visit_times > 0
            )
        }
        eligible_viewpoint_node_ids = [
            node_id
            for node_id in viewpoint_node_ids
            if node_id not in detection_fixed_viewpoint_node_ids
        ]

        for target_id in self._active_target_ids():
            for node_id in detection_fixed_viewpoint_node_ids:
                self.nodes[node_id].target_probs[target_id] = 0.0

            if not eligible_viewpoint_node_ids:
                continue

            raw_total = sum(
                float(viewpoint_initial_probs[node_id][target_id])
                for node_id in eligible_viewpoint_node_ids
            )
            if raw_total <= 0.0:
                raise ValueError(
                    "MLLM viewpoint target probabilities for target %s sum to %s."
                    % (target_id, raw_total)
                )

            for node_id in eligible_viewpoint_node_ids:
                self.nodes[node_id].target_probs[target_id] = (
                    float(viewpoint_initial_probs[node_id][target_id]) / raw_total
                )

    def _apply_region_target_probabilities(
        self,
        region_target_scores: Dict[int, Dict[str, float]],
        previous_type1_region_ids: Set[int],
    ) -> None:
        region_node_ids = [
            node_id for node_id, node in self.nodes.items() if node.type == TYPE_REGION
        ]

        for node_id, node in self.nodes.items():
            if node.type != TYPE_REGION:
                continue

            assigned_viewpoint_ids = self.region_to_viewpoints.get(node_id, set())
            if assigned_viewpoint_ids:
                for target_id in self._active_target_ids():
                    node.raw_target_probs[target_id] = sum(
                        float(self.nodes[viewpoint_id].target_probs[target_id])
                        for viewpoint_id in assigned_viewpoint_ids
                    ) / float(len(assigned_viewpoint_ids))
                continue

            if node_id in region_target_scores:
                for target_id, value in region_target_scores[node_id].items():
                    node.raw_target_probs[target_id] = float(value)
            elif node_id in previous_type1_region_ids:
                missing_target_ids = [
                    target_id
                    for target_id in self._active_target_ids()
                    if target_id not in region_target_scores.get(node_id, {})
                ]
                if missing_target_ids:
                    raise ValueError(
                        "Region %s changed from assigned to unassigned and requires "
                        "fresh region_target_scores for targets %s."
                        % (node_id, missing_target_ids)
                    )

        if not region_node_ids:
            return

        for target_id in self._active_target_ids():
            raw_total = sum(
                float(self.nodes[node_id].raw_target_probs[target_id])
                for node_id in region_node_ids
            )
            if raw_total <= 0.0:
                raise ValueError(
                    "Region target probabilities for target %s sum to %s."
                    % (target_id, raw_total)
                )

            for node_id in region_node_ids:
                self.nodes[node_id].target_probs[target_id] = (
                    float(self.nodes[node_id].raw_target_probs[target_id]) / raw_total
                )

    def _empirical_grounded_vv_stats(self) -> Tuple[float, float]:
        epsilon = float(self.bayes_config["epsilon"])
        grounded_vv_edges = [
            edge
            for edge in self.edges.values()
            if self._edge_type(edge) == "vv" and edge.grounded
        ]

        if not grounded_vv_edges:
            raise ValueError(
                "Cannot update uncertain edge hypotheses without grounded "
                "viewpoint-viewpoint distance evidence."
            )

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
        existing_edge_ids: Set[Tuple[int, int]],
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
        grounded_vv_edges = [
            edge
            for edge in self.edges.values()
            if self._edge_type(edge) == "vv" and edge.grounded
        ]
        grounded_vv_stats = (
            self._empirical_grounded_vv_stats() if grounded_vv_edges else None
        )

        for edge_id, edge in self.edges.items():
            edge_type = self._edge_type(edge)
            if edge_type == "vv" and edge.grounded:
                edge.distance_var = 0.0
                edge.cond_exist_prob = 1.0
                edge.exist_prob = 1.0
                continue

            if edge_id not in existing_edge_ids:
                edge.cond_exist_prob = previous_cond_exist_probs.get(
                    edge_id, edge.cond_exist_prob
                )
                continue

            prior_mean = previous_distance_means.get(edge_id, edge.distance_mean)
            prior_var = previous_distance_vars.get(
                edge_id, sigma_vv2 if edge_type == "vv" else sigma_vz2
            )
            prior_var = max(float(prior_var), epsilon)

            if edge_type == "vv":
                if grounded_vv_stats is None:
                    edge.distance_mean = prior_mean
                    edge.distance_var = prior_var
                    edge.cond_exist_prob = previous_cond_exist_probs.get(
                        edge_id, edge.cond_exist_prob
                    )
                    continue
                empirical_mean, empirical_var = grounded_vv_stats
                empirical_var = max(empirical_var, epsilon)
                assignment_indicator = self._vp_assignment_indicator(
                    edge.source_node_id, edge.target_node_id
                )
                cue_mean = empirical_mean
                cue_var = empirical_var / (1.0 + kappa_vv * assignment_indicator)
            else:
                viewpoint_id = (
                    edge.source_node_id
                    if self.nodes[edge.source_node_id].type == TYPE_VP
                    else edge.target_node_id
                )
                if not self.viewpoint_rgb_evidence.get(viewpoint_id):
                    edge.distance_mean = prior_mean
                    edge.distance_var = prior_var
                    edge.cond_exist_prob = previous_cond_exist_probs.get(
                        edge_id, edge.cond_exist_prob
                    )
                    continue
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
        existing_edge_ids: Set[Tuple[int, int]],
        previous_distance_means: Dict[Tuple[int, int], float],
        previous_cond_exist_probs: Dict[Tuple[int, int], float],
        scorer,
    ) -> None:
        epsilon = float(self.bayes_config["epsilon"])
        varrho = float(self.bayes_config["varrho"])
        eta_vz = float(self.bayes_config["eta_vz"])
        grounded_vv_edges = [
            edge
            for edge in self.edges.values()
            if self._edge_type(edge) == "vv" and edge.grounded
        ]
        grounded_vv_stats = (
            self._empirical_grounded_vv_stats() if grounded_vv_edges else None
        )

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

            if edge_id not in existing_edge_ids:
                edge.cond_exist_prob = prior_cond_exist_prob
                edge.exist_prob = self._unconditional_edge_exist_prob(edge)
                edge.grounded = False
                continue

            if edge_type == "vv":
                assignment_indicator = self._vp_assignment_indicator(
                    edge.source_node_id, edge.target_node_id
                )
                edge_comp_score = math.log(varrho / (1.0 - varrho)) * (
                    2.0 * assignment_indicator - 1.0
                )
                if grounded_vv_stats is not None:
                    empirical_mean, empirical_var = grounded_vv_stats
                    empirical_var = max(empirical_var, epsilon)
                    prior_distance = previous_distance_means.get(
                        edge_id, edge.distance_mean
                    )
                    edge_comp_score -= ((prior_distance - empirical_mean) ** 2) / (
                        2.0 * empirical_var
                    )
                exist_likelihood = math.exp(0.5 * edge_comp_score)
                non_exist_likelihood = math.exp(-0.5 * edge_comp_score)
            else:
                semantic_score = self._vz_semantic_score(edge, scorer)
                exist_likelihood = math.exp(eta_vz * semantic_score)
                non_exist_likelihood = math.exp(-eta_vz * semantic_score)

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

            edge.exist_prob = self._unconditional_edge_exist_prob(edge)
            edge.grounded = False

    def _unconditional_edge_exist_prob(self, edge: GraphEdge) -> float:
        if self._edge_type(edge) == "vv":
            return float(edge.cond_exist_prob)
        region_id = (
            edge.source_node_id
            if self.nodes[edge.source_node_id].type == TYPE_REGION
            else edge.target_node_id
        )
        return float(edge.cond_exist_prob) * float(self.nodes[region_id].exist_prob)

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
