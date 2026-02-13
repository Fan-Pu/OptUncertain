import MatterSim
import os
import debugpy
import time
import math
import Helper
from collections import defaultdict
import random

if __name__ == "__main__":
    random.seed(42)
    pause_time = 1.0
    debugpy.listen(("0.0.0.0", 5678))
    print("debugpy listening on 5678, waiting...")
    debugpy.wait_for_client()
    print("debugger attached, continuing...")

    sim = Helper.init_render()

    sim.initialize()
    scan_id = "17DRP5sb8fy"
    vp_ids = Helper.get_viewpoints(scan_id)
    # debugpy.breakpoint()
    vp_id = "10c252c90fa24ef3b698c6f54d984c5c"
    sim.newEpisode([scan_id], [vp_id], [0.0], [0.0])

    heading = 0
    elevation = 0  # this cannot be changed
    location = 0
    ANGLEDELTA = 5 * math.pi / 180
    scan_dict = defaultdict(list)  # key: viewpointId; value: heading_idx
    heading_list = [i for i in range(12, 24)]
    sim.makeAction([location], [heading], [elevation])
    Helper.render_sim_state(sim.getState()[0])

    while True:
        time.sleep(pause_time)
        scan_dict.clear()
        # scan horizontally
        for i in heading_list:
            sim.makeAction([location], [1], [elevation])
            state = sim.getState()[0]  # current state
            locations = state.navigableLocations
            for idx, loc in enumerate(locations[1:]):
                scan_dict[loc.viewpointId].append(i)
        # randomly choose a viewpoint
        selected_viewpointId = random.choice(list(scan_dict.keys()))
        selected_heading_id = scan_dict[selected_viewpointId][0]
        # smoothly move to the selected state
        for i in range(12, selected_heading_id + 1):
            time.sleep(pause_time)
            sim.makeAction([location], [1], [elevation])
            state = sim.getState()[0]  # current state
            Helper.render_sim_state(state)
        locations = sim.getState()[0].navigableLocations
        location_id = [
            i for i, x in enumerate(locations) if x.viewpointId == selected_viewpointId
        ][0]
        time.sleep(1.5)
        sim.makeAction([location_id], [0], [elevation])
        Helper.render_sim_state(sim.getState()[0])
        # debugpy.breakpoint()

    debugpy.breakpoint()
    test = sim.getState()[0]

    print("done")
    sdas = 0
