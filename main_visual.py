import argparse
import time

from graph_visualizer import visualize_instance


def main(argv=None):
    parser = argparse.ArgumentParser(description="Visualize a saved test case.")
    parser.add_argument("test_case", help="Test case name, such as test1.")
    parser.add_argument(
        "--texture-output-size",
        type=int,
        default=1080,
        help="Maximum birdview texture dimension in pixels. Try 3600 or 4096 for more zoomable detail.",
    )
    parser.add_argument(
        "--texture-cut-z-offset",
        type=float,
        default=0.1,
        help="Birdview cut-plane height above viewpoint z in meters. Larger values include higher wall objects.",
    )
    parser.add_argument(
        "--texture-render-mode",
        choices=("multi_slice_composite", "single_cutaway"),
        default="multi_slice_composite",
        help="Birdview texture renderer. Use single_cutaway to restore the original one-cut render.",
    )
    parser.add_argument(
        "--texture-composite-max-z-offset",
        type=float,
        default=1.6,
        help="Maximum viewpoint-relative cut height for multi-slice compositing.",
    )
    parser.add_argument(
        "--texture-composite-slices",
        type=int,
        default=5,
        help="Number of cut planes to composite in multi-slice mode.",
    )
    args = parser.parse_args(argv)

    server = visualize_instance(
        args.test_case,
        texture_output_size=args.texture_output_size,
        texture_cut_z_offset=args.texture_cut_z_offset,
        texture_render_mode=args.texture_render_mode,
        texture_composite_max_z_offset=args.texture_composite_max_z_offset,
        texture_composite_slices=args.texture_composite_slices,
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
