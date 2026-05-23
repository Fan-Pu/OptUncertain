import argparse
import time

from graph_visualizer import visualize_instance


def main(argv=None):
    parser = argparse.ArgumentParser(description="Visualize a saved test case.")
    parser.add_argument("test_case", help="Test case name, such as test1.")
    parser.add_argument(
        "--texture-output-size",
        type=int,
        default=4096 * 2,
        help="Maximum birdview texture dimension in pixels. Try 3600 or 4096 for more zoomable detail.",
    )
    parser.add_argument(
        "--texture-cut-z-offset",
        type=float,
        default=0.3,
        help="Birdview cut-plane height above viewpoint z in meters. Larger values include higher wall objects.",
    )
    args = parser.parse_args(argv)

    server = visualize_instance(
        args.test_case,
        texture_output_size=args.texture_output_size,
        texture_cut_z_offset=args.texture_cut_z_offset,
    )
    print("Visualizer running at %s" % server.url)
    print("Press Ctrl+C to stop.")
    try:
        while server.thread.is_alive():
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("\nStopping visualizer.")
        server.shutdown()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
