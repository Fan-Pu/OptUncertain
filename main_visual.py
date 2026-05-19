import argparse
import time

from graph_visualizer import visualize_instance
from oracle_runner import run_oracle


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Visualize a saved test case or run its oracle solution."
    )
    parser.add_argument("test_case", help="Test case name, such as test1.")
    parser.add_argument(
        "--oracle",
        action="store_true",
        help="Run the perfect-knowledge oracle optimization.",
    )
    args = parser.parse_args(argv)

    if args.oracle:
        run_oracle(args.test_case)
        return 0

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
