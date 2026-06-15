import Helper

if __name__ == "__main__":
    sim = Helper.init_render()
    sim.initialize()

    scan_id = "8194nk5LbLH"
    start_vp_id = "6c49579a5cd34df8acb7f790b74e9eae"
    Helper.build_viewpoint_index(scan_id)
    sim.newEpisode([scan_id], [start_vp_id], [0.0], [0.0])

    print("Explore mode: Use arrow keys to navigate. Ctrl+C to exit.")
    Helper.explore_world(sim)
