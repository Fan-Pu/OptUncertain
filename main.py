from doctest import debug
import json
from pathlib import Path
import sys
from typing import Dict, List
import numpy as np
import debugpy

import Helper

from optimization_model import RollingHorizonOptimizer
from semantic_persistence.hypothesis_graph import HypothesisGraph
from semantic_persistence.mllm_client import MLLMClient

Explore_mode = False  # True: manual keyboard control
LAST_IMAGE_RIGHT_SHIFT_STEPS = 6


def select_target_observation(
    tgt,
    horizon_headings,
    horizon_rgb_frames,
    horizon_depths,
):
    if not tgt["found"]:
        return None, None, None

    target_strip_index = int(tgt["strip_index"])
    return (
        float(horizon_headings[target_strip_index]),
        horizon_rgb_frames[target_strip_index],
        horizon_depths[target_strip_index],
    )


if __name__ == "__main__":
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

    while True:
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

        if all(hypothesis_graph.target_found.values()):
            hypothesis_graph.export_debug_snapshot(
                output_dir=debug_output_dir,
                step_index=debug_step_index,
            )
            return {"target_found": dict(hypothesis_graph.target_found)}

        if mllm_output is None:
            raise RuntimeError(
                "Graph generation was skipped, but not all targets are marked found."
            )

        hypothesis_graph.update_from_mllm(
            mllm_output=mllm_output,
            agent_observations=agent_observations,
            scorer=scorer,
        )
        hypothesis_graph.export_debug_snapshot(
            output_dir=debug_output_dir,
            step_index=debug_step_index,
        )

        # print target finding status
        print("Target finding status:")
        for target_id, found in hypothesis_graph.target_found.items():
            print(f"  {target_id}: {'Found' if found else 'Not found'}")

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
            # The graph is updated with the new viewpoint assignment before executing the move.
            hypothesis_graph.nodes[next_vp_node_id].grounded = True
            print(f"Move spec for {agent_id}: {next_vp_node_id}")

        # debugpy.breakpoint()

        Helper.execute_individual_first_hops(sims=agent_sims, move_specs=move_specs)
        for _ in range(2):
            print()

        if debug_step_index == 3:
            debugpy.breakpoint()


def main(argv: List[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if len(argv) != 1:
        raise SystemExit("Usage: python main.py <scenario_config.json>")

    run_scenario(argv[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
