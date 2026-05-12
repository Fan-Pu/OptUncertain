import json
import subprocess
import unittest
from unittest.mock import patch
from urllib.request import urlopen

from graph_visualizer import start_visualizer_server
from graph_visualizer.loader import load_visualization_steps
from graph_visualizer.viewer import render_viewer_html


class GraphVisualizerTest(unittest.TestCase):
    def test_loader_discovers_test1_steps(self):
        steps = load_visualization_steps("test1")

        self.assertEqual([step["step_index"] for step in steps], [0, 1, 2, 3])

    def test_loader_combines_step_payload(self):
        step = load_visualization_steps("test1")[0]

        self.assertIn("layout", step)
        self.assertIn("hypothesis", step)
        self.assertIn("semantic", step)
        self.assertIn("detection", step)
        self.assertIn("user_message", step)
        self.assertIn("observation_images", step)
        self.assertEqual(step["layout"]["observation_step"], 1)
        self.assertEqual(step["hypothesis"]["observation_step"], 1)
        self.assertGreater(len(step["semantic"]["visible_region_nodes"]), 0)
        self.assertGreater(len(step["detection"]["detections"]), 0)
        self.assertGreater(len(step["user_message"]), 0)
        self.assertEqual(
            sorted(image["agent_id"] for image in step["observation_images"]),
            ["agent0", "agent1"],
        )

    def test_server_serves_html_and_steps(self):
        server = start_visualizer_server("test1", open_browser=False)
        try:
            with urlopen(server.url, timeout=5) as response:
                html = response.read().decode("utf-8")
            with urlopen(server.url + "api/steps", timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
        finally:
            server.shutdown()

        self.assertIn("Graph Hypothesis Visualizer", html)
        self.assertEqual(payload["instance_name"], "test1")
        self.assertEqual(len(payload["steps"]), 4)

    def test_server_opens_windows_browser_when_requested(self):
        server = None
        with patch("graph_visualizer.server.subprocess.run") as run:
            server = start_visualizer_server("test1", open_browser=True)

            run.assert_called_once_with(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-Command",
                    "Start-Process",
                    server.url,
                ],
                check=True,
            )
        server.shutdown()

    def test_server_raises_when_windows_browser_open_fails(self):
        with patch("graph_visualizer.server.subprocess.run") as run:
            run.side_effect = subprocess.CalledProcessError(
                returncode=1,
                cmd=["powershell.exe"],
            )

            with self.assertRaises(subprocess.CalledProcessError):
                start_visualizer_server("test1", open_browser=True)

    def test_viewer_has_step_controls(self):
        html = render_viewer_html()

        self.assertIn("Previous", html)
        self.assertIn("Next", html)
        self.assertIn("stepLabel", html)


if __name__ == "__main__":
    unittest.main()
