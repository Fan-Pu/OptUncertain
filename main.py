import os
import debugpy
import math
import Helper
import numpy as np

from semantic_persistence.clip_encoder import CLIPTextEmbedder, CLIPImageEmbedder
from semantic_persistence.vpbank_manager import get_or_create_vp_bank


if __name__ == "__main__":
    # -------------------- Debugger --------------------
    debugpy.listen(("0.0.0.0", 5678))
    print("debugpy listening on 5678, waiting...")
    debugpy.wait_for_client()
    print("debugger attached, continuing...")

    # -------------------- Simulator --------------------
    sim = Helper.init_render()
    sim.initialize()

    debugpy.breakpoint()  # set breakpoint here to inspect sim, e.g. sim.getState()

    scan_id = "17DRP5sb8fy"
    start_vp_id = "10c252c90fa24ef3b698c6f54d984c5c"
    sim.newEpisode([scan_id], [start_vp_id], [0.0], [0.0])

    # -------------------- encoders (GPU) --------------------
    MODEL_DIR = os.path.join("models", "clip-vit-base-patch32")
    text_embedder = CLIPTextEmbedder(model_id=MODEL_DIR, local_files_only=True)
    image_embedder = CLIPImageEmbedder(model_id=MODEL_DIR, local_files_only=True)

    # -------------------- VP bank (auto-build if missing) --------------------
    # Bank will be stored under: ./vpbanks/<scan_id>_vpbank.npz
    # If missing, we build it using Matterport rendering + SigLIP image encoder.
    # Your container already sets dataset/connectivity using MP_ROOT.

    MP_ROOT = "/root/mount/Matterport3DSimulator"  # repo root inside container
    dataset_path = os.path.join(MP_ROOT, "data/v1/scans")
    connectivity_dir = os.path.join(MP_ROOT, "connectivity")

    vp_bank = get_or_create_vp_bank(
        scan_id=scan_id,
        vpbanks_dir="vpbanks",
        bank_filename=f"{scan_id}_vpbank.npz",
        dataset_path=dataset_path,
        connectivity_dir=connectivity_dir,
        image_embedder=image_embedder,
        num_views=12,
        elevation_degrees=0.0,
        image_width=640,
        image_height=480,
        vfov_degrees=60.0,
    )

    debugpy.breakpoint()  # set breakpoint here to inspect vp_bank, text_embedder, etc.

    # -------------------- Goal --------------------
    # Replace with your target query.
    goal_text = "television"

    # -------------------- Render initial state --------------------
    initial_state = sim.getState()[0]
    Helper.render_sim_state(initial_state)
    initial_heading = initial_state.heading
    print(f"Initial heading: {math.degrees(initial_heading):.2f} degrees")

    while True:
        # Full horizon scan with integrated target check
        (
            best_heading_for_vp,
            _,
            target_found,
            target_heading,
            target_distance,
        ) = Helper.horizon_scan_return(
            sim,
            goal_text=goal_text,
            text_embedder=text_embedder,
            image_embedder=image_embedder,
            similarity_threshold=0.25,
            distance_threshold=1.5,
        )

        if target_found:
            # Rotate and no move since we're already at the target VP
            Helper.rotate_to_target_heading_mov2vp(sim, target_heading, None)
            print(
                f"✓✓✓ SUCCESS: Target '{goal_text}' has been reached ({target_distance:.2f} meters away) ! ✓✓✓"
            )
            break
        if not best_heading_for_vp:
            print("No navigable neighbors found. Stopping.")
            break

        # Choose next viewpoint using retrieval score (no randomness)
        candidate_vps = list(best_heading_for_vp.keys())
        target_vp_id, score = Helper.select_next_viewpoint_by_retrieval(
            candidate_vps=candidate_vps,
            goal_text=goal_text,
            vp_bank=vp_bank,
            text_embedder=text_embedder,
        )
        target_heading = best_heading_for_vp[target_vp_id]
        print(f"Selected next vp: {target_vp_id}, retrieval score={score:.3f}")

        # Rotate and move
        Helper.rotate_to_target_heading_mov2vp(sim, target_heading, target_vp_id)
