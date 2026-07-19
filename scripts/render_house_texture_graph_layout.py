from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


VIEWER_REFERENCE_HEIGHT = 560.0
VIEWER_EDGE_WIDTH = 1.0
VIEWER_NODE_RADIUS = 4.0
VIEWER_LABELED_NODE_RADIUS = 7.0
VIEWER_NODE_STROKE_WIDTH = 1.5
VIEWER_NODE_LABEL_FONT_SIZE = 6.5
VIEWER_EDGE_COLOR = "#8b97a9"
VIEWER_NODE_FILL = "#475467"
VIEWER_NODE_STROKE = "#ffffff"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render a Matterport house texture with its connectivity graph."
    )
    parser.add_argument("--texture", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--connectivity", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--texture-opacity", type=float, default=0.5)
    parser.add_argument("--node-labels", action="store_true")
    parser.add_argument("--label-font", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not 0.0 <= args.texture_opacity <= 1.0:
        raise ValueError("--texture-opacity must be between 0 and 1.")

    texture = Image.open(args.texture).convert("RGB")
    metadata = read_json(args.metadata)
    connectivity = read_json(args.connectivity)

    expected_size = (int(metadata["width"]), int(metadata["height"]))
    if texture.size != expected_size:
        raise ValueError(
            f"Texture size {texture.size} does not match metadata size {expected_size}."
        )

    min_x = float(metadata["min_x"])
    max_x = float(metadata["max_x"])
    min_y = float(metadata["min_y"])
    max_y = float(metadata["max_y"])
    width, height = texture.size

    white = Image.new("RGB", texture.size, "white")
    canvas = Image.blend(white, texture, args.texture_opacity)
    draw = ImageDraw.Draw(canvas)

    def position(record: dict) -> tuple[float, float]:
        pose = record["pose"]
        x = (float(pose[3]) - min_x) / (max_x - min_x) * width
        y = (max_y - float(pose[7])) / (max_y - min_y) * height
        return x, y

    included = {
        index: record
        for index, record in enumerate(connectivity)
        if bool(record["included"])
    }
    positions = {index: position(record) for index, record in included.items()}

    style_scale = height / VIEWER_REFERENCE_HEIGHT
    edge_width = max(1, round(VIEWER_EDGE_WIDTH * style_scale))
    for source_index, source in included.items():
        for target_index, target in included.items():
            if source_index >= target_index:
                continue
            if not bool(source["unobstructed"][target_index]):
                continue
            if not bool(target["unobstructed"][source_index]):
                continue
            draw.line(
                (positions[source_index], positions[target_index]),
                fill=VIEWER_EDGE_COLOR,
                width=edge_width,
            )

    node_radius = (
        VIEWER_LABELED_NODE_RADIUS if args.node_labels else VIEWER_NODE_RADIUS
    )
    radius = node_radius * style_scale
    half_stroke = VIEWER_NODE_STROKE_WIDTH * style_scale / 2.0
    outer_radius = radius + half_stroke
    inner_radius = radius - half_stroke
    label_font = None
    if args.node_labels:
        label_font = ImageFont.truetype(
            args.label_font,
            size=round(VIEWER_NODE_LABEL_FONT_SIZE * style_scale),
        )
    for node_index in sorted(positions):
        x, y = positions[node_index]
        draw.ellipse(
            (
                x - outer_radius,
                y - outer_radius,
                x + outer_radius,
                y + outer_radius,
            ),
            fill=VIEWER_NODE_STROKE,
        )
        draw.ellipse(
            (
                x - inner_radius,
                y - inner_radius,
                x + inner_radius,
                y + inner_radius,
            ),
            fill=VIEWER_NODE_FILL,
        )
        if label_font is not None:
            label = str(node_index)
            left, top, right, bottom = draw.textbbox((0, 0), label, font=label_font)
            draw.text(
                (
                    x - (right - left) / 2.0 - left,
                    y - (bottom - top) / 2.0 - top,
                ),
                label,
                font=label_font,
                fill=VIEWER_NODE_STROKE,
            )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(args.output, dpi=(300, 300), optimize=True)


if __name__ == "__main__":
    main()
