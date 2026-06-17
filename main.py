import argparse
import copy
from datetime import datetime, timezone
import hashlib
import heapq
from itertools import combinations
import json
import math
from pathlib import Path
import random
import sys
import time
from typing import Dict, List, Tuple
import debugpy
from tqdm import tqdm

import Helper
from route_plotter import (
    load_environment_graph,
    print_route_summary,
    summarize_routes,
)
from optimizer_route_logger import write_optimizer_route_log

CENTRAL_CONFIG_SECTIONS = ("mllm", "bayes", "optimizer")
DEFAULT_CONFIG_PATH = Path("config") / "default_config.json"
DEBUGPY_LISTENING = False
BATCH_GENERATION_VERSION = 3


def _read_json(path: str | Path) -> object:
    with open(path, "r", encoding="utf-8") as file_handle:
        return json.load(file_handle)


def _write_json(path: str | Path, payload: object) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as file_handle:
        json.dump(payload, file_handle, indent=2)
        file_handle.write("\n")


def _read_json_if_exists(path: str | Path) -> object | None:
    json_path = Path(path)
    if not json_path.exists():
        return None
    return _read_json(json_path)


def _project_root() -> Path:
    return Path(__file__).resolve().parent


def _default_config_path(project_root: str | Path | None = None) -> Path:
    root = Path(project_root).resolve() if project_root is not None else _project_root()
    return root / DEFAULT_CONFIG_PATH


def load_default_config(project_root: str | Path | None = None) -> Dict[str, object]:
    config = _read_json(_default_config_path(project_root))
    if not isinstance(config, dict):
        raise TypeError("Central config must be a JSON object.")
    for section in CENTRAL_CONFIG_SECTIONS:
        if section not in config:
            raise KeyError("Central config is missing section %s." % section)
        if not isinstance(config[section], dict):
            raise TypeError("Central config section %s must be an object." % section)
    return copy.deepcopy(config)


def is_batch_config(config: Dict[str, object]) -> bool:
    return all(
        key in config
        for key in ("scans", "agent_num_selections", "target_num_selections")
    )


def _merge_single_scenario_config(
    scenario_config: Dict[str, object],
    case_id: str,
    default_config: Dict[str, object],
) -> Dict[str, object]:
    scenario = copy.deepcopy(scenario_config)
    for key in ("scan_id", "agents", "targets"):
        if key not in scenario:
            raise KeyError("Scenario %s is missing %s." % (case_id, key))

    for section in CENTRAL_CONFIG_SECTIONS:
        scenario.pop(section, None)

    scenario["test_case"] = str(case_id)
    for section in CENTRAL_CONFIG_SECTIONS:
        scenario[section] = copy.deepcopy(default_config[section])

    scenario["mllm"]["raw_output_dir"] = (
        Path("mllm_raw_outputs") / str(case_id)
    ).as_posix()
    scenario["mllm"]["debug_output_dir"] = (
        Path("mllm_debug_outputs") / str(case_id)
    ).as_posix()
    return scenario


def load_scenario_config(
    config_path: str | Path,
    default_config: Dict[str, object] | None = None,
) -> Dict[str, object]:
    path = Path(config_path)
    scenario = _read_json(path)
    if not isinstance(scenario, dict):
        raise TypeError("Scenario config must be a JSON object.")
    if is_batch_config(scenario):
        raise ValueError("Batch config cannot be loaded as a single scenario.")
    return _merge_single_scenario_config(
        scenario_config=scenario,
        case_id=path.stem,
        default_config=default_config or load_default_config(),
    )


def _normalize_scenario_record(
    scenario: Dict[str, object],
    case_id: str,
    default_config: Dict[str, object],
) -> Dict[str, object]:
    if is_batch_config(scenario):
        raise ValueError("Batch config cannot be normalized as a single scenario.")
    return _merge_single_scenario_config(
        scenario_config=scenario,
        case_id=case_id,
        default_config=default_config,
    )


def _normalize_targets(targets: List[Dict[str, object]]) -> List[Dict[str, object]]:
    """Return target records in the format used by HypothesisGraph and MLLMClient.

    Required fields:
    - target_id
    - description

    Optional field:
    - distance_threshold_m

    If distance_threshold_m is absent, a direct MLLM detection is treated as
    sufficient to mark the target as completed.
    """
    normalized_targets = []

    for target in targets:
        if "target_id" not in target:
            raise KeyError("Each target must contain target_id.")
        if "description" not in target:
            raise KeyError("Each target must contain description.")

        normalized_target = {
            "target_id": str(target["target_id"]),
            "description": str(target["description"]),
        }

        if "distance_threshold_m" in target:
            normalized_target["distance_threshold_m"] = float(
                target["distance_threshold_m"]
            )

        normalized_targets.append(normalized_target)

    target_ids = [target["target_id"] for target in normalized_targets]
    if len(target_ids) != len(set(target_ids)):
        raise ValueError("Target ids must be unique.")

    return normalized_targets


def _target_records_for_graph(
    targets: List[Dict[str, object]],
) -> List[Dict[str, object]]:
    """Return only the fields used by HypothesisGraph and the MLLM prompt."""
    return [
        {
            "target_id": str(target["target_id"]),
            "description": str(target["description"]),
        }
        for target in targets
    ]


def _id_sort_key(identifier: object):
    text = str(identifier)
    if text.startswith("agent") and text[len("agent") :].isdigit():
        return (0, int(text[len("agent") :]), text)
    if text.isdigit():
        return (0, int(text), text)
    return (1, text)


def _selection_requests(
    selections: List[Dict[str, object]],
    number_key: str,
) -> List[Tuple[int, int]]:
    requests = []
    for selection in selections:
        number = int(selection[number_key])
        case_number = int(selection["case_number"])
        for case_index in range(case_number):
            requests.append((number, case_index))
    return requests


def _available_viewpoint_ids(scan_id: str, project_root: Path) -> List[str]:
    environment_graph = load_environment_graph(
        scan_id=scan_id,
        connectivity_dir=project_root / "connectivity",
    )
    return [
        environment_graph.viewpoint_id_by_index[node_id]
        for node_id in sorted(environment_graph.viewpoint_id_by_index)
    ]


def _shortest_path_distances_by_node(environment_graph) -> Dict[int, Dict[int, float]]:
    adjacency = {node_id: [] for node_id in environment_graph.viewpoint_id_by_index}
    for edge_id, distance in environment_graph.edge_distances.items():
        source_id, target_id = edge_id
        adjacency[source_id].append((target_id, float(distance)))
        adjacency[target_id].append((source_id, float(distance)))

    distances_by_source = {}
    for source_id in sorted(adjacency):
        distances = {source_id: 0.0}
        queue = [(0.0, source_id)]
        while queue:
            distance, node_id = heapq.heappop(queue)
            if distance != distances[node_id]:
                continue
            for neighbor_id, edge_distance in adjacency[node_id]:
                next_distance = distance + edge_distance
                if (
                    neighbor_id not in distances
                    or next_distance < distances[neighbor_id]
                ):
                    distances[neighbor_id] = next_distance
                    heapq.heappush(queue, (next_distance, neighbor_id))
        distances_by_source[source_id] = distances

    return distances_by_source


def _select_spread_viewpoint_ids(
    environment_graph,
    agent_number: int,
    random_source: random.Random,
) -> List[str]:
    node_ids = sorted(environment_graph.viewpoint_id_by_index)
    if int(agent_number) > len(node_ids):
        raise ValueError(
            "Requested %s agents but only %s viewpoints exist."
            % (int(agent_number), len(node_ids))
        )

    distances_by_node = _shortest_path_distances_by_node(environment_graph)
    selected_node_ids = [random_source.choice(node_ids)]
    remaining_node_ids = set(node_ids) - set(selected_node_ids)

    while len(selected_node_ids) < int(agent_number):
        scored_candidates = []
        for node_id in remaining_node_ids:
            min_distance = min(
                distances_by_node[selected_id].get(node_id, math.inf)
                for selected_id in selected_node_ids
            )
            scored_candidates.append((min_distance, node_id))

        best_min_distance = max(score for score, _ in scored_candidates)
        tied_node_ids = sorted(
            node_id
            for score, node_id in scored_candidates
            if score == best_min_distance
        )
        next_node_id = random_source.choice(tied_node_ids)
        selected_node_ids.append(next_node_id)
        remaining_node_ids.remove(next_node_id)

    return [
        environment_graph.viewpoint_id_by_index[node_id]
        for node_id in selected_node_ids
    ]


def _build_diverse_target_selections(
    targets: List[Dict[str, object]],
    target_number: int,
    selection_count: int,
    random_source: random.Random,
) -> List[List[Dict[str, object]]]:
    all_combinations = list(combinations(targets, int(target_number)))
    selections = []

    while len(selections) < int(selection_count):
        deck = list(all_combinations)
        random_source.shuffle(deck)
        for target_combination in deck:
            selections.append([copy.deepcopy(target) for target in target_combination])
            if len(selections) >= int(selection_count):
                break

    return selections


def _batch_config_hash(batch_config: Dict[str, object]) -> str:
    encoded = json.dumps(
        {
            "batch_generation_version": BATCH_GENERATION_VERSION,
            "batch_config": batch_config,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def generate_batch_scenarios(
    batch_config: Dict[str, object],
    batch_id: str,
    project_root: str | Path | None = None,
    default_config: Dict[str, object] | None = None,
    rng: random.Random | None = None,
) -> Tuple[List[Dict[str, object]], Dict[str, object]]:
    if not is_batch_config(batch_config):
        raise ValueError("Batch config must contain scans and selection blocks.")

    root = Path(project_root).resolve() if project_root is not None else _project_root()
    central_config = default_config or load_default_config(root)
    random_source = rng or random.Random()
    max_steps = int(batch_config["max_steps"]) if "max_steps" in batch_config else None

    agent_requests = _selection_requests(
        list(batch_config["agent_num_selections"]),
        "agent_number",
    )
    target_requests = _selection_requests(
        list(batch_config["target_num_selections"]),
        "target_number",
    )

    scenarios = []
    generated_cases: Dict[str, object] = {}
    for scan in batch_config["scans"]:
        scan_id = str(scan["scan_id"])
        scan_targets = _normalize_targets(list(scan["targets"]))
        environment_graph = load_environment_graph(
            scan_id=scan_id,
            connectivity_dir=root / "connectivity",
        )
        viewpoint_ids = [
            environment_graph.viewpoint_id_by_index[node_id]
            for node_id in sorted(environment_graph.viewpoint_id_by_index)
        ]
        target_selection_counts: Dict[int, int] = {}
        for target_number, _ in target_requests:
            if target_number > len(scan_targets):
                raise ValueError(
                    "Batch scan %s requested %s targets but only %s targets are "
                    "defined." % (scan_id, target_number, len(scan_targets))
                )
            target_selection_counts[target_number] = target_selection_counts.get(
                target_number, 0
            ) + len(agent_requests)
        target_selections_by_number = {
            target_number: _build_diverse_target_selections(
                targets=scan_targets,
                target_number=target_number,
                selection_count=selection_count,
                random_source=random_source,
            )
            for target_number, selection_count in target_selection_counts.items()
        }
        target_selection_offsets = {
            target_number: 0 for target_number in target_selection_counts
        }
        case_index_for_scan = 1

        for agent_number, agent_selection_index in agent_requests:
            if agent_number > len(viewpoint_ids):
                raise ValueError(
                    "Batch scan %s requested %s agents but only %s viewpoints exist."
                    % (scan_id, agent_number, len(viewpoint_ids))
                )

            for target_number, target_selection_index in target_requests:
                case_id = "%s_case_%04d" % (scan_id, case_index_for_scan)
                case_index_for_scan += 1

                selected_viewpoint_ids = _select_spread_viewpoint_ids(
                    environment_graph=environment_graph,
                    agent_number=agent_number,
                    random_source=random_source,
                )
                target_selection_offset = target_selection_offsets[target_number]
                selected_targets = target_selections_by_number[target_number][
                    target_selection_offset
                ]
                target_selection_offsets[target_number] = target_selection_offset + 1
                agents = [
                    {
                        "id": "agent%s" % agent_index,
                        "start_viewpoint_id": viewpoint_id,
                        "heading": 0.0,
                        "elevation": 0.0,
                    }
                    for agent_index, viewpoint_id in enumerate(selected_viewpoint_ids)
                ]
                base_scenario = {
                    "scan_id": scan_id,
                    "agents": agents,
                    "targets": selected_targets,
                }
                scenario = _normalize_scenario_record(
                    scenario=base_scenario,
                    case_id=case_id,
                    default_config=central_config,
                )
                if max_steps is not None:
                    scenario["max_steps"] = max_steps
                scenarios.append(scenario)
                generated_case = {
                    "test_case": case_id,
                    "scan_id": scan_id,
                    "agent_number": agent_number,
                    "agent_selection_index": agent_selection_index,
                    "target_number": target_number,
                    "target_selection_index": target_selection_index,
                    "agents": agents,
                    "targets": selected_targets,
                    "raw_output_dir": scenario["mllm"]["raw_output_dir"],
                    "debug_output_dir": scenario["mllm"]["debug_output_dir"],
                }
                if max_steps is not None:
                    generated_case["max_steps"] = max_steps
                generated_cases[case_id] = generated_case

    summary = {
        "batch_id": str(batch_id),
        "batch_config_hash": _batch_config_hash(batch_config),
        "generated_case_count": len(generated_cases),
        "case_order": list(generated_cases),
        "cases": generated_cases,
    }
    return scenarios, summary


def write_batch_case_summary(
    batch_id: str,
    summary: Dict[str, object],
    project_root: str | Path | None = None,
) -> Path:
    root = Path(project_root).resolve() if project_root is not None else _project_root()
    output_path = root / "mllm_debug_outputs" / str(batch_id) / "generated_cases.json"
    _write_json(output_path, summary)
    return output_path


def _batch_case_summary_path(
    batch_id: str,
    project_root: str | Path | None = None,
) -> Path:
    root = Path(project_root).resolve() if project_root is not None else _project_root()
    return root / "mllm_debug_outputs" / str(batch_id) / "generated_cases.json"


def _case_order_from_batch_summary(summary: Dict[str, object]) -> List[str]:
    if "case_order" in summary:
        return [str(case_id) for case_id in summary["case_order"]]
    return [str(case_id) for case_id in summary["cases"]]


def _scenario_from_generated_case(
    generated_case: Dict[str, object],
    default_config: Dict[str, object],
) -> Dict[str, object]:
    case_id = str(generated_case["test_case"])
    base_scenario = {
        "scan_id": str(generated_case["scan_id"]),
        "agents": copy.deepcopy(generated_case["agents"]),
        "targets": copy.deepcopy(generated_case["targets"]),
    }
    scenario = _normalize_scenario_record(
        scenario=base_scenario,
        case_id=case_id,
        default_config=default_config,
    )
    if "max_steps" in generated_case:
        scenario["max_steps"] = int(generated_case["max_steps"])
    return scenario


def _scenarios_from_batch_summary(
    summary: Dict[str, object],
    default_config: Dict[str, object],
) -> List[Dict[str, object]]:
    cases = summary["cases"]
    return [
        _scenario_from_generated_case(
            generated_case=cases[case_id],
            default_config=default_config,
        )
        for case_id in _case_order_from_batch_summary(summary)
    ]


def load_or_generate_batch_scenarios(
    batch_config: Dict[str, object],
    batch_id: str,
    default_config: Dict[str, object],
    project_root: str | Path | None = None,
) -> Tuple[List[Dict[str, object]], Dict[str, object], Path]:
    summary_path = _batch_case_summary_path(
        batch_id,
        project_root=project_root,
    )
    existing_summary = _read_json_if_exists(summary_path)
    expected_hash = _batch_config_hash(batch_config)
    if existing_summary is not None:
        if not isinstance(existing_summary, dict):
            raise TypeError("Generated batch case summary must be a JSON object.")
        saved_hash = existing_summary.get("batch_config_hash")
        if saved_hash != expected_hash:
            raise ValueError(
                "Existing generated batch cases for %s were produced from a "
                "different batch config. Delete %s to start a new random batch."
                % (str(batch_id), str(summary_path))
            )
        return (
            _scenarios_from_batch_summary(existing_summary, default_config),
            existing_summary,
            summary_path,
        )

    scenarios, summary = generate_batch_scenarios(
        batch_config=batch_config,
        batch_id=batch_id,
        project_root=project_root,
        default_config=default_config,
    )
    write_batch_case_summary(
        batch_id=batch_id,
        summary=summary,
        project_root=project_root,
    )
    return scenarios, summary, summary_path


def _collect_completed_targets(
    mllm_output: Dict[str, object],
    agent_observations: List[Dict[str, object]],
    targets: List[Dict[str, object]],
    hypothesis_graph,
) -> List[Dict[str, object]]:
    """Collect completed targets based on current direct detections.

    The graph is keyed by target_id. This function checks current direct
    detections and returns detected targets that are completed according to
    hypothesis_graph.target_found or can be marked completed now.

    If a target is already marked found in hypothesis_graph.target_found, it can
    still be returned when it is detected in the current MLLM output. This avoids
    losing the agent_id and target localization after the graph state has already
    been updated.
    """

    target_records = _normalize_targets(targets)
    valid_target_ids = {str(target["target_id"]) for target in target_records}

    agent_observation_by_id = {
        str(observation["agent_id"]): observation for observation in agent_observations
    }

    found_detections_by_target: Dict[str, List[Dict[str, object]]] = {
        target_id: [] for target_id in valid_target_ids
    }

    for detection in mllm_output.get("detections", []):
        agent_id = str(detection["agent_id"])

        if agent_id not in agent_observation_by_id:
            raise ValueError("Detection uses unknown agent_id %s." % agent_id)

        found_target_indices = detection["found_target_indices"]
        target_center_xs = detection["target_center_xs"]

        if len(found_target_indices) != len(target_center_xs):
            raise ValueError(
                "found_target_indices and target_center_xs must have the same "
                "length for agent %s." % agent_id
            )

        for item_index, target_id_raw in enumerate(found_target_indices):
            target_id = str(target_id_raw)

            if target_id not in valid_target_ids:
                raise ValueError(
                    "Detection uses unknown target_id %s for agent %s."
                    % (target_id, agent_id)
                )

            target_center_x = target_center_xs[item_index]

            if target_center_x is None:
                raise ValueError(
                    "Found detection for agent %s target %s has null target_center_x."
                    % (agent_id, target_id)
                )

            target_center_x = float(target_center_x)

            if not (0.0 <= target_center_x <= 1.0):
                raise ValueError(
                    "target_center_x must be in [0, 1], got %s." % target_center_x
                )

            target_heading = Helper.panorama_center_x_to_heading(
                target_center_x,
                agent_observation_by_id[agent_id]["horizon_headings"],
            )

            found_detections_by_target[target_id].append(
                {
                    "agent_id": agent_id,
                    "target_center_x": target_center_x,
                    "target_heading": target_heading,
                }
            )

    completed_targets = []

    for target in target_records:
        target_id = str(target["target_id"])

        if not found_detections_by_target[target_id]:
            continue

        if not hypothesis_graph.target_found.get(target_id, False):
            hypothesis_graph.mark_target_found(target_id)

        detection = sorted(
            found_detections_by_target[target_id],
            key=lambda item: _id_sort_key(item["agent_id"]),
        )[0]

        completed_targets.append(
            {
                "target_id": target_id,
                "description": str(target["description"]),
                "agent_id": detection["agent_id"],
                "target_center_x": detection["target_center_x"],
                "target_heading": detection["target_heading"],
            }
        )

    return completed_targets


def _center_completed_targets(
    agent_sims,
    agent_ids,
    completed_targets,
    show_agent_views: bool = True,
) -> None:
    """Rotate agents in-place to center the found targets in their view."""

    completed_targets_by_agent = {}
    for completed_target in completed_targets:
        agent_id = str(completed_target["agent_id"])
        completed_targets_by_agent.setdefault(agent_id, []).append(completed_target)

    for agent_targets in completed_targets_by_agent.values():
        agent_targets.sort(key=lambda item: _id_sort_key(item["target_id"]))

    max_target_count = max(
        (len(agent_targets) for agent_targets in completed_targets_by_agent.values()),
        default=0,
    )

    for target_index in range(max_target_count):
        sims_to_rotate = []
        target_headings = []
        window_names = []
        notifications = []

        for agent_index, (agent_id, sim) in enumerate(zip(agent_ids, agent_sims)):
            agent_targets = completed_targets_by_agent.get(str(agent_id), [])
            if target_index >= len(agent_targets):
                continue

            completed_target = agent_targets[target_index]
            sims_to_rotate.append(sim)
            target_headings.append(float(completed_target["target_heading"]))
            window_names.append("Agent %s" % agent_index)
            notifications.append(
                "Target %s is found." % (completed_target["target_id"])
            )

        if not sims_to_rotate:
            continue

        Helper.execute_individual_rotations(
            sims=sims_to_rotate,
            target_headings=target_headings,
            window_names=window_names,
            notifications=notifications,
            render=show_agent_views,
        )


def _init_agent_sims(scenario: Dict[str, object], scan_id: str):
    sims = []
    for agent in scenario["agents"]:
        sim = Helper.init_render(batch_size=1, enable_render=False)
        sim.initialize()
        sim.newEpisode(
            [scan_id],
            [str(agent["start_viewpoint_id"])],
            [float(agent.get("heading", 0.0))],
            [float(agent.get("elevation", 0.0))],
        )
        sims.append(sim)
    return sims


def _current_agent_states(agent_sims):
    return [sim.getState()[0] for sim in agent_sims]


def _initialize_executed_routes(scenario: Dict[str, object]) -> Dict[str, List[int]]:
    return {
        str(agent["id"]): [
            int(Helper.viewpoint_index_by_vp_label[str(agent["start_viewpoint_id"])])
        ]
        for agent in scenario["agents"]
    }


def _append_executed_route_nodes(
    executed_routes_by_agent: Dict[str, List[int]],
    next_route_node_ids_by_agent: Dict[str, int],
    agent_ids: List[str],
) -> None:
    for agent_id in agent_ids:
        executed_routes_by_agent[agent_id].append(
            int(next_route_node_ids_by_agent[agent_id])
        )


def _record_completed_target_nodes(
    completed_targets: List[Dict[str, object]],
    agent_observations: List[Dict[str, object]],
    completed_target_node_ids: Dict[str, int],
) -> None:
    observation_by_agent_id = {
        str(observation["agent_id"]): observation for observation in agent_observations
    }
    for completed_target in completed_targets:
        target_id = str(completed_target["target_id"])
        if target_id not in completed_target_node_ids:
            agent_id = str(completed_target["agent_id"])
            completed_target_node_ids[target_id] = int(
                observation_by_agent_id[agent_id]["current_viewpoint_index"]
            )


def _write_mllm_route_summary(
    test_case: str,
    scan_id: str,
    debug_output_dir: str,
    executed_routes_by_agent: Dict[str, List[int]],
    completed_target_node_ids: Dict[str, int],
    target_found: Dict[str, bool],
    status: str,
    stop_reason: str,
    steps_completed: int,
    max_steps: int | None = None,
    extra_metadata: Dict[str, object] | None = None,
) -> Dict[str, object]:
    environment_graph = load_environment_graph(scan_id=scan_id)
    summary = summarize_routes(
        test_case=test_case,
        environment_graph=environment_graph,
        routes_by_agent=executed_routes_by_agent,
        target_node_ids_by_target_id=completed_target_node_ids,
    )
    summary["status"] = str(status)
    summary["stop_reason"] = str(stop_reason)
    summary["target_found"] = {
        str(target_id): bool(found) for target_id, found in target_found.items()
    }
    summary["steps_completed"] = int(steps_completed)
    if max_steps is not None:
        summary["max_steps"] = int(max_steps)
    if extra_metadata is not None:
        summary.update(copy.deepcopy(extra_metadata))
    output_dir = Path(debug_output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / ("%s_mllm_route_summary.txt" % str(test_case))
    with open(summary_path, "w", encoding="utf-8") as summary_file_handle:
        json.dump(summary, summary_file_handle, indent=2)
    print("Saved MLLM route summary to %s.\n" % str(summary_path))
    print_route_summary(
        summary=summary,
        title="MLLM executed route solution for %s" % str(test_case),
    )
    return summary


def _max_steps_reached(step_index: int, max_steps: int | None) -> bool:
    if max_steps is None:
        return False
    return int(step_index) + 1 >= int(max_steps)


def _target_directed_eligible_endpoint_ids(hypothesis_graph) -> List[int]:
    current_viewpoint_ids = {
        int(node_id) for node_id in hypothesis_graph.agent_current_vp_ids.values()
    }
    return [
        int(node_id)
        for node_id in sorted(hypothesis_graph.nodes)
        if hypothesis_graph.nodes[node_id].type == Helper.TYPE_VP
        and int(node_id) not in current_viewpoint_ids
        and not bool(hypothesis_graph.nodes[node_id].grounded)
        and int(hypothesis_graph.nodes[node_id].node_visit_times) == 0
    ]


def _target_directed_search_exhaustion_info(
    hypothesis_graph,
    target_found_flags: Dict[str, bool],
) -> Dict[str, object] | None:
    active_target_ids = [
        str(target_id)
        for target_id in hypothesis_graph.target_ids
        if not bool(target_found_flags[str(target_id)])
    ]
    if not active_target_ids:
        return None

    eligible_endpoint_ids = _target_directed_eligible_endpoint_ids(hypothesis_graph)
    if eligible_endpoint_ids:
        return None

    return {
        "target_directed_search_exhausted_target_ids": active_target_ids,
        "target_directed_eligible_endpoint_ids": eligible_endpoint_ids,
    }


def _target_directed_no_positive_reward_info(
    hypothesis_graph,
    target_found_flags: Dict[str, bool],
    use_raw_target_probs: bool,
) -> Dict[str, object] | None:
    active_target_ids = [
        str(target_id)
        for target_id in hypothesis_graph.target_ids
        if not bool(target_found_flags[str(target_id)])
    ]
    if not active_target_ids:
        return None

    eligible_endpoint_ids = _target_directed_eligible_endpoint_ids(hypothesis_graph)
    if not eligible_endpoint_ids:
        return None

    reward_source_name = "raw_target_probs" if use_raw_target_probs else "target_probs"
    no_positive_reward_target_ids = []
    for target_id in active_target_ids:
        has_positive_reward = any(
            float(
                getattr(hypothesis_graph.nodes[node_id], reward_source_name).get(
                    target_id, 0.0
                )
            )
            > 0.0
            for node_id in eligible_endpoint_ids
        )
        if not has_positive_reward:
            no_positive_reward_target_ids.append(target_id)

    if not no_positive_reward_target_ids:
        return None

    return {
        "target_directed_no_positive_reward_target_ids": (
            no_positive_reward_target_ids
        ),
        "target_directed_eligible_endpoint_ids": eligible_endpoint_ids,
        "target_directed_reward_source": reward_source_name,
    }


def _wait_for_debugger() -> None:
    global DEBUGPY_LISTENING

    if not DEBUGPY_LISTENING:
        debugpy.listen(("0.0.0.0", 5678))
        DEBUGPY_LISTENING = True
        print("debugpy listening on 5678, waiting...")

    if not debugpy.is_client_connected():
        debugpy.wait_for_client()
    print("debugger attached, continuing...")


def run_scenario(
    config_or_scenario: str | Path | Dict[str, object],
    show_agent_views: bool = True,
    default_config: Dict[str, object] | None = None,
) -> Dict[str, object]:
    from optimization_model import RollingHorizonOptimizer
    from semantic_persistence import (
        HypothesisGraph,
        MLLMClient,
        MLLMProviderCreditError,
        MLLMRetryExhaustedError,
        SigLIPScorer,
    )

    # -------------------- Debugger --------------------
    _wait_for_debugger()

    if isinstance(config_or_scenario, dict):
        if "mllm" in config_or_scenario:
            scenario = copy.deepcopy(config_or_scenario)
        else:
            scenario = _normalize_scenario_record(
                scenario=config_or_scenario,
                case_id=str(config_or_scenario.get("test_case", "default")),
                default_config=default_config or load_default_config(),
            )
    else:
        scenario = load_scenario_config(
            config_or_scenario,
            default_config=default_config,
        )
    run_output_dir = scenario["mllm"].get("raw_output_dir", "mllm_raw_outputs/default")
    debug_output_dir = scenario["mllm"].get(
        "debug_output_dir", "mllm_debug_outputs/default"
    )
    agent_ids = [str(agent["id"]) for agent in scenario["agents"]]
    scan_id = str(scenario["scan_id"])
    test_case = str(scenario["test_case"])
    max_steps = int(scenario["max_steps"]) if "max_steps" in scenario else None

    Helper.build_viewpoint_index(scan_id)
    executed_routes_by_agent = _initialize_executed_routes(scenario)
    completed_target_node_ids: Dict[str, int] = {}
    agent_sims = _init_agent_sims(scenario=scenario, scan_id=scan_id)

    targets = _normalize_targets(scenario["targets"])
    graph_targets = _target_records_for_graph(targets)

    hypothesis_graph = HypothesisGraph(
        targets=graph_targets,
        bayes_config=scenario["bayes"],
    )

    optimizer = RollingHorizonOptimizer(scenario["optimizer"])

    # for huggingface, use base_url="https://router.huggingface.co/v1" and api_key_env="HF_TOKEN"
    # for DeepInfra, use base_url="https://api.deepinfra.com/v1/openai" and api_key_env="DEEPINFRA_TOKEN"
    # for DASHSCOPE, use base_url="https://dashscope-us.aliyuncs.com/compatible-mode/v1" and api_key_env="DASHSCOPE_API_KEY"
    mllm_client = MLLMClient(
        graph_model_name=str(scenario["mllm"]["graph_model_name"]),
        # detection
        detection_model_name=str(scenario["mllm"]["detection_model_name"]),
        detection_base_url="https://router.huggingface.co/v1",
        detection_api_key_env="HF_TOKEN",
        # graph generation
        graph_base_url="https://dashscope-us.aliyuncs.com/compatible-mode/v1",
        graph_api_key_env="DASHSCOPE_API_KEY",
        read_saved_raw_outputs=bool(
            scenario["mllm"].get("read_saved_raw_outputs", False)
        ),
        raw_output_dir=run_output_dir,
        raw_debug_dir=debug_output_dir,
        max_validation_retries=int(scenario["mllm"].get("max_validation_retries", 2)),
        max_request_timeout_retries=int(
            scenario["mllm"].get("max_request_timeout_retries", 1)
        ),
    )

    scorer = SigLIPScorer()

    all_targets_found = False

    while not all_targets_found:
        if all(hypothesis_graph.target_found.values()):
            return {"target_found": dict(hypothesis_graph.target_found)}

        agent_observations = Helper.horizon_scan_individual_sims_return(
            sims=agent_sims,
            agent_ids=agent_ids,
            viewpoint_index_by_vp=Helper.viewpoint_index_by_vp_label,
        )

        if show_agent_views:
            Helper.render_sim_state(
                _current_agent_states(agent_sims),
                viewpoint_index_by_vp=Helper.viewpoint_index_by_vp_label,
            )

        # The graph summary is sent to the MLLM before update_from_mllm().
        # Therefore, sync the current agent viewpoint ids from observations first.
        # This does not create semantic regions or viewpoint assignments.
        hypothesis_graph.sync_agent_current_viewpoints(agent_observations)

        try:
            mllm_output = mllm_client.propose_semantic_nodes(
                agent_observations=agent_observations,
                targets=graph_targets,
                graph=hypothesis_graph,
                scorer=scorer,
            )
        except MLLMRetryExhaustedError as exc:
            failed_step_index = int(exc.step_index)
            steps_completed = max(0, failed_step_index - 1)
            hypothesis_graph.export_debug_snapshot(
                output_dir=debug_output_dir,
                step_index=failed_step_index,
            )
            route_summary = _write_mllm_route_summary(
                test_case=test_case,
                scan_id=scan_id,
                debug_output_dir=debug_output_dir,
                executed_routes_by_agent=executed_routes_by_agent,
                completed_target_node_ids=completed_target_node_ids,
                target_found=hypothesis_graph.target_found,
                status="incomplete",
                stop_reason="mllm_retry_exhausted",
                steps_completed=steps_completed,
                max_steps=max_steps,
                extra_metadata={
                    "failed_step_index": failed_step_index,
                    "mllm_stage": exc.stage,
                    "mllm_attempts": exc.attempts,
                    "error": exc.last_error,
                },
            )
            return {
                "target_found": dict(hypothesis_graph.target_found),
                "status": "incomplete",
                "stop_reason": "mllm_retry_exhausted",
                "steps_completed": steps_completed,
                "max_steps": max_steps,
                "failed_step_index": failed_step_index,
                "mllm_stage": exc.stage,
                "mllm_attempts": exc.attempts,
                "error": exc.last_error,
                "route_summary": route_summary,
            }
        except MLLMProviderCreditError as exc:
            failed_step_index = int(exc.step_index or 0)
            steps_completed = max(0, failed_step_index - 1)
            hypothesis_graph.export_debug_snapshot(
                output_dir=debug_output_dir,
                step_index=failed_step_index,
            )
            route_summary = _write_mllm_route_summary(
                test_case=test_case,
                scan_id=scan_id,
                debug_output_dir=debug_output_dir,
                executed_routes_by_agent=executed_routes_by_agent,
                completed_target_node_ids=completed_target_node_ids,
                target_found=hypothesis_graph.target_found,
                status="terminated",
                stop_reason="provider_credit_exhausted",
                steps_completed=steps_completed,
                max_steps=max_steps,
                extra_metadata={
                    "failed_step_index": failed_step_index,
                    "mllm_stage": exc.stage,
                    "mllm_router": exc.router,
                    "mllm_model": exc.model,
                    "provider_status_code": exc.status_code,
                    "provider_code": exc.provider_code,
                    "provider_type": exc.provider_type,
                    "error": exc.message,
                },
            )
            return {
                "target_found": dict(hypothesis_graph.target_found),
                "status": "terminated",
                "stop_reason": "provider_credit_exhausted",
                "steps_completed": steps_completed,
                "max_steps": max_steps,
                "failed_step_index": failed_step_index,
                "mllm_stage": exc.stage,
                "mllm_router": exc.router,
                "mllm_model": exc.model,
                "provider_status_code": exc.status_code,
                "provider_code": exc.provider_code,
                "provider_type": exc.provider_type,
                "error": exc.message,
                "route_summary": route_summary,
            }

        debug_step_index = int(mllm_client.semantic_raw_output_index) - 1

        completed_targets = _collect_completed_targets(
            mllm_output={"detections": mllm_client.last_direct_detections},
            agent_observations=agent_observations,
            targets=targets,
            hypothesis_graph=hypothesis_graph,
        )
        _record_completed_target_nodes(
            completed_targets=completed_targets,
            agent_observations=agent_observations,
            completed_target_node_ids=completed_target_node_ids,
        )

        _center_completed_targets(
            agent_sims=agent_sims,
            agent_ids=agent_ids,
            completed_targets=completed_targets,
            show_agent_views=show_agent_views,
        )

        # Check if all targets are found after processing direct detections, before updating the graph with MLLM output.
        if all(hypothesis_graph.target_found.values()):
            all_targets_found = True

        if mllm_output is not None:
            hypothesis_graph.update_from_mllm(
                mllm_output=mllm_output,
                agent_observations=agent_observations,
                scorer=scorer,
            )
        else:
            hypothesis_graph.update_without_mllm(agent_observations=agent_observations)

        hypothesis_graph.export_debug_snapshot(
            output_dir=debug_output_dir,
            step_index=debug_step_index,
        )

        if all_targets_found:
            route_summary = _write_mllm_route_summary(
                test_case=test_case,
                scan_id=scan_id,
                debug_output_dir=debug_output_dir,
                executed_routes_by_agent=executed_routes_by_agent,
                completed_target_node_ids=completed_target_node_ids,
                target_found=hypothesis_graph.target_found,
                status="completed",
                stop_reason="all_targets_found",
                steps_completed=debug_step_index + 1,
                max_steps=max_steps,
            )
            return {
                "target_found": dict(hypothesis_graph.target_found),
                "status": "completed",
                "stop_reason": "all_targets_found",
                "steps_completed": debug_step_index + 1,
                "route_summary": route_summary,
            }

        if bool(getattr(optimizer, "target_directed_mode", False)):
            search_exhaustion_info = _target_directed_search_exhaustion_info(
                hypothesis_graph=hypothesis_graph,
                target_found_flags=hypothesis_graph.target_found,
            )
            if search_exhaustion_info is not None:
                route_summary = _write_mllm_route_summary(
                    test_case=test_case,
                    scan_id=scan_id,
                    debug_output_dir=debug_output_dir,
                    executed_routes_by_agent=executed_routes_by_agent,
                    completed_target_node_ids=completed_target_node_ids,
                    target_found=hypothesis_graph.target_found,
                    status="incomplete",
                    stop_reason="target_directed_search_exhausted",
                    steps_completed=debug_step_index + 1,
                    max_steps=max_steps,
                    extra_metadata=search_exhaustion_info,
                )
                return {
                    "target_found": dict(hypothesis_graph.target_found),
                    "status": "incomplete",
                    "stop_reason": "target_directed_search_exhausted",
                    "steps_completed": debug_step_index + 1,
                    "max_steps": max_steps,
                    "route_summary": route_summary,
                    **search_exhaustion_info,
                }

            no_positive_reward_info = _target_directed_no_positive_reward_info(
                hypothesis_graph=hypothesis_graph,
                target_found_flags=hypothesis_graph.target_found,
                use_raw_target_probs=optimizer.target_directed_use_raw_target_probs,
            )
            if no_positive_reward_info is not None:
                route_summary = _write_mllm_route_summary(
                    test_case=test_case,
                    scan_id=scan_id,
                    debug_output_dir=debug_output_dir,
                    executed_routes_by_agent=executed_routes_by_agent,
                    completed_target_node_ids=completed_target_node_ids,
                    target_found=hypothesis_graph.target_found,
                    status="incomplete",
                    stop_reason="target_directed_no_positive_reward_endpoint",
                    steps_completed=debug_step_index + 1,
                    max_steps=max_steps,
                    extra_metadata=no_positive_reward_info,
                )
                return {
                    "target_found": dict(hypothesis_graph.target_found),
                    "status": "incomplete",
                    "stop_reason": "target_directed_no_positive_reward_endpoint",
                    "steps_completed": debug_step_index + 1,
                    "max_steps": max_steps,
                    "route_summary": route_summary,
                    **no_positive_reward_info,
                }

        optimization_result = optimizer.solve(
            hypothesis_graph=hypothesis_graph,
            agent_current_vp_ids=hypothesis_graph.agent_current_vp_ids,
            target_found_flags=hypothesis_graph.target_found,
        )
        optimizer_route_log_path = write_optimizer_route_log(
            output_dir=debug_output_dir,
            test_case=test_case,
            optimization_result=optimization_result,
            agent_ids=agent_ids,
            step_index=debug_step_index,
        )
        print("Saved optimizer route log to %s.\n" % str(optimizer_route_log_path))

        observations_by_agent = {
            str(observation["agent_id"]): observation
            for observation in agent_observations
        }

        move_specs = []
        next_route_node_ids_by_agent = {}
        for agent_id in agent_ids:
            agent_path = optimization_result["agent_paths"][agent_id]
            next_vp_node_id = int(agent_path["next_vp_node_id"])
            next_route_node_ids_by_agent[agent_id] = next_vp_node_id
            next_viewpoint_id = Helper.viewpoint_vp_label_by_index[next_vp_node_id]
            agent_observation = observations_by_agent[agent_id]

            move_specs.append(
                {
                    "target_heading": float(
                        agent_observation["best_heading_for_vp"][next_viewpoint_id]
                    ),
                    "target_viewpoint_id": next_viewpoint_id,
                }
            )
            # The graph is updated with the new viewpoint assignment before executing the move.
            hypothesis_graph.nodes[next_vp_node_id].grounded = True
            print(f"Move spec for {agent_id}: {next_vp_node_id}")

        Helper.execute_individual_first_hops(
            sims=agent_sims,
            move_specs=move_specs,
            render=show_agent_views,
        )
        _append_executed_route_nodes(
            executed_routes_by_agent=executed_routes_by_agent,
            next_route_node_ids_by_agent=next_route_node_ids_by_agent,
            agent_ids=agent_ids,
        )
        for _ in range(2):
            print()

        if _max_steps_reached(debug_step_index, max_steps):
            route_summary = _write_mllm_route_summary(
                test_case=test_case,
                scan_id=scan_id,
                debug_output_dir=debug_output_dir,
                executed_routes_by_agent=executed_routes_by_agent,
                completed_target_node_ids=completed_target_node_ids,
                target_found=hypothesis_graph.target_found,
                status="incomplete",
                stop_reason="max_steps",
                steps_completed=debug_step_index + 1,
                max_steps=max_steps,
            )
            return {
                "target_found": dict(hypothesis_graph.target_found),
                "status": "incomplete",
                "stop_reason": "max_steps",
                "steps_completed": debug_step_index + 1,
                "max_steps": max_steps,
                "route_summary": route_summary,
            }


def _resolve_scenario_config(case_or_config: str) -> str:
    path = Path(case_or_config)
    if path.exists():
        return str(path)
    return str(Path("scenarios") / ("%s.json" % str(case_or_config)))


def _batch_skip_ledger_path(
    batch_id: str,
    project_root: str | Path | None = None,
) -> Path:
    root = Path(project_root).resolve() if project_root is not None else _project_root()
    return root / "mllm_debug_outputs" / str(batch_id) / "skipped_cases.json"


def _batch_progress_path(
    batch_id: str,
    project_root: str | Path | None = None,
) -> Path:
    root = Path(project_root).resolve() if project_root is not None else _project_root()
    return root / "mllm_debug_outputs" / str(batch_id) / "batch_progress.json"


def _batch_termination_path(
    batch_id: str,
    project_root: str | Path | None = None,
) -> Path:
    root = Path(project_root).resolve() if project_root is not None else _project_root()
    return root / "mllm_debug_outputs" / str(batch_id) / "batch_termination.json"


def _build_batch_skip_record(
    scenario: Dict[str, object],
    result: Dict[str, object],
) -> Dict[str, object]:
    mllm_config = scenario["mllm"]
    record = {
        "test_case": str(scenario["test_case"]),
        "scan_id": str(scenario["scan_id"]),
        "status": str(result.get("status", "incomplete")),
        "reason": str(result.get("stop_reason", "not_completed")),
        "debug_output_dir": str(mllm_config["debug_output_dir"]),
        "raw_output_dir": str(mllm_config["raw_output_dir"]),
    }

    if "steps_completed" in result:
        record["steps_completed"] = int(result["steps_completed"])
    if "max_steps" in result and result["max_steps"] is not None:
        record["max_steps"] = int(result["max_steps"])
    elif "max_steps" in scenario:
        record["max_steps"] = int(scenario["max_steps"])

    for key in (
        "failed_step_index",
        "mllm_stage",
        "mllm_router",
        "mllm_model",
        "mllm_attempts",
        "provider_status_code",
        "provider_code",
        "provider_type",
        "error",
        "target_directed_search_exhausted_target_ids",
        "target_directed_no_positive_reward_target_ids",
        "target_directed_eligible_endpoint_ids",
        "target_directed_reward_source",
    ):
        if key in result:
            record[key] = result[key]

    return record


def _build_batch_completed_record(
    scenario: Dict[str, object],
    result: Dict[str, object],
) -> Dict[str, object]:
    mllm_config = scenario["mllm"]
    record = {
        "test_case": str(scenario["test_case"]),
        "scan_id": str(scenario["scan_id"]),
        "status": str(result["status"]),
        "reason": str(result.get("stop_reason", "all_targets_found")),
        "debug_output_dir": str(mllm_config["debug_output_dir"]),
        "raw_output_dir": str(mllm_config["raw_output_dir"]),
    }
    if "steps_completed" in result:
        record["steps_completed"] = int(result["steps_completed"])
    return record


def write_batch_skip_ledger(
    batch_id: str,
    skipped_cases: Dict[str, object],
    project_root: str | Path | None = None,
) -> Path:
    payload = {
        "batch_id": str(batch_id),
        "skipped_case_count": len(skipped_cases),
        "cases": skipped_cases,
    }
    output_path = _batch_skip_ledger_path(batch_id, project_root=project_root)
    _write_json(output_path, payload)
    return output_path


def _next_pending_case_id(
    case_order: List[str],
    completed_cases: Dict[str, object],
    skipped_cases: Dict[str, object],
    terminated_case: str | None,
) -> str | None:
    if terminated_case is not None:
        return str(terminated_case)
    completed_or_skipped = set(completed_cases).union(skipped_cases)
    for case_id in case_order:
        if case_id not in completed_or_skipped:
            return case_id
    return None


def write_batch_progress(
    batch_id: str,
    case_order: List[str],
    completed_cases: Dict[str, object],
    skipped_cases: Dict[str, object],
    status: str,
    terminated_case: str | None = None,
    project_root: str | Path | None = None,
) -> Path:
    payload = {
        "batch_id": str(batch_id),
        "status": str(status),
        "case_order": [str(case_id) for case_id in case_order],
        "completed_case_count": len(completed_cases),
        "skipped_case_count": len(skipped_cases),
        "completed_cases": completed_cases,
        "skipped_cases": skipped_cases,
        "terminated_case": None if terminated_case is None else str(terminated_case),
        "next_case_id": _next_pending_case_id(
            case_order=case_order,
            completed_cases=completed_cases,
            skipped_cases=skipped_cases,
            terminated_case=terminated_case,
        ),
    }
    output_path = _batch_progress_path(batch_id, project_root=project_root)
    _write_json(output_path, payload)
    return output_path


def _build_batch_termination_record(
    scenario: Dict[str, object],
    result: Dict[str, object],
) -> Dict[str, object]:
    mllm_config = scenario["mllm"]
    record = {
        "reason": "provider_credit_exhausted",
        "test_case": str(scenario["test_case"]),
        "scan_id": str(scenario["scan_id"]),
        "status": str(result["status"]),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "debug_output_dir": str(mllm_config["debug_output_dir"]),
        "raw_output_dir": str(mllm_config["raw_output_dir"]),
    }
    for key in (
        "failed_step_index",
        "steps_completed",
        "mllm_stage",
        "mllm_router",
        "mllm_model",
        "provider_status_code",
        "provider_code",
        "provider_type",
        "error",
    ):
        if key in result:
            record[key] = result[key]
    return record


def write_batch_termination(
    batch_id: str,
    scenario: Dict[str, object],
    result: Dict[str, object],
    project_root: str | Path | None = None,
) -> Path:
    output_path = _batch_termination_path(batch_id, project_root=project_root)
    _write_json(output_path, _build_batch_termination_record(scenario, result))
    return output_path


def _load_batch_resume_state(
    batch_id: str,
    project_root: str | Path | None = None,
) -> Tuple[Dict[str, object], Dict[str, object]]:
    progress = _read_json_if_exists(
        _batch_progress_path(batch_id, project_root=project_root)
    )
    skipped = _read_json_if_exists(
        _batch_skip_ledger_path(batch_id, project_root=project_root)
    )
    completed_cases = {}
    skipped_cases = {}
    if isinstance(progress, dict):
        completed_cases = dict(progress.get("completed_cases", {}))
        skipped_cases.update(dict(progress.get("skipped_cases", {})))
    if isinstance(skipped, dict):
        skipped_cases.update(dict(skipped.get("cases", {})))
    return completed_cases, skipped_cases


def run_batch_config(
    batch_config_path: str | Path,
    show_agent_views: bool = True,
) -> Dict[str, object]:
    path = Path(batch_config_path)
    batch_config = _read_json(path)
    if not isinstance(batch_config, dict):
        raise TypeError("Batch config must be a JSON object.")
    if not is_batch_config(batch_config):
        raise ValueError("Config %s is not a batch config." % str(path))

    batch_id = path.stem
    default_config = load_default_config()
    scenarios, summary, summary_path = load_or_generate_batch_scenarios(
        batch_config=batch_config,
        batch_id=batch_id,
        default_config=default_config,
    )

    case_order = _case_order_from_batch_summary(summary)
    results = {}
    completed_cases, skipped_cases = _load_batch_resume_state(batch_id)
    progress_bar = tqdm(
        total=len(case_order),
        initial=len(completed_cases) + len(skipped_cases),
        unit="case",
        file=sys.stdout,
        bar_format=(
            "{l_bar}{bar}| {n_fmt}/{total_fmt} {percentage:3.0f}% "
            "elapsed {elapsed} ETA {remaining}"
        ),
    )
    tqdm.write("Using generated batch case summary at %s.\n" % str(summary_path))
    skipped_cases_path = _batch_skip_ledger_path(batch_id)
    progress_path = write_batch_progress(
        batch_id=batch_id,
        case_order=case_order,
        completed_cases=completed_cases,
        skipped_cases=skipped_cases,
        status="running",
    )
    termination_path = _batch_termination_path(batch_id)

    for scenario in scenarios:
        test_case = str(scenario["test_case"])
        if test_case in completed_cases:
            tqdm.write("Skipping previously completed batch case %s.\n" % test_case)
            continue
        if test_case in skipped_cases:
            tqdm.write("Skipping previously skipped batch case %s.\n" % test_case)
            continue

        tqdm.write("Running generated batch case %s.\n" % test_case)
        results[test_case] = run_scenario(
            scenario,
            show_agent_views=show_agent_views,
            default_config=default_config,
        )
        if results[test_case].get("status") == "completed":
            completed_cases[test_case] = _build_batch_completed_record(
                scenario=scenario,
                result=results[test_case],
            )
            progress_path = write_batch_progress(
                batch_id=batch_id,
                case_order=case_order,
                completed_cases=completed_cases,
                skipped_cases=skipped_cases,
                status="running",
            )
            progress_bar.update(1)
        elif results[test_case].get("status") == "terminated":
            termination_path = write_batch_termination(
                batch_id=batch_id,
                scenario=scenario,
                result=results[test_case],
            )
            progress_path = write_batch_progress(
                batch_id=batch_id,
                case_order=case_order,
                completed_cases=completed_cases,
                skipped_cases=skipped_cases,
                status="terminated",
                terminated_case=test_case,
            )
            progress_bar.update(1)
            tqdm.write(
                "Saved batch termination notice to %s.\n" % str(termination_path)
            )
            break
        else:
            skipped_cases[test_case] = _build_batch_skip_record(
                scenario=scenario,
                result=results[test_case],
            )
            skipped_cases_path = write_batch_skip_ledger(
                batch_id,
                skipped_cases,
            )
            progress_path = write_batch_progress(
                batch_id=batch_id,
                case_order=case_order,
                completed_cases=completed_cases,
                skipped_cases=skipped_cases,
                status="running",
            )
            progress_bar.update(1)
            tqdm.write(
                "Saved skipped batch case ledger to %s.\n" % str(skipped_cases_path)
            )
    else:
        progress_path = write_batch_progress(
            batch_id=batch_id,
            case_order=case_order,
            completed_cases=completed_cases,
            skipped_cases=skipped_cases,
            status="completed",
        )

    progress_bar.close()

    return {
        "status": (
            "terminated"
            if any(result.get("status") == "terminated" for result in results.values())
            else "completed"
        ),
        "generated_cases": summary,
        "generated_cases_path": str(summary_path),
        "skipped_cases_path": str(skipped_cases_path),
        "progress_path": str(progress_path),
        "termination_path": str(termination_path),
        "results": results,
    }


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a scenario or its perfect-knowledge oracle solution."
    )
    parser.add_argument(
        "case_or_config",
        help="Scenario config path or test case name, such as test1.",
    )
    parser.add_argument(
        "--oracle",
        action="store_true",
        help="Run the perfect-knowledge oracle optimization for the named test case.",
    )
    parser.add_argument(
        "--hide-agent-views",
        action="store_true",
        help="Hide interactive agent observation and rotation windows.",
    )
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    if args.oracle:
        from oracle_runner import run_oracle

        run_oracle(args.case_or_config)
        return 0

    config_path = _resolve_scenario_config(args.case_or_config)
    raw_config = _read_json(config_path)
    if isinstance(raw_config, dict) and is_batch_config(raw_config):
        result = run_batch_config(
            config_path,
            show_agent_views=not args.hide_agent_views,
        )
        if result.get("status") == "terminated":
            return 1
    else:
        run_scenario(
            config_path,
            show_agent_views=not args.hide_agent_views,
        )

    debugpy.breakpoint()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
