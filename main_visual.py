from doctest import debug
import time

from graph_visualizer import visualize_instance


def main():
    server = visualize_instance("test2")
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
