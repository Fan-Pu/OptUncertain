import os
import time
import debugpy
import random

import Helper
import numpy as np
import cv2

from semantic_persistence.clip_encoder import CLIPTextEmbedder, CLIPImageEmbedder
from semantic_persistence.mllm_client import LocalQwen2VLClient
from semantic_persistence.utils import cosine_sim
import semantic_persistence.owl_detect_distance as owl


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

    # -------------------- Encoders (GPU) --------------------
    MODEL_DIR = os.path.join("models", "clip-vit-base-patch32")
    text_embedder = CLIPTextEmbedder(model_id=MODEL_DIR, local_files_only=True)
    image_embedder = CLIPImageEmbedder(model_id=MODEL_DIR, local_files_only=True)

    # -------------------- MLLM --------------------
    mllm = LocalQwen2VLClient(model_name="Qwen/Qwen2-VL-2B-Instruct", h_fov=Helper.HFOV)

    # -------------------- OWL-ViT target detector --------------------
    owl_detector = owl.OwlDetector(device="cuda")

    # -------------------- Task --------------------
    target_object = os.environ.get("TARGET_OBJECT", "television").strip()

    # -------------------- Loop --------------------
    while True:
        state = sim.getState()[0]
        cur_vp = state.location.viewpointId

        # Render current observation
        Helper.render_sim_state(state)

        # 1) Panoramic scan at the current viewpoint.
        #    This yields:
        #      - local moveable neighbors (observed nodes): keys of best_heading_for_vp
        #      - horizon_images: RGB frames used as MLLM context
        (
            best_heading_for_vp,
            _,
            target_found,
            target_heading,
            target_distance,
            target_box,
            horizon_rgb_images,
            horizon_headings,
        ) = Helper.horizon_scan_return(
            sim,
            goal_text=target_object,
            owl_detector=owl_detector,
            enable_target_check=True,
            distance_threshold=10,
        )

        # If the target is reachable from the current viewpoint, finish.
        if target_found:
            Helper.rotate_to_target_heading_mov2vp(sim, target_heading, None)
            rgb = np.array(sim.getState()[0].rgb, copy=True)
            Helper.put_detect_box(rgb, target_box, target_object, target_distance)
            cv2.imshow("MLLM RGB", rgb)
            cv2.waitKey(1)
            print(
                f"✓✓✓ SUCCESS: Target reached ({target_distance:.2f} meters away) ✓✓✓"
            )
            debugpy.breakpoint()
            break

        # If there are no moveable neighbors, stop.
        if not best_heading_for_vp:
            print("[STOP] No navigable neighbors returned by the scan.")
            break

        # 2) MLLM proposes region labels based on the *current* panoramic observation only.
        #    We do NOT assume access to the full set of viewpoints in the scan.
        # if horizon_rgb_images:
        #     cv2.imshow("MLLM RGB", horizon_rgb_images[0])
        #     cv2.waitKey(1)

        start_time = time.perf_counter()
        mllm_out = mllm.propose_semantic_nodes(
            observation_images=horizon_rgb_images, topk=5
        )
        runtime = time.perf_counter() - start_time
        print(f"[MLLM] runtime: {runtime:.2f} seconds")

        if not isinstance(mllm_out, list) or len(mllm_out) == 0:
            print(
                "[WARN] MLLM returned no regions. Falling back to greedy first neighbor."
            )
            next_vp = list(best_heading_for_vp.keys())[0]
            Helper.rotate_to_target_heading_mov2vp(
                sim, best_heading_for_vp[next_vp], next_vp
            )
            print(f"[Move] {cur_vp} -> {next_vp}")
            continue

        # Sort by confidence
        mllm_out = sorted(
            mllm_out, key=lambda x: float(x.get("confidence", 0.0)), reverse=True
        )

        top = mllm_out[0]
        semantic_label = str(top.get("label", "")).strip()
        top_conf = float(top.get("confidence", 0.0))
        support_views = top.get("support_views", None)
        num_obs_images = top.get("num_obs_images", None)

        if isinstance(support_views, list):
            support_views = [
                int(x) for x in support_views if str(x).lstrip("-").isdigit()
            ]
        else:
            support_views = None
        try:
            num_obs_images = int(num_obs_images) if num_obs_images is not None else None
        except Exception:
            num_obs_images = None

        print(f"[MLLM] Top region: {semantic_label} (confidence={top_conf:.2f})")
        if support_views is not None and num_obs_images is not None:
            print(
                f"[MLLM] support_views={support_views} over num_obs_images={num_obs_images}"
            )

        if not semantic_label:
            print("[WARN] Empty label. Falling back to greedy first neighbor.")
            next_vp = list(best_heading_for_vp.keys())[0]
            Helper.rotate_to_target_heading_mov2vp(
                sim, best_heading_for_vp[next_vp], next_vp
            )
            print(f"[Move] {cur_vp} -> {next_vp}")
            continue

        # 3) Choose the next move among the *locally observable* neighbors only.
        #    We score each neighbor u using the horizon RGB image that best faces u,
        #    then compute CLIP similarity with the chosen semantic_label.
        best_next_vp = random.choice(list(best_heading_for_vp.keys()))

        print(f"[Select] next_vp={best_next_vp}")

        # 4) Execute one-step move (fully executable in MatterSim).
        Helper.rotate_to_target_heading_mov2vp(
            sim, best_heading_for_vp[best_next_vp], best_next_vp
        )
        print(f"[Move] {cur_vp} -> {best_next_vp}")

        debugpy.breakpoint()
