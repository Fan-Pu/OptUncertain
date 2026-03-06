import os
import time
import debugpy
import random
import math

import Helper
import numpy as np
import cv2

from semantic_persistence.mllm_client import LocalQwen2VLClient


Explore_mode = False  # True: manual keyboard control


def _angle_diff_rad(a: float, b: float) -> float:
    """Smallest absolute difference between two angles (radians)."""
    d = (a - b + math.pi) % (2.0 * math.pi) - math.pi
    return abs(d)


def _closest_view_index(horizon_headings: list[float], target_heading: float) -> int:
    best_i = 0
    best_d = float("inf")
    for i, h in enumerate(horizon_headings):
        d = _angle_diff_rad(h, target_heading)
        if d < best_d:
            best_d = d
            best_i = i
    return best_i


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

    # -------------------- Encoders (GPU) --------------------
    MODEL_DIR = os.path.join("models", "clip-vit-base-patch32")

    # -------------------- MLLM --------------------
    mllm = LocalQwen2VLClient(model_name="Qwen/Qwen2-VL-2B-Instruct", h_fov=Helper.HFOV)

    # -------------------- Task --------------------
    target_object = os.environ.get("TARGET_OBJECT", "television").strip()

    # -------------------- Loop --------------------
    while True:
        state = sim.getState()[0]
        cur_vp = state.location.viewpointId

        Helper.render_sim_state(state)

        # 1) Panoramic scan at the current viewpoint.
        best_heading_for_vp, _, horizon_rgb_images, horizon_headings = (
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

        # 3) Choose a region label (optional). If no region labels are returned, fall back.
        regions = mllm_out.get("regions", []) if isinstance(mllm_out, dict) else []
        if not isinstance(regions, list) or len(regions) == 0:
            print(
                "[WARN] MLLM returned no regions. Falling back to greedy first neighbor."
            )
            next_vp = list(best_heading_for_vp.keys())[0]
            Helper.rotate_to_target_heading_mov2vp(
                sim, best_heading_for_vp[next_vp], next_vp
            )
            print(f"[Move] {cur_vp} -> {next_vp}")
            continue

        regions = sorted(
            regions, key=lambda x: float(x.get("confidence", 0.0)), reverse=True
        )
        top = regions[0]
        semantic_label = str(top.get("label", "")).strip()
        top_conf = float(top.get("confidence", 0.0))
        print(f"[MLLM] Top region: {semantic_label} (confidence={top_conf:.2f})")

        if not semantic_label:
            print("[WARN] Empty label. Falling back to greedy first neighbor.")
            next_vp = list(best_heading_for_vp.keys())[0]
            Helper.rotate_to_target_heading_mov2vp(
                sim, best_heading_for_vp[next_vp], next_vp
            )
            print(f"[Move] {cur_vp} -> {next_vp}")
            continue

        debugpy.breakpoint()

        # 4) Score each locally observable neighbor using the view that best faces it,
        #    then compute CLIP similarity with semantic_label.
        text_emb = text_embedder.embed(semantic_label)

        best_next_vp = None

        print(f"[Select] next_vp={best_next_vp}")

        # 5) Execute one-step move (fully executable in MatterSim).
        Helper.rotate_to_target_heading_mov2vp(
            sim, best_heading_for_vp[best_next_vp], best_next_vp
        )
        print(f"[Move] {cur_vp} -> {best_next_vp}")

        debugpy.breakpoint()
