import os
import time
import debugpy

import Helper

from semantic_persistence.mllm_client import MLLMClient


Explore_mode = False  # True: manual keyboard control

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
    sim.newEpisode([scan_id], [start_vp_id], [0.0], [0.0])

    # -------------------- Explore mode --------------------
    if Explore_mode:
        print("Explore mode: Use arrow keys to navigate. Ctrl+C to exit.")
        Helper.explore_world(sim)
        raise SystemExit(0)

    # -------------------- MLLM --------------------
    mllm = MLLMClient(
        "meta-llama/Llama-4-Scout-17B-16E-Instruct:cheapest",
        max_new_tokens=160,
        h_fov=Helper.HFOV,
    )

    # -------------------- Task --------------------
    target_object = os.environ.get("TARGET_OBJECT", "television").strip()
    distance_threshold_m = float(
        os.environ.get("TARGET_DISTANCE_THRESHOLD_M", "1.0").strip()
    )

    # -------------------- Loop --------------------
    while True:
        state = sim.getState()[0]
        cur_vp = state.location.viewpointId

        Helper.render_sim_state(state)

        # 1) Scan the current viewpoint and keep the RGB frames, their headings, and
        #    the aligned depth maps together so later queries can reuse the same view.
        best_heading_for_vp, _, horizon_rgb_images, horizon_headings, horizon_depths = (
            Helper.horizon_scan_return(sim)
        )

        if not best_heading_for_vp:
            print("[STOP] No navigable neighbors returned by the scan.")
            break

        # 2) Ask the MLLM to label the current/neighboring regions and report which
        #    RGB view contains the target object.
        start_time = time.perf_counter()
        mllm_out = mllm.propose_semantic_nodes(
            observation_images=horizon_rgb_images,
            topk=5,
            target_object=target_object,
            depth_images=horizon_depths,
        )
        runtime = time.perf_counter() - start_time
        print(f"[MLLM] runtime: {runtime:.2f} seconds")

        # 2a) The detection step above already guarantees the target is in the chosen
        #     RGB frame, so the follow-up query only needs to estimate distance from
        #     the aligned RGB/depth pair.
        tgt = mllm_out.get("target", {}) if isinstance(mllm_out, dict) else {}
        tgt_found = bool(tgt.get("found", False))
        orig_idx = -1
        target_views = tgt.get("views", [])
        target_confidences = tgt.get("confidence", [])
        if (
            isinstance(target_views, list)
            and isinstance(target_confidences, list)
            and target_views
        ):
            paired_candidates = [
                (int(view_idx), float(confidence))
                for view_idx, confidence in zip(target_views, target_confidences)
            ]
            if paired_candidates:
                orig_idx = max(paired_candidates, key=lambda pair: pair[1])[0]
        if tgt_found and orig_idx != -1:
            target_heading = float(horizon_headings[orig_idx])
            target_rgb_image = horizon_rgb_images[orig_idx]
            target_depth_image = horizon_depths[orig_idx]

            print(f"Target '{target_object}' detected by MLLM in view {orig_idx}.")
            depth_start_time = time.perf_counter()
            distance_out = {"distance_m": 2.375}
            # distance_out = mllm.estimate_target_distance(
            #     rgb_image=target_rgb_image,
            #     depth_image=target_depth_image,
            #     target_object=target_object,
            # )
            depth_runtime = time.perf_counter() - depth_start_time
            print(f"[MLLM distance] runtime: {depth_runtime:.2f} seconds")

            debugpy.breakpoint()

            distance_m = distance_out.get("distance_m")

            if distance_m is not None:
                print(
                    f"Target '{target_object}' distance estimate: {distance_m:.2f} m "
                    f"(threshold: {distance_threshold_m:.2f} m)."
                )
                if distance_m <= distance_threshold_m:
                    Helper.rotate_to_target_heading_mov2vp(sim, target_heading, None)
                    Helper.render_sim_state(sim.getState()[0])
                    debugpy.breakpoint()
                    break

                print(
                    f"[CONTINUE] Target detected but distance {distance_m:.2f} m exceeds "
                    f"threshold {distance_threshold_m:.2f} m."
                )
            else:
                print(
                    f"[CONTINUE] Target '{target_object}' detected, but distance could not be estimated."
                )

        debugpy.breakpoint()

        # 3) Fall back to the existing greedy navigation rule when the target is not
        #    visible or the distance estimate is unusable.
        next_vp = list(best_heading_for_vp.keys())[0]
        Helper.rotate_to_target_heading_mov2vp(
            sim, best_heading_for_vp[next_vp], next_vp
        )
        print(f"[Move] {cur_vp} -> {next_vp}")

        debugpy.breakpoint()
