from __future__ import annotations

from typing import Dict, List, Tuple

from gurobipy import GRB, Model, quicksum

from Helper import TYPE_VP


class RollingHorizonOptimizer:
    def __init__(self, optimizer_config: dict | None = None):
        optimizer_config = optimizer_config or {}
        self.goal_weight = float(optimizer_config.get("goal_weight", 0.2222))
        self.dist_weight = float(optimizer_config.get("dist_weight", 0.2222))
        self.arc_weight = float(optimizer_config.get("arc_weight", 0.4444))
        self.node_weight = float(optimizer_config.get("node_weight", 0.1111))
        self.ungrounded_reward_weight = float(
            optimizer_config.get("ungrounded_reward_weight", 0.8)
        )

    def solve(
        self,
        hypothesis_graph,
        agent_current_vp_ids: Dict[str, int],
        target_found_flags: Dict[str, bool],
    ) -> Dict[str, object]:
        agent_ids = list(agent_current_vp_ids)
        start_node_ids = {int(node_id) for node_id in agent_current_vp_ids.values()}
        candidate_node_ids = [
            node_id for node_id in sorted(hypothesis_graph.nodes) if node_id not in start_node_ids
        ]
        directed_edges = self._build_directed_edges(
            hypothesis_graph=hypothesis_graph,
            start_node_ids=start_node_ids,
        )
        edge_distance = {
            (source_id, target_id): hypothesis_graph.edges[tuple(sorted((source_id, target_id)))].distance_mean
            for source_id, target_id in directed_edges
        }
        edge_nonexist_penalty = {
            (source_id, target_id): 1.0
            - hypothesis_graph.edges[tuple(sorted((source_id, target_id)))].exist_prob
            for source_id, target_id in directed_edges
        }
        node_nonexist_penalty = {
            node_id: 1.0 - hypothesis_graph.nodes[node_id].exist_prob
            for node_id in candidate_node_ids
        }
        node_reward = {}
        for node_id in candidate_node_ids:
            node = hypothesis_graph.nodes[node_id]
            reward_weight = 1.0 if node.grounded else self.ungrounded_reward_weight
            node_reward[node_id] = {
                target_id: reward_weight * node.target_probs[target_id]
                for target_id in hypothesis_graph.target_descriptions
            }

        model = Model("multi_agent_many_to_many")
        model.Params.OutputFlag = 0

        x = {}
        for agent_id in agent_ids:
            for source_id, target_id in directed_edges:
                x[(source_id, target_id, agent_id)] = model.addVar(
                    vtype=GRB.BINARY,
                    name="x_%s_%s_%s" % (source_id, target_id, agent_id),
                )

        y = {}
        u = {}
        for agent_id in agent_ids:
            for node_id in candidate_node_ids:
                y[(node_id, agent_id)] = model.addVar(
                    vtype=GRB.BINARY,
                    name="y_%s_%s" % (node_id, agent_id),
                )
                u[(node_id, agent_id)] = model.addVar(
                    lb=1.0,
                    ub=float(len(candidate_node_ids)),
                    vtype=GRB.CONTINUOUS,
                    name="u_%s_%s" % (node_id, agent_id),
                )

        alpha = {}
        for agent_id in agent_ids:
            for node_id in candidate_node_ids:
                for target_id in hypothesis_graph.target_descriptions:
                    alpha[(node_id, target_id, agent_id)] = model.addVar(
                        vtype=GRB.BINARY,
                        name="alpha_%s_%s_%s" % (node_id, target_id, agent_id),
                    )

        (
            goal_lower_bound,
            goal_upper_bound,
            dist_lower_bound,
            dist_upper_bound,
            arc_lower_bound,
            arc_upper_bound,
            node_lower_bound,
            node_upper_bound,
        ) = self._objective_bounds(
            hypothesis_graph=hypothesis_graph,
            agent_current_vp_ids=agent_current_vp_ids,
            target_found_flags=target_found_flags,
            candidate_node_ids=candidate_node_ids,
            directed_edges=directed_edges,
            edge_distance=edge_distance,
            edge_nonexist_penalty=edge_nonexist_penalty,
            node_reward=node_reward,
            node_nonexist_penalty=node_nonexist_penalty,
        )

        goal_term = quicksum(
            node_reward[node_id][target_id] * alpha[(node_id, target_id, agent_id)]
            for agent_id in agent_ids
            for node_id in candidate_node_ids
            for target_id in hypothesis_graph.target_descriptions
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
            for node_id in candidate_node_ids
        )

        model.setObjective(
            self.goal_weight
            * ((goal_term - goal_lower_bound) / (goal_upper_bound - goal_lower_bound))
            - self.dist_weight
            * ((dist_term - dist_lower_bound) / (dist_upper_bound - dist_lower_bound))
            - self.arc_weight
            * ((arc_term - arc_lower_bound) / (arc_upper_bound - arc_lower_bound))
            - self.node_weight
            * ((node_term - node_lower_bound) / (node_upper_bound - node_lower_bound)),
            GRB.MAXIMIZE,
        )

        for agent_id in agent_ids:
            start_node_id = int(agent_current_vp_ids[agent_id])
            model.addConstr(
                quicksum(
                    x[(source_id, target_id, agent_id)]
                    for source_id, target_id in directed_edges
                    if source_id == start_node_id
                )
                == 1,
                name="depart_%s" % agent_id,
            )
            model.addConstr(
                quicksum(
                    x[(source_id, target_id, agent_id)]
                    for source_id, target_id in directed_edges
                    if source_id == start_node_id
                    and hypothesis_graph.nodes[target_id].type == TYPE_VP
                )
                == 1,
                name="first_hop_vp_%s" % agent_id,
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

            for node_id in candidate_node_ids:
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

            model.addConstr(
                quicksum(
                    x[(source_id, target_id, agent_id)]
                    for source_id, target_id in directed_edges
                    if source_id in candidate_node_ids
                )
                == quicksum(y[(node_id, agent_id)] for node_id in candidate_node_ids) - 1,
                name="open_path_%s" % agent_id,
            )

            for source_id, target_id in directed_edges:
                if source_id not in candidate_node_ids or target_id not in candidate_node_ids:
                    continue
                model.addConstr(
                    u[(source_id, agent_id)]
                    - u[(target_id, agent_id)]
                    + len(candidate_node_ids) * x[(source_id, target_id, agent_id)]
                    <= len(candidate_node_ids) - 1,
                    name="mtz_%s_%s_%s" % (source_id, target_id, agent_id),
                )

        for agent_id in agent_ids:
            for node_id in candidate_node_ids:
                for target_id in hypothesis_graph.target_descriptions:
                    model.addConstr(
                        alpha[(node_id, target_id, agent_id)]
                        <= (1 - int(bool(target_found_flags[target_id])))
                        * y[(node_id, agent_id)],
                        name="alpha_link_%s_%s_%s" % (node_id, target_id, agent_id),
                    )

        for target_id in hypothesis_graph.target_descriptions:
            model.addConstr(
                quicksum(
                    alpha[(node_id, target_id, agent_id)]
                    for agent_id in agent_ids
                    for node_id in candidate_node_ids
                )
                <= 1 - int(bool(target_found_flags[target_id])),
                name="unique_target_%s" % target_id,
            )

        model.optimize()
        if model.Status != GRB.OPTIMAL:
            raise RuntimeError("Optimizer did not find an optimal solution")

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
            agent_paths[agent_id] = {
                "planned_path_node_ids": planned_path_node_ids,
                "next_vp_node_id": planned_path_node_ids[0],
                "route_node_ids": route_node_ids,
            }

        target_assignments = []
        for agent_id in agent_ids:
            for node_id in candidate_node_ids:
                for target_id in hypothesis_graph.target_descriptions:
                    if alpha[(node_id, target_id, agent_id)].X > 0.5:
                        target_assignments.append(
                            {
                                "agent_id": agent_id,
                                "node_id": node_id,
                                "target_id": target_id,
                            }
                        )

        return {
            "agent_paths": agent_paths,
            "target_assignments": target_assignments,
            "objective_value": model.ObjVal,
            "selected_edges": selected_edges,
        }

    def _build_directed_edges(
        self,
        hypothesis_graph,
        start_node_ids,
    ) -> List[Tuple[int, int]]:
        directed_edges = []
        for edge in hypothesis_graph.edges.values():
            source_id = edge.source_node_id
            target_id = edge.target_node_id
            if target_id not in start_node_ids:
                directed_edges.append((source_id, target_id))
            if source_id not in start_node_ids:
                directed_edges.append((target_id, source_id))
        return sorted(set(directed_edges))

    def _objective_bounds(
        self,
        hypothesis_graph,
        agent_current_vp_ids,
        target_found_flags,
        candidate_node_ids,
        directed_edges,
        edge_distance,
        edge_nonexist_penalty,
        node_reward,
        node_nonexist_penalty,
    ):
        goal_lower_bound = 0.0
        goal_upper_bound = 0.0
        for target_id, is_found in target_found_flags.items():
            if is_found:
                continue
            goal_upper_bound += max(
                node_reward[node_id][target_id] for node_id in candidate_node_ids
            )

        dist_lower_bound = 0.0
        arc_lower_bound = 0.0
        node_lower_bound = 0.0
        for agent_id, start_node_id in agent_current_vp_ids.items():
            viewpoint_outgoing_edges = [
                (source_id, target_id)
                for source_id, target_id in directed_edges
                if source_id == start_node_id
                and hypothesis_graph.nodes[target_id].type == TYPE_VP
            ]
            dist_lower_bound += min(
                edge_distance[(source_id, target_id)]
                for source_id, target_id in viewpoint_outgoing_edges
            )
            arc_lower_bound += min(
                edge_nonexist_penalty[(source_id, target_id)]
                for source_id, target_id in viewpoint_outgoing_edges
            )
            node_lower_bound += min(
                node_nonexist_penalty[target_id]
                for _, target_id in viewpoint_outgoing_edges
            )

        max_edge_distance = max(
            edge_distance[(source_id, target_id)] for source_id, target_id in directed_edges
        )
        max_arc_penalty = max(
            edge_nonexist_penalty[(source_id, target_id)]
            for source_id, target_id in directed_edges
        )
        max_node_penalty = max(
            node_nonexist_penalty[node_id] for node_id in candidate_node_ids
        )
        scale = float(len(agent_current_vp_ids) * len(candidate_node_ids))
        dist_upper_bound = scale * max_edge_distance
        arc_upper_bound = scale * max_arc_penalty
        node_upper_bound = scale * max_node_penalty
        return (
            goal_lower_bound,
            goal_upper_bound,
            dist_lower_bound,
            dist_upper_bound,
            arc_lower_bound,
            arc_upper_bound,
            node_lower_bound,
            node_upper_bound,
        )

    def _extract_path(
        self,
        start_node_id: int,
        selected_edges: List[Tuple[int, int]],
    ) -> Tuple[List[int], List[int]]:
        outgoing_by_source = {source_id: target_id for source_id, target_id in selected_edges}
        route_node_ids = [start_node_id]
        planned_path_node_ids = []
        current_node_id = outgoing_by_source[start_node_id]
        while True:
            route_node_ids.append(current_node_id)
            planned_path_node_ids.append(current_node_id)
            if current_node_id not in outgoing_by_source:
                break
            current_node_id = outgoing_by_source[current_node_id]
        return planned_path_node_ids, route_node_ids
