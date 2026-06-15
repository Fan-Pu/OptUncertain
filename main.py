import Helper

if __name__ == "__main__":
    sim = Helper.init_render()
    sim.initialize()

    scan_id = "JF19kD82Mey"
    start_vp_id = "96490c4da78240058d1f76a07ed95c9d"
    Helper.build_viewpoint_index(scan_id)
    sim.newEpisode([scan_id], [start_vp_id], [0.0], [0.0])

    print("Explore mode: Use arrow keys to navigate. Ctrl+C to exit.")
    Helper.explore_world(sim)
