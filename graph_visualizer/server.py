from __future__ import annotations

import json
import mimetypes
import subprocess
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from .loader import load_visualization_steps, resolve_project_root
from .viewer import render_viewer_html


@dataclass
class VisualizationServer:
    instance_name: str
    host: str
    port: int
    project_root: Path
    httpd: ThreadingHTTPServer
    thread: threading.Thread

    @property
    def url(self) -> str:
        return "http://%s:%d/" % (self.host, self.port)

    def shutdown(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5.0)


def _open_windows_browser(url: str) -> None:
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", "Start-Process", url],
        check=True,
    )


def visualize_instance(
    instance_name: str,
    project_root: str | Path | None = None,
    host: str = "127.0.0.1",
    port: int = 0,
) -> VisualizationServer:
    return start_visualizer_server(
        instance_name=instance_name,
        project_root=project_root,
        host=host,
        port=port,
        open_browser=True,
    )


def start_visualizer_server(
    instance_name: str,
    project_root: str | Path | None = None,
    host: str = "127.0.0.1",
    port: int = 0,
    open_browser: bool = False,
) -> VisualizationServer:
    root = resolve_project_root(project_root)
    steps = load_visualization_steps(instance_name=instance_name, project_root=root)
    payload = {
        "instance_name": str(instance_name),
        "steps": steps,
    }
    html_bytes = render_viewer_html().encode("utf-8")

    class VisualizerRequestHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self._send_bytes(html_bytes, "text/html; charset=utf-8")
            elif parsed.path == "/api/steps":
                payload_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
                self._send_bytes(payload_bytes, "application/json; charset=utf-8")
            elif parsed.path.startswith("/assets/"):
                asset_path = root / unquote(parsed.path[len("/assets/") :])
                media_type = mimetypes.guess_type(str(asset_path))[0]
                self._send_bytes(
                    asset_path.read_bytes(),
                    media_type or "application/octet-stream",
                )
            else:
                self.send_error(404)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path not in ("/api/layout-position", "/api/layout-positions"):
                self.send_error(404)
                return
            content_length = int(self.headers["Content-Length"])
            body = self.rfile.read(content_length)
            update = json.loads(body.decode("utf-8"))
            if parsed.path == "/api/layout-position":
                _save_layout_position(
                    project_root=root,
                    instance_name=str(instance_name),
                    payload=payload,
                    step_index=int(update["step_index"]),
                    node_id=int(update["node_id"]),
                    x=float(update["x"]),
                    y=float(update["y"]),
                )
            else:
                _save_layout_positions(
                    project_root=root,
                    instance_name=str(instance_name),
                    payload=payload,
                    step_index=int(update["step_index"]),
                    positions=update["positions"],
                )
            self._send_bytes(b"{}", "application/json; charset=utf-8")

        def log_message(self, format: str, *args: object) -> None:
            return

        def _send_bytes(self, content: bytes, content_type: str) -> None:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

    httpd = ThreadingHTTPServer((host, int(port)), VisualizerRequestHandler)
    actual_port = int(httpd.server_address[1])
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    server = VisualizationServer(
        instance_name=str(instance_name),
        host=host,
        port=actual_port,
        project_root=root,
        httpd=httpd,
        thread=thread,
    )
    if open_browser:
        _open_windows_browser(server.url)
    return server


def _save_layout_position(
    project_root: Path,
    instance_name: str,
    payload: dict[str, object],
    step_index: int,
    node_id: int,
    x: float,
    y: float,
) -> None:
    _save_layout_positions(
        project_root=project_root,
        instance_name=instance_name,
        payload=payload,
        step_index=step_index,
        positions=[
            {
                "node_id": node_id,
                "x": x,
                "y": y,
            }
        ],
    )


def _save_layout_positions(
    project_root: Path,
    instance_name: str,
    payload: dict[str, object],
    step_index: int,
    positions: list[dict[str, object]],
) -> None:
    debug_dir = project_root / "mllm_debug_outputs" / str(instance_name)
    layout_path = debug_dir / ("graph_layout_step_%04d.json" % int(step_index))
    layout = json.loads(layout_path.read_text(encoding="utf-8"))
    position_by_node_id = {
        int(position["node_id"]): position
        for position in positions
    }
    for node in layout["nodes"]:
        position = position_by_node_id.get(int(node["id"]))
        if position is not None:
            node["x"] = float(position["x"])
            node["y"] = float(position["y"])
    layout_path.write_text(
        json.dumps(layout, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    for step in payload["steps"]:
        if int(step["step_index"]) == int(step_index):
            step["layout"] = layout
            break
