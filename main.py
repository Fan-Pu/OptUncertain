import argparse
import json
from pathlib import Path
import sys
import time
from typing import Dict, List
import debugpy

import Helper
from route_plotter import (
    load_environment_graph,
    print_route_summary,
    summarize_routes,
)


def load_scenario_config(config_path: str) -> Dict[str, object]:
    with open(config_path, "r", encoding="utf-8") as file_handle:
        return json.load(file_handle)


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


def _center_completed_targets(agent_sims, agent_ids, completed_targets) -> None:
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
            PAUSE_TIME=Helper.PAUSE_TIME,
            window_names=window_names,
            notifications=notifications,
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


def _write_mllm_completion_route_summary(
    test_case: str,
    scan_id: str,
    debug_output_dir: str,
    executed_routes_by_agent: Dict[str, List[int]],
    completed_target_node_ids: Dict[str, int],
) -> Dict[str, object]:
    environment_graph = load_environment_graph(scan_id=scan_id)
    summary = summarize_routes(
        test_case=test_case,
        environment_graph=environment_graph,
        routes_by_agent=executed_routes_by_agent,
        target_node_ids_by_target_id=completed_target_node_ids,
    )
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


def run_scenario(config_path: str) -> Dict[str, object]:
    from optimization_model import RollingHorizonOptimizer
    from semantic_persistence import HypothesisGraph, MLLMClient, SigLIPScorer

    # -------------------- Debugger --------------------
    debugpy.listen(("0.0.0.0", 5678))
    print("debugpy listening on 5678, waiting...")
    debugpy.wait_for_client()
    print("debugger attached, continuing...")

    scenario = load_scenario_config(config_path)
    run_output_dir = scenario["mllm"].get("raw_output_dir", "mllm_raw_outputs/default")
    debug_output_dir = scenario["mllm"].get(
        "debug_output_dir", "mllm_debug_outputs/default"
    )
    agent_ids = [str(agent["id"]) for agent in scenario["agents"]]
    scan_id = str(scenario["scan_id"])
    test_case = Path(debug_output_dir).name

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

    mllm_client = MLLMClient(
        graph_model_name=str(scenario["mllm"]["graph_model_name"]),
        detection_model_name=str(scenario["mllm"]["detection_model_name"]),
        max_new_tokens=int(scenario["mllm"]["max_new_tokens"]),
        read_saved_raw_outputs=bool(
            scenario["mllm"].get("read_saved_raw_outputs", False)
        ),
        raw_output_dir=run_output_dir,
        raw_debug_dir=debug_output_dir,
        max_validation_retries=int(scenario["mllm"].get("max_validation_retries", 2)),
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

        Helper.render_sim_state(
            _current_agent_states(agent_sims),
            viewpoint_index_by_vp=Helper.viewpoint_index_by_vp_label,
        )

        # The graph summary is sent to the MLLM before update_from_mllm().
        # Therefore, sync the current agent viewpoint ids from observations first.
        # This does not create semantic regions or viewpoint assignments.
        hypothesis_graph.sync_agent_current_viewpoints(agent_observations)

        mllm_output = mllm_client.propose_semantic_nodes(
            agent_observations=agent_observations,
            targets=graph_targets,
            graph=hypothesis_graph,
            scorer=scorer,
        )

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

        # print target finding status
        print("Target finding status:")
        for target_id, found in hypothesis_graph.target_found.items():
            print(f"  {target_id}: {'Found' if found else 'Not found'}")

        if all_targets_found:
            route_summary = _write_mllm_completion_route_summary(
                test_case=test_case,
                scan_id=scan_id,
                debug_output_dir=debug_output_dir,
                executed_routes_by_agent=executed_routes_by_agent,
                completed_target_node_ids=completed_target_node_ids,
            )
            debugpy.breakpoint()
            return {
                "target_found": dict(hypothesis_graph.target_found),
                "route_summary": route_summary,
            }

        optimization_result = optimizer.solve(
            hypothesis_graph=hypothesis_graph,
            agent_current_vp_ids=hypothesis_graph.agent_current_vp_ids,
            target_found_flags=hypothesis_graph.target_found,
        )

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

        Helper.execute_individual_first_hops(sims=agent_sims, move_specs=move_specs)
        _append_executed_route_nodes(
            executed_routes_by_agent=executed_routes_by_agent,
            next_route_node_ids_by_agent=next_route_node_ids_by_agent,
            agent_ids=agent_ids,
        )
        for _ in range(2):
            print()

        if debug_step_index == 7:
            debugpy.breakpoint()


def _resolve_scenario_config(case_or_config: str) -> str:
    path = Path(case_or_config)
    if path.exists():
        return str(path)
    return str(Path("scenarios") / ("%s.json" % str(case_or_config)))


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
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    if args.oracle:
        from oracle_runner import run_oracle

        run_oracle(args.case_or_config)
        return 0

    run_scenario(_resolve_scenario_config(args.case_or_config))

    debugpy.breakpoint()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
