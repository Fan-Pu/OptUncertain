import Helper

if __name__ == "__main__":
    sim = Helper.init_render()
    sim.initialize()

    scan_id = "17DRP5sb8fy"
    start_vp_id = "00ebbf3782c64d74aaf7dd39cd561175"
    Helper.build_viewpoint_index(scan_id)
    sim.newEpisode([scan_id], [start_vp_id], [0.0], [0.0])

    print("Explore mode: Use arrow keys to navigate. Ctrl+C to exit.")
    Helper.explore_world(sim)
