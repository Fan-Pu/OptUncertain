from doctest import debug
import json
from pathlib import Path
import sys
import time
from typing import Dict, List
import debugpy

import Helper


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

        target_indices = detection.get("target_indices", [])
        founds = detection.get("founds", [])
        target_center_xs = detection.get("target_center_xs", None)

        if len(target_indices) != len(founds):
            raise ValueError(
                "target_indices and founds must have the same length "
                "for agent %s." % agent_id
            )

        if target_center_xs is not None and len(target_center_xs) != len(
            target_indices
        ):
            raise ValueError(
                "target_center_xs and target_indices must have the same length "
                "for agent %s." % agent_id
            )

        for item_index, target_id_raw in enumerate(target_indices):
            target_id = str(target_id_raw)

            if target_id not in valid_target_ids:
                continue

            found = founds[item_index]
            if not isinstance(found, bool):
                raise TypeError(
                    "Detection founds values must be booleans for agent %s." % agent_id
                )

            if not found:
                continue

            if target_center_xs is None:
                raise KeyError(
                    "Found detection for agent %s target %s requires target_center_xs."
                    % (agent_id, target_id)
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

        detection = found_detections_by_target[target_id][0]

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

    completed_target_by_agent = {}
    for completed_target in completed_targets:
        agent_id = str(completed_target["agent_id"])
        if agent_id not in completed_target_by_agent:
            completed_target_by_agent[agent_id] = completed_target

    sims_to_rotate = []
    target_headings = []
    window_names = []
    notifications = []
    for agent_index, (agent_id, sim) in enumerate(zip(agent_ids, agent_sims)):
        if agent_id in completed_target_by_agent:
            completed_target = completed_target_by_agent[agent_id]
            sims_to_rotate.append(sim)
            target_headings.append(float(completed_target["target_heading"]))
            window_names.append("Agent %s" % agent_index)
            notifications.append(
                "Target %s is found." % (completed_target["target_id"])
            )

    if sims_to_rotate:
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

    Helper.build_viewpoint_index(scan_id)
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
        )
        debug_step_index = int(mllm_client.semantic_raw_output_index) - 1

        completed_targets = _collect_completed_targets(
            mllm_output={"detections": mllm_client.last_direct_detections},
            agent_observations=agent_observations,
            targets=targets,
            hypothesis_graph=hypothesis_graph,
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
            debugpy.breakpoint()
            return {"target_found": dict(hypothesis_graph.target_found)}

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
        for agent_id in agent_ids:
            agent_path = optimization_result["agent_paths"][agent_id]
            next_vp_node_id = int(agent_path["next_vp_node_id"])
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
        for _ in range(2):
            print()

        if debug_step_index == 7:
            debugpy.breakpoint()


def main(argv: List[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if len(argv) != 1:
        raise SystemExit("Usage: python main.py <scenario_config.json>")

    run_scenario(argv[0])

    debugpy.breakpoint()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
