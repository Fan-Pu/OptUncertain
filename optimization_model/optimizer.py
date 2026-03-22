from gurobipy import GRB, Model, quicksum


class RollingHorizonOptimizer:
    def __init__(self):
        self.alpha = 1.0  # weight for distance cost: the cost between the current viewpoint and the next viewpoint.
        self.beta = 2.0  # weight for risk cost: the cost of traversing an edge with low existence probability.
        self.gamma = 0.5  # weight for node risk cost: the cost of resolving a node with low existence probability.
        self.service_cost = 0.5
        self.budget = 20.0
        self.grounded_resolution_weight = 1.25
        self.ungrounded_resolution_weight = 1.0
        self.visibility_by_node_id = (
            {}
        )  # node_id -> visibility (0.0 to 1.0), where 1.0 means fully visible from the current viewpoint and 0.0 means not visible at all

    def solve(self, hypothesis_graph, current_vp_node_id):
        """Plan a multi-step viewpoint route and expose its first hop."""

        # The current viewpoint has already been observed completely.
        self.visibility_by_node_id[current_vp_node_id] = 1.0

        # Only viewpoints in the same connected component can appear in the route.
        component_node_ids, undirected_edges = self._get_component(
            hypothesis_graph, current_vp_node_id
        )

        # Search nodes are the candidate future viewpoints. The current viewpoint is the
        # fixed route start, so it does not get its own visit variable.
        search_node_ids = [
            node_id
            for node_id in sorted(component_node_ids)
            if node_id != current_vp_node_id
        ]

        # The graph stores undirected navigation edges, but the MILP uses directed edge
        # decisions so both travel directions are enumerated here.
        directed_edges = []
        edge_distance = {}  # (source_id, target_id) -> travel distance
        edge_risk = {}  # (source_id, target_id) -> uncertainty penalty
        for source_id, target_id, edge in undirected_edges:
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
        for node_id in search_node_ids:
            node = hypothesis_graph.nodes[node_id]
            region_id = hypothesis_graph.viewpoint_to_region.get(node_id)
            region = (
                hypothesis_graph.nodes[region_id] if region_id is not None else None
            )
            target_prob = max(
                node.target_prob,
                region.target_prob if region is not None else 0.0,
            )
            visibility = self.visibility_by_node_id.get(node_id, 0.0)
            node_reward[node_id] = target_prob * (1.0 - visibility)
            node_risk[node_id] = (
                1.0 - region.exist_prob if region is not None else 1.0 - node.exist_prob
            )
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

        # y[i] = 1 if viewpoint i is included in the selected route.
        y = {
            node_id: model.addVar(vtype=GRB.BINARY, name=f"y_{node_id}")
            for node_id in search_node_ids
        }

        # u[i] is the Miller-Tucker-Zemlin ordering variable used only to eliminate
        # disconnected subtours among visited viewpoints.
        u = {
            node_id: model.addVar(
                lb=1.0,
                ub=float(len(search_node_ids)),
                vtype=GRB.CONTINUOUS,
                name=f"u_{node_id}",
            )
            for node_id in search_node_ids
        }

        model.setObjective(
            quicksum(
                resolution_weight[node_id] * node_reward[node_id] * y[node_id]
                for node_id in search_node_ids
            )
            - self.alpha
            * quicksum(
                edge_distance[edge_id] * x[edge_id] for edge_id in directed_edges
            )
            - self.beta
            * quicksum(edge_risk[edge_id] * x[edge_id] for edge_id in directed_edges)
            - self.gamma
            * quicksum(node_risk[node_id] * y[node_id] for node_id in search_node_ids),
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

        for node_id in search_node_ids:
            # Every visited viewpoint has exactly one predecessor in the path.
            model.addConstr(
                quicksum(
                    x[(source_id, target_id)]
                    for source_id, target_id in directed_edges
                    if target_id == node_id
                )
                == y[node_id],
                name=f"flow_in_{node_id}",
            )

            # Internal path nodes have one successor, while the final node has none.
            model.addConstr(
                quicksum(
                    x[(source_id, target_id)]
                    for source_id, target_id in directed_edges
                    if source_id == node_id
                )
                <= y[node_id],
                name=f"flow_out_{node_id}",
            )

        # In an open path, every visited node except the terminal node contributes one
        # outgoing edge. This makes the selected edges form a single ordered path.
        model.addConstr(
            quicksum(
                x[(source_id, target_id)]
                for source_id, target_id in directed_edges
                if source_id in search_node_ids
            )
            == quicksum(y[node_id] for node_id in search_node_ids) - 1,
            name="open_path_edge_count",
        )

        model.addConstr(
            quicksum(edge_distance[edge_id] * x[edge_id] for edge_id in directed_edges)
            + quicksum(self.service_cost * y[node_id] for node_id in search_node_ids)
            <= self.budget,
            name="budget",
        )

        for source_id in search_node_ids:
            for target_id in search_node_ids:
                if source_id == target_id or (source_id, target_id) not in x:
                    continue
                # MTZ constraints suppress detached cycles that do not belong to the main
                # route that starts at current_vp_node_id.
                model.addConstr(
                    u[source_id]
                    - u[target_id]
                    + len(search_node_ids) * x[(source_id, target_id)]
                    <= len(search_node_ids) - 1,
                    name=f"mtz_{source_id}_{target_id}",
                )

        model.optimize()

        selected_edges = [edge_id for edge_id, var in x.items() if var.X > 0.5]
        planned_path_node_ids, route_node_ids = self._extract_path_from_selected_edges(
            current_vp_node_id, selected_edges
        )

        return {
            # Ordered future viewpoints, excluding the current start viewpoint.
            "planned_path_node_ids": planned_path_node_ids,
            # The control loop still executes only the first step of the plan.
            "next_vp_node_id": planned_path_node_ids[0],
            # Full ordered path chosen by the MILP, including the current viewpoint.
            "route_node_ids": route_node_ids,
            "objective_value": model.ObjVal,
            "selected_edges": selected_edges,
        }

    def _extract_path_from_selected_edges(self, current_vp_node_id, selected_edges):
        """Convert selected directed edges into the ordered path and future waypoints."""
        outgoing_by_source = {
            source_id: target_id for source_id, target_id in selected_edges
        }

        planned_path_node_ids = []
        route_node_ids = [current_vp_node_id]
        next_node_id = outgoing_by_source[current_vp_node_id]

        # Follow the unique selected outgoing edge from each source until the path reaches
        # its terminal viewpoint, which has no outgoing selected edge.
        while True:
            planned_path_node_ids.append(next_node_id)
            route_node_ids.append(next_node_id)
            if next_node_id not in outgoing_by_source:
                break
            next_node_id = outgoing_by_source[next_node_id]

        return planned_path_node_ids, route_node_ids

    def _get_component(self, hypothesis_graph, current_vp_node_id):
        # Region nodes are semantic annotations, not motion states. The motion planner only
        # expands the connected component over viewpoint nodes.
        adjacency = {}
        undirected_edges = []
        for edge in hypothesis_graph.edges.values():
            source_node = hypothesis_graph.nodes[edge.source_node_id]
            target_node = hypothesis_graph.nodes[edge.target_node_id]
            if source_node.type != 1 or target_node.type != 1:
                continue
            adjacency.setdefault(source_node.node_id, set()).add(target_node.node_id)
            adjacency.setdefault(target_node.node_id, set()).add(source_node.node_id)
            undirected_edges.append((source_node.node_id, target_node.node_id, edge))

        component_node_ids = set()
        frontier = [current_vp_node_id]
        while frontier:
            node_id = frontier.pop()
            if node_id in component_node_ids:
                continue
            component_node_ids.add(node_id)
            frontier.extend(sorted(adjacency.get(node_id, set()) - component_node_ids))

        component_edges = [
            (source_id, target_id, edge)
            for source_id, target_id, edge in undirected_edges
            if source_id in component_node_ids and target_id in component_node_ids
        ]
        return component_node_ids, component_edges
