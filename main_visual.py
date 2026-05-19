import argparse
import time

from graph_visualizer import visualize_instance


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Visualize a saved test case."
    )
    parser.add_argument("test_case", help="Test case name, such as test1.")
    args = parser.parse_args(argv)

    server = visualize_instance(args.test_case)
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
