from __future__ import annotations

import heapq
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple

from route_plotter import (
    EnvironmentGraph,
    load_environment_graph,
    print_route_summary,
    summarize_routes,
)
from optimizer_route_logger import write_optimizer_route_log

TYPE_VP = 1


@dataclass
class OracleNode:
    node_id: int
    label: str
    type: int
    exist_prob: float
    grounded: bool
    target_probs: Dict[str, float]
    node_visit_times: int = 0
    connected_node_ids: set[int] = field(default_factory=set)


@dataclass
class OracleEdge:
    source_node_id: int
    target_node_id: int
    distance_mean: float
    distance_var: float
    cond_exist_prob: float
    exist_prob: float
    grounded: bool

    @property
    def edge_id(self) -> Tuple[int, int]:
        return tuple(sorted((self.source_node_id, self.target_node_id)))


@dataclass
class OracleGraph:
    target_records: List[Dict[str, str]]
    nodes: Dict[int, OracleNode]
    edges: Dict[Tuple[int, int], OracleEdge]
    observation_step: int = 0

    @property
    def target_ids(self) -> List[str]:
        return [target["target_id"] for target in self.target_records]

    @property
    def target_id_to_description(self) -> Dict[str, str]:
        return {
            target["target_id"]: target["description"] for target in self.target_records
        }


@dataclass
class OracleInstance:
    test_case: str
    scan_id: str
    graph: OracleGraph
    agent_current_vp_ids: Dict[str, int]
    environment_graph: EnvironmentGraph
    target_node_ids_by_target_id: Dict[str, int]
    target_candidate_node_ids_by_target_id: Dict[str, List[int]]


@dataclass
class OracleRouteChoice:
    cost: float
    covered_mask: int
    route_node_ids: List[int]


def build_oracle_instance(
    test_case: str | Dict[str, object],
    project_root: str | Path | None = None,
    connectivity_dir: str | Path | None = None,
    oracle_targets_path: str | Path | None = None,
) -> OracleInstance:
    root = Path(project_root).resolve() if project_root is not None else Path.cwd()
    if isinstance(test_case, dict):
        case_name = str(test_case["test_case"])
        scenario = test_case
    else:
        case_name, scenario_path = _resolve_oracle_case(
            case_or_config=str(test_case),
            project_root=root,
        )
        scenario = _read_json(scenario_path)

    scan_id = str(scenario["scan_id"])
    environment_graph = load_environment_graph(
        scan_id=scan_id,
        connectivity_dir=connectivity_dir,
    )

    target_records = [
        {
            "target_id": str(target["target_id"]),
            "description": str(target["description"]),
        }
        for target in scenario["targets"]
    ]
    viewpoint_index_by_id = {
        viewpoint_id: node_id
        for node_id, viewpoint_id in environment_graph.viewpoint_id_by_index.items()
    }
    target_candidate_node_ids_by_target_id = _target_candidate_node_ids_by_target_id(
        case_name=case_name,
        scenario=scenario,
        target_records=target_records,
        viewpoint_index_by_id=viewpoint_index_by_id,
        oracle_targets_path=(
            Path(oracle_targets_path)
            if oracle_targets_path is not None
            else root / "scenarios" / "oracle_targets.json"
        ),
    )
    target_node_ids_by_target_id = {
        target_id: candidate_node_ids[0]
        for target_id, candidate_node_ids in target_candidate_node_ids_by_target_id.items()
    }

    nodes = {}
    target_ids = [target["target_id"] for target in target_records]
    for node_id, viewpoint_id in environment_graph.viewpoint_id_by_index.items():
        nodes[node_id] = OracleNode(
            node_id=node_id,
            label=viewpoint_id,
            type=TYPE_VP,
            exist_prob=1.0,
            grounded=True,
            target_probs={
                target_id: (
                    1.0
                    if node_id in target_candidate_node_ids_by_target_id[target_id]
                    else 0.0
                )
                for target_id in target_ids
            },
            node_visit_times=0,
        )

    edges = {}
    for edge_id, distance in environment_graph.edge_distances.items():
        edges[edge_id] = OracleEdge(
            source_node_id=edge_id[0],
            target_node_id=edge_id[1],
            distance_mean=distance,
            distance_var=0.0,
            cond_exist_prob=1.0,
            exist_prob=1.0,
            grounded=True,
        )
        nodes[edge_id[0]].connected_node_ids.add(edge_id[1])
        nodes[edge_id[1]].connected_node_ids.add(edge_id[0])

    agent_current_vp_ids = {
        str(agent["id"]): viewpoint_index_by_id[str(agent["start_viewpoint_id"])]
        for agent in scenario["agents"]
    }

    return OracleInstance(
        test_case=case_name,
        scan_id=scan_id,
        graph=OracleGraph(
            target_records=target_records,
            nodes=nodes,
            edges=edges,
        ),
        agent_current_vp_ids=agent_current_vp_ids,
        environment_graph=environment_graph,
        target_node_ids_by_target_id=target_node_ids_by_target_id,
        target_candidate_node_ids_by_target_id=target_candidate_node_ids_by_target_id,
    )


def run_oracle(
    test_case: str | Dict[str, object],
    project_root: str | Path | None = None,
    connectivity_dir: str | Path | None = None,
    oracle_targets_path: str | Path | None = None,
    output_dir: str | Path | None = None,
    wait_for_debugger: bool = False,
    print_summary: bool = True,
    write_model_lp: bool = True,
    use_shortest_walk_solver: bool = False,
) -> Dict[str, object]:
    root = Path(project_root).resolve() if project_root is not None else Path.cwd()
    if wait_for_debugger:
        _wait_for_debugger()

    instance = build_oracle_instance(
        test_case=test_case,
        project_root=root,
        connectivity_dir=(
            Path(connectivity_dir) if connectivity_dir is not None else root / "connectivity"
        ),
        oracle_targets_path=oracle_targets_path,
    )
    if use_shortest_walk_solver:
        result = _solve_oracle_shortest_walk(instance)
    else:
        from optimization_model import RollingHorizonOptimizer

        optimizer = RollingHorizonOptimizer(
            _oracle_optimizer_config(write_model_lp=write_model_lp)
        )
        result = optimizer.solve(
            hypothesis_graph=instance.graph,
            agent_current_vp_ids=instance.agent_current_vp_ids,
            target_found_flags={
                target_id: False for target_id in instance.graph.target_ids
            },
        )

    summary = summarize_oracle_solution(instance=instance, optimization_result=result)
    output_root = (
        Path(output_dir)
        if output_dir is not None
        else root / "mllm_debug_outputs" / instance.test_case
    )
    output_root.mkdir(parents=True, exist_ok=True)
    optimizer_route_log_path = write_optimizer_route_log(
        output_dir=output_root,
        test_case=instance.test_case,
        optimization_result=result,
        agent_ids=list(instance.agent_current_vp_ids),
        step_index=None,
        filename="optimizer_routes_oracle.json",
    )
    print("Saved oracle optimizer route log to %s.\n" % str(optimizer_route_log_path))
    summary_path = output_root / ("%s_oracle_route_summary.txt" % instance.test_case)
    with open(summary_path, "w", encoding="utf-8") as summary_file_handle:
        json.dump(summary, summary_file_handle, indent=2)
    print("Saved oracle route summary to %s.\n" % str(summary_path))
    if print_summary:
        print_oracle_summary(summary)
    return summary


def run_batch_oracles(
    batch_config_path: str | Path,
    project_root: str | Path | None = None,
    wait_for_debugger: bool = False,
) -> Dict[str, object]:
    root = Path(project_root).resolve() if project_root is not None else Path.cwd()
    path = Path(batch_config_path)
    if not path.is_absolute():
        path = root / path

    batch_config = _read_json(path)
    if not _is_batch_config(batch_config):
        raise ValueError("Config %s is not a batch config." % str(path))

    batch_id = path.stem
    generated_cases_path = (
        root / "mllm_debug_outputs" / batch_id / "generated_cases.json"
    )
    generated_summary = _read_json(generated_cases_path)
    case_order = [str(case_id) for case_id in generated_summary["case_order"]]
    cases = generated_summary["cases"]
    scan_targets = _batch_scan_targets_by_id(batch_config)
    oracle_summary_path = (
        root / "mllm_debug_outputs" / batch_id / "oracle_summaries.json"
    )

    summaries = {}
    for case_index, case_id in enumerate(case_order, start=1):
        generated_case = cases[case_id]
        output_dir = root / str(generated_case["debug_output_dir"])
        if _oracle_case_outputs_exist(output_dir=output_dir, case_id=case_id):
            print(
                "Skipping completed oracle batch case %s (%s/%s)."
                % (case_id, case_index, len(case_order))
            )
            summaries[case_id] = _read_oracle_case_summary(
                output_dir=output_dir,
                case_id=case_id,
            )
            _write_batch_oracle_summaries(
                output_path=oracle_summary_path,
                batch_id=batch_id,
                case_order=case_order,
                summaries=summaries,
            )
            continue

        scenario = _scenario_from_generated_batch_case(
            generated_case=generated_case,
            scan_targets=scan_targets,
        )
        print(
            "Running oracle for batch case %s (%s/%s)."
            % (case_id, case_index, len(case_order))
        )
        summaries[case_id] = run_oracle(
            scenario,
            project_root=root,
            connectivity_dir=root / "connectivity",
            output_dir=output_dir,
            wait_for_debugger=wait_for_debugger,
            print_summary=False,
            write_model_lp=False,
            use_shortest_walk_solver=True,
        )
        _write_batch_oracle_summaries(
            output_path=oracle_summary_path,
            batch_id=batch_id,
            case_order=case_order,
            summaries=summaries,
        )

    print("Saved batch oracle summaries to %s.\n" % str(oracle_summary_path))
    return {
        "batch_id": batch_id,
        "oracle_case_count": len(summaries),
        "oracle_summaries_path": str(oracle_summary_path),
        "cases": summaries,
    }


def summarize_oracle_solution(
    instance: OracleInstance,
    optimization_result: Dict[str, object],
) -> Dict[str, object]:
    routes_by_agent = {}
    for agent_id in instance.agent_current_vp_ids:
        agent_path = optimization_result["agent_paths"][agent_id]
        routes_by_agent[agent_id] = [
            int(node_id) for node_id in agent_path["route_node_ids"]
        ]
    routes_by_agent = _pad_routes_to_equal_length(routes_by_agent)
    return summarize_routes(
        test_case=instance.test_case,
        environment_graph=instance.environment_graph,
        routes_by_agent=routes_by_agent,
        target_node_ids_by_target_id=_target_assignment_node_ids(
            instance=instance,
            optimization_result=optimization_result,
        ),
    )


def _pad_routes_to_equal_length(
    routes_by_agent: Dict[str, List[int]],
) -> Dict[str, List[int]]:
    max_route_length = max(
        len(route_node_ids) for route_node_ids in routes_by_agent.values()
    )
    return {
        agent_id: route_node_ids
        + [route_node_ids[-1]] * (max_route_length - len(route_node_ids))
        for agent_id, route_node_ids in routes_by_agent.items()
    }


def _target_assignment_node_ids(
    instance: OracleInstance,
    optimization_result: Dict[str, object],
) -> Dict[str, int]:
    target_node_ids_by_target_id = dict(instance.target_node_ids_by_target_id)
    for assignment in optimization_result["target_assignments"]:
        target_node_ids_by_target_id[str(assignment["target_id"])] = int(
            assignment["node_id"]
        )
    return target_node_ids_by_target_id


def _solve_oracle_shortest_walk(instance: OracleInstance) -> Dict[str, object]:
    target_ids = instance.graph.target_ids
    target_bit_by_id = {
        target_id: 1 << target_index for target_index, target_id in enumerate(target_ids)
    }
    full_target_mask = (1 << len(target_ids)) - 1
    node_cover_mask = {
        node_id: _target_cover_mask_for_node(
            node_id=node_id,
            target_candidate_node_ids_by_target_id=(
                instance.target_candidate_node_ids_by_target_id
            ),
            target_bit_by_id=target_bit_by_id,
        )
        for node_id in instance.environment_graph.viewpoint_id_by_index
    }
    target_candidate_node_ids = sorted(
        {
            node_id
            for node_ids in instance.target_candidate_node_ids_by_target_id.values()
            for node_id in node_ids
        }
    )
    important_node_ids = sorted(
        set(instance.agent_current_vp_ids.values()) | set(target_candidate_node_ids)
    )
    adjacency = _environment_adjacency(instance.environment_graph)
    shortest_paths = {
        source_node_id: _dijkstra_shortest_paths(
            adjacency=adjacency,
            source_node_id=source_node_id,
        )
        for source_node_id in important_node_ids
    }
    agent_choices_by_agent = {
        agent_id: _shortest_walk_choices_for_agent(
            start_node_id=start_node_id,
            target_candidate_node_ids=target_candidate_node_ids,
            node_cover_mask=node_cover_mask,
            shortest_paths=shortest_paths,
        )
        for agent_id, start_node_id in instance.agent_current_vp_ids.items()
    }
    selected_choices_by_agent = _select_multi_agent_oracle_choices(
        agent_ids=list(instance.agent_current_vp_ids),
        agent_choices_by_agent=agent_choices_by_agent,
        full_target_mask=full_target_mask,
    )
    target_assignments = _target_assignments_for_routes(
        instance=instance,
        selected_choices_by_agent=selected_choices_by_agent,
    )
    agent_paths = {}
    selected_edges = {}
    for agent_id, route_choice in selected_choices_by_agent.items():
        route_node_ids = route_choice.route_node_ids
        selected_edges[agent_id] = [
            (source_id, target_id)
            for source_id, target_id in zip(route_node_ids, route_node_ids[1:])
        ]
        agent_paths[agent_id] = {
            "planned_path_node_ids": route_node_ids[1:],
            "next_vp_node_id": (
                route_node_ids[1] if len(route_node_ids) > 1 else route_node_ids[0]
            ),
            "route_node_ids": route_node_ids,
            "objective_terms": {
                "raw": {"distance": route_choice.cost},
                "normalized_contribution": {},
                "weighted_contribution": {"distance": route_choice.cost},
            },
        }
    total_distance = sum(
        route_choice.cost for route_choice in selected_choices_by_agent.values()
    )
    return {
        "solver": {
            "name": "oracle_shortest_walk",
            "status": "OPTIMAL",
        },
        "agent_paths": agent_paths,
        "target_assignments": target_assignments,
        "objective_value": total_distance,
        "objective_terms": {"global": {"raw": {"distance": total_distance}}},
        "selected_edges": selected_edges,
    }


def _target_cover_mask_for_node(
    node_id: int,
    target_candidate_node_ids_by_target_id: Dict[str, List[int]],
    target_bit_by_id: Dict[str, int],
) -> int:
    cover_mask = 0
    for target_id, candidate_node_ids in target_candidate_node_ids_by_target_id.items():
        if node_id in candidate_node_ids:
            cover_mask |= target_bit_by_id[target_id]
    return cover_mask


def _environment_adjacency(
    environment_graph: EnvironmentGraph,
) -> Dict[int, List[Tuple[int, float]]]:
    adjacency = {
        node_id: [] for node_id in environment_graph.viewpoint_id_by_index
    }
    for edge_id, distance in environment_graph.edge_distances.items():
        source_id, target_id = edge_id
        adjacency[source_id].append((target_id, float(distance)))
        adjacency[target_id].append((source_id, float(distance)))
    return adjacency


def _dijkstra_shortest_paths(
    adjacency: Dict[int, List[Tuple[int, float]]],
    source_node_id: int,
) -> Tuple[Dict[int, float], Dict[int, int]]:
    distances = {source_node_id: 0.0}
    predecessors: Dict[int, int] = {}
    queue = [(0.0, source_node_id)]
    while queue:
        distance, node_id = heapq.heappop(queue)
        if distance != distances[node_id]:
            continue
        for neighbor_id, edge_distance in adjacency[node_id]:
            candidate_distance = distance + edge_distance
            if (
                neighbor_id not in distances
                or candidate_distance < distances[neighbor_id]
            ):
                distances[neighbor_id] = candidate_distance
                predecessors[neighbor_id] = node_id
                heapq.heappush(queue, (candidate_distance, neighbor_id))
    return distances, predecessors


def _shortest_path_between(
    source_node_id: int,
    target_node_id: int,
    predecessors: Dict[int, int],
) -> List[int]:
    if source_node_id == target_node_id:
        return [source_node_id]
    path = [target_node_id]
    while path[-1] != source_node_id:
        path.append(predecessors[path[-1]])
    path.reverse()
    return path


def _path_cover_mask(path_node_ids: List[int], node_cover_mask: Dict[int, int]) -> int:
    cover_mask = 0
    for node_id in path_node_ids:
        cover_mask |= node_cover_mask[node_id]
    return cover_mask


def _shortest_walk_choices_for_agent(
    start_node_id: int,
    target_candidate_node_ids: List[int],
    node_cover_mask: Dict[int, int],
    shortest_paths: Dict[int, Tuple[Dict[int, float], Dict[int, int]]],
) -> Dict[int, OracleRouteChoice]:
    start_mask = node_cover_mask[start_node_id]
    best_states: Dict[Tuple[int, int], OracleRouteChoice] = {
        (start_mask, start_node_id): OracleRouteChoice(
            cost=0.0,
            covered_mask=start_mask,
            route_node_ids=[start_node_id],
        )
    }
    queue = [(0.0, start_mask, start_node_id)]
    while queue:
        cost, covered_mask, node_id = heapq.heappop(queue)
        state_key = (covered_mask, node_id)
        if cost != best_states[state_key].cost:
            continue
        distances, _ = shortest_paths[node_id]
        for target_node_id in target_candidate_node_ids:
            if target_node_id == node_id or target_node_id not in distances:
                continue
            _, predecessors = shortest_paths[node_id]
            path_node_ids = _shortest_path_between(
                source_node_id=node_id,
                target_node_id=target_node_id,
                predecessors=predecessors,
            )
            next_covered_mask = covered_mask | _path_cover_mask(
                path_node_ids=path_node_ids,
                node_cover_mask=node_cover_mask,
            )
            next_cost = cost + distances[target_node_id]
            next_route_node_ids = (
                best_states[state_key].route_node_ids + path_node_ids[1:]
            )
            next_state_key = (next_covered_mask, target_node_id)
            if _is_better_route_choice(
                cost=next_cost,
                route_node_ids=next_route_node_ids,
                existing_choice=best_states.get(next_state_key),
            ):
                best_states[next_state_key] = OracleRouteChoice(
                    cost=next_cost,
                    covered_mask=next_covered_mask,
                    route_node_ids=next_route_node_ids,
                )
                heapq.heappush(queue, (next_cost, next_covered_mask, target_node_id))

    choices_by_mask: Dict[int, OracleRouteChoice] = {}
    for route_choice in best_states.values():
        if _is_better_route_choice(
            cost=route_choice.cost,
            route_node_ids=route_choice.route_node_ids,
            existing_choice=choices_by_mask.get(route_choice.covered_mask),
        ):
            choices_by_mask[route_choice.covered_mask] = route_choice
    return choices_by_mask


def _is_better_route_choice(
    cost: float,
    route_node_ids: List[int],
    existing_choice: OracleRouteChoice | None,
) -> bool:
    if existing_choice is None:
        return True
    if cost < existing_choice.cost:
        return True
    return cost == existing_choice.cost and route_node_ids < existing_choice.route_node_ids


def _select_multi_agent_oracle_choices(
    agent_ids: List[str],
    agent_choices_by_agent: Dict[str, Dict[int, OracleRouteChoice]],
    full_target_mask: int,
) -> Dict[str, OracleRouteChoice]:
    states: Dict[int, Tuple[float, Dict[str, OracleRouteChoice]]] = {0: (0.0, {})}
    for agent_id in agent_ids:
        next_states: Dict[int, Tuple[float, Dict[str, OracleRouteChoice]]] = {}
        for covered_mask, (cost, selected_choices) in states.items():
            for route_choice in agent_choices_by_agent[agent_id].values():
                next_covered_mask = covered_mask | route_choice.covered_mask
                next_cost = cost + route_choice.cost
                next_selected_choices = dict(selected_choices)
                next_selected_choices[agent_id] = route_choice
                if _is_better_multi_agent_choice(
                    cost=next_cost,
                    selected_choices=next_selected_choices,
                    existing_state=next_states.get(next_covered_mask),
                ):
                    next_states[next_covered_mask] = (
                        next_cost,
                        next_selected_choices,
                    )
        states = next_states
    if full_target_mask not in states:
        raise RuntimeError("Oracle targets are not jointly reachable by the agents.")
    return states[full_target_mask][1]


def _is_better_multi_agent_choice(
    cost: float,
    selected_choices: Dict[str, OracleRouteChoice],
    existing_state: Tuple[float, Dict[str, OracleRouteChoice]] | None,
) -> bool:
    if existing_state is None:
        return True
    existing_cost, existing_choices = existing_state
    if cost < existing_cost:
        return True
    return cost == existing_cost and _route_signature(selected_choices) < _route_signature(
        existing_choices
    )


def _route_signature(selected_choices: Dict[str, OracleRouteChoice]) -> List[List[int]]:
    return [
        selected_choices[agent_id].route_node_ids
        for agent_id in sorted(selected_choices)
    ]


def _target_assignments_for_routes(
    instance: OracleInstance,
    selected_choices_by_agent: Dict[str, OracleRouteChoice],
) -> List[Dict[str, object]]:
    target_assignments = []
    for target_id in instance.graph.target_ids:
        candidate_node_ids = set(
            instance.target_candidate_node_ids_by_target_id[target_id]
        )
        for agent_id, route_choice in selected_choices_by_agent.items():
            assigned_node_id = next(
                (
                    node_id
                    for node_id in route_choice.route_node_ids
                    if node_id in candidate_node_ids
                ),
                None,
            )
            if assigned_node_id is not None:
                target_assignments.append(
                    {
                        "target_id": target_id,
                        "node_id": int(assigned_node_id),
                        "agent_id": agent_id,
                    }
                )
                break
        else:
            raise RuntimeError("Oracle route does not cover target %s." % target_id)
    return target_assignments


def print_oracle_summary(summary: Dict[str, object]) -> None:
    print_route_summary(
        summary=summary,
        title="Oracle solution for %s" % summary["test_case"],
    )


def _resolve_oracle_case(case_or_config: str, project_root: Path) -> Tuple[str, Path]:
    path = Path(case_or_config)
    if path.exists():
        scenario_path = path.resolve()
        return scenario_path.stem, scenario_path
    if not path.is_absolute() and (project_root / path).exists():
        scenario_path = (project_root / path).resolve()
        return scenario_path.stem, scenario_path
    if path.suffix == ".json":
        scenario_path = path if path.is_absolute() else project_root / path
        return path.stem, scenario_path
    return (
        str(case_or_config),
        project_root / "scenarios" / ("%s.json" % str(case_or_config)),
    )


def _oracle_optimizer_config(write_model_lp: bool = True) -> Dict[str, float | bool]:
    # unique_target_reward: enables target assignment variables z[target, node, agent].
    # allow_inactive_agents: lets agents with no assigned target stay at their current viewpoint.
    # force_positive_target_assignment: prevents assigning a target to a zero-probability node.
    # minimize_distance_after_targets: makes the oracle minimize travel distance after target coverage constraints are enforced.
    return {
        "goal_weight": 1000.0,
        "dist_weight": 1.0,
        "arc_weight": 0.0,
        "node_weight": 0.0,
        "visit_weight": 0.0,
        "unique_target_reward": True,
        "allow_inactive_agents": True,
        "force_positive_target_assignment": True,
        "minimize_distance_after_targets": True,
        "write_model_lp": bool(write_model_lp),
    }


def _target_candidate_node_ids_by_target_id(
    case_name: str,
    scenario: Dict[str, object],
    target_records: List[Dict[str, str]],
    viewpoint_index_by_id: Dict[str, int],
    oracle_targets_path: Path,
) -> Dict[str, List[int]]:
    scenario_targets_by_id = {
        str(target["target_id"]): target for target in scenario["targets"]
    }
    if any(
        "detectable_viewpoint_ids" in scenario_targets_by_id[target["target_id"]]
        for target in target_records
    ):
        return {
            target["target_id"]: [
                viewpoint_index_by_id[str(viewpoint_id)]
                for viewpoint_id in scenario_targets_by_id[target["target_id"]][
                    "detectable_viewpoint_ids"
                ]
            ]
            for target in target_records
        }

    oracle_targets = _read_json(oracle_targets_path)
    oracle_target_mapping = oracle_targets[case_name]
    return {
        target["target_id"]: [int(oracle_target_mapping[target["target_id"]])]
        for target in target_records
    }


def _scenario_from_generated_batch_case(
    generated_case: Dict[str, object],
    scan_targets: Dict[str, Dict[str, Dict[str, object]]],
) -> Dict[str, object]:
    scan_id = str(generated_case["scan_id"])
    targets = []
    for target in generated_case["targets"]:
        target_id = str(target["target_id"])
        enriched_target = dict(target)
        enriched_target["detectable_viewpoint_ids"] = list(
            scan_targets[scan_id][target_id]["detectable_viewpoint_ids"]
        )
        targets.append(enriched_target)

    return {
        "test_case": str(generated_case["test_case"]),
        "scan_id": scan_id,
        "agents": list(generated_case["agents"]),
        "targets": targets,
    }


def _batch_scan_targets_by_id(
    batch_config: Dict[str, object],
) -> Dict[str, Dict[str, Dict[str, object]]]:
    return {
        str(scan["scan_id"]): {
            str(target["target_id"]): target for target in scan["targets"]
        }
        for scan in batch_config["scans"]
    }


def _oracle_case_output_paths(output_dir: Path, case_id: str) -> Tuple[Path, Path]:
    return (
        output_dir / ("%s_oracle_route_summary.txt" % str(case_id)),
        output_dir / "optimizer_routes_oracle.json",
    )


def _oracle_case_outputs_exist(output_dir: Path, case_id: str) -> bool:
    summary_path, route_log_path = _oracle_case_output_paths(
        output_dir=output_dir,
        case_id=case_id,
    )
    return summary_path.exists() and route_log_path.exists()


def _read_oracle_case_summary(output_dir: Path, case_id: str) -> Dict[str, object]:
    summary_path, _ = _oracle_case_output_paths(
        output_dir=output_dir,
        case_id=case_id,
    )
    return _read_json(summary_path)


def _write_batch_oracle_summaries(
    output_path: Path,
    batch_id: str,
    case_order: List[str],
    summaries: Dict[str, object],
) -> None:
    _write_json(
        output_path,
        {
            "batch_id": batch_id,
            "oracle_case_count": len(summaries),
            "case_order": case_order,
            "cases": summaries,
        },
    )


def _is_batch_config(config: Dict[str, object]) -> bool:
    return all(
        key in config
        for key in ("scans", "agent_num_selections", "target_num_selections")
    )


def _wait_for_debugger() -> None:
    import debugpy

    debugpy.listen(("0.0.0.0", 5678))
    print("debugpy listening on 5678, waiting...")
    debugpy.wait_for_client()
    print("debugger attached, continuing...")


def _read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main(argv: List[str] | None = None) -> int:
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Run perfect-knowledge oracle solutions for a scenario or batch."
    )
    parser.add_argument(
        "case_or_config",
        help="Scenario or batch config path, or a scenario name such as test1.",
    )
    parser.add_argument(
        "--wait-for-debugger",
        action="store_true",
        help="Wait for a debugpy client before running an oracle.",
    )
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    root = Path.cwd()
    _, config_path = _resolve_oracle_case(
        case_or_config=str(args.case_or_config),
        project_root=root,
    )
    raw_config = _read_json(config_path)

    if isinstance(raw_config, dict) and _is_batch_config(raw_config):
        run_batch_oracles(
            config_path,
            project_root=root,
            wait_for_debugger=args.wait_for_debugger,
        )
    else:
        run_oracle(
            config_path,
            project_root=root,
            wait_for_debugger=args.wait_for_debugger,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
