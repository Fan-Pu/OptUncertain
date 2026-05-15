from __future__ import annotations

from typing import Dict, List, Tuple

import debugpy
from gurobipy import GRB, Model, quicksum
from torch import mode

from Helper import TYPE_VP


class RollingHorizonOptimizer:
    def __init__(self, optimizer_config: dict | None = None):
        optimizer_config = optimizer_config or {}
        self.goal_weight = float(optimizer_config.get("goal_weight"))
        self.dist_weight = float(optimizer_config.get("dist_weight"))
        self.arc_weight = float(optimizer_config.get("arc_weight"))
        self.node_weight = float(optimizer_config.get("node_weight"))
        self.visit_weight = float(optimizer_config.get("visit_weight"))
        # the above should sum to 1.0
        self.ungrounded_reward_weight = float(
            optimizer_config.get("ungrounded_reward_weight")
        )  # the weight for rewards from ungrounded nodes, which may be less reliable than grounded nodes.

    def solve(
        self,
        hypothesis_graph,
        agent_current_vp_ids: Dict[str, int],
        target_found_flags: Dict[str, bool],
    ) -> Dict[str, object]:
        agent_ids = list(agent_current_vp_ids)
        target_ids = list(hypothesis_graph.target_ids)

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

        for agent_id in agent_ids:
            if not candidate_node_ids_by_agent[agent_id]:
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
            - hypothesis_graph.edges[tuple(sorted((source_id, target_id)))].exist_prob
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

        node_reward = {}
        for node_id in all_node_ids:
            node = hypothesis_graph.nodes[node_id]
            reward_weight = 1.0 if node.grounded else self.ungrounded_reward_weight
            node_reward[node_id] = {
                target_id: reward_weight * node.target_probs.get(target_id, 0.0)
                for target_id in target_ids
            }

        for agent_id in agent_ids:
            start_node_id = int(agent_current_vp_ids[agent_id])
            first_hop_vp_edges = [
                (source_id, target_id)
                for source_id, target_id in directed_edges
                if source_id == start_node_id
                and hypothesis_graph.nodes[target_id].type == TYPE_VP
            ]
            if not first_hop_vp_edges:
                raise RuntimeError(
                    "Agent %s has no outgoing viewpoint first-hop edge from node %s."
                    % (agent_id, start_node_id)
                )

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
        mtz_node_count = len(all_node_ids)

        for agent_id in agent_ids:
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
        )

        goal_term = quicksum(
            (1 - int(bool(target_found_flags[target_id])))
            * node_reward[node_id][target_id]
            * y[(node_id, agent_id)]
            for agent_id in agent_ids
            for node_id in candidate_node_ids_by_agent[agent_id]
            for target_id in target_ids
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

            for source_id, target_id in directed_edges:
                model.addConstr(
                    u[(source_id, agent_id)]
                    - u[(target_id, agent_id)]
                    + mtz_node_count * x[(source_id, target_id, agent_id)]
                    <= mtz_node_count - 1,
                    name="mtz_%s_%s_%s" % (source_id, target_id, agent_id),
                )

        # test
        # model.addConstr(x[16, 0, agent_ids[0]] == 1)
        # model.addConstr(x[9, 41, agent_ids[1]] == 1)

        model.update()
        model.optimize()

        if model.Status != GRB.OPTIMAL:
            raise RuntimeError("Optimizer did not find an optimal solution.")

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
                raise RuntimeError(
                    "Optimizer returned an empty path for agent %s." % agent_id
                )

            agent_paths[agent_id] = {
                "planned_path_node_ids": planned_path_node_ids,
                "next_vp_node_id": planned_path_node_ids[0],
                "route_node_ids": route_node_ids,
            }

        target_assignments = []

        # calculate all terms in the objective for debugging and analysis
        calculated_goal_term = goal_term.getValue()
        calculated_dist_term = dist_term.getValue()
        calculated_arc_term = arc_term.getValue()
        calculated_node_term = node_term.getValue()
        calculated_visit_term = visit_term.getValue()

        calculated_x_by_agent = {
            agent_id: [
                (source_id, target_id)
                for source_id, target_id in directed_edges
                if x[(source_id, target_id, agent_id)].X == 1.0
            ]
            for agent_id in agent_ids
        }

        return {
            "agent_paths": agent_paths,
            "target_assignments": target_assignments,
            "objective_value": model.ObjVal,
            "selected_edges": selected_edges,
        }

    def _normalized_expression(
        self, expression, lower_bound: float, upper_bound: float
    ):
        if lower_bound == upper_bound:
            return 0.0
        else:
            return (expression - float(lower_bound)) / (
                float(upper_bound) - float(lower_bound)
            )

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
    ):
        agent_ids = list(agent_current_vp_ids)
        goal_lower_bound = 0.0
        goal_upper_bound = sum(
            (1 - int(bool(target_found_flags[target_id])))
            * node_reward[node_id][target_id]
            for agent_id in agent_ids
            for node_id in candidate_node_ids_by_agent[agent_id]
            for target_id in target_ids
        )

        dist_lower_bound = 0.0
        dist_upper_bound = 0.0
        arc_lower_bound = 0.0
        arc_upper_bound = 0.0
        node_lower_bound = 0.0
        visit_lower_bound = 0.0

        for agent_id, start_node_id in agent_current_vp_ids.items():
            viewpoint_outgoing_edges = [
                (source_id, target_id)
                for source_id, target_id in directed_edges
                if source_id == int(start_node_id)
                and hypothesis_graph.nodes[target_id].type == TYPE_VP
            ]

            if not viewpoint_outgoing_edges:
                raise RuntimeError(
                    "Agent %s has no outgoing viewpoint edge from node %s."
                    % (agent_id, start_node_id)
                )

            goal_lower_bound += min(
                sum(
                    (1 - int(bool(target_found_flags[target_id])))
                    * node_reward[first_hop_node_id][target_id]
                    for target_id in target_ids
                )
                for _, first_hop_node_id in viewpoint_outgoing_edges
            )

            dist_lower_bound += min(
                edge_distance[(source_id, target_id)]
                for source_id, target_id in viewpoint_outgoing_edges
            )
            dist_upper_bound += max(
                edge_distance[(source_id, target_id)]
                for source_id, target_id in viewpoint_outgoing_edges
            ) + (len(all_node_ids) - 2) * max(
                edge_distance[(source_id, target_id)]
                for source_id, target_id in directed_edges
                if source_id != int(start_node_id) and target_id != int(start_node_id)
            )

            arc_upper_bound += (len(all_node_ids) - 2) * max(
                edge_nonexist_penalty[(source_id, target_id)]
                for source_id, target_id in directed_edges
                if source_id != int(start_node_id) and target_id != int(start_node_id)
            )

            visit_lower_bound += min(
                revisit_penalty.get(target_id, 0.0)
                for _, target_id in viewpoint_outgoing_edges
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
