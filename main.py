from doctest import debug
import os
import time
import debugpy

import Helper

from semantic_persistence.hypothesis_graph import HypothesisGraph
from semantic_persistence.mllm_client import MLLMClient


Explore_mode = False  # True: manual keyboard control
LAST_IMAGE_RIGHT_SHIFT_STEPS = 6

if __name__ == "__main__":
    # -------------------- Debugger --------------------
    debugpy.listen(("0.0.0.0", 5678))
    print("debugpy listening on 5678, waiting...")
    debugpy.wait_for_client()
    print("debugger attached, continuing...")

    # -------------------- Simulator --------------------
    sim = Helper.init_render()
    sim.initialize()

    # -------------------- Episode --------------------
    scan_id = "17DRP5sb8fy"
    start_vp_id = "10c252c90fa24ef3b698c6f54d984c5c"
    Helper.build_viewpoint_index(scan_id)
    sim.newEpisode([scan_id], [start_vp_id], [0.0], [0.0])

    # -------------------- Explore mode --------------------
    if Explore_mode:
        print("Explore mode: Use arrow keys to navigate. Ctrl+C to exit.")
        Helper.explore_world(sim)
        raise SystemExit(0)

    # -------------------- MLLM --------------------
    model_name = "meta-llama/Llama-4-Maverick-17B-128E-Instruct:cheapest"
    # model_name = "meta-llama/Llama-4-Scout-17B-16E-Instruct:cheapest"
    mllm = MLLMClient(
        model_name=model_name,
        max_new_tokens=160,
        h_fov=Helper.HFOV,
        last_image_right_shift_steps=LAST_IMAGE_RIGHT_SHIFT_STEPS,
    )

    # -------------------- Task --------------------
    target_object = os.environ.get("TARGET_OBJECT", "green plant on the table").strip()
    distance_threshold_m = float(
        os.environ.get("TARGET_DISTANCE_THRESHOLD_M", "1.0").strip()
    )
    hypothesis_graph = HypothesisGraph()
    observation_step = 0

    # -------------------- Loop --------------------
    while True:
        observation_step += 1
        state = sim.getState()[0]
        cur_vp = state.location.viewpointId

        Helper.render_sim_state(
            state, viewpoint_index_by_vp=Helper.viewpoint_index_by_vp_label
        )

        # 1) Scan the current viewpoint and keep the raw RGB frames, the annotated
        #    MLLM frames, their headings, and the aligned depth maps together.
        (
            best_heading_for_vp,
            _,
            horizon_rgb_images,
            horizon_mllm_images,
            horizon_headings,
            horizon_depths,
            observation_context,
        ) = Helper.horizon_scan_return(
            sim,
            viewpoint_index_by_vp=Helper.viewpoint_index_by_vp_label,
        )

        if not best_heading_for_vp:
            print("[STOP] No navigable neighbors returned by the scan.")
            break

        # 2) Ask the MLLM to label the current/neighboring regions and report which
        #    RGB view contains the target object.
        #
        #    The prompt now receives a compact snapshot of the existing hypothesis
        #    graph so the model can reuse old node ids instead of regenerating
        #    redundant semantic nodes for already-known locations.
        start_time = time.perf_counter()
        mllm_out = mllm.propose_semantic_nodes(
            observation_images=horizon_mllm_images,
            target_object=target_object,
            depth_images=horizon_depths,
            viewpoint_context=observation_context,
            graph=hypothesis_graph,
        )
        runtime = time.perf_counter() - start_time
        print(f"[MLLM] runtime: {runtime:.2f} seconds")

        debugpy.breakpoint()

        # 2b) Convert the one-step MLLM output into a persistent hypothesis graph.
        #     This preserves semantic nodes and uncertain structural edges across
        #     multiple robot viewpoints instead of treating each scan independently.
        hypothesis_graph.update_from_mllm(mllm_output=mllm_out)
        print(
            f"[HypothesisGraph] updated nodes={len(hypothesis_graph.nodes)} "
            f"edges={len(hypothesis_graph.edges)}"
        )

        debugpy.breakpoint()

        # 2a) The detection step above already guarantees the target is in the chosen
        #     RGB frame, so the follow-up query only needs to estimate distance from
        #     the aligned RGB/depth pair.
        tgt = mllm_out.get("target", {}) if isinstance(mllm_out, dict) else {}
        terminate = Helper.target_detection(
            tgt,
            horizon_headings,
            horizon_rgb_images,
            horizon_depths,
            target_object,
            distance_threshold_m,
        )

        debugpy.breakpoint()

        # 3) Optimization model selects the best neighboring viewpoint to move to based on the MLLM-labeled graph and the target detection results.
        next_vp = list(best_heading_for_vp.keys())[0]
        Helper.rotate_to_target_heading_mov2vp(
            sim, best_heading_for_vp[next_vp], next_vp
        )
        print(f"[Move] {cur_vp} -> {next_vp}")

        debugpy.breakpoint()
