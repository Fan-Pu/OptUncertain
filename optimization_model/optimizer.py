from gurobipy import GRB, Model, quicksum

from Helper import TYPE_VP
from semantic_persistence.hypothesis_graph import HypothesisGraph, GraphNode, GraphEdge


class RollingHorizonOptimizer:
    def __init__(self):
        self.alpha = 1.0  # weight for distance cost: the cost between the current viewpoint and the next viewpoint.
        self.beta = 2.0  # weight for risk cost: the cost of traversing an edge with low existence probability.
        self.gamma = 0.5  # weight for node risk cost: the cost of resolving a node with low existence probability.
        self.service_cost = 0.5
        self.budget = 20.0
        self.grounded_resolution_weight = 1.25
        self.ungrounded_resolution_weight = 1.0

    def solve(self, hypothesis_graph, current_vp_node_id):
        """Plan a multi-step viewpoint route and expose its first hop."""

        # Candidate path nodes include both viewpoint and region nodes. The current
        # viewpoint is the fixed route start, so it does not get its own path variable.
        path_node_ids = [
            node_id
            for node_id in sorted(hypothesis_graph.nodes)
            if node_id != current_vp_node_id
        ]

        # The graph stores undirected navigation edges, but the MILP uses directed edge
        # decisions so both travel directions are enumerated here for viewpoint-region
        # and viewpoint-viewpoint connectivity alike.
        directed_edges = []
        edge_distance = {}  # (source_id, target_id) -> travel distance
        edge_risk = {}  # (source_id, target_id) -> uncertainty penalty
        for edge in hypothesis_graph.edges.values():
            source_id = edge.source_node_id
            target_id = edge.target_node_id
            directed_edges.append((source_id, target_id))
            directed_edges.append((target_id, source_id))
            edge_distance[(source_id, target_id)] = edge.distance
            edge_distance[(target_id, source_id)] = edge.distance
            edge_risk[(source_id, target_id)] = 1.0 - edge.exist_prob
            edge_risk[(target_id, source_id)] = 1.0 - edge.exist_prob

        # Reward and risk terms for visiting each viewpoint.
        #
        # node_reward[node_id]:
        #   Expected value of visiting the viewpoint. This is based on the best target
        #   probability attached either to the viewpoint itself or to its linked region,
        #   discounted by how much of that viewpoint has already been seen.
        #
        # node_risk[node_id]:
        #   Penalty for spending effort on a low-confidence node/region.
        #
        # resolution_weight[node_id]:
        #   Extra reward multiplier for grounded nodes because they are backed by
        #   stronger evidence than ungrounded hypotheses.
        node_reward = {}
        node_risk = {}
        resolution_weight = {}
        for node_id in path_node_ids:
            node: GraphNode = hypothesis_graph.nodes[node_id]
            target_prob = node.target_prob
            node_reward[node_id] = target_prob
            node_risk[node_id] = 1.0 - node.exist_prob
            resolution_weight[node_id] = (
                self.grounded_resolution_weight
                if node.grounded
                else self.ungrounded_resolution_weight
            )

        model = Model("rolling_horizon_milp")
        model.Params.OutputFlag = 0

        # x[(i, j)] = 1 if the route travels along directed edge i -> j.
        x = {
            (source_id, target_id): model.addVar(
                vtype=GRB.BINARY, name=f"x_{source_id}_{target_id}"
            )
            for source_id, target_id in directed_edges
        }

        # y[i] = 1 if node i is included in the selected path.
        y = {
            node_id: model.addVar(vtype=GRB.BINARY, name=f"y_{node_id}")
            for node_id in path_node_ids
        }

        # u[i] is the Miller-Tucker-Zemlin ordering variable used only to eliminate
        # disconnected subtours among selected path nodes.
        u = {
            node_id: model.addVar(
                lb=1.0,
                ub=float(len(path_node_ids)),
                vtype=GRB.CONTINUOUS,
                name=f"u_{node_id}",
            )
            for node_id in path_node_ids
        }

        model.setObjective(
            quicksum(
                resolution_weight[node_id] * node_reward[node_id] * y[node_id]
                for node_id in path_node_ids
            )
            - self.alpha
            * quicksum(
                edge_distance[edge_id] * x[edge_id] for edge_id in directed_edges
            )
            - self.beta
            * quicksum(edge_risk[edge_id] * x[edge_id] for edge_id in directed_edges)
            - self.gamma
            * quicksum(node_risk[node_id] * y[node_id] for node_id in path_node_ids),
            GRB.MAXIMIZE,
        )

        # The optimizer must choose exactly one first move away from the current viewpoint.
        model.addConstr(
            quicksum(
                x[(source_id, target_id)]
                for source_id, target_id in directed_edges
                if source_id == current_vp_node_id
            )
            == 1,
            name="depart_current",
        )

        # The first node after the current viewpoint must itself be a viewpoint.
        model.addConstr(
            quicksum(
                x[(source_id, target_id)]
                for source_id, target_id in directed_edges
                if source_id == current_vp_node_id
                and hypothesis_graph.nodes[target_id].type == TYPE_VP
            )
            == 1,
            name="first_hop_is_viewpoint",
        )

        # This is an open path, not a tour, so the planned route must not return to the
        # current viewpoint inside the same solve.
        model.addConstr(
            quicksum(
                x[(source_id, target_id)]
                for source_id, target_id in directed_edges
                if target_id == current_vp_node_id
            )
            == 0,
            name="do_not_return_current",
        )

        for node_id in path_node_ids:
            # Every selected node has exactly one predecessor in the path.
            model.addConstr(
                quicksum(
                    x[(source_id, target_id)]
                    for source_id, target_id in directed_edges
                    if target_id == node_id
                )
                == y[node_id],
                name=f"flow_in_{node_id}",
            )

            # Internal path nodes have one successor, while the terminal node has none.
            model.addConstr(
                quicksum(
                    x[(source_id, target_id)]
                    for source_id, target_id in directed_edges
                    if source_id == node_id
                )
                <= y[node_id],
                name=f"flow_out_{node_id}",
            )

        # In an open path, every selected node except the terminal node contributes one
        # outgoing edge. This makes the selected edges form a single ordered path even
        # when region nodes appear as transit nodes.
        model.addConstr(
            quicksum(
                x[(source_id, target_id)]
                for source_id, target_id in directed_edges
                if source_id in path_node_ids
            )
            == quicksum(y[node_id] for node_id in path_node_ids) - 1,
            name="open_path_edge_count",
        )

        # model.addConstr(
        #     quicksum(edge_distance[edge_id] * x[edge_id] for edge_id in directed_edges)
        #     + quicksum(self.service_cost * y[node_id] for node_id in path_node_ids)
        #     <= self.budget,
        #     name="budget",
        # )

        for source_id in path_node_ids:
            for target_id in path_node_ids:
                if source_id == target_id or (source_id, target_id) not in x:
                    continue
                # MTZ constraints suppress detached cycles that do not belong to the
                # main route that starts at current_vp_node_id.
                model.addConstr(
                    u[source_id]
                    - u[target_id]
                    + len(path_node_ids) * x[(source_id, target_id)]
                    <= len(path_node_ids) - 1,
                    name=f"mtz_{source_id}_{target_id}",
                )

        model.optimize()

        selected_edges = [edge_id for edge_id, var in x.items() if var.X > 0.5]
        planned_path_node_ids, route_node_ids = self._extract_path_from_selected_edges(
            current_vp_node_id, selected_edges
        )

        return {
            # Ordered future path nodes, excluding the current start viewpoint.
            "planned_path_node_ids": planned_path_node_ids,
            # The control loop still executes only the first step of the plan, which is
            # constrained to be a viewpoint node.
            "next_vp_node_id": planned_path_node_ids[0],
            # Full ordered path chosen by the MILP, including the current viewpoint.
            "route_node_ids": route_node_ids,
            "objective_value": model.ObjVal,
            "selected_edges": selected_edges,
        }

    def _extract_path_from_selected_edges(self, current_vp_node_id, selected_edges):
        """Convert selected directed edges into the ordered mixed-node path."""
        outgoing_by_source = {
            source_id: target_id for source_id, target_id in selected_edges
        }

        planned_path_node_ids = []
        route_node_ids = [current_vp_node_id]
        next_node_id = outgoing_by_source[current_vp_node_id]

        # Follow the unique selected outgoing edge from each source until the path
        # reaches its terminal node, which has no outgoing selected edge.
        while True:
            planned_path_node_ids.append(next_node_id)
            route_node_ids.append(next_node_id)
            if next_node_id not in outgoing_by_source:
                break
            next_node_id = outgoing_by_source[next_node_id]

        return planned_path_node_ids, route_node_ids
