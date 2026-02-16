import os
import debugpy
import time
import math
import Helper
from collections import defaultdict
import random
from Helper import pause_time, decision_pause

if __name__ == "__main__":
    random.seed(42)

    debugpy.listen(("0.0.0.0", 5678))
    print("debugpy listening on 5678, waiting...")
    debugpy.wait_for_client()
    print("debugger attached, continuing...")

    sim = Helper.init_render()
    sim.initialize()

    scan_id = "17DRP5sb8fy"
    vp_id = "10c252c90fa24ef3b698c6f54d984c5c"
    sim.newEpisode([scan_id], [vp_id], [0.0], [0.0])

    # Render initial state
    initial_state = sim.getState()[0]
    Helper.render_sim_state(initial_state)
    initial_heading = initial_state.heading
    print(f"Initial heading: {math.degrees(initial_heading):.2f} degrees")

    while True:
        # Full horizon scan, record best heading for each candidate neighbor
        best_heading_for_vp, start_state = Helper.horizon_scan_return(sim)

        if not best_heading_for_vp:
            print("No navigable neighbors found. Stopping.")
            break

        # Randomly choose a neighbor viewpointId from 360-degree scan to move to
        target_vp_id = random.choice(list(best_heading_for_vp.keys()))
        target_heading = best_heading_for_vp[target_vp_id]

        # Rotate to where that neighbor was best visible and move to the target viewpoint with rendering
        Helper.rotate_to_target_heading_mov2vp(sim, target_heading, target_vp_id)
