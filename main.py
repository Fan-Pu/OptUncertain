from doctest import debug
import json
import sys
from typing import Dict, List

import debugpy

import Helper


def load_scenario_config(config_path: str) -> Dict[str, object]:
    with open(config_path, "r", encoding="utf-8") as file_handle:
        return json.load(file_handle)


def _found_detections_by_target(
    mllm_output: Dict[str, object],
    agent_observations: List[Dict[str, object]],
    unfound_target_descriptions,
):
    observations_by_agent = {
        str(observation["agent_id"]): observation for observation in agent_observations
    }
    found_detections = {}
    for detection in mllm_output["detections"]:
        agent_id = str(detection["agent_id"])
        agent_observation = observations_by_agent[agent_id]
        target_description = str(detection["target"])
        if target_description not in unfound_target_descriptions:
            continue
        if not bool(detection["found"]):
            continue
        found_detections.setdefault(target_description, []).append(
            {
                "agent_id": agent_id,
                "target_rgb_image": agent_observation["raw_panorama"],
                "target_depth_image": agent_observation["depth_panorama"],
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
    target_thresholds = {
        str(target["description"]): float(target["distance_threshold_m"])
        for target in targets
    }
    unfound_target_descriptions = {
        target_description
        for target_description, is_found in hypothesis_graph.target_found.items()
        if not is_found
    }
    found_detections = _found_detections_by_target(
        mllm_output=mllm_output,
        agent_observations=agent_observations,
        unfound_target_descriptions=unfound_target_descriptions,
    )

    completed_target_descriptions = []
    for target_description, detections in found_detections.items():
        for detection in detections:
            distance_output = mllm_client.estimate_target_distance(
                rgb_image=detection["target_rgb_image"],
                depth_image=detection["target_depth_image"],
                target_object=target_description,
            )
            if (
                float(distance_output["distance_m"])
                <= target_thresholds[target_description]
            ):
                hypothesis_graph.mark_target_found(target_description)
                completed_target_descriptions.append(target_description)
                break
    return completed_target_descriptions


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

    target_descriptions = [str(target["description"]) for target in scenario["targets"]]
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

    # scorer.test_score_images_text("test.png")

    debugpy.breakpoint()  # Set a breakpoint here to inspect initial state before the loop starts

    while True:
        if all(hypothesis_graph.target_found.values()):
            return {"target_found": dict(hypothesis_graph.target_found)}

        agent_observations = Helper.horizon_scan_batch_return(
            sim=sim,
            agent_ids=agent_ids,
            viewpoint_index_by_vp=Helper.viewpoint_index_by_vp_label,
        )

        debugpy.breakpoint()  # Set a breakpoint here to inspect agent observations before processing with MLLM
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
        Helper.execute_batched_first_hops(sim=sim, move_specs=move_specs)


def main(argv: List[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 1:
        raise SystemExit("Usage: python main.py <scenario_config.json>")
    run_scenario(argv[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
