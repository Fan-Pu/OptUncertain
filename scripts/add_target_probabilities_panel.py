from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


AGENT_COLORS = ("#48963A", "#E56800", "#69499B")
TITLE_COLOR = "#282196"
INK = "#262626"
GRID = "#C8C8D3"
HEADER_FILL = "#EEEEF6"
LOW_FILL = (250, 250, 255)
HIGH_FILL = (82, 70, 205)


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    filename = "arialbd.ttf" if bold else "arial.ttf"
    return ImageFont.truetype(str(Path("C:/Windows/Fonts") / filename), size=size)


def _centered_text(
    draw: ImageDraw.ImageDraw,
    box: tuple[float, float, float, float],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: str | tuple[int, int, int] = INK,
) -> None:
    x0, y0, x1, y1 = box
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    width = right - left
    height = bottom - top
    draw.text(
        ((x0 + x1 - width) / 2 - left, (y0 + y1 - height) / 2 - top),
        text,
        font=font,
        fill=fill,
    )


def _blend_probability(value: float, maximum: float) -> tuple[int, int, int]:
    weight = 0.0 if maximum == 0.0 else min(max(value / maximum, 0.0), 1.0)
    weight = weight**0.72
    return tuple(
        round(low + weight * (high - low))
        for low, high in zip(LOW_FILL, HIGH_FILL)
    )


def _load_groups(
    hypothesis_path: Path,
    layout_path: Path,
    selected_target_ids: list[str] | None,
) -> tuple[list[dict[str, object]], list[str], float]:
    hypothesis = json.loads(hypothesis_path.read_text(encoding="utf-8"))
    layout = json.loads(layout_path.read_text(encoding="utf-8"))

    viewpoints = {
        int(node["id"]): node
        for node in hypothesis["nodes"]
        if node["type"] == "viewpoint"
    }
    adjacency = {node_id: set() for node_id in viewpoints}
    for edge in hypothesis["edges"]:
        if edge["type"] != "vv":
            continue
        i = int(edge["i"])
        j = int(edge["j"])
        adjacency[i].add(j)
        adjacency[j].add(i)

    active_target_ids = sorted(
        (
            str(target_id)
            for target_id, found in hypothesis["target_found"].items()
            if not bool(found)
        ),
        key=int,
    )
    target_ids = active_target_ids if selected_target_ids is None else selected_target_ids
    maximum = max(
        float(node["target_probs"][target_id])
        for node in viewpoints.values()
        for target_id in target_ids
    )

    groups: list[dict[str, object]] = []
    covered: set[int] = set()
    for agent_index, agent_id in enumerate(sorted(layout["agent_current_vp_ids"])):
        current = int(layout["agent_current_vp_ids"][agent_id])
        component = {current}
        frontier = [current]
        while frontier:
            node_id = frontier.pop()
            for neighbor in adjacency[node_id]:
                if neighbor not in component:
                    component.add(neighbor)
                    frontier.append(neighbor)
        ordered = [current] + sorted(component.difference({current}))
        overlap = covered.intersection(component)
        if overlap:
            raise ValueError("Viewpoints assigned to multiple agents: %s" % sorted(overlap))
        covered.update(component)
        groups.append(
            {
                "agent_label": "A%d" % (agent_index + 1),
                "color": AGENT_COLORS[agent_index],
                "current": current,
                "viewpoints": [
                    {
                        "id": node_id,
                        "target_probs": {
                            target_id: float(viewpoints[node_id]["target_probs"][target_id])
                            for target_id in target_ids
                        },
                    }
                    for node_id in ordered
                ],
            }
        )

    if covered != set(viewpoints):
        raise ValueError(
            "Unassigned viewpoints: %s" % sorted(set(viewpoints).difference(covered))
        )
    return groups, target_ids, maximum


def compose(
    source_path: Path,
    hypothesis_path: Path,
    layout_path: Path,
    output_path: Path,
    selected_target_ids: list[str] | None = None,
) -> None:
    source = Image.open(source_path).convert("RGB")
    groups, target_ids, maximum = _load_groups(
        hypothesis_path,
        layout_path,
        selected_target_ids,
    )

    gap = 16
    right_margin = 18
    panel_width = 640
    canvas = Image.new(
        "RGB",
        (source.width + gap + panel_width + right_margin, source.height),
        "white",
    )
    canvas.paste(source, (0, 0))
    draw = ImageDraw.Draw(canvas)

    panel_x0 = source.width + gap
    panel_x1 = panel_x0 + panel_width
    panel_y0 = 57
    panel_y1 = source.height - 19

    title_font = _font(25, bold=True)
    subtitle_font = _font(14)
    header_font = _font(15, bold=True)
    cell_font = _font(15)
    cell_bold_font = _font(15, bold=True)
    foot_font = _font(12)

    _centered_text(
        draw,
        (panel_x0, 20, panel_x1, 57),
        "Target probabilities at viewpoints",
        title_font,
        TITLE_COLOR,
    )
    draw.rounded_rectangle(
        (panel_x0, panel_y0, panel_x1, panel_y1),
        radius=12,
        fill="white",
        outline="#303030",
        width=4,
    )
    _centered_text(
        draw,
        (panel_x0 + 8, panel_y0 + 5, panel_x1 - 8, panel_y0 + 30),
        (
            "p(target | viewpoint), active targets only"
            if selected_target_ids is None
            else "p(target | viewpoint), selected active targets"
        ),
        subtitle_font,
        "#4C4C58",
    )

    table_x0 = panel_x0 + 20
    table_x1 = panel_x1 - 20
    table_y0 = panel_y0 + 34
    header_height = 30
    row_height = 26
    probability_width = (table_x1 - table_x0 - 66 - 60) // len(target_ids)
    column_widths = [66, 60] + [probability_width] * len(target_ids)
    column_widths[-1] += table_x1 - table_x0 - sum(column_widths)
    if sum(column_widths) != table_x1 - table_x0:
        raise ValueError("Panel column widths do not match available table width.")

    column_edges = [table_x0]
    for width in column_widths:
        column_edges.append(column_edges[-1] + width)

    draw.rounded_rectangle(
        (table_x0, table_y0, table_x1, table_y0 + header_height),
        radius=6,
        fill=HEADER_FILL,
        outline=GRID,
        width=1,
    )
    headers = ["Agent", "VP"] + ["t%s" % target_id for target_id in target_ids]
    for column_index, header in enumerate(headers):
        _centered_text(
            draw,
            (
                column_edges[column_index],
                table_y0,
                column_edges[column_index + 1],
                table_y0 + header_height,
            ),
            header,
            header_font,
            TITLE_COLOR if column_index >= 2 else INK,
        )
        if column_index:
            draw.line(
                (column_edges[column_index], table_y0, column_edges[column_index], table_y0 + header_height),
                fill=GRID,
                width=1,
            )

    row_y = table_y0 + header_height
    for group in groups:
        group_rows = group["viewpoints"]
        group_y0 = row_y
        group_y1 = group_y0 + row_height * len(group_rows)
        group_color = str(group["color"])
        draw.rounded_rectangle(
            (column_edges[0] + 4, group_y0 + 3, column_edges[1] - 4, group_y1 - 3),
            radius=8,
            fill=group_color,
        )
        _centered_text(
            draw,
            (column_edges[0] + 4, group_y0 + 3, column_edges[1] - 4, group_y1 - 3),
            str(group["agent_label"]),
            _font(18, bold=True),
            "white",
        )

        for viewpoint in group_rows:
            row_y1 = row_y + row_height
            draw.rectangle(
                (column_edges[1], row_y, table_x1, row_y1),
                fill="white",
                outline=GRID,
                width=1,
            )
            is_current = int(viewpoint["id"]) == int(group["current"])
            vp_label = "%s%s" % (viewpoint["id"], " *" if is_current else "")
            _centered_text(
                draw,
                (column_edges[1], row_y, column_edges[2], row_y1),
                vp_label,
                cell_bold_font if is_current else cell_font,
                group_color if is_current else INK,
            )

            for target_index, target_id in enumerate(target_ids):
                column_index = target_index + 2
                value = float(viewpoint["target_probs"][target_id])
                fill = _blend_probability(value, maximum)
                draw.rectangle(
                    (
                        column_edges[column_index],
                        row_y,
                        column_edges[column_index + 1],
                        row_y1,
                    ),
                    fill=fill,
                    outline=GRID,
                    width=1,
                )
                text_fill = "white" if value / maximum >= 0.58 else INK
                _centered_text(
                    draw,
                    (
                        column_edges[column_index],
                        row_y,
                        column_edges[column_index + 1],
                        row_y1,
                    ),
                    "%.3f" % value,
                    cell_bold_font if value / maximum >= 0.58 else cell_font,
                    text_fill,
                )
            row_y = row_y1

        draw.line((table_x0, group_y1, table_x1, group_y1), fill=group_color, width=2)

    footer_y = panel_y1 - 34
    draw.text(
        (table_x0, footer_y),
        "* current viewpoint",
        font=foot_font,
        fill="#55555F",
    )
    legend_x0 = panel_x1 - 223
    legend_x1 = panel_x1 - 57
    legend_y0 = footer_y + 2
    legend_y1 = footer_y + 14
    for x in range(int(legend_x0), int(legend_x1)):
        value = maximum * (x - legend_x0) / (legend_x1 - legend_x0 - 1)
        draw.line((x, legend_y0, x, legend_y1), fill=_blend_probability(value, maximum))
    draw.rectangle((legend_x0, legend_y0, legend_x1, legend_y1), outline=GRID, width=1)
    draw.text((legend_x0 - 13, footer_y), "0", font=foot_font, fill="#55555F")
    draw.text(
        (legend_x1 + 5, footer_y),
        "%.2f" % maximum,
        font=foot_font,
        fill="#55555F",
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, format="PNG", optimize=True, dpi=(300, 300))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--hypothesis", type=Path, required=True)
    parser.add_argument("--layout", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--target-ids", nargs="+", metavar="TARGET_ID")
    args = parser.parse_args()
    compose(
        args.source,
        args.hypothesis,
        args.layout,
        args.output,
        args.target_ids,
    )
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
