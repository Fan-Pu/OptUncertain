import os
import time
import debugpy
import math
import Helper
import numpy as np
import cv2
from semantic_persistence.clip_encoder import CLIPTextEmbedder, CLIPImageEmbedder
from semantic_persistence.vpbank_manager import get_or_create_vp_bank
from semantic_persistence.grounding import RetrievalGrounder
from semantic_persistence.nav_graph import (
    load_nav_graph,
    shortest_path_next_hop,
    argmin_distance_to_set,
)
from semantic_persistence.mllm_client import LocalQwen2VLClient
import semantic_persistence.owl_detect_distance as owl

Explore_mode = (
    False  # Set to True to enable manual exploration mode (use arrow keys to navigate)
)


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
        exit(0)

    # -------------------- Encoders (GPU) --------------------
    MODEL_DIR = os.path.join("models", "clip-vit-base-patch32")
    text_embedder = CLIPTextEmbedder(model_id=MODEL_DIR, local_files_only=True)
    image_embedder = CLIPImageEmbedder(model_id=MODEL_DIR, local_files_only=True)

    # -------------------- Matterport paths --------------------
    MP_ROOT = "/root/mount/Matterport3DSimulator"  # repo root inside container
    dataset_path = os.path.join(MP_ROOT, "data/v1/scans")
    connectivity_dir = os.path.join(MP_ROOT, "connectivity")

    # -------------------- VP bank (offline cache) --------------------
    # Bank stored under: ./vpbanks/<scan_id>_vpbank.npz.
    # VP bank contains pre-embedded RGB observations (vp_view_embs) for each viewpoint + camera xyz coordinates (vp_xyz).
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

    # -------------------- Connectivity graph --------------------
    # adjacency is a dict: {vp_id: List[neighbor_vp_id]}.
    adjacency = load_nav_graph(connectivity_dir=connectivity_dir, scan_id=scan_id)

    # -------------------- MLLM + Grounder --------------------
    mllm = LocalQwen2VLClient(model_name="Qwen/Qwen2-VL-2B-Instruct", h_fov=Helper.HFOV)
    grounder = RetrievalGrounder(
        text_embedder=text_embedder, topk=12, score_threshold=None
    )

    # -------------------- OWL-ViT target deterctor --------------------
    owl_detector = owl.OwlDetector(device="cuda")

    # -------------------- Task --------------------
    # For paper alignment: instruction goes to MLLM; grounding maps semantic regions to viewpoint sets.
    # Single source of truth for the target object in this run
    target_object = os.environ.get("TARGET_OBJECT", "television").strip()
    # Instruction used by the MLLM proposer (kept consistent with local target check)
    instruction = f"Find the {target_object}."

    # -------------------- Loop --------------------
    while True:
        state = sim.getState()[0]
        cur_vp = state.location.viewpointId

        # Render and show current observation
        Helper.render_sim_state(state)

        # 1) Check if target is reachable at current viewpoint (fast local check)
        (
            best_heading_for_vp,
            _,
            target_found,
            target_heading,
            target_distance,
            horizon_rgb_images,
        ) = Helper.horizon_scan_return(
            sim,
            goal_text=target_object,
            text_embedder=text_embedder,
            image_embedder=image_embedder,
            owl_detector=owl_detector,
        )

        if target_found:
            Helper.rotate_to_target_heading_mov2vp(sim, target_heading, None)
            print(
                f"✓✓✓ SUCCESS: Target reached ({target_distance:.2f} meters away) ✓✓✓"
            )
            break

        # 2) MLLM proposes semantic regions (based on partial observation + instruction)
        # Use the full 360 horizontal scan (all headings) as MLLM visual context.
        # Note: this can be many images (HORIZON_LEN). If you hit API limits, downsample horizon_rgb_images.
        if horizon_rgb_images:
            cv2.imshow("MLLM RGB", horizon_rgb_images[0])
            cv2.waitKey(1)

        start_time = time.perf_counter()
        # Call local Qwen2-VL (returns: list[{"label","confidence","type"}])
        mllm_out = mllm.propose_semantic_nodes(
            observation_images=horizon_rgb_images,
            topk=5,
        )
        runtime = time.perf_counter() - start_time
        print(f"[MLLM] Propose semantic nodes runtime: {runtime:.2f} seconds")

        # mllm_out is a LIST
        if not isinstance(mllm_out, list) or len(mllm_out) == 0:
            print(
                "[WARN] No semantic regions returned by MLLM. Falling back to greedy neighbor selection."
            )
            if not best_heading_for_vp:
                print("No navigable neighbors. Stop.")
                break
            next_vp_id = list(best_heading_for_vp.keys())[0]
            Helper.rotate_to_target_heading_mov2vp(
                sim, best_heading_for_vp[next_vp_id], next_vp_id
            )
            continue

        # sort by confidence (descending)
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
                int(x)
                for x in support_views
                if isinstance(x, (int, float, str)) and str(x).lstrip("-").isdigit()
            ]
        else:
            support_views = None

        try:
            num_obs_images = int(num_obs_images) if num_obs_images is not None else None
        except Exception:
            num_obs_images = None
        print(
            f"[MLLM] Top semantic region: {semantic_label} (confidence={top_conf:.2f})"
        )

        if support_views is not None and num_obs_images is not None:
            print(
                f"[MLLM] support_views={support_views} over num_obs_images={num_obs_images}"
            )

        if not semantic_label:
            print(
                "[WARN] Empty label from MLLM. Falling back to greedy neighbor selection."
            )
            if not best_heading_for_vp:
                print("No navigable neighbors. Stop.")
                break
            next_vp_id = list(best_heading_for_vp.keys())[0]
            Helper.rotate_to_target_heading_mov2vp(
                sim, best_heading_for_vp[next_vp_id], next_vp_id
            )
            continue

        debugpy.breakpoint()  # inspect mllm_out and semantic_label here if you want

        # 3) Ground semantic label to viewpoint set Omega_s over the full known graph
        omega, scores = grounder.ground(vp_bank=vp_bank, text=semantic_label)
        if not omega:
            print(
                "[WARN] Grounding returned empty Omega. Using greedy neighbor selection."
            )
            if not best_heading_for_vp:
                print("No navigable neighbors. Stop.")
                break
            next_vp_id = list(best_heading_for_vp.keys())[0]
            Helper.rotate_to_target_heading_mov2vp(
                sim, best_heading_for_vp[next_vp_id], next_vp_id
            )
            continue

        # Pick a target viewpoint inside Omega (best retrieval score)
        target_vp = max(omega, key=lambda vp: scores.get(vp, -1e9))

        # Optionally, pick the closest member of Omega by graph distance (more stable)
        closest_vp, hop_d = argmin_distance_to_set(
            adjacency, start_vp=cur_vp, target_set=set(omega)
        )
        if closest_vp is not None:
            target_vp = closest_vp
        print(
            f"[Grounding] |Omega|={len(omega)}; chosen target_vp={target_vp}; hop_d={hop_d}"
        )

        # 4) Move one step toward target_vp using the known connectivity graph
        next_hop = shortest_path_next_hop(adjacency, start_vp=cur_vp, goal_vp=target_vp)
        if next_hop is None:
            print(
                "[WARN] Target unreachable or already here. Picking another proposal next step."
            )
            continue

        # Compute heading needed to face next_hop (use current state's navigableLocations)
        locs = state.navigableLocations
        rel_heading = None
        for loc in locs:
            if loc.viewpointId == next_hop:
                rel_heading = float(loc.rel_heading)
                break

        if rel_heading is None:
            # Should be rare: nav graph and simulator disagree
            print(
                "[WARN] next_hop not in navigableLocations. Falling back to horizon scan."
            )
            best_heading_for_vp, _, _, _, _ = Helper.horizon_scan_return(
                sim,
                goal_text=target_object,
                text_embedder=text_embedder,
                image_embedder=image_embedder,
            )
            if not best_heading_for_vp:
                break
            next_vp_id = list(best_heading_for_vp.keys())[0]
            Helper.rotate_to_target_heading_mov2vp(
                sim, best_heading_for_vp[next_vp_id], next_vp_id
            )
            continue

        # Rotate toward next hop and move
        Helper.rotate_to_target_heading_mov2vp(sim, rel_heading, next_hop)
        print(f"[Move] {cur_vp} -> {next_hop}")
