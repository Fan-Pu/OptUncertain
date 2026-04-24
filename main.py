import json
import sys
from typing import Dict, List

import Helper


def load_scenario_config(config_path: str) -> Dict[str, object]:
    with open(config_path, "r", encoding="utf-8") as file_handle:
        return json.load(file_handle)


def select_detection_observation(
    agent_observation: Dict[str, object],
    detection: Dict[str, object],
):
    if not bool(detection["found"]):
        return None, None, None
    strip_index = int(detection["strip_index"])
    return (
        float(agent_observation["horizon_headings"][strip_index]),
        agent_observation["horizon_rgb_frames"][strip_index],
        agent_observation["horizon_depths"][strip_index],
    )


def _best_detections_by_target(
    mllm_output: Dict[str, object],
    agent_observations: List[Dict[str, object]],
    unfound_target_ids,
):
    observations_by_agent = {
        str(observation["agent_id"]): observation for observation in agent_observations
    }
    best_detections = {}
    for agent_payload in mllm_output["agents"]:
        agent_id = str(agent_payload["agent_id"])
        agent_observation = observations_by_agent[agent_id]
        for detection in agent_payload["detections"]:
            target_id = str(detection["target_id"])
            if target_id not in unfound_target_ids:
                continue
            if not bool(detection["found"]):
                continue
            target_heading, target_rgb_image, target_depth_image = select_detection_observation(
                agent_observation=agent_observation,
                detection=detection,
            )
            candidate = {
                "agent_id": agent_id,
                "confidence": float(detection["confidence"]),
                "target_heading": target_heading,
                "target_rgb_image": target_rgb_image,
                "target_depth_image": target_depth_image,
            }
            if target_id not in best_detections:
                best_detections[target_id] = candidate
                continue
            if candidate["confidence"] > best_detections[target_id]["confidence"]:
                best_detections[target_id] = candidate
    return best_detections


def _mark_completed_targets(
    mllm_client,
    mllm_output: Dict[str, object],
    agent_observations: List[Dict[str, object]],
    targets: List[Dict[str, object]],
    hypothesis_graph,
) -> List[str]:
    target_descriptions = {
        str(target["id"]): str(target["description"]) for target in targets
    }
    target_thresholds = {
        str(target["id"]): float(target["distance_threshold_m"]) for target in targets
    }
    unfound_target_ids = {
        target_id for target_id, is_found in hypothesis_graph.target_found.items() if not is_found
    }
    best_detections = _best_detections_by_target(
        mllm_output=mllm_output,
        agent_observations=agent_observations,
        unfound_target_ids=unfound_target_ids,
    )

    completed_target_ids = []
    for target_id, detection in best_detections.items():
        distance_output = mllm_client.estimate_target_distance(
            rgb_image=detection["target_rgb_image"],
            depth_image=detection["target_depth_image"],
            target_object=target_descriptions[target_id],
        )
        if float(distance_output["distance_m"]) <= target_thresholds[target_id]:
            hypothesis_graph.mark_target_found(target_id)
            completed_target_ids.append(target_id)
    return completed_target_ids


def run_scenario(config_path: str) -> Dict[str, object]:
    from optimization_model import RollingHorizonOptimizer
    from semantic_persistence import HypothesisGraph, MLLMClient, SigLIPScorer

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

    target_descriptions = {
        str(target["id"]): str(target["description"]) for target in scenario["targets"]
    }
    hypothesis_graph = HypothesisGraph(
        target_descriptions=target_descriptions,
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
        mllm_output = mllm_client.propose_semantic_nodes(
            agent_observations=agent_observations,
            targets=scenario["targets"],
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
            targets=scenario["targets"],
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
            str(observation["agent_id"]): observation for observation in agent_observations
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
        Helper.execute_batched_first_hops(sim=sim, move_specs=move_specs)


def main(argv: List[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 1:
        raise SystemExit("Usage: python main.py <scenario_config.json>")
    run_scenario(argv[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
