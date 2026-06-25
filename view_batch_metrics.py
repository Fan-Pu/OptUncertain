from __future__ import annotations

import argparse
import html
import mimetypes
import subprocess
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse


FIGURE_FILES = [
    "method_comparison_task_metrics.png",
    "method_comparison_detection_metrics.png",
    "grouped_metrics_by_agent_target.png",
]

PDF_FILES = [
    "method_comparison_task_metrics.pdf",
    "method_comparison_detection_metrics.pdf",
    "grouped_metrics_by_agent_target.pdf",
]

CSV_FILES = [
    "method_metrics.csv",
    "group_metrics_by_agent_target.csv",
]


@dataclass(frozen=True)
class ViewerConfig:
    metrics_dir: Path
    host: str
    port: int
    open_browser: bool


def main() -> int:
    args = _parse_args()
    config = ViewerConfig(
        metrics_dir=_resolve_path(args.metrics_dir),
        host=str(args.host),
        port=int(args.port),
        open_browser=bool(args.open_browser),
    )
    _validate_metrics_dir(config.metrics_dir)
    _serve(config)
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Open an interactive browser viewer for batch metric figures."
    )
    parser.add_argument("--metrics-dir", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=0, type=int)
    browser_group = parser.add_mutually_exclusive_group()
    browser_group.add_argument(
        "--open-browser",
        dest="open_browser",
        action="store_true",
        help="Open the viewer URL in the default browser.",
    )
    browser_group.add_argument(
        "--no-open-browser",
        dest="open_browser",
        action="store_false",
        help="Start the server without opening a browser.",
    )
    parser.set_defaults(open_browser=False)
    return parser.parse_args()


def _resolve_path(path: str | Path) -> Path:
    path = Path(path)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()


def _validate_metrics_dir(metrics_dir: Path) -> None:
    if not metrics_dir.is_dir():
        raise FileNotFoundError(str(metrics_dir))
    for filename in [*FIGURE_FILES, *PDF_FILES, *CSV_FILES]:
        path = metrics_dir / filename
        if not path.is_file():
            raise FileNotFoundError(str(path))


def _serve(config: ViewerConfig) -> None:
    metrics_dir = config.metrics_dir
    html_bytes = _render_html(metrics_dir).encode("utf-8")
    allowed_files = set(FIGURE_FILES) | set(PDF_FILES) | set(CSV_FILES)

    class MetricsViewerHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self._send_bytes(html_bytes, "text/html; charset=utf-8")
                return
            if parsed.path.startswith("/assets/"):
                filename = Path(unquote(parsed.path[len("/assets/") :])).name
                if filename not in allowed_files:
                    self.send_error(404)
                    return
                asset_path = metrics_dir / filename
                content_type = mimetypes.guess_type(str(asset_path))[0]
                self._send_bytes(
                    asset_path.read_bytes(),
                    content_type or "application/octet-stream",
                )
                return
            self.send_error(404)

        def log_message(self, format: str, *args: object) -> None:
            return

        def _send_bytes(
            self,
            content: bytes,
            content_type: str,
            status: int = 200,
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

    httpd = ThreadingHTTPServer((config.host, config.port), MetricsViewerHandler)
    actual_port = int(httpd.server_address[1])
    url = "http://%s:%d/" % (config.host, actual_port)
    print("Serving batch metric viewer at %s" % url)
    print("Press Ctrl+C to stop the server.")
    if config.open_browser:
        _open_windows_browser(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        httpd.server_close()


def _open_windows_browser(url: str) -> None:
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", "Start-Process", url],
        check=True,
    )


def _render_html(metrics_dir: Path) -> str:
    figure_cards = "\n".join(
        _figure_card(
            figure_id="figure%d" % index,
            title=title,
            png=png,
            pdf=pdf,
        )
        for index, (title, png, pdf) in enumerate(
            [
                (
                    "Task Metrics",
                    "method_comparison_task_metrics.png",
                    "method_comparison_task_metrics.pdf",
                ),
                (
                    "Detection Metrics",
                    "method_comparison_detection_metrics.png",
                    "method_comparison_detection_metrics.pdf",
                ),
                (
                    "Grouped Metrics",
                    "grouped_metrics_by_agent_target.png",
                    "grouped_metrics_by_agent_target.pdf",
                ),
            ],
            start=1,
        )
    )
    csv_sections = "\n".join(
        _csv_section(title=title, filename=filename)
        for title, filename in [
            ("Method Metrics", "method_metrics.csv"),
            ("Grouped Metrics By Agent And Target", "group_metrics_by_agent_target.csv"),
        ]
    )
    escaped_metrics_dir = html.escape(str(metrics_dir))
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Batch Metric Viewer</title>
  <style>
    :root {
      --bg: #f6f7f9;
      --panel: #ffffff;
      --text: #172033;
      --muted: #5d6678;
      --border: #d6dbe5;
      --accent: #2f5f9f;
      --button: #eef2f7;
      --button-hover: #dfe7f2;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: Arial, Helvetica, sans-serif;
    }
    header {
      padding: 18px 24px;
      background: #ffffff;
      border-bottom: 1px solid var(--border);
      position: sticky;
      top: 0;
      z-index: 10;
    }
    h1 {
      margin: 0;
      font-size: 20px;
      font-weight: 650;
    }
    .subtitle {
      margin-top: 4px;
      color: var(--muted);
      font-size: 13px;
    }
    main {
      padding: 18px 24px 32px;
      max-width: 1440px;
      margin: 0 auto;
    }
    .figure-grid {
      display: grid;
      grid-template-columns: 1fr;
      gap: 18px;
    }
    .panel {
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 8px;
      overflow: hidden;
    }
    .panel-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 12px 14px;
      border-bottom: 1px solid var(--border);
    }
    h2 {
      margin: 0;
      font-size: 16px;
      font-weight: 650;
    }
    .tools {
      display: flex;
      align-items: center;
      gap: 6px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }
    button, .download-link {
      border: 1px solid var(--border);
      background: var(--button);
      color: var(--text);
      border-radius: 6px;
      padding: 6px 9px;
      font-size: 13px;
      line-height: 1;
      cursor: pointer;
      text-decoration: none;
      font-family: inherit;
    }
    button:hover, .download-link:hover {
      background: var(--button-hover);
    }
    .group-control {
      display: flex;
      align-items: center;
      gap: 6px;
      color: var(--muted);
      font-size: 13px;
    }
    .group-control select {
      border: 1px solid var(--border);
      background: #ffffff;
      color: var(--text);
      border-radius: 6px;
      padding: 5px 8px;
      font: inherit;
    }
    .viewer {
      height: min(68vh, 780px);
      min-height: 430px;
      position: relative;
      overflow: hidden;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 12px;
      background:
        linear-gradient(45deg, #f0f2f5 25%, transparent 25%),
        linear-gradient(-45deg, #f0f2f5 25%, transparent 25%),
        linear-gradient(45deg, transparent 75%, #f0f2f5 75%),
        linear-gradient(-45deg, transparent 75%, #f0f2f5 75%);
      background-size: 24px 24px;
      background-position: 0 0, 0 12px, 12px -12px, -12px 0;
    }
    .viewer img {
      display: block;
      max-width: 100%;
      max-height: 100%;
      object-fit: contain;
      user-select: none;
      -webkit-user-drag: none;
      box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.08);
      background: white;
    }
    .tables {
      margin-top: 18px;
      display: grid;
      grid-template-columns: 1fr;
      gap: 18px;
    }
    .table-wrap {
      overflow: auto;
      max-height: 440px;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }
    th, td {
      padding: 7px 9px;
      border-bottom: 1px solid var(--border);
      white-space: nowrap;
      text-align: right;
    }
    th:first-child, td:first-child {
      text-align: left;
      position: sticky;
      left: 0;
      background: var(--panel);
    }
    th {
      background: #f2f5f9;
      font-weight: 650;
      color: var(--text);
      position: sticky;
      top: 0;
      z-index: 1;
    }
    th:first-child {
      z-index: 2;
      background: #f2f5f9;
    }
    .group-row td {
      position: static;
      text-align: left;
      background: #e9eef6;
      color: var(--text);
      font-weight: 650;
      border-top: 2px solid #b9c5d6;
      border-bottom: 1px solid #b9c5d6;
    }
    .method-row td,
    .method-row td:first-child {
      background: var(--method-bg);
    }
    .path {
      font-family: Consolas, monospace;
    }
    @media (max-width: 760px) {
      main { padding: 12px; }
      header { padding: 14px 12px; }
      .panel-header {
        align-items: flex-start;
        flex-direction: column;
      }
      .tools { justify-content: flex-start; }
      .viewer {
        height: 58vh;
        min-height: 300px;
      }
    }
  </style>
</head>
<body>
  <header>
    <h1>Batch Metric Viewer</h1>
    <div class="subtitle">Serving <span class="path">""" + escaped_metrics_dir + """</span></div>
  </header>
  <main>
    <section class="figure-grid">
""" + figure_cards + """
    </section>
    <section class="tables">
""" + csv_sections + """
    </section>
  </main>
  <script>
    const HIDDEN_ORACLE_METRICS = new Set([
      "verified_success_rate",
      "progress",
      "team_ppl_total",
      "team_ppl_makespan"
    ]);
    const GROUPED_TABLE_STATE = {
      rows: null,
      groupMode: "agent"
    };

    async function loadCsvTable(tableId, url) {
      const response = await fetch(url);
      const text = await response.text();
      const rows = parseCsv(text);
      const target = document.getElementById(tableId);
      target.innerHTML = tableHtml(rows);
    }

    async function loadGroupedCsvTable(tableId, url) {
      const response = await fetch(url);
      const text = await response.text();
      const rows = parseCsv(text);
      GROUPED_TABLE_STATE.rows = rows;
      renderGroupedCsvTable(tableId);
      document.getElementById("groupModeSelect").addEventListener("change", event => {
        GROUPED_TABLE_STATE.groupMode = event.target.value;
        renderGroupedCsvTable(tableId);
      });
    }

    function renderGroupedCsvTable(tableId) {
      const target = document.getElementById(tableId);
      target.innerHTML = groupedTableHtml(
        GROUPED_TABLE_STATE.rows,
        GROUPED_TABLE_STATE.groupMode
      );
    }

    function parseCsv(text) {
      const rows = [];
      let row = [];
      let field = "";
      let quoted = false;
      for (let i = 0; i < text.length; i += 1) {
        const ch = text[i];
        if (quoted) {
          if (ch === '"' && text[i + 1] === '"') {
            field += '"';
            i += 1;
          } else if (ch === '"') {
            quoted = false;
          } else {
            field += ch;
          }
          continue;
        }
        if (ch === '"') {
          quoted = true;
        } else if (ch === ",") {
          row.push(field);
          field = "";
        } else if (ch === "\\n") {
          row.push(field);
          rows.push(row);
          row = [];
          field = "";
        } else if (ch !== "\\r") {
          field += ch;
        }
      }
      if (field.length || row.length) {
        row.push(field);
        rows.push(row);
      }
      return rows.filter(item => item.length && item.some(value => value.length));
    }

    function tableHtml(rows) {
      if (!rows.length) return "";
      const headers = rows[0];
      const bodyRows = rows.slice(1);
      return `
        <table>
          <thead><tr>${headers.map(item => `<th>${escapeHtml(item)}</th>`).join("")}</tr></thead>
          <tbody>
            ${bodyRows.map(row => dataRowHtml(headers, row)).join("")}
          </tbody>
        </table>
      `;
    }

    function groupedTableHtml(rows, groupMode) {
      if (!rows.length) return "";
      const headers = rows[0];
      const bodyRows = rows.slice(1);
      const indexByHeader = Object.fromEntries(headers.map((item, index) => [item, index]));
      const methodOrder = methodOrderByFirstAppearance(bodyRows, indexByHeader);
      const sortedRows = bodyRows.slice().sort(
        (a, b) => compareGroupedRows(a, b, indexByHeader, methodOrder, groupMode)
      );
      let currentKey = "";
      const rowHtml = [];
      for (const row of sortedRows) {
        const agentNumber = row[indexByHeader.agent_number];
        const targetNumber = row[indexByHeader.target_number];
        const key = groupMode === "agent" ? targetNumber : agentNumber;
        if (key !== currentKey) {
          currentKey = key;
          const groupLabel = groupMode === "agent"
            ? `Targets = ${escapeHtml(targetNumber)}`
            : `Agents = ${escapeHtml(agentNumber)}`;
          rowHtml.push(
            `<tr class="group-row"><td colspan="${headers.length}">${groupLabel}</td></tr>`
          );
        }
        rowHtml.push(dataRowHtml(headers, row, methodBackground(row[indexByHeader.method], methodOrder)));
      }
      return `
        <table>
          <thead><tr>${headers.map(item => `<th>${escapeHtml(item)}</th>`).join("")}</tr></thead>
          <tbody>
            ${rowHtml.join("")}
          </tbody>
        </table>
      `;
    }

    function compareGroupedRows(a, b, indexByHeader, methodOrder, groupMode) {
      const agentDifference = Number(a[indexByHeader.agent_number]) - Number(b[indexByHeader.agent_number]);
      const targetDifference = Number(a[indexByHeader.target_number]) - Number(b[indexByHeader.target_number]);
      if (groupMode === "agent") {
        if (targetDifference !== 0) return targetDifference;
        if (agentDifference !== 0) return agentDifference;
      } else {
        if (agentDifference !== 0) return agentDifference;
        if (targetDifference !== 0) return targetDifference;
      }
      return methodSortValue(a[indexByHeader.method], methodOrder) - methodSortValue(b[indexByHeader.method], methodOrder);
    }

    function methodOrderByFirstAppearance(rows, indexByHeader) {
      const order = new Map();
      for (const row of rows) {
        const method = row[indexByHeader.method];
        if (!order.has(method)) order.set(method, order.size);
      }
      return order;
    }

    function methodSortValue(method, methodOrder) {
      return { Oracle: -2, Proposed: -1 }[method] ?? methodOrder.get(method);
    }

    function methodBackground(method, methodOrder) {
      if (method === "Oracle") return "#eaf3ff";
      if (method === "Proposed") return "#fff2e4";
      const palette = ["#eef7ee", "#f4eef9", "#eef7f8", "#f8f3e8", "#f6eeee"];
      return palette[methodOrder.get(method) % palette.length];
    }

    function dataRowHtml(headers, row, methodBackgroundColor = "") {
      const style = methodBackgroundColor ? ` style="--method-bg: ${methodBackgroundColor}"` : "";
      const className = methodBackgroundColor ? ` class="method-row"` : "";
      const methodIndex = headers.indexOf("method");
      const isOracle = methodIndex >= 0 && row[methodIndex] === "Oracle";
      return `<tr${className}${style}>${headers.map((header, index) => {
        const value = isOracle && HIDDEN_ORACLE_METRICS.has(header) ? "" : row[index] || "";
        return `<td>${escapeHtml(value)}</td>`;
      }).join("")}</tr>`;
    }

    function escapeHtml(value) {
      return String(value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
    }

    loadCsvTable("methodMetricsTable", "/assets/method_metrics.csv");
    loadGroupedCsvTable("groupMetricsTable", "/assets/group_metrics_by_agent_target.csv");
  </script>
</body>
</html>
"""


def _figure_card(figure_id: str, title: str, png: str, pdf: str) -> str:
    escaped_figure_id = html.escape(figure_id)
    escaped_title = html.escape(title)
    escaped_png = html.escape(png)
    escaped_pdf = html.escape(pdf)
    return f"""      <article class="panel figure-panel">
        <div class="panel-header">
          <h2>{escaped_title}</h2>
          <div class="tools">
            <a class="download-link" href="/assets/{escaped_png}" download>PNG</a>
            <a class="download-link" href="/assets/{escaped_pdf}" download>PDF</a>
          </div>
        </div>
        <div id="{escaped_figure_id}" class="viewer">
          <img src="/assets/{escaped_png}" alt="{escaped_title}">
        </div>
      </article>"""


def _csv_section(title: str, filename: str) -> str:
    normalized_table_id = {
        "method_metrics.csv": "methodMetricsTable",
        "group_metrics_by_agent_target.csv": "groupMetricsTable",
    }[filename]
    escaped_title = html.escape(title)
    escaped_filename = html.escape(filename)
    escaped_table_id = html.escape(normalized_table_id)
    group_control = ""
    if filename == "group_metrics_by_agent_target.csv":
        group_control = """            <label class="group-control" for="groupModeSelect">
              Group control
              <select id="groupModeSelect">
                <option value="agent" selected>agent</option>
                <option value="target">target</option>
              </select>
            </label>
"""
    return f"""      <article class="panel">
        <div class="panel-header">
          <h2>{escaped_title}</h2>
          <div class="tools">
{group_control}\
            <a class="download-link" href="/assets/{escaped_filename}" download>CSV</a>
          </div>
        </div>
        <div id="{escaped_table_id}" class="table-wrap"></div>
      </article>"""


if __name__ == "__main__":
    raise SystemExit(main())
