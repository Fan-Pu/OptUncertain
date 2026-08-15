from __future__ import annotations

from typing import Dict, List, Tuple

import debugpy
from gurobipy import GRB, Model, quicksum

from Helper import TYPE_REGION, TYPE_VP


class RollingHorizonOptimizer:
    def __init__(
        self,
        optimizer_config: dict | None = None,
        gurobi_env=None,
    ):
        optimizer_config = optimizer_config or {}
        self.gurobi_env = gurobi_env
        self.goal_weight = float(optimizer_config.get("goal_weight"))
        self.dist_weight = float(optimizer_config.get("dist_weight"))
        self.arc_weight = float(optimizer_config.get("arc_weight"))
        self.node_weight = float(optimizer_config.get("node_weight"))
        self.visit_weight = float(optimizer_config.get("visit_weight"))
        # the above should sum to 1.0
        self.target_directed_mode = bool(
            optimizer_config.get("target_directed_mode", False)
        )
        self.target_directed_each_agent_when_possible = bool(
            optimizer_config.get("target_directed_each_agent_when_possible", True)
        )
        self.target_directed_use_raw_target_probs = bool(
            optimizer_config.get("target_directed_use_raw_target_probs", True)
        )
        self.unique_target_reward = bool(
            optimizer_config.get("unique_target_reward", False)
            or self.target_directed_mode
        )
        self.allow_inactive_agents = bool(
            optimizer_config.get("allow_inactive_agents", False)
        )
        self.force_positive_target_assignment = bool(
            optimizer_config.get("force_positive_target_assignment", False)
            or self.target_directed_mode
        )
        self.minimize_distance_after_targets = bool(
            optimizer_config.get("minimize_distance_after_targets", False)
        )
        self.write_model_lp = bool(optimizer_config.get("write_model_lp", True))

    def solve(
        self,
        hypothesis_graph,
        agent_current_vp_ids: Dict[str, int],
        target_found_flags: Dict[str, bool],
    ) -> Dict[str, object]:
        agent_ids = list(agent_current_vp_ids)
        target_ids = list(hypothesis_graph.target_ids)
        active_target_ids = [
            target_id for target_id in target_ids if not target_found_flags[target_id]
        ]

        if not agent_ids:
            raise RuntimeError("No active agents are available for optimization.")

        if not target_ids:
            raise RuntimeError("No target ids are available for optimization.")

        all_node_ids = sorted(hypothesis_graph.nodes)
        candidate_node_ids_by_agent = {
            agent_id: [
                node_id
                for node_id in all_node_ids
                if node_id != int(agent_current_vp_ids[agent_id])
            ]
            for agent_id in agent_ids
        }
        candidate_viewpoint_node_ids_by_agent = {
            agent_id: [
                node_id
                for node_id in candidate_node_ids_by_agent[agent_id]
                if hypothesis_graph.nodes[node_id].type == TYPE_VP
            ]
            for agent_id in agent_ids
        }
        current_viewpoint_ids = {int(value) for value in agent_current_vp_ids.values()}
        if self.target_directed_mode:
            reward_node_ids_by_agent = {
                agent_id: [
                    node_id
                    for node_id in candidate_node_ids_by_agent[agent_id]
                    if self._is_target_directed_reward_endpoint(
                        hypothesis_graph=hypothesis_graph,
                        node_id=node_id,
                        current_viewpoint_ids=current_viewpoint_ids,
                    )
                ]
                for agent_id in agent_ids
            }
        else:
            reward_node_ids_by_agent = {
                agent_id: [int(agent_current_vp_ids[agent_id])]
                + candidate_node_ids_by_agent[agent_id]
                for agent_id in agent_ids
            }
        for agent_id in agent_ids:
            if not candidate_node_ids_by_agent[agent_id]:
                if self.allow_inactive_agents:
                    continue
                raise RuntimeError(
                    "No candidate nodes are available for agent %s." % agent_id
                )

        directed_edges = self._build_directed_edges(
            hypothesis_graph=hypothesis_graph,
        )

        if not directed_edges:
            raise RuntimeError(
                "No directed edges are available for optimization. "
                "Check whether the graph contains local viewpoint-viewpoint edges."
            )

        edge_distance = {
            (source_id, target_id): hypothesis_graph.edges[
                tuple(sorted((source_id, target_id)))
            ].distance_mean
            for source_id, target_id in directed_edges
        }

        edge_nonexist_penalty = {
            (source_id, target_id): 1.0
            - hypothesis_graph.edges[
                tuple(sorted((source_id, target_id)))
            ].cond_exist_prob
            for source_id, target_id in directed_edges
        }

        node_nonexist_penalty = {
            node_id: 1.0 - hypothesis_graph.nodes[node_id].exist_prob
            for node_id in all_node_ids
        }

        revisit_penalty = {
            node_id: (
                float(hypothesis_graph.nodes[node_id].node_visit_times)
                if hypothesis_graph.nodes[node_id].type == TYPE_VP
                else 0.0
            )
            for node_id in all_node_ids
        }
        grounded_vv_degree = {node_id: 0 for node_id in all_node_ids}
        for edge in hypothesis_graph.edges.values():
            source_id = edge.source_node_id
            target_id = edge.target_node_id
            if self._is_grounded_vv_edge(hypothesis_graph, source_id, target_id):
                grounded_vv_degree[source_id] += 1
                grounded_vv_degree[target_id] += 1
        blocked_revisit_viewpoint_node_ids = {
            node_id
            for node_id in all_node_ids
            if hypothesis_graph.nodes[node_id].type == TYPE_VP
            and hypothesis_graph.nodes[node_id].grounded
            and hypothesis_graph.nodes[node_id].node_visit_times > 0
            and grounded_vv_degree[node_id] == 1
        }

        if self.target_directed_mode:
            reward_node_ids_by_agent = {
                agent_id: self._reachable_reward_endpoint_ids(
                    hypothesis_graph=hypothesis_graph,
                    start_node_id=int(agent_current_vp_ids[agent_id]),
                    directed_edges=directed_edges,
                    reward_node_ids=reward_node_ids_by_agent[agent_id],
                    blocked_revisit_viewpoint_node_ids=(
                        blocked_revisit_viewpoint_node_ids
                    ),
                )
                for agent_id in agent_ids
            }

        node_reward = {}
        for node_id in all_node_ids:
            node = hypothesis_graph.nodes[node_id]
            if node.type == TYPE_REGION:
                node_reward[node_id] = {target_id: 0.0 for target_id in target_ids}
                continue
            target_score_source = (
                node.raw_target_probs
                if self.target_directed_mode
                and self.target_directed_use_raw_target_probs
                else node.target_probs
            )
            node_reward[node_id] = {
                target_id: target_score_source.get(target_id, 0.0)
                for target_id in target_ids
            }

        if self.target_directed_mode:
            self._validate_target_directed_reward_endpoints(
                active_target_ids=active_target_ids,
                agent_ids=agent_ids,
                reward_node_ids_by_agent=reward_node_ids_by_agent,
                node_reward=node_reward,
            )

        for agent_id in agent_ids:
            start_node_id = int(agent_current_vp_ids[agent_id])
            first_hop_grounded_vv_edges = [
                (source_id, target_id)
                for source_id, target_id in directed_edges
                if source_id == start_node_id
                and self._is_grounded_vv_edge(
                    hypothesis_graph,
                    source_id,
                    target_id,
                )
            ]
            if not first_hop_grounded_vv_edges and not self.allow_inactive_agents:
                raise RuntimeError(
                    "Agent %s has no outgoing grounded VV first-hop edge from node %s."
                    % (agent_id, start_node_id)
                )

        if self.gurobi_env is None:
            model = Model("multi_agent_many_to_many")
        else:
            model = Model(
                "multi_agent_many_to_many",
                env=self.gurobi_env,
            )
        model.Params.OutputFlag = 0
        model.Params.TimeLimit = 30.0

        x = {}
        for agent_id in agent_ids:
            for source_id, target_id in directed_edges:
                x[(source_id, target_id, agent_id)] = model.addVar(
                    vtype=GRB.BINARY,
                    name="x_%s_%s_%s" % (source_id, target_id, agent_id),
                )

        y = {}
        u = {}
        agent_active = {}
        mtz_node_count = len(all_node_ids)

        for agent_id in agent_ids:
            if self.allow_inactive_agents:
                agent_active[agent_id] = model.addVar(
                    vtype=GRB.BINARY,
                    name="agent_active_%s" % agent_id,
                )

            for node_id in candidate_node_ids_by_agent[agent_id]:
                y[(node_id, agent_id)] = model.addVar(
                    vtype=GRB.BINARY,
                    name="y_%s_%s" % (node_id, agent_id),
                )

            for node_id in all_node_ids:
                u[(node_id, agent_id)] = model.addVar(
                    lb=1.0,
                    ub=float(mtz_node_count),
                    vtype=GRB.CONTINUOUS,
                    name="u_%s_%s" % (node_id, agent_id),
                )

        target_reward_assignment = {}
        if self.unique_target_reward:
            for agent_id in agent_ids:
                for node_id in reward_node_ids_by_agent[agent_id]:
                    for target_id in target_ids:
                        target_reward_assignment[(target_id, node_id, agent_id)] = (
                            model.addVar(
                                vtype=GRB.BINARY,
                                name="z_%s_%s_%s" % (target_id, node_id, agent_id),
                            )
                        )

        if self.unique_target_reward:
            goal_term = quicksum(
                node_reward[node_id][target_id]
                * target_reward_assignment[(target_id, node_id, agent_id)]
                for agent_id in agent_ids
                for node_id in reward_node_ids_by_agent[agent_id]
                for target_id in target_ids
            )
        else:
            goal_term = quicksum(
                max(
                    (1 - int(bool(target_found_flags[target_id])))
                    * node_reward[node_id][target_id]
                    for target_id in target_ids
                )
                * y[(node_id, agent_id)]
                for agent_id in agent_ids
                for node_id in candidate_node_ids_by_agent[agent_id]
            )

        dist_term = quicksum(
            edge_distance[(source_id, target_id)] * x[(source_id, target_id, agent_id)]
            for agent_id in agent_ids
            for source_id, target_id in directed_edges
        )

        arc_term = quicksum(
            edge_nonexist_penalty[(source_id, target_id)]
            * x[(source_id, target_id, agent_id)]
            for agent_id in agent_ids
            for source_id, target_id in directed_edges
        )

        node_term = quicksum(
            node_nonexist_penalty[node_id] * y[(node_id, agent_id)]
            for agent_id in agent_ids
            for node_id in candidate_node_ids_by_agent[agent_id]
        )

        visit_term = quicksum(
            revisit_penalty[node_id] * y[(node_id, agent_id)]
            for agent_id in agent_ids
            for node_id in candidate_viewpoint_node_ids_by_agent[agent_id]
        )

        objective_bounds = None
        if self.minimize_distance_after_targets and not self.target_directed_mode:
            model.setObjective(dist_term, GRB.MINIMIZE)
        else:
            (
                goal_lower_bound,
                goal_upper_bound,
                dist_lower_bound,
                dist_upper_bound,
                arc_lower_bound,
                arc_upper_bound,
                node_lower_bound,
                node_upper_bound,
                visit_lower_bound,
                visit_upper_bound,
            ) = self._objective_bounds(
                hypothesis_graph=hypothesis_graph,
                agent_current_vp_ids=agent_current_vp_ids,
                target_found_flags=target_found_flags,
                target_ids=target_ids,
                all_node_ids=all_node_ids,
                candidate_node_ids_by_agent=candidate_node_ids_by_agent,
                candidate_viewpoint_node_ids_by_agent=(
                    candidate_viewpoint_node_ids_by_agent
                ),
                directed_edges=directed_edges,
                edge_distance=edge_distance,
                edge_nonexist_penalty=edge_nonexist_penalty,
                node_reward=node_reward,
                node_nonexist_penalty=node_nonexist_penalty,
                revisit_penalty=revisit_penalty,
                unique_target_reward=self.unique_target_reward,
                allow_inactive_agents=self.allow_inactive_agents,
                reward_node_ids_by_agent=reward_node_ids_by_agent,
                blocked_revisit_viewpoint_node_ids=blocked_revisit_viewpoint_node_ids,
            )
            objective_bounds = {
                "goal": (goal_lower_bound, goal_upper_bound),
                "distance": (dist_lower_bound, dist_upper_bound),
                "arc_nonexistence": (arc_lower_bound, arc_upper_bound),
                "node_nonexistence": (node_lower_bound, node_upper_bound),
                "revisit": (visit_lower_bound, visit_upper_bound),
            }

            normalized_goal = self._normalized_expression(
                goal_term,
                goal_lower_bound,
                goal_upper_bound,
            )
            normalized_dist = self._normalized_expression(
                dist_term,
                dist_lower_bound,
                dist_upper_bound,
            )
            normalized_arc = self._normalized_expression(
                arc_term,
                arc_lower_bound,
                arc_upper_bound,
            )
            normalized_node = self._normalized_expression(
                node_term,
                node_lower_bound,
                node_upper_bound,
            )
            normalized_visit = self._normalized_expression(
                visit_term,
                visit_lower_bound,
                visit_upper_bound,
            )

            if self.target_directed_mode:
                model.ModelSense = GRB.MAXIMIZE
                model.setObjectiveN(
                    goal_term,
                    index=0,
                    priority=2,
                    weight=1.0,
                    abstol=0.0,
                    reltol=0.0,
                    name="target_directed_reward",
                )
                model.setObjectiveN(
                    -self.dist_weight * normalized_dist
                    - self.arc_weight * normalized_arc
                    - self.node_weight * normalized_node
                    - self.visit_weight * normalized_visit,
                    index=1,
                    priority=1,
                    weight=1.0,
                    abstol=0.0,
                    reltol=0.0,
                    name="target_directed_route_cost",
                )
            else:
                model.setObjective(
                    self.goal_weight * normalized_goal
                    - self.dist_weight * normalized_dist
                    - self.arc_weight * normalized_arc
                    - self.node_weight * normalized_node
                    - self.visit_weight * normalized_visit,
                    GRB.MAXIMIZE,
                )

        for agent_id in agent_ids:
            start_node_id = int(agent_current_vp_ids[agent_id])
            departure_count = quicksum(
                x[(source_id, target_id, agent_id)]
                for source_id, target_id in directed_edges
                if source_id == start_node_id
            )
            first_hop_viewpoint_count = quicksum(
                x[(source_id, target_id, agent_id)]
                for source_id, target_id in directed_edges
                if source_id == start_node_id
                and hypothesis_graph.nodes[target_id].type == TYPE_VP
            )
            first_hop_grounded_vv_count = quicksum(
                x[(source_id, target_id, agent_id)]
                for source_id, target_id in directed_edges
                if source_id == start_node_id
                and self._is_grounded_vv_edge(
                    hypothesis_graph,
                    source_id,
                    target_id,
                )
            )

            if self.allow_inactive_agents:
                model.addConstr(
                    departure_count == agent_active[agent_id],
                    name="depart_%s" % agent_id,
                )

                model.addConstr(
                    first_hop_viewpoint_count == agent_active[agent_id],
                    name="first_hop_vp_%s" % agent_id,
                )

                model.addConstr(
                    first_hop_grounded_vv_count == agent_active[agent_id],
                    name="first_hop_grounded_vv_%s" % agent_id,
                )
            else:
                model.addConstr(
                    departure_count == 1,
                    name="depart_%s" % agent_id,
                )

                model.addConstr(
                    first_hop_viewpoint_count == 1,
                    name="first_hop_vp_%s" % agent_id,
                )

                model.addConstr(
                    first_hop_grounded_vv_count == 1,
                    name="first_hop_grounded_vv_%s" % agent_id,
                )

            model.addConstr(
                quicksum(
                    x[(source_id, target_id, agent_id)]
                    for source_id, target_id in directed_edges
                    if target_id == start_node_id
                )
                == 0,
                name="no_return_%s" % agent_id,
            )

            for node_id in candidate_node_ids_by_agent[agent_id]:
                model.addConstr(
                    quicksum(
                        x[(source_id, target_id, agent_id)]
                        for source_id, target_id in directed_edges
                        if target_id == node_id
                    )
                    == y[(node_id, agent_id)],
                    name="flow_in_%s_%s" % (node_id, agent_id),
                )

                model.addConstr(
                    quicksum(
                        x[(source_id, target_id, agent_id)]
                        for source_id, target_id in directed_edges
                        if source_id == node_id
                    )
                    <= y[(node_id, agent_id)],
                    name="flow_out_%s_%s" % (node_id, agent_id),
                )

                if self.allow_inactive_agents:
                    model.addConstr(
                        y[(node_id, agent_id)] <= agent_active[agent_id],
                        name="inactive_no_visit_%s_%s" % (node_id, agent_id),
                    )

                if node_id in blocked_revisit_viewpoint_node_ids:
                    model.addConstr(
                        y[(node_id, agent_id)] == 0,
                        name="no_revisit_grounded_leaf_%s_%s"
                        % (node_id, agent_id),
                    )

            if self.unique_target_reward:
                for node_id in reward_node_ids_by_agent[agent_id]:
                    for target_id in target_ids:
                        if node_id != start_node_id:
                            model.addConstr(
                                target_reward_assignment[
                                    (target_id, node_id, agent_id)
                                ]
                                <= y[(node_id, agent_id)],
                                name="target_reward_visit_%s_%s_%s"
                                % (target_id, node_id, agent_id),
                            )
                        if self.allow_inactive_agents:
                            model.addConstr(
                                target_reward_assignment[
                                    (target_id, node_id, agent_id)
                                ]
                                <= agent_active[agent_id],
                                name="target_reward_active_%s_%s_%s"
                                % (target_id, node_id, agent_id),
                            )

            for source_id, target_id in directed_edges:
                model.addConstr(
                    u[(source_id, agent_id)]
                    - u[(target_id, agent_id)]
                    + mtz_node_count * x[(source_id, target_id, agent_id)]
                    <= mtz_node_count - 1,
                    name="mtz_%s_%s_%s" % (source_id, target_id, agent_id),
                )

        if self.unique_target_reward and self.force_positive_target_assignment:
            for target_id in target_ids:
                for agent_id in agent_ids:
                    for node_id in reward_node_ids_by_agent[agent_id]:
                        if node_reward[node_id][target_id] == 0.0:
                            model.addConstr(
                                target_reward_assignment[
                                    (target_id, node_id, agent_id)
                                ]
                                == 0,
                                name="target_reward_positive_%s_%s_%s"
                                % (target_id, node_id, agent_id),
                            )

        if self.unique_target_reward:
            for target_id in target_ids:
                target_assignment_sum = quicksum(
                    target_reward_assignment[(target_id, node_id, agent_id)]
                    for agent_id in agent_ids
                    for node_id in reward_node_ids_by_agent[agent_id]
                )
                if target_found_flags[target_id]:
                    model.addConstr(
                        target_assignment_sum == 0,
                        name="target_reward_found_%s" % target_id,
                    )
                elif self.target_directed_mode:
                    model.addConstr(
                        target_assignment_sum <= 1,
                        name="target_reward_unique_%s" % target_id,
                    )
                else:
                    model.addConstr(
                        target_assignment_sum == 1,
                        name="target_reward_unique_%s" % target_id,
                    )

        if (
            self.unique_target_reward
            and self.target_directed_mode
            and self.target_directed_each_agent_when_possible
            and len(active_target_ids) >= len(agent_ids)
        ):
            positive_target_candidates_by_agent = {
                agent_id: {
                    target_id
                    for target_id in active_target_ids
                    if any(
                        node_reward[node_id][target_id] > 0.0
                        for node_id in reward_node_ids_by_agent[agent_id]
                    )
                }
                for agent_id in agent_ids
            }
            if self._has_full_agent_target_matching(
                agent_ids=agent_ids,
                target_candidates_by_agent=positive_target_candidates_by_agent,
            ):
                for agent_id in agent_ids:
                    agent_target_assignment_sum = quicksum(
                        target_reward_assignment[(target_id, node_id, agent_id)]
                        for target_id in active_target_ids
                        for node_id in reward_node_ids_by_agent[agent_id]
                    )
                    if self.allow_inactive_agents:
                        model.addConstr(
                            agent_target_assignment_sum >= agent_active[agent_id],
                            name="target_directed_agent_assignment_%s" % agent_id,
                        )
                    else:
                        model.addConstr(
                            agent_target_assignment_sum >= 1,
                            name="target_directed_agent_assignment_%s" % agent_id,
                        )
            else:
                print(
                    "Skipping per-agent target-directed assignment constraints "
                    "because no distinct positive target matching covers all agents."
                )

        viewpoint_node_ids = [
            node_id
            for node_id in all_node_ids
            if hypothesis_graph.nodes[node_id].type == TYPE_VP
        ]
        for agent_index, agent_id in enumerate(agent_ids):
            for other_agent_id in agent_ids[agent_index + 1 :]:
                for viewpoint_id in viewpoint_node_ids:
                    action_at_viewpoint = self._action_at_viewpoint_expression(
                        model_vars=x,
                        directed_edges=directed_edges,
                        agent_id=agent_id,
                        start_node_id=int(agent_current_vp_ids[agent_id]),
                        viewpoint_id=viewpoint_id,
                        agent_active=(
                            agent_active[agent_id]
                            if self.allow_inactive_agents
                            else None
                        ),
                    )
                    other_action_at_viewpoint = self._action_at_viewpoint_expression(
                        model_vars=x,
                        directed_edges=directed_edges,
                        agent_id=other_agent_id,
                        start_node_id=int(agent_current_vp_ids[other_agent_id]),
                        viewpoint_id=viewpoint_id,
                        agent_active=(
                            agent_active[other_agent_id]
                            if self.allow_inactive_agents
                            else None
                        ),
                    )
                    model.addConstr(
                        action_at_viewpoint + other_action_at_viewpoint <= 1,
                        name=(
                            "unique_action_%s_%s_%s"
                            % (agent_id, other_agent_id, viewpoint_id)
                        ),
                    )

        # test
        # model.addConstr(x[16, 0, agent_ids[0]] == 1)
        # model.addConstr(x[9, 41, agent_ids[1]] == 1)

        model.update()
        self._write_model_if_enabled(model)
        self._print_model_size(model)
        print("Optimizing model...")
        model.optimize()
        print("Total time for optimization: %s seconds" % model.Runtime)

        self._assert_accepted_solver_status(model)
        solver_metadata = self._solver_metadata(model)

        agent_paths = {}
        selected_edges = {}

        for agent_id in agent_ids:
            chosen_edges = [
                (source_id, target_id)
                for source_id, target_id in directed_edges
                if x[(source_id, target_id, agent_id)].X > 0.5
            ]

            selected_edges[agent_id] = chosen_edges

            planned_path_node_ids, route_node_ids = self._extract_path(
                start_node_id=int(agent_current_vp_ids[agent_id]),
                selected_edges=chosen_edges,
            )

            if not planned_path_node_ids:
                if self.allow_inactive_agents and agent_active[agent_id].X < 0.5:
                    agent_paths[agent_id] = {
                        "planned_path_node_ids": [],
                        "next_vp_node_id": int(agent_current_vp_ids[agent_id]),
                        "route_node_ids": [int(agent_current_vp_ids[agent_id])],
                    }
                    continue
                raise RuntimeError(
                    "Optimizer returned an empty path for agent %s." % agent_id
                )

            agent_paths[agent_id] = {
                "planned_path_node_ids": planned_path_node_ids,
                "next_vp_node_id": planned_path_node_ids[0],
                "route_node_ids": route_node_ids,
            }

        target_assignments = []
        if self.unique_target_reward:
            target_assignments = [
                {
                    "target_id": str(target_id),
                    "node_id": int(node_id),
                    "agent_id": str(agent_id),
                }
                for target_id in target_ids
                for agent_id in agent_ids
                for node_id in reward_node_ids_by_agent[agent_id]
                if target_reward_assignment[(target_id, node_id, agent_id)].X > 0.5
            ]

        objective_terms = self._build_objective_terms(
            agent_ids=agent_ids,
            target_ids=target_ids,
            target_found_flags=target_found_flags,
            directed_edges=directed_edges,
            candidate_node_ids_by_agent=candidate_node_ids_by_agent,
            candidate_viewpoint_node_ids_by_agent=(
                candidate_viewpoint_node_ids_by_agent
            ),
            reward_node_ids_by_agent=reward_node_ids_by_agent,
            edge_distance=edge_distance,
            edge_nonexist_penalty=edge_nonexist_penalty,
            node_nonexist_penalty=node_nonexist_penalty,
            revisit_penalty=revisit_penalty,
            node_reward=node_reward,
            x=x,
            y=y,
            target_reward_assignment=target_reward_assignment,
            objective_bounds=objective_bounds,
            objective_value=float(model.ObjVal),
        )
        for agent_id in agent_ids:
            agent_paths[agent_id]["objective_terms"] = objective_terms["by_agent"][
                agent_id
            ]

        return {
            "agent_paths": agent_paths,
            "target_assignments": target_assignments,
            "objective_value": model.ObjVal,
            "objective_terms": objective_terms,
            "selected_edges": selected_edges,
            "solver": solver_metadata,
        }

    @classmethod
    def _assert_accepted_solver_status(cls, model) -> None:
        status = int(model.Status)
        if status == GRB.OPTIMAL:
            return
        if status == GRB.TIME_LIMIT and int(model.SolCount) > 0:
            print("Gurobi reached TimeLimit with a feasible incumbent; using incumbent.")
            return
        if status == GRB.TIME_LIMIT:
            raise RuntimeError(
                "Optimizer reached the time limit without a feasible incumbent solution."
            )
        raise RuntimeError(
            "Optimizer did not find an optimal solution or a time-limit incumbent. "
            "Gurobi status: %s."
            % cls._solver_status_name(status)
        )

    @staticmethod
    def _solver_status_name(status: int) -> str:
        status_names = {
            GRB.LOADED: "LOADED",
            GRB.OPTIMAL: "OPTIMAL",
            GRB.INFEASIBLE: "INFEASIBLE",
            GRB.INF_OR_UNBD: "INF_OR_UNBD",
            GRB.UNBOUNDED: "UNBOUNDED",
            GRB.CUTOFF: "CUTOFF",
            GRB.ITERATION_LIMIT: "ITERATION_LIMIT",
            GRB.NODE_LIMIT: "NODE_LIMIT",
            GRB.TIME_LIMIT: "TIME_LIMIT",
            GRB.SOLUTION_LIMIT: "SOLUTION_LIMIT",
            GRB.INTERRUPTED: "INTERRUPTED",
            GRB.NUMERIC: "NUMERIC",
            GRB.SUBOPTIMAL: "SUBOPTIMAL",
            GRB.INPROGRESS: "INPROGRESS",
            GRB.USER_OBJ_LIMIT: "USER_OBJ_LIMIT",
            GRB.WORK_LIMIT: "WORK_LIMIT",
            GRB.MEM_LIMIT: "MEM_LIMIT",
        }
        return status_names.get(int(status), str(int(status)))

    @staticmethod
    def _has_full_agent_target_matching(
        *,
        agent_ids: List[str],
        target_candidates_by_agent: Dict[str, set[str]],
    ) -> bool:
        matched_agent_by_target: Dict[str, str] = {}

        def assign(agent_id: str, visited_targets: set[str]) -> bool:
            for target_id in sorted(target_candidates_by_agent.get(agent_id, set())):
                if target_id in visited_targets:
                    continue
                visited_targets.add(target_id)
                matched_agent = matched_agent_by_target.get(target_id)
                if matched_agent is None or assign(matched_agent, visited_targets):
                    matched_agent_by_target[target_id] = agent_id
                    return True
            return False

        for agent_id in agent_ids:
            if not assign(agent_id, set()):
                return False
        return True

    @classmethod
    def _solver_metadata(cls, model) -> Dict[str, object]:
        status = int(model.Status)
        is_multi_objective = int(model.NumObj) > 1
        metadata = {
            "status": status,
            "status_name": cls._solver_status_name(status),
            "runtime_seconds": float(model.Runtime),
            "solution_count": int(model.SolCount),
            "objective_value": float(model.ObjVal),
            "used_time_limit_incumbent": bool(status == GRB.TIME_LIMIT),
            "is_multi_objective": is_multi_objective,
        }
        if not is_multi_objective:
            metadata["objective_bound"] = float(model.ObjBound)
            metadata["mip_gap"] = float(model.MIPGap)
        return metadata

    def _write_model_if_enabled(self, model: Model) -> None:
        if self.write_model_lp:
            self._write_model(model)

    def _write_model(self, model: Model) -> None:
        model.write("optimization_model.lp")
        print("Wrote Gurobi model to optimization_model.lp.")

    def _print_model_size(self, model: Model) -> None:
        binary_count = 0
        continuous_count = 0
        integer_count = 0

        for variable in model.getVars():
            if variable.VType == GRB.BINARY:
                binary_count += 1
            elif variable.VType == GRB.CONTINUOUS:
                continuous_count += 1
            elif variable.VType == GRB.INTEGER:
                integer_count += 1

        print("Gurobi model size:")
        print("  rows: %s" % model.NumConstrs)
        print("  columns: %s" % model.NumVars)
        print("  binary variables: %s" % binary_count)
        print("  continuous variables: %s" % continuous_count)
        print("  integer variables: %s" % integer_count)

    def _is_target_directed_reward_endpoint(
        self,
        hypothesis_graph,
        node_id: int,
        current_viewpoint_ids: set[int],
    ) -> bool:
        node = hypothesis_graph.nodes[node_id]
        if node.type == TYPE_VP:
            return (
                int(node_id) not in current_viewpoint_ids
                and not bool(node.grounded)
                and int(node.node_visit_times) == 0
            )
        if node.type == TYPE_REGION:
            return False
        raise ValueError("Unknown graph node type %s for node %s." % (node.type, node_id))

    def _validate_target_directed_reward_endpoints(
        self,
        active_target_ids: List[str],
        agent_ids: List[str],
        reward_node_ids_by_agent: Dict[str, List[int]],
        node_reward: Dict[int, Dict[str, float]],
    ) -> None:
        for target_id in active_target_ids:
            positive_endpoint_records = [
                {
                    "agent_id": str(agent_id),
                    "node_id": int(node_id),
                    "reward": float(node_reward[node_id][target_id]),
                }
                for agent_id in agent_ids
                for node_id in reward_node_ids_by_agent[agent_id]
                if float(node_reward[node_id][target_id]) > 0.0
            ]
            if positive_endpoint_records:
                continue

            eligible_endpoint_ids = sorted(
                {
                    int(node_id)
                    for agent_id in agent_ids
                    for node_id in reward_node_ids_by_agent[agent_id]
                }
            )
            raise RuntimeError(
                "Target-directed mode has no positive eligible endpoint for "
                "unfound target %s. Eligible endpoint ids: %s."
                % (target_id, eligible_endpoint_ids)
            )

    def _normalized_expression(
        self, expression, lower_bound: float, upper_bound: float
    ):
        if lower_bound == upper_bound:
            return 0.0
        else:
            return (expression - float(lower_bound)) / (
                float(upper_bound) - float(lower_bound)
            )

    def _normalized_value(
        self, value: float, lower_bound: float, upper_bound: float
    ) -> float:
        if lower_bound == upper_bound:
            return 0.0
        return (float(value) - float(lower_bound)) / (
            float(upper_bound) - float(lower_bound)
        )

    def _build_objective_terms(
        self,
        agent_ids,
        target_ids,
        target_found_flags,
        directed_edges,
        candidate_node_ids_by_agent,
        candidate_viewpoint_node_ids_by_agent,
        reward_node_ids_by_agent,
        edge_distance,
        edge_nonexist_penalty,
        node_nonexist_penalty,
        revisit_penalty,
        node_reward,
        x,
        y,
        target_reward_assignment,
        objective_bounds,
        objective_value: float,
    ) -> Dict[str, object]:
        term_names = [
            "goal",
            "distance",
            "arc_nonexistence",
            "node_nonexistence",
            "revisit",
        ]
        weights = {
            "goal": self.goal_weight,
            "distance": self.dist_weight,
            "arc_nonexistence": self.arc_weight,
            "node_nonexistence": self.node_weight,
            "revisit": self.visit_weight,
        }
        signs = {
            "goal": 1.0,
            "distance": -1.0,
            "arc_nonexistence": -1.0,
            "node_nonexistence": -1.0,
            "revisit": -1.0,
        }

        raw_by_agent = {}
        for agent_id in agent_ids:
            if self.unique_target_reward:
                goal_value = sum(
                    node_reward[node_id][target_id]
                    * target_reward_assignment[(target_id, node_id, agent_id)].X
                    for node_id in reward_node_ids_by_agent[agent_id]
                    for target_id in target_ids
                )
            else:
                goal_value = sum(
                    max(
                        (1 - int(bool(target_found_flags[target_id])))
                        * node_reward[node_id][target_id]
                        for target_id in target_ids
                    )
                    * y[(node_id, agent_id)].X
                    for node_id in candidate_node_ids_by_agent[agent_id]
                )

            raw_by_agent[agent_id] = {
                "goal": float(goal_value),
                "distance": float(
                    sum(
                        edge_distance[(source_id, target_id)]
                        * x[(source_id, target_id, agent_id)].X
                        for source_id, target_id in directed_edges
                    )
                ),
                "arc_nonexistence": float(
                    sum(
                        edge_nonexist_penalty[(source_id, target_id)]
                        * x[(source_id, target_id, agent_id)].X
                        for source_id, target_id in directed_edges
                    )
                ),
                "node_nonexistence": float(
                    sum(
                        node_nonexist_penalty[node_id] * y[(node_id, agent_id)].X
                        for node_id in candidate_node_ids_by_agent[agent_id]
                    )
                ),
                "revisit": float(
                    sum(
                        revisit_penalty[node_id] * y[(node_id, agent_id)].X
                        for node_id in candidate_viewpoint_node_ids_by_agent[agent_id]
                    )
                ),
            }

        global_raw = {
            term_name: float(
                sum(raw_by_agent[agent_id][term_name] for agent_id in agent_ids)
            )
            for term_name in term_names
        }

        if self.minimize_distance_after_targets:
            by_agent = {
                agent_id: {
                    "raw": raw_by_agent[agent_id],
                    "normalized_contribution": {},
                    "weighted_contribution": {
                        "distance": raw_by_agent[agent_id]["distance"]
                    },
                }
                for agent_id in agent_ids
            }
            return {
                "objective_value": float(objective_value),
                "objective_sense": "minimize",
                "objective_constant_offset": 0.0,
                "weighted_contribution_sum": global_raw["distance"],
                "global": {
                    "raw": global_raw,
                    "bounds": {},
                    "normalized": {},
                    "weighted": {"distance": global_raw["distance"]},
                },
                "by_agent": by_agent,
            }

        global_normalized = {}
        global_weighted = {}
        objective_constant_offset = 0.0
        by_agent = {}
        for agent_id in agent_ids:
            by_agent[agent_id] = {
                "raw": raw_by_agent[agent_id],
                "normalized_contribution": {},
                "weighted_contribution": {},
            }

        for term_name in term_names:
            lower_bound, upper_bound = objective_bounds[term_name]
            global_normalized[term_name] = self._normalized_value(
                global_raw[term_name],
                lower_bound,
                upper_bound,
            )
            global_weighted[term_name] = (
                signs[term_name] * weights[term_name] * global_normalized[term_name]
            )
            if lower_bound == upper_bound:
                for agent_id in agent_ids:
                    by_agent[agent_id]["normalized_contribution"][term_name] = 0.0
                    by_agent[agent_id]["weighted_contribution"][term_name] = 0.0
                continue

            term_range = float(upper_bound) - float(lower_bound)
            objective_constant_offset += (
                signs[term_name] * weights[term_name] * (-float(lower_bound))
            ) / term_range
            for agent_id in agent_ids:
                normalized_contribution = raw_by_agent[agent_id][term_name] / term_range
                by_agent[agent_id]["normalized_contribution"][term_name] = float(
                    normalized_contribution
                )
                by_agent[agent_id]["weighted_contribution"][term_name] = float(
                    signs[term_name] * weights[term_name] * normalized_contribution
                )

        return {
            "objective_value": float(objective_value),
            "objective_sense": "maximize",
            "objective_constant_offset": float(objective_constant_offset),
            "weighted_contribution_sum": float(sum(global_weighted.values())),
            "global": {
                "raw": global_raw,
                "bounds": {
                    term_name: {
                        "lower": float(objective_bounds[term_name][0]),
                        "upper": float(objective_bounds[term_name][1]),
                    }
                    for term_name in term_names
                },
                "normalized": global_normalized,
                "weighted": global_weighted,
            },
            "by_agent": by_agent,
        }

    def _build_directed_edges(
        self,
        hypothesis_graph,
    ) -> List[Tuple[int, int]]:
        directed_edges = []

        for edge in hypothesis_graph.edges.values():
            source_id = edge.source_node_id
            target_id = edge.target_node_id

            directed_edges.append((source_id, target_id))
            directed_edges.append((target_id, source_id))

        return sorted(set(directed_edges))

    def _reachable_reward_endpoint_ids(
        self,
        hypothesis_graph,
        start_node_id: int,
        directed_edges: List[Tuple[int, int]],
        reward_node_ids: List[int],
        blocked_revisit_viewpoint_node_ids: set[int],
    ) -> List[int]:
        reward_node_id_set = {int(node_id) for node_id in reward_node_ids}
        blocked_node_ids = {int(node_id) for node_id in blocked_revisit_viewpoint_node_ids}
        adjacency = {}
        for source_id, target_id in directed_edges:
            adjacency.setdefault(int(source_id), []).append(int(target_id))

        queue = []
        seen = {int(start_node_id)}
        for source_id, target_id in directed_edges:
            if int(source_id) != int(start_node_id):
                continue
            if int(target_id) in blocked_node_ids:
                continue
            if not self._is_grounded_vv_edge(hypothesis_graph, source_id, target_id):
                continue
            queue.append(int(target_id))
            seen.add(int(target_id))

        reachable_reward_node_ids = []
        while queue:
            node_id = queue.pop(0)
            if node_id in reward_node_id_set:
                reachable_reward_node_ids.append(node_id)

            for next_node_id in adjacency.get(node_id, []):
                if next_node_id in seen:
                    continue
                if next_node_id in blocked_node_ids:
                    continue
                seen.add(next_node_id)
                queue.append(next_node_id)

        return sorted(set(reachable_reward_node_ids))

    def _action_at_viewpoint_expression(
        self,
        model_vars,
        directed_edges: List[Tuple[int, int]],
        agent_id: str,
        start_node_id: int,
        viewpoint_id: int,
        agent_active=None,
    ):
        first_hop_to_viewpoint = quicksum(
            model_vars[(source_id, target_id, agent_id)]
            for source_id, target_id in directed_edges
            if source_id == start_node_id and target_id == viewpoint_id
        )
        if agent_active is not None and viewpoint_id == start_node_id:
            return first_hop_to_viewpoint + (1 - agent_active)
        return first_hop_to_viewpoint

    def _is_grounded_vv_edge(
        self,
        hypothesis_graph,
        source_id: int,
        target_id: int,
    ) -> bool:
        return (
            hypothesis_graph.nodes[source_id].type == TYPE_VP
            and hypothesis_graph.nodes[target_id].type == TYPE_VP
            and hypothesis_graph.edges[tuple(sorted((source_id, target_id)))].grounded
        )

    def _objective_bounds(
        self,
        hypothesis_graph,
        agent_current_vp_ids,
        target_found_flags,
        target_ids,
        all_node_ids,
        candidate_node_ids_by_agent,
        candidate_viewpoint_node_ids_by_agent,
        directed_edges,
        edge_distance,
        edge_nonexist_penalty,
        node_reward,
        node_nonexist_penalty,
        revisit_penalty,
        unique_target_reward=False,
        allow_inactive_agents=False,
        reward_node_ids_by_agent=None,
        blocked_revisit_viewpoint_node_ids=None,
    ):
        agent_ids = list(agent_current_vp_ids)
        if reward_node_ids_by_agent is None:
            reward_node_ids_by_agent = candidate_node_ids_by_agent
        blocked_revisit_viewpoint_node_ids = set(
            blocked_revisit_viewpoint_node_ids or set()
        )

        def active_node_reward(node_id: int) -> float:
            return max(
                (1 - int(bool(target_found_flags[target_id])))
                * node_reward[node_id][target_id]
                for target_id in target_ids
            )

        goal_lower_bound = 0.0
        if unique_target_reward:
            goal_upper_bound = sum(
                (
                    0.0
                    if target_found_flags[target_id]
                    else max(
                        node_reward[node_id][target_id]
                        for agent_id in agent_ids
                        for node_id in reward_node_ids_by_agent[agent_id]
                    )
                )
                for target_id in target_ids
            )
        else:
            goal_upper_bound = sum(
                active_node_reward(node_id)
                for agent_id in agent_ids
                for node_id in candidate_node_ids_by_agent[agent_id]
                if node_id not in blocked_revisit_viewpoint_node_ids
            )

        dist_lower_bound = 0.0
        dist_upper_bound = 0.0
        arc_lower_bound = 0.0
        arc_upper_bound = 0.0
        node_lower_bound = 0.0
        visit_lower_bound = 0.0

        for agent_id, start_node_id in agent_current_vp_ids.items():
            first_hop_grounded_vv_edges = [
                (source_id, target_id)
                for source_id, target_id in directed_edges
                if source_id == int(start_node_id)
                and self._is_grounded_vv_edge(
                    hypothesis_graph,
                    source_id,
                    target_id,
                )
            ]

            if not first_hop_grounded_vv_edges:
                if allow_inactive_agents:
                    continue
                raise RuntimeError(
                    "Agent %s has no outgoing grounded VV edge from node %s."
                    % (agent_id, start_node_id)
                )

            if not unique_target_reward:
                first_hop_goal_edges = [
                    (source_id, target_id)
                    for source_id, target_id in first_hop_grounded_vv_edges
                    if target_id not in blocked_revisit_viewpoint_node_ids
                ]
                if not first_hop_goal_edges:
                    if allow_inactive_agents:
                        continue
                    raise RuntimeError(
                        "Agent %s has no non-dead-end grounded first-hop edge from "
                        "node %s." % (agent_id, start_node_id)
                    )
                goal_lower_bound += min(
                    active_node_reward(first_hop_node_id)
                    for _, first_hop_node_id in first_hop_goal_edges
                )

            if not allow_inactive_agents:
                dist_lower_bound += min(
                    edge_distance[(source_id, target_id)]
                    for source_id, target_id in first_hop_grounded_vv_edges
                )
            non_start_edges = [
                (source_id, target_id)
                for source_id, target_id in directed_edges
                if source_id != int(start_node_id) and target_id != int(start_node_id)
            ]
            upper_bound_edges = (
                directed_edges
                if unique_target_reward or not non_start_edges
                else non_start_edges
            )
            dist_upper_bound += max(
                edge_distance[(source_id, target_id)]
                for source_id, target_id in first_hop_grounded_vv_edges
            ) + (len(all_node_ids) - 2) * (
                max(
                    edge_distance[(source_id, target_id)]
                    for source_id, target_id in upper_bound_edges
                )
            )

            if unique_target_reward or not non_start_edges:
                arc_upper_bound += (len(all_node_ids) - 1) * max(
                    edge_nonexist_penalty[(source_id, target_id)]
                    for source_id, target_id in directed_edges
                )
            else:
                arc_upper_bound += (len(all_node_ids) - 2) * max(
                    edge_nonexist_penalty[(source_id, target_id)]
                    for source_id, target_id in non_start_edges
                )

            if not allow_inactive_agents:
                visit_lower_bound += min(
                    revisit_penalty.get(target_id, 0.0)
                    for _, target_id in first_hop_grounded_vv_edges
                )

        node_upper_bound = sum(
            node_nonexist_penalty[node_id]
            for agent_id in agent_ids
            for node_id in candidate_node_ids_by_agent[agent_id]
        )
        visit_upper_bound = sum(
            revisit_penalty[node_id]
            for agent_id in agent_ids
            for node_id in candidate_viewpoint_node_ids_by_agent[agent_id]
        )

        return (
            goal_lower_bound,
            goal_upper_bound,
            dist_lower_bound,
            dist_upper_bound,
            arc_lower_bound,
            arc_upper_bound,
            node_lower_bound,
            node_upper_bound,
            visit_lower_bound,
            visit_upper_bound,
        )

    def _extract_path(
        self,
        start_node_id: int,
        selected_edges: List[Tuple[int, int]],
    ) -> Tuple[List[int], List[int]]:
        outgoing_by_source = {
            source_id: target_id for source_id, target_id in selected_edges
        }

        if start_node_id not in outgoing_by_source:
            return [], [start_node_id]

        route_node_ids = [start_node_id]
        planned_path_node_ids = []
        current_node_id = outgoing_by_source[start_node_id]
        visited_node_ids = {start_node_id}

        while True:
            if current_node_id in visited_node_ids:
                raise RuntimeError(
                    "Extracted path contains a cycle at node %s." % current_node_id
                )

            visited_node_ids.add(current_node_id)
            route_node_ids.append(current_node_id)
            planned_path_node_ids.append(current_node_id)

            if current_node_id not in outgoing_by_source:
                break

            current_node_id = outgoing_by_source[current_node_id]

        return planned_path_node_ids, route_node_ids
