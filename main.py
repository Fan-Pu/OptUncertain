import os
import time
import debugpy

import Helper

from semantic_persistence.mllm_client import LocalQwen3VLClient


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
    mllm = LocalQwen3VLClient(model_name="Qwen/Qwen3-VL-4B-Instruct", h_fov=Helper.HFOV)

    # -------------------- Task --------------------
    target_object = os.environ.get("TARGET_OBJECT", "television").strip()

    # -------------------- Loop --------------------
    while True:
        state = sim.getState()[0]
        cur_vp = state.location.viewpointId

        Helper.render_sim_state(state)

        # 1) Panoramic scan at the current viewpoint.
        best_heading_for_vp, _, horizon_rgb_images, horizon_headings, horizon_depths = (
            Helper.horizon_scan_return(sim)
        )

        if not best_heading_for_vp:
            print("[STOP] No navigable neighbors returned by the scan.")
            break

        # 2) MLLM: (a) propose region labels AND (b) detect whether the target object
        #    appears in any of the horizon images, returning the image indices.
        start_time = time.perf_counter()
        mllm_out = mllm.propose_semantic_nodes(
            observation_images=horizon_rgb_images,
            topk=5,
            target_object=target_object,
        )
        runtime = time.perf_counter() - start_time
        print(f"[MLLM] runtime: {runtime:.2f} seconds")

        # 2a) If MLLM says the target is visible in some view, rotate to that view and stop.
        tgt = mllm_out.get("target", {}) if isinstance(mllm_out, dict) else {}
        tgt_found = bool(tgt.get("found", False))
        tgt_views = tgt.get("views", []) or []
        index_map = (
            mllm_out.get("index_map", list(range(len(horizon_headings))))
            if isinstance(mllm_out, dict)
            else list(range(len(horizon_headings)))
        )

        if tgt_found and isinstance(tgt_views, list) and len(tgt_views) > 0:
            # Choose the first supporting view and map it back to the original horizon index.
            try:
                v_idx = int(tgt_views[0])
            except Exception:
                v_idx = None

            if v_idx is not None and 0 <= v_idx < len(index_map):
                orig_idx = int(index_map[v_idx])
                orig_idx = max(0, min(orig_idx, len(horizon_headings) - 1))
                target_heading = float(horizon_headings[orig_idx])

                print(
                    f"✓ Target '{target_object}' detected by MLLM in view {v_idx} (orig={orig_idx})."
                )
                Helper.rotate_to_target_heading_mov2vp(sim, target_heading, None)
                Helper.render_sim_state(sim.getState()[0])
                debugpy.breakpoint()
                break

        # 3) Greedy navigation fallback when target is not detected.
        next_vp = list(best_heading_for_vp.keys())[0]
        Helper.rotate_to_target_heading_mov2vp(
            sim, best_heading_for_vp[next_vp], next_vp
        )
        print(f"[Move] {cur_vp} -> {next_vp}")

        debugpy.breakpoint()
