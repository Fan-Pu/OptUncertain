from __future__ import annotations

import json
import mimetypes
import subprocess
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from .loader import load_solution_payload, load_visualization_steps, resolve_project_root
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
    texture_output_size: int = 1800,
    texture_cut_z_offset: float = 0.15,
    texture_render_mode: str = "multi_slice_composite",
    texture_composite_max_z_offset: float = 1.6,
    texture_composite_slices: int = 5,
) -> VisualizationServer:
    return start_visualizer_server(
        instance_name=instance_name,
        project_root=project_root,
        host=host,
        port=port,
        open_browser=True,
        texture_output_size=texture_output_size,
        texture_cut_z_offset=texture_cut_z_offset,
        texture_render_mode=texture_render_mode,
        texture_composite_max_z_offset=texture_composite_max_z_offset,
        texture_composite_slices=texture_composite_slices,
    )


def start_visualizer_server(
    instance_name: str,
    project_root: str | Path | None = None,
    host: str = "127.0.0.1",
    port: int = 0,
    open_browser: bool = False,
    texture_output_size: int = 1800,
    texture_cut_z_offset: float = 0.15,
    texture_render_mode: str = "multi_slice_composite",
    texture_composite_max_z_offset: float = 1.6,
    texture_composite_slices: int = 5,
) -> VisualizationServer:
    root = resolve_project_root(project_root)
    steps = load_visualization_steps(instance_name=instance_name, project_root=root)
    payload = {
        "instance_name": str(instance_name),
        "steps": steps,
    }
    payload.update(
        load_solution_payload(
            instance_name=instance_name,
            project_root=root,
            texture_output_size=texture_output_size,
            texture_cut_z_offset=texture_cut_z_offset,
            texture_render_mode=texture_render_mode,
            texture_composite_max_z_offset=texture_composite_max_z_offset,
            texture_composite_slices=texture_composite_slices,
        )
    )
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
            if parsed.path == "/api/shutdown":
                self._send_bytes(b"{}", "application/json; charset=utf-8")
                threading.Thread(target=httpd.shutdown, daemon=True).start()
                return
            self.send_error(404)
            return

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

