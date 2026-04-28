import json
import math
import sys
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


def _found_detections_by_target(
    mllm_output: Dict[str, object],
    agent_observations: List[Dict[str, object]],
    unfound_target_ids,
):
    """Collect direct detections from the new MLLM raw format.

    Expected detection format:
    {
        "agent_id": "agent0",
        "target_indices": ["0", "1"],
        "founds": [false, true]
    }
    """
    observations_by_agent = {
        str(observation["agent_id"]): observation for observation in agent_observations
    }

    found_detections = {}

    for detection in mllm_output["detections"]:
        agent_id = str(detection["agent_id"])
        if agent_id not in observations_by_agent:
            raise KeyError("Detection uses unknown agent id %s." % agent_id)

        target_indices = list(detection["target_indices"])
        founds = list(detection["founds"])

        if len(target_indices) != len(founds):
            raise ValueError(
                "detections[].target_indices and detections[].founds must have "
                "the same length for agent %s." % agent_id
            )

        agent_observation = observations_by_agent[agent_id]

        for target_id, found in zip(target_indices, founds):
            target_id = str(target_id)

            if target_id not in unfound_target_ids:
                continue
            if not bool(found):
                continue

            found_detections.setdefault(target_id, []).append(
                {
                    "agent_id": agent_id,
                    "target_rgb_image": agent_observation["raw_panorama"],
                    "target_depth_image": agent_observation.get("depth_panorama"),
                }
            )

    return found_detections


def _mark_completed_targets(
    mllm_client,
    mllm_output: Dict[str, object],
    agent_observations: List[Dict[str, object]],
    targets: List[Dict[str, object]],
    hypothesis_graph,
) -> List[str]:
    """Mark targets as completed based on direct detections.

    The graph is keyed by target_id. If a target record has distance_threshold_m,
    the target is marked completed only when the estimated distance is within
    the threshold. If distance_threshold_m is absent, direct detection alone is
    treated as sufficient.
    """
    target_records = _normalize_targets(targets)

    target_descriptions_by_id = {
        target["target_id"]: target["description"] for target in target_records
    }

    target_thresholds = {
        target["target_id"]: (
            float(target["distance_threshold_m"])
            if "distance_threshold_m" in target
            else math.inf
        )
        for target in target_records
    }

    unfound_target_ids = {
        str(target_id)
        for target_id, is_found in hypothesis_graph.target_found.items()
        if not is_found
    }

    found_detections = _found_detections_by_target(
        mllm_output=mllm_output,
        agent_observations=agent_observations,
        unfound_target_ids=unfound_target_ids,
    )

    completed_target_ids = []

    for target_id, detections in found_detections.items():
        target_description = target_descriptions_by_id[target_id]
        threshold_m = target_thresholds[target_id]

        for detection in detections:
            # If the scenario does not provide distance_threshold_m, direct
            # detection is enough to mark the target as completed.
            if math.isinf(threshold_m):
                hypothesis_graph.mark_target_found(target_id)
                completed_target_ids.append(target_id)
                break

            depth_image = detection.get("target_depth_image")
            if depth_image is None:
                raise KeyError(
                    "Target %s has distance_threshold_m, but the observation does "
                    "not contain depth_panorama." % target_id
                )

            distance_output = mllm_client.estimate_target_distance(
                rgb_image=detection["target_rgb_image"],
                depth_image=depth_image,
                target_object=target_description,
            )

            if float(distance_output["distance_m"]) <= threshold_m:
                hypothesis_graph.mark_target_found(target_id)
                completed_target_ids.append(target_id)
                break

    return completed_target_ids


def run_scenario(config_path: str) -> Dict[str, object]:
    from optimization_model import RollingHorizonOptimizer
    from semantic_persistence import HypothesisGraph, MLLMClient, SigLIPScorer

    # -------------------- Debugger --------------------
    debugpy.listen(("0.0.0.0", 5678))
    print("debugpy listening on 5678, waiting...")
    debugpy.wait_for_client()
    print("debugger attached, continuing...")

    scenario = load_scenario_config(config_path)
    agent_ids = [str(agent["id"]) for agent in scenario["agents"]]
    scan_id = str(scenario["scan_id"])

    sim = Helper.init_render(batch_size=len(agent_ids), enable_render=False)
    sim.initialize()
    Helper.build_viewpoint_index(scan_id)

    sim.newEpisode(
        [scan_id for _ in scenario["agents"]],
        [str(agent["start_viewpoint_id"]) for agent in scenario["agents"]],
        [float(agent.get("heading", 0.0)) for agent in scenario["agents"]],
        [float(agent.get("elevation", 0.0)) for agent in scenario["agents"]],
    )

    targets = _normalize_targets(scenario["targets"])
    graph_targets = _target_records_for_graph(targets)

    hypothesis_graph = HypothesisGraph(
        targets=graph_targets,
        bayes_config=scenario["bayes"],
    )

    optimizer = RollingHorizonOptimizer(scenario["optimizer"])

    mllm_client = MLLMClient(
        model_name=str(scenario["mllm"]["model_name"]),
        max_new_tokens=int(scenario["mllm"]["max_new_tokens"]),
    )

    scorer = SigLIPScorer()

    while True:
        if all(hypothesis_graph.target_found.values()):
            return {"target_found": dict(hypothesis_graph.target_found)}

        agent_observations = Helper.horizon_scan_batch_return(
            sim=sim,
            agent_ids=agent_ids,
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

        hypothesis_graph.update_from_mllm(
            mllm_output=mllm_output,
            agent_observations=agent_observations,
            scorer=scorer,
        )

        _mark_completed_targets(
            mllm_client=mllm_client,
            mllm_output=mllm_output,
            agent_observations=agent_observations,
            targets=targets,
            hypothesis_graph=hypothesis_graph,
        )

        if all(hypothesis_graph.target_found.values()):
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
            hypothesis_graph.nodes[next_vp_node_id].grounded = True
            hypothesis_graph.nodes[next_vp_node_id].node_visit_times += 1
            print(f"Move spec for {agent_id}: {next_vp_node_id}")

        Helper.execute_batched_first_hops(sim=sim, move_specs=move_specs)


def main(argv: List[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if len(argv) != 1:
        raise SystemExit("Usage: python main.py <scenario_config.json>")

    run_scenario(argv[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
