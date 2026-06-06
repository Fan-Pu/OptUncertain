from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple

import debugpy

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


def build_oracle_instance(
    test_case: str,
    project_root: str | Path | None = None,
    connectivity_dir: str | Path | None = None,
    oracle_targets_path: str | Path | None = None,
) -> OracleInstance:
    root = Path(project_root).resolve() if project_root is not None else Path.cwd()
    case_name, scenario_path = _resolve_oracle_case(
        case_or_config=str(test_case),
        project_root=root,
    )
    scenario = _read_json(scenario_path)
    oracle_targets = _read_json(
        Path(oracle_targets_path)
        if oracle_targets_path is not None
        else root / "scenarios" / "oracle_targets.json"
    )

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
    oracle_target_mapping = oracle_targets[case_name]
    target_node_ids_by_target_id = {
        target["target_id"]: int(oracle_target_mapping[target["target_id"]])
        for target in target_records
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
                    1.0 if target_node_ids_by_target_id[target_id] == node_id else 0.0
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

    viewpoint_index_by_id = {
        viewpoint_id: node_id
        for node_id, viewpoint_id in environment_graph.viewpoint_id_by_index.items()
    }
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
    )


def run_oracle(
    test_case: str,
    project_root: str | Path | None = None,
    connectivity_dir: str | Path | None = None,
    oracle_targets_path: str | Path | None = None,
    output_dir: str | Path | None = None,
) -> Dict[str, object]:
    from optimization_model import RollingHorizonOptimizer

    # -------------------- Debugger --------------------
    debugpy.listen(("0.0.0.0", 5678))
    print("debugpy listening on 5678, waiting...")
    debugpy.wait_for_client()
    print("debugger attached, continuing...")

    instance = build_oracle_instance(
        test_case=test_case,
        project_root=project_root,
        connectivity_dir=connectivity_dir,
        oracle_targets_path=oracle_targets_path,
    )
    optimizer = RollingHorizonOptimizer(_oracle_optimizer_config())
    result = optimizer.solve(
        hypothesis_graph=instance.graph,
        agent_current_vp_ids=instance.agent_current_vp_ids,
        target_found_flags={
            target_id: False for target_id in instance.graph.target_ids
        },
    )

    summary = summarize_oracle_solution(instance=instance, optimization_result=result)
    root = Path(project_root).resolve() if project_root is not None else Path.cwd()
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
    print_oracle_summary(summary)
    return summary


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
        target_node_ids_by_target_id=instance.target_node_ids_by_target_id,
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


def _oracle_optimizer_config() -> Dict[str, float]:
    return {
        "goal_weight": 1000.0,
        "dist_weight": 1.0,
        "arc_weight": 0.0,
        "node_weight": 0.0,
        "visit_weight": 0.0,
        "ungrounded_reward_weight": 1.0,
        "unique_target_reward": True,
        "allow_inactive_agents": True,
        "force_positive_target_assignment": True,
        "minimize_distance_after_targets": True,
    }


def _read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))
