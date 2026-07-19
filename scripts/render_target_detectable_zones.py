from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


REFERENCE_HEIGHT = 560.0
REGION_COLORS = (
    "#0f766e",
    "#2563eb",
    "#ca8a04",
    "#c026d3",
    "#dc2626",
    "#16a34a",
    "#7c3aed",
    "#ea580c",
)
REGION_FILL_OPACITY = 0.18
REGION_BOUNDARY_WIDTH = 2.0
REGION_NODE_RADIUS = 38.0
REGION_CORRIDOR_RADIUS = 18.0
GRAPH_EDGE_COLOR = "#8b97a9"
GRAPH_EDGE_WIDTH = 1.0
GRAPH_NODE_FILL = "#475467"
GRAPH_NODE_RADIUS = 7.0
GRAPH_NODE_STROKE = "#ffffff"
GRAPH_NODE_STROKE_WIDTH = 1.5
GRAPH_NODE_LABEL_FONT_SIZE = 6.5


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Render target-specific detectable-viewpoint zones over a Matterport "
            "house texture and connectivity graph."
        )
    )
    parser.add_argument("--texture", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--connectivity", type=Path, required=True)
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--scan-id", required=True)
    parser.add_argument("--font", type=Path, required=True)
    parser.add_argument("--bold-font", type=Path, required=True)
    parser.add_argument("--texture-opacity", type=float, default=0.5)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def hex_rgb(color: str) -> tuple[int, int, int]:
    value = color.removeprefix("#")
    return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))


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


def wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: float,
) -> list[str]:
    words = text.split()
    lines = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        left, _, right, _ = draw.textbbox((0, 0), candidate, font=font)
        if right - left <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def main() -> None:
    args = parse_args()
    if not 0.0 <= args.texture_opacity <= 1.0:
        raise ValueError("--texture-opacity must be between 0 and 1.")

    texture = Image.open(args.texture).convert("RGB")
    metadata = read_json(args.metadata)
    connectivity = read_json(args.connectivity)
    scenario = read_json(args.scenario)
    scan = next(item for item in scenario["scans"] if item["scan_id"] == args.scan_id)

    expected_size = (int(metadata["width"]), int(metadata["height"]))
    if texture.size != expected_size:
        raise ValueError(
            f"Texture size {texture.size} does not match metadata size {expected_size}."
        )

    width, height = texture.size
    style_scale = height / REFERENCE_HEIGHT
    min_x = float(metadata["min_x"])
    max_x = float(metadata["max_x"])
    min_y = float(metadata["min_y"])
    max_y = float(metadata["max_y"])

    included = {
        node_id: record
        for node_id, record in enumerate(connectivity)
        if bool(record["included"])
    }
    viewpoint_index = {
        str(record["image_id"]): node_id for node_id, record in included.items()
    }

    def position(record: dict) -> tuple[float, float]:
        pose = record["pose"]
        return (
            (float(pose[3]) - min_x) / (max_x - min_x) * width,
            (max_y - float(pose[7])) / (max_y - min_y) * height,
        )

    positions = {node_id: position(record) for node_id, record in included.items()}

    target_nodes = {}
    for target in scan["targets"]:
        target_id = str(target["target_id"])
        target_nodes[target_id] = {
            viewpoint_index[str(viewpoint_id)]
            for viewpoint_id in target["detectable_viewpoint_ids"]
        }

    graph_edges = []
    for source_id, source in included.items():
        for target_id, target in included.items():
            if source_id >= target_id:
                continue
            if not bool(source["unobstructed"][target_id]):
                continue
            if not bool(target["unobstructed"][source_id]):
                continue
            graph_edges.append((source_id, target_id))

    white = Image.new("RGB", texture.size, "white")
    plot = Image.blend(white, texture, args.texture_opacity).convert("RGBA")

    region_node_radius = round(REGION_NODE_RADIUS * style_scale)
    region_corridor_radius = round(REGION_CORRIDOR_RADIUS * style_scale)
    boundary_width = round(REGION_BOUNDARY_WIDTH * style_scale)
    masks = {}
    for target_id in sorted(target_nodes, key=int):
        mask = Image.new("L", plot.size, 0)
        mask_draw = ImageDraw.Draw(mask)
        nodes = target_nodes[target_id]
        for source_id, target_node_id in graph_edges:
            if source_id not in nodes or target_node_id not in nodes:
                continue
            source = positions[source_id]
            target_position = positions[target_node_id]
            mask_draw.line(
                (source, target_position),
                fill=255,
                width=region_corridor_radius * 2,
            )
            for x, y in (source, target_position):
                mask_draw.ellipse(
                    (
                        x - region_corridor_radius,
                        y - region_corridor_radius,
                        x + region_corridor_radius,
                        y + region_corridor_radius,
                    ),
                    fill=255,
                )
        for node_id in nodes:
            x, y = positions[node_id]
            mask_draw.ellipse(
                (
                    x - region_node_radius,
                    y - region_node_radius,
                    x + region_node_radius,
                    y + region_node_radius,
                ),
                fill=255,
            )
        masks[target_id] = mask

    for target_id in sorted(masks, key=int):
        color = REGION_COLORS[int(target_id)]
        fill_layer = Image.new("RGBA", plot.size, hex_rgb(color) + (0,))
        fill_layer.putalpha(
            masks[target_id].point(
                lambda value: round(value * REGION_FILL_OPACITY)
            )
        )
        plot = Image.alpha_composite(plot, fill_layer)

    for target_id in sorted(masks, key=int):
        color = REGION_COLORS[int(target_id)]
        edge_mask = masks[target_id].filter(ImageFilter.FIND_EDGES)
        edge_mask = edge_mask.point(lambda value: 255 if value else 0)
        edge_mask = edge_mask.filter(
            ImageFilter.MaxFilter(boundary_width if boundary_width % 2 else boundary_width + 1)
        )
        boundary_layer = Image.new("RGBA", plot.size, hex_rgb(color) + (0,))
        boundary_layer.putalpha(edge_mask)
        plot = Image.alpha_composite(plot, boundary_layer)

    draw = ImageDraw.Draw(plot)
    for source_id, target_id in graph_edges:
        draw.line(
            (positions[source_id], positions[target_id]),
            fill=GRAPH_EDGE_COLOR,
            width=round(GRAPH_EDGE_WIDTH * style_scale),
        )

    node_font = ImageFont.truetype(
        args.bold_font, size=round(GRAPH_NODE_LABEL_FONT_SIZE * style_scale)
    )
    for node_id in sorted(positions):
        center = positions[node_id]
        centered_circle(
            draw,
            center,
            GRAPH_NODE_RADIUS * style_scale,
            GRAPH_NODE_FILL,
            GRAPH_NODE_STROKE,
            GRAPH_NODE_STROKE_WIDTH * style_scale,
        )
        label = str(node_id)
        left, top, right, bottom = draw.textbbox((0, 0), label, font=node_font)
        draw.text(
            (
                center[0] - (right - left) / 2.0 - left,
                center[1] - (bottom - top) / 2.0 - top,
            ),
            label,
            font=node_font,
            fill=GRAPH_NODE_STROKE,
        )

    legend_width = 1200
    combined = Image.new("RGBA", (width + legend_width, height), "white")
    combined.paste(plot, (0, 0))
    legend_draw = ImageDraw.Draw(combined)
    legend_draw.line(
        ((width + 2, 80), (width + 2, height - 80)),
        fill="#d0d5dd",
        width=4,
    )

    title_font = ImageFont.truetype(args.bold_font, size=72)
    target_font = ImageFont.truetype(args.bold_font, size=58)
    description_font = ImageFont.truetype(args.font, size=46)
    legend_x = width + 84
    legend_right = width + legend_width - 74
    legend_draw.text(
        (legend_x, 90),
        "Detectable-viewpoint zones",
        font=title_font,
        fill="#111827",
    )
    item_y = 250
    text_x = legend_x + 96
    description_width = legend_right - text_x
    for target in sorted(scan["targets"], key=lambda item: int(item["target_id"])):
        target_id = str(target["target_id"])
        color = REGION_COLORS[int(target_id)]
        swatch_center = (legend_x + 34, item_y + 35)
        swatch_radius = 28
        color_rgb = hex_rgb(color)
        light_fill = tuple(
            round(channel * REGION_FILL_OPACITY + 255 * (1.0 - REGION_FILL_OPACITY))
            for channel in color_rgb
        )
        legend_draw.ellipse(
            (
                swatch_center[0] - swatch_radius,
                swatch_center[1] - swatch_radius,
                swatch_center[0] + swatch_radius,
                swatch_center[1] + swatch_radius,
            ),
            fill=light_fill,
            outline=color,
            width=8,
        )
        legend_draw.text(
            (text_x, item_y),
            f"t{target_id}",
            font=target_font,
            fill="#111827",
        )
        description_y = item_y + 72
        description_lines = wrap_text(
            legend_draw,
            str(target["description"]),
            description_font,
            description_width,
        )
        for line_index, line in enumerate(description_lines):
            legend_draw.text(
                (text_x, description_y + line_index * 58),
                line,
                font=description_font,
                fill="#344054",
            )
        node_ids = ", ".join(
            str(node_id) for node_id in sorted(target_nodes[target_id])
        )
        nodes_y = description_y + len(description_lines) * 58 + 10
        legend_draw.text(
            (text_x, nodes_y),
            f"VPs: {node_ids}",
            font=description_font,
            fill="#667085",
        )
        item_y = nodes_y + 112

    args.output.parent.mkdir(parents=True, exist_ok=True)
    combined.convert("RGB").save(args.output, dpi=(300, 300), optimize=True)


if __name__ == "__main__":
    main()
