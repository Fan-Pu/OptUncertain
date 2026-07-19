from __future__ import annotations

import argparse
import json
import math
import re
from collections import defaultdict
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


REFERENCE_HEIGHT = 560.0
BASE_EDGE_COLOR = "#c7ced8"
BASE_EDGE_WIDTH = 1.0
BASE_NODE_FILL = "#475467"
BASE_NODE_RADIUS = 4.0
BASE_NODE_STROKE = "#ffffff"
BASE_NODE_STROKE_WIDTH = 1.5
ROUTE_COLORS = ("#d62728", "#1f77b4", "#2ca02c")
ROUTE_LINE_WIDTH = 2.0
ROUTE_LINE_OPACITY = 0.78
ROUTE_LANE_SPACING = 5.0
ROUTE_STEP_RADIUS = 6.0
ROUTE_START_RADIUS = 8.0
ROUTE_MARKER_STROKE_WIDTH = 2.0
ROUTE_START_STROKE = "#111827"
TARGET_FILL = "#f2c300"
TARGET_STROKE = "#111827"
TARGET_STROKE_WIDTH = 1.5
TARGET_OUTER_RADIUS = 12.0
TARGET_INNER_RADIUS = 5.0
TARGET_LABEL_FONT_SIZE = 12.0


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render a saved VLFM-G solution in the graph visualizer route style."
    )
    parser.add_argument("--texture", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--connectivity", type=Path, required=True)
    parser.add_argument("--route-summary", type=Path, required=True)
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--detection-dir", type=Path, required=True)
    parser.add_argument("--episode-state-dir", type=Path, required=True)
    parser.add_argument("--font", type=Path, required=True)
    parser.add_argument("--output-image", type=Path, required=True)
    parser.add_argument("--output-details", type=Path, required=True)
    parser.add_argument("--texture-opacity", type=float, default=1.0)
    return parser.parse_args()


def centered_circle(
    draw: ImageDraw.ImageDraw,
    center: tuple[float, float],
    radius: float,
    fill: str,
    stroke: str,
    stroke_width: float,
) -> None:
    x, y = center
    half_stroke = stroke_width / 2.0
    outer_radius = radius + half_stroke
    inner_radius = radius - half_stroke
    draw.ellipse(
        (
            x - outer_radius,
            y - outer_radius,
            x + outer_radius,
            y + outer_radius,
        ),
        fill=stroke,
    )
    draw.ellipse(
        (
            x - inner_radius,
            y - inner_radius,
            x + inner_radius,
            y + inner_radius,
        ),
        fill=fill,
    )


def quadratic_points(
    start: tuple[float, float],
    control: tuple[float, float],
    end: tuple[float, float],
    sample_count: int = 64,
) -> list[tuple[float, float]]:
    points = []
    for sample_index in range(sample_count + 1):
        t = sample_index / sample_count
        one_minus_t = 1.0 - t
        points.append(
            (
                one_minus_t * one_minus_t * start[0]
                + 2.0 * one_minus_t * t * control[0]
                + t * t * end[0],
                one_minus_t * one_minus_t * start[1]
                + 2.0 * one_minus_t * t * control[1]
                + t * t * end[1],
            )
        )
    return points


def star_points(
    center: tuple[float, float], outer_radius: float, inner_radius: float
) -> list[tuple[float, float]]:
    cx, cy = center
    points = []
    for point_index in range(10):
        radius = outer_radius if point_index % 2 == 0 else inner_radius
        angle = -math.pi / 2.0 + point_index * math.pi / 5.0
        points.append(
            (cx + math.cos(angle) * radius, cy + math.sin(angle) * radius)
        )
    return points


def discovery_events(
    detection_dir: Path,
    episode_state_dir: Path,
    expected_target_nodes: dict[str, int],
) -> dict[str, dict[str, object]]:
    discoveries = {}
    detection_pattern = re.compile(r"detection_step_(\d{4})\.json$")
    for detection_path in sorted(detection_dir.glob("detection_step_*.json")):
        match = detection_pattern.fullmatch(detection_path.name)
        step_index = int(match.group(1))
        state = read_json(
            episode_state_dir / f"episode_state_step_{step_index:04d}.json"
        )
        agent_nodes = {
            str(agent_id): int(node_id)
            for agent_id, node_id in state["agent_current_vp_ids"].items()
        }
        for detection in read_json(detection_path)["detections"]:
            agent_id = str(detection["agent_id"])
            node_id = agent_nodes[agent_id]
            for target_id in detection["found_target_indices"]:
                target_id = str(target_id)
                if node_id != expected_target_nodes[target_id]:
                    raise ValueError(
                        f"Target {target_id} was detected at node {node_id}, but the "
                        f"route summary records node {expected_target_nodes[target_id]}."
                    )
                discoveries[target_id] = {
                    "step_index": step_index,
                    "agent_id": agent_id,
                    "node_id": node_id,
                }
    if set(discoveries) != set(expected_target_nodes):
        raise ValueError("Detection records do not cover every target in the route summary.")
    return discoveries


def route_edge_events(agents: list[dict]) -> list[dict[str, object]]:
    unique_events = {}
    for agent_index, agent in enumerate(agents):
        route = [int(node_id) for node_id in agent["route_node_ids"]]
        for route_index, (source, target) in enumerate(zip(route, route[1:])):
            if source == target:
                continue
            low, high = sorted((source, target))
            bundle_key = (low, high)
            event_key = (str(agent["agent_id"]), bundle_key)
            if event_key not in unique_events:
                unique_events[event_key] = {
                    "agent_id": str(agent["agent_id"]),
                    "agent_index": agent_index,
                    "route_index": route_index,
                    "route_indices": [],
                    "source_node_id": low,
                    "target_node_id": high,
                    "bundle_key": bundle_key,
                }
            unique_events[event_key]["route_indices"].append(route_index)

    bundles = defaultdict(list)
    for event in unique_events.values():
        bundles[event["bundle_key"]].append(event)

    assigned = []
    for events in bundles.values():
        events.sort(key=lambda event: (event["agent_index"], event["route_index"]))
        for lane_index, event in enumerate(events):
            event["lane_offset"] = (
                lane_index - (len(events) - 1) / 2.0
            ) * ROUTE_LANE_SPACING
            assigned.append(event)
    assigned.sort(key=lambda event: (event["agent_index"], event["route_index"]))
    return assigned


def render_figure(
    args: argparse.Namespace,
    summary: dict,
    target_descriptions: dict[str, str],
) -> None:
    texture = Image.open(args.texture).convert("RGB")
    metadata = read_json(args.metadata)
    connectivity = read_json(args.connectivity)
    expected_size = (int(metadata["width"]), int(metadata["height"]))
    if texture.size != expected_size:
        raise ValueError(
            f"Texture size {texture.size} does not match metadata size {expected_size}."
        )
    if not 0.0 <= args.texture_opacity <= 1.0:
        raise ValueError("--texture-opacity must be between 0 and 1.")

    width, height = texture.size
    style_scale = height / REFERENCE_HEIGHT
    min_x = float(metadata["min_x"])
    max_x = float(metadata["max_x"])
    min_y = float(metadata["min_y"])
    max_y = float(metadata["max_y"])

    white = Image.new("RGB", texture.size, "white")
    canvas = Image.blend(white, texture, args.texture_opacity).convert("RGBA")
    draw = ImageDraw.Draw(canvas)

    included = {
        index: record
        for index, record in enumerate(connectivity)
        if bool(record["included"])
    }

    def position(record: dict) -> tuple[float, float]:
        pose = record["pose"]
        x = (float(pose[3]) - min_x) / (max_x - min_x) * width
        y = (max_y - float(pose[7])) / (max_y - min_y) * height
        return x, y

    positions = {node_id: position(record) for node_id, record in included.items()}

    base_edge_width = round(BASE_EDGE_WIDTH * style_scale)
    for source_id, source in included.items():
        for target_id, target in included.items():
            if source_id >= target_id:
                continue
            if not bool(source["unobstructed"][target_id]):
                continue
            if not bool(target["unobstructed"][source_id]):
                continue
            draw.line(
                (positions[source_id], positions[target_id]),
                fill=BASE_EDGE_COLOR,
                width=base_edge_width,
            )

    for node_id in sorted(positions):
        centered_circle(
            draw,
            positions[node_id],
            BASE_NODE_RADIUS * style_scale,
            BASE_NODE_FILL,
            BASE_NODE_STROKE,
            BASE_NODE_STROKE_WIDTH * style_scale,
        )

    route_overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    route_draw = ImageDraw.Draw(route_overlay)
    route_line_width = round(ROUTE_LINE_WIDTH * style_scale)
    for event in route_edge_events(summary["agents"]):
        source = positions[event["source_node_id"]]
        target = positions[event["target_node_id"]]
        dx = target[0] - source[0]
        dy = target[1] - source[1]
        length = math.hypot(dx, dy)
        ux = dx / length
        uy = dy / length
        start_padding = (
            ROUTE_START_RADIUS
            if int(event["route_index"]) == 0
            else ROUTE_STEP_RADIUS
        ) * style_scale
        end_padding = 10.0 * style_scale
        start = (
            source[0] + ux * start_padding,
            source[1] + uy * start_padding,
        )
        end = (
            target[0] - ux * end_padding,
            target[1] - uy * end_padding,
        )
        midpoint = ((start[0] + end[0]) / 2.0, (start[1] + end[1]) / 2.0)
        normal = (-dy / length, dx / length)
        lane_offset = float(event["lane_offset"]) * style_scale
        control = (
            midpoint[0] + normal[0] * lane_offset,
            midpoint[1] + normal[1] * lane_offset,
        )
        color = ROUTE_COLORS[int(event["agent_index"])]
        rgba = tuple(Image.new("RGB", (1, 1), color).getpixel((0, 0))) + (
            round(255 * ROUTE_LINE_OPACITY),
        )
        route_draw.line(
            quadratic_points(start, control, end),
            fill=rgba,
            width=route_line_width,
            joint="curve",
        )
    canvas = Image.alpha_composite(canvas, route_overlay)
    draw = ImageDraw.Draw(canvas)

    for agent_index, agent in enumerate(summary["agents"]):
        color = ROUTE_COLORS[agent_index]
        for route_index, node_id in enumerate(agent["route_node_ids"]):
            is_start = route_index == 0
            centered_circle(
                draw,
                positions[int(node_id)],
                (ROUTE_START_RADIUS if is_start else ROUTE_STEP_RADIUS)
                * style_scale,
                color,
                ROUTE_START_STROKE if is_start else BASE_NODE_STROKE,
                ROUTE_MARKER_STROKE_WIDTH * style_scale,
            )

    targets_by_node = defaultdict(list)
    for target_id, node_id in summary["target_node_ids_by_target_id"].items():
        targets_by_node[int(node_id)].append(str(target_id))

    target_font = ImageFont.truetype(
        args.font, size=round(TARGET_LABEL_FONT_SIZE * style_scale)
    )
    for node_id in sorted(targets_by_node):
        center = positions[node_id]
        target_ids = sorted(targets_by_node[node_id], key=int)
        star = star_points(
            center,
            TARGET_OUTER_RADIUS * style_scale,
            TARGET_INNER_RADIUS * style_scale,
        )
        draw.polygon(star, fill=TARGET_FILL)
        draw.line(
            star + [star[0]],
            fill=TARGET_STROKE,
            width=round(TARGET_STROKE_WIDTH * style_scale),
            joint="curve",
        )
        label = ",".join(target_ids)
        draw.text(
            (
                center[0] + 12.0 * style_scale,
                center[1] - 10.0 * style_scale,
            ),
            label,
            font=target_font,
            fill=TARGET_STROKE,
            stroke_width=round(4.0 * style_scale),
            stroke_fill=BASE_NODE_STROKE,
            anchor="ls",
        )

    args.output_image.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(args.output_image, dpi=(300, 300), optimize=True)


def write_route_details(
    args: argparse.Namespace,
    summary: dict,
    connectivity: list[dict],
    target_descriptions: dict[str, str],
    discoveries: dict[str, dict[str, object]],
) -> None:
    lines = [
        "VLFM-G route details",
        "====================",
        f"Test case: {summary['test_case']}",
        "Result source: saved balanced-100 VLFM-G benchmark output",
        f"Status: {summary['status']}",
        f"Stop reason: {summary['stop_reason']}",
        f"Detection steps completed: {summary['steps_completed']}",
        f"Maximum allowed steps: {summary['max_steps']}",
        f"Total distance: {float(summary['total_distance']):.6f}",
        f"Maximum agent distance: {float(summary['maximum_agent_distance']):.6f}",
        "",
    ]

    discoveries_by_agent = defaultdict(list)
    for target_id, discovery in discoveries.items():
        discoveries_by_agent[str(discovery["agent_id"])].append(
            (int(discovery["step_index"]), int(target_id), discovery)
        )

    for agent_index, agent in enumerate(summary["agents"]):
        agent_id = str(agent["agent_id"])
        route_nodes = [int(node_id) for node_id in agent["route_node_ids"]]
        route_viewpoints = [str(item) for item in agent["route_viewpoint_ids"]]
        edge_distances = [float(item) for item in agent["edge_distances"]]
        lines.extend(
            [
                f"{agent_id} ({ROUTE_COLORS[agent_index]})",
                "-" * (len(agent_id) + 10),
                f"Start node: {route_nodes[0]}",
                f"End node: {route_nodes[-1]}",
                f"Movement count: {agent['step_count']}",
                f"Wait steps: {agent['wait_steps']}",
                f"Path distance: {float(agent['path_distance']):.6f}",
                "Route node IDs: " + " -> ".join(str(item) for item in route_nodes),
                "",
                "Route viewpoints:",
            ]
        )
        for route_index, (node_id, viewpoint_id) in enumerate(
            zip(route_nodes, route_viewpoints)
        ):
            lines.append(
                f"  visit {route_index:02d}: node {node_id:02d} | {viewpoint_id}"
            )
        lines.extend(["", "Movement segments:"])
        cumulative_distance = 0.0
        for movement_index, (source, target, distance) in enumerate(
            zip(route_nodes, route_nodes[1:], edge_distances), start=1
        ):
            cumulative_distance += distance
            lines.append(
                f"  move {movement_index:02d}: {source:02d} -> {target:02d} | "
                f"distance {distance:.6f} | cumulative {cumulative_distance:.6f}"
            )
        lines.extend(["", "Targets found:"])
        for step_index, target_number, discovery in sorted(
            discoveries_by_agent[agent_id]
        ):
            target_id = str(target_number)
            lines.append(
                f"  target {target_id} at detection step {step_index:02d}, "
                f"node {int(discovery['node_id']):02d}: "
                f"{target_descriptions[target_id]}"
            )
        lines.extend(["", ""])

    lines.extend(["Target discoveries", "=================="])
    for target_id in sorted(target_descriptions, key=int):
        discovery = discoveries[target_id]
        node_id = int(discovery["node_id"])
        viewpoint_id = str(connectivity[node_id]["image_id"])
        lines.extend(
            [
                f"Target {target_id}: {target_descriptions[target_id]}",
                f"  found by: {discovery['agent_id']}",
                f"  detection step: {int(discovery['step_index']):02d}",
                f"  node: {node_id}",
                f"  viewpoint ID: {viewpoint_id}",
            ]
        )

    args.output_details.parent.mkdir(parents=True, exist_ok=True)
    args.output_details.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    summary = read_json(args.route_summary)
    case = read_json(args.case)
    connectivity = read_json(args.connectivity)
    target_descriptions = {
        str(target["target_id"]): str(target["description"])
        for target in case["targets"]
    }
    target_nodes = {
        str(target_id): int(node_id)
        for target_id, node_id in summary["target_node_ids_by_target_id"].items()
    }
    discoveries = discovery_events(
        args.detection_dir, args.episode_state_dir, target_nodes
    )
    render_figure(args, summary, target_descriptions)
    write_route_details(
        args, summary, connectivity, target_descriptions, discoveries
    )


if __name__ == "__main__":
    main()
