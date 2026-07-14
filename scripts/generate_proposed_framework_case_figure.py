from __future__ import annotations

import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps
from reportlab.pdfgen import canvas as pdf_canvas


ROOT = Path(__file__).resolve().parents[1]
CASE_ID = "JF19kD82Mey_case_0030"
SCAN_ID = "JF19kD82Mey"
DEBUG_DIR = ROOT / "mllm_debug_outputs_balanced100_GPT54Medium" / CASE_ID
RAW_DIR = ROOT / "mllm_raw_outputs_balanced100_GPT54Medium" / CASE_ID
OUTPUT_DIR = ROOT / "paper_figures"

CANVAS_WIDTH = 4200
CANVAS_HEIGHT = 2980
BACKGROUND = "#FFFFFF"
INK = "#20252B"
MUTED = "#5D6670"
RULE = "#CBD1D6"
PALE = "#F4F6F7"

REGION_COLORS = {
    50: "#4477AA",
    51: "#66CCEE",
    52: "#228833",
    53: "#CCBB44",
    54: "#AA3377",
    55: "#999999",
    56: "#EE6677",
    57: "#44AA99",
    58: "#EE7733",
    59: "#8844AA",
}

REGION_SHORT_NAMES = {
    50: "Dining",
    51: "Courtyard",
    52: "Lounge",
    53: "Kitchen",
    54: "Bedroom + desk",
    55: "Hallway",
    56: "Bathroom",
    57: "Windowed room",
    58: "Stair hall",
    59: "Wood bedroom",
}

AGENT_COLORS = {
    "agent0": "#111111",
    "agent1": "#3A3A3A",
    "agent2": "#666666",
}

TARGET_COLORS = {"3": "#D55E00", "4": "#0072B2"}

FONT_REGULAR_PATH = Path(r"C:\Windows\Fonts\arial.ttf")
FONT_BOLD_PATH = Path(r"C:\Windows\Fonts\arialbd.ttf")


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(
        str(FONT_BOLD_PATH if bold else FONT_REGULAR_PATH),
        size=size,
    )


F_PANEL = font(58, bold=True)
F_SECTION = font(46, bold=True)
F_LABEL = font(39, bold=True)
F_BODY = font(36)
F_SMALL = font(31)
F_SMALL_BOLD = font(31, bold=True)
F_NODE = font(35, bold=True)
F_REGION = font(33, bold=True)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def rgba(hex_color: str, alpha: int) -> tuple[int, int, int, int]:
    value = hex_color.lstrip("#")
    return (
        int(value[0:2], 16),
        int(value[2:4], 16),
        int(value[4:6], 16),
        alpha,
    )


def text_size(draw: ImageDraw.ImageDraw, text: str, text_font: ImageFont.ImageFont) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=text_font)
    return box[2] - box[0], box[3] - box[1]


def draw_arrow(
    draw: ImageDraw.ImageDraw,
    start: tuple[int, int],
    end: tuple[int, int],
    color: str = MUTED,
    width: int = 8,
) -> None:
    draw.line([start, end], fill=color, width=width)
    angle = math.atan2(end[1] - start[1], end[0] - start[0])
    head = 24
    left = (
        end[0] - head * math.cos(angle - math.pi / 6),
        end[1] - head * math.sin(angle - math.pi / 6),
    )
    right = (
        end[0] - head * math.cos(angle + math.pi / 6),
        end[1] - head * math.sin(angle + math.pi / 6),
    )
    draw.polygon([end, left, right], fill=color)


def panorama_panel(
    image_path: Path,
    width: int,
    height: int,
    agent_label: str,
    semantic_label: str,
) -> Image.Image:
    panel = Image.new("RGB", (width, height), BACKGROUND)
    draw = ImageDraw.Draw(panel)
    image_height = height - 58
    panorama = ImageOps.fit(
        Image.open(image_path).convert("RGB"),
        (width, image_height),
        method=Image.Resampling.LANCZOS,
    )
    panel.paste(panorama, (0, 0))
    draw.rectangle((0, 0, width - 1, image_height - 1), outline="#9EA5AB", width=3)
    draw.rounded_rectangle((16, 14, 188, 66), radius=8, fill=(255, 255, 255, 232))
    draw.text((30, 20), agent_label, font=F_LABEL, fill=INK)
    draw.text((8, image_height + 8), semantic_label, font=F_SMALL, fill=MUTED)
    return panel


def convex_hull(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    unique = sorted(set(points))
    if len(unique) <= 1:
        return unique

    def cross(o: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    for point in unique:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    upper: list[tuple[float, float]] = []
    for point in reversed(unique):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return lower[:-1] + upper[:-1]


def expand_polygon(points: list[tuple[float, float]], padding: float) -> list[tuple[float, float]]:
    center_x = sum(point[0] for point in points) / len(points)
    center_y = sum(point[1] for point in points) / len(points)
    expanded = []
    for x, y in points:
        dx = x - center_x
        dy = y - center_y
        norm = math.hypot(dx, dy)
        if norm == 0:
            expanded.append((x, y))
        else:
            expanded.append((x + padding * dx / norm, y + padding * dy / norm))
    return expanded


def topdown_texture_paths() -> dict[int, Path]:
    cache_dir = ROOT / "topdown_texture_cache" / SCAN_ID
    paths = {}
    for metadata_path in cache_dir.glob("*_topdown_texture.json"):
        metadata = read_json(metadata_path)
        paths[int(metadata["floor_index"])] = metadata_path.with_suffix(".png")
    return paths


def map_metadata() -> dict:
    cache_dir = ROOT / "topdown_texture_cache" / SCAN_ID
    metadata_path = next(cache_dir.glob("*floor0*_topdown_texture.json"))
    return read_json(metadata_path)


def connectivity_nodes() -> dict[int, dict[str, float]]:
    connectivity = read_json(ROOT / "connectivity" / f"{SCAN_ID}_connectivity.json")
    nodes = {}
    for index, item in enumerate(connectivity):
        pose = item["pose"]
        z = float(pose[11])
        nodes[index] = {
            "x": float(pose[3]),
            "y": float(pose[7]),
            "z": z,
            "floor": 0 if z < 3.140187029220779 else 1,
        }
    return nodes


def render_graph_map(
    layout: dict,
    floor_index: int,
    width: int,
    height: int,
    step_index: int,
    highlight_hypotheses: bool,
) -> Image.Image:
    texture_path = topdown_texture_paths()[floor_index]
    pad_x = 50
    pad_y = 24
    inner_width = width - 2 * pad_x
    inner_height = height - 2 * pad_y
    texture = Image.open(texture_path).convert("RGB").resize(
        (inner_width, inner_height), Image.Resampling.LANCZOS
    )
    texture = ImageEnhance.Color(texture).enhance(0.42)
    texture = ImageEnhance.Contrast(texture).enhance(0.84)
    texture = Image.blend(texture, Image.new("RGB", texture.size, "white"), 0.12)
    image = Image.new("RGBA", (width, height), (255, 255, 255, 255))
    image.paste(texture.convert("RGBA"), (pad_x, pad_y))
    overlay = Image.new("RGBA", image.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)

    metadata = map_metadata()
    min_x = float(metadata["min_x"])
    max_x = float(metadata["max_x"])
    min_y = float(metadata["min_y"])
    max_y = float(metadata["max_y"])
    node_coordinates = connectivity_nodes()

    def position(node_id: int) -> tuple[float, float]:
        node = node_coordinates[int(node_id)]
        x = pad_x + (node["x"] - min_x) / (max_x - min_x) * inner_width
        y = pad_y + (max_y - node["y"]) / (max_y - min_y) * inner_height
        return x, y

    layout_node_ids = {
        int(node["id"])
        for node in layout["nodes"]
        if node["type"] == "viewpoint" and node_coordinates[int(node["id"])]["floor"] == floor_index
    }

    region_to_viewpoints = {
        int(region_id): [
            int(node_id)
            for node_id in node_ids
            if int(node_id) in layout_node_ids
        ]
        for region_id, node_ids in layout["region_to_viewpoints"].items()
    }

    for region_id, node_ids in sorted(region_to_viewpoints.items()):
        if not node_ids:
            continue
        points = [position(node_id) for node_id in node_ids]
        color = REGION_COLORS[region_id]
        if len(points) == 1:
            x, y = points[0]
            draw.ellipse((x - 42, y - 42, x + 42, y + 42), fill=rgba(color, 64), outline=rgba(color, 185), width=5)
        elif len(points) == 2:
            draw.line(points, fill=rgba(color, 72), width=74)
            for x, y in points:
                draw.ellipse((x - 37, y - 37, x + 37, y + 37), fill=rgba(color, 72))
        else:
            hull = convex_hull(points)
            if len(hull) >= 3:
                expanded = expand_polygon(hull, 34)
                draw.polygon(expanded, fill=rgba(color, 55), outline=rgba(color, 190), width=5)
            else:
                draw.line(points, fill=rgba(color, 72), width=74)

    for edge in layout["edges"]:
        i = int(edge["i"])
        j = int(edge["j"])
        if i not in layout_node_ids or j not in layout_node_ids:
            continue
        points = [position(i), position(j)]
        draw.line(points, fill=(255, 255, 255, 235), width=11)
        draw.line(points, fill=(65, 72, 78, 220), width=5)

    viewpoint_to_region = {
        int(node_id): int(region_id)
        for node_id, region_id in layout["viewpoint_to_region"].items()
    }
    for node_id in sorted(layout_node_ids):
        x, y = position(node_id)
        region_id = viewpoint_to_region[node_id]
        color = REGION_COLORS[region_id]
        draw.ellipse((x - 16, y - 16, x + 16, y + 16), fill=color, outline="white", width=5)
        draw.ellipse((x - 17, y - 17, x + 17, y + 17), outline=INK, width=2)
        draw.text((x + 18, y - 26), str(node_id), font=F_NODE, fill=INK, stroke_width=5, stroke_fill="white")

    agent_short_labels = {"agent0": "A0", "agent1": "A1", "agent2": "A2"}
    for agent_id, node_id in layout["agent_current_vp_ids"].items():
        node_id = int(node_id)
        if node_id not in layout_node_ids:
            continue
        x, y = position(node_id)
        draw.ellipse((x - 29, y - 29, x + 29, y + 29), outline=AGENT_COLORS[agent_id], width=9)
        label = agent_short_labels[agent_id]
        draw.rounded_rectangle((x - 38, y - 78, x + 38, y - 34), radius=7, fill=(255, 255, 255, 236), outline=AGENT_COLORS[agent_id], width=3)
        label_width, _ = text_size(draw, label, F_SMALL_BOLD)
        draw.text((x - label_width / 2, y - 73), label, font=F_SMALL_BOLD, fill=AGENT_COLORS[agent_id])

    for region_id, node_ids in sorted(region_to_viewpoints.items()):
        if not node_ids:
            continue
        points = [position(node_id) for node_id in node_ids]
        center_x = sum(point[0] for point in points) / len(points)
        center_y = sum(point[1] for point in points) / len(points)
        tag = f"R{region_id}"
        tag_width, tag_height = text_size(draw, tag, F_REGION)
        box = (center_x - tag_width / 2 - 9, center_y + 26, center_x + tag_width / 2 + 9, center_y + 26 + tag_height + 8)
        draw.rounded_rectangle(box, radius=7, fill=(255, 255, 255, 228), outline=REGION_COLORS[region_id], width=4)
        draw.text((box[0] + 9, box[1] + 1), tag, font=F_REGION, fill=INK)

    if highlight_hypotheses and floor_index == 1:
        hypothesis_specs = [(9, "3"), (20, "4"), (41, "4")]
        for node_id, target_id in hypothesis_specs:
            x, y = position(node_id)
            color = TARGET_COLORS[target_id]
            draw.ellipse((x - 32, y - 32, x + 32, y + 32), outline="white", width=13)
            draw.ellipse((x - 34, y - 34, x + 34, y + 34), outline=color, width=8)

    result = Image.alpha_composite(image, overlay).convert("RGB")
    border = ImageDraw.Draw(result)
    border.rectangle((0, 0, width - 1, height - 1), outline="#9EA5AB", width=3)
    return result


def draw_region_legend(
    draw: ImageDraw.ImageDraw,
    region_ids: list[int],
    x: int,
    y: int,
    width: int,
) -> int:
    columns = 5
    column_width = width // columns
    row_height = 57
    for index, region_id in enumerate(region_ids):
        column = index % columns
        row = index // columns
        item_x = x + column * column_width
        item_y = y + row * row_height
        draw.rounded_rectangle(
            (item_x, item_y + 7, item_x + 30, item_y + 37),
            radius=5,
            fill=REGION_COLORS[region_id],
        )
        draw.text(
            (item_x + 42, item_y),
            f"R{region_id} {REGION_SHORT_NAMES[region_id]}",
            font=F_SMALL,
            fill=INK,
        )
    rows = math.ceil(len(region_ids) / columns)
    return y + rows * row_height


def draw_step_row(
    canvas: Image.Image,
    step_index: int,
    row_y: int,
    panel_letters: tuple[str, str],
    title: str,
    pano_semantic_labels: list[str],
) -> None:
    draw = ImageDraw.Draw(canvas)
    row_height = 1210
    pano_x = 90
    pano_width = 1760
    pano_height = 330
    map_x = 2180
    map_width = 940
    map_height = 464
    map_gap = 42

    draw.line((80, row_y - 24, CANVAS_WIDTH - 80, row_y - 24), fill=RULE, width=4)
    draw.text((pano_x, row_y), f"({panel_letters[0]})  {title}", font=F_PANEL, fill=INK)
    graph_title = "Initial semantic graph" if step_index == 1 else "Updated graph + hypotheses"
    draw.text((map_x, row_y), f"({panel_letters[1]})  {graph_title}", font=F_PANEL, fill=INK)

    for agent_index in range(3):
        image_path = DEBUG_DIR / f"observation_step_{step_index:04d}_agent_agent{agent_index}.jpg"
        panel = panorama_panel(
            image_path=image_path,
            width=pano_width,
            height=pano_height,
            agent_label=f"Agent {agent_index}",
            semantic_label=pano_semantic_labels[agent_index],
        )
        canvas.paste(panel, (pano_x, row_y + 86 + agent_index * (pano_height + 20)))

    arrow_y = row_y + 555
    draw_arrow(draw, (1880, arrow_y), (2140, arrow_y), color="#6C737A", width=9)
    arrow_label = "MLLM semantic\nreasoning"
    draw.multiline_text((1878, arrow_y - 105), arrow_label, font=F_SMALL_BOLD, fill=MUTED, spacing=5, align="center")

    layout = read_json(DEBUG_DIR / f"graph_layout_step_{step_index:04d}.json")
    floor0 = render_graph_map(
        layout=layout,
        floor_index=0,
        width=map_width,
        height=map_height,
        step_index=step_index,
        highlight_hypotheses=step_index == 2,
    )
    floor1 = render_graph_map(
        layout=layout,
        floor_index=1,
        width=map_width,
        height=map_height,
        step_index=step_index,
        highlight_hypotheses=step_index == 2,
    )
    map_y = row_y + 90
    canvas.paste(floor0, (map_x, map_y))
    canvas.paste(floor1, (map_x + map_width + map_gap, map_y))
    draw.text((map_x + 16, map_y + 14), "Ground floor", font=F_SECTION, fill=INK, stroke_width=5, stroke_fill="white")
    draw.text((map_x + map_width + map_gap + 16, map_y + 14), "Upper floor", font=F_SECTION, fill=INK, stroke_width=5, stroke_fill="white")

    region_ids = sorted(int(region_id) for region_id in layout["region_to_viewpoints"])
    legend_end_y = draw_region_legend(
        draw,
        region_ids=region_ids,
        x=map_x,
        y=map_y + map_height + 28,
        width=map_width * 2 + map_gap,
    )

    viewpoint_count = sum(1 for node in layout["nodes"] if node["type"] == "viewpoint")
    region_count = sum(1 for node in layout["nodes"] if node["type"] == "region")
    edge_count = len(layout["edges"])
    summary_y = legend_end_y + 24
    draw.rounded_rectangle(
        (map_x, summary_y, map_x + map_width * 2 + map_gap, summary_y + 92),
        radius=10,
        fill=PALE,
        outline=RULE,
        width=3,
    )
    summary = f"{viewpoint_count} viewpoints     {region_count} semantic regions     {edge_count} grounded edges"
    draw.text((map_x + 34, summary_y + 22), summary, font=F_LABEL, fill=INK)

    hypothesis_y = summary_y + 122
    if step_index == 1:
        draw.text((map_x, hypothesis_y), "Context-consistent target-location hypotheses", font=F_SECTION, fill=INK)
        draw.text(
            (map_x, hypothesis_y + 58),
            "T3 keyboard  →  vp 8 (0.758)     T4 blue chair  →  vp 8 (0.599)     T6 horse-base lamp  →  vp 8 (0.676)",
            font=F_BODY,
            fill=MUTED,
        )
    else:
        draw.text((map_x, hypothesis_y), "Refined hypotheses after new observations", font=F_SECTION, fill=INK)
        draw.ellipse((map_x, hypothesis_y + 69, map_x + 28, hypothesis_y + 97), fill=TARGET_COLORS["3"])
        draw.text((map_x + 42, hypothesis_y + 59), "T3 keyboard: vp 9 (0.747)", font=F_BODY, fill=INK)
        draw.ellipse((map_x + 610, hypothesis_y + 69, map_x + 638, hypothesis_y + 97), fill=TARGET_COLORS["4"])
        draw.text((map_x + 652, hypothesis_y + 59), "T4 chair: vp 20 (0.412), vp 41 (0.312)", font=F_BODY, fill=INK)
        draw.text(
            (map_x, hypothesis_y + 116),
            "Outdoor and kitchen candidates are strongly down-weighted for the upstairs-bedroom target.",
            font=F_SMALL,
            fill=MUTED,
        )


def draw_bottom_flow(canvas: Image.Image) -> None:
    draw = ImageDraw.Draw(canvas)
    y = 2730
    draw.line((80, y - 40, CANVAS_WIDTH - 80, y - 40), fill=RULE, width=4)
    labels = [
        "Distributed panoramas",
        "Semantic-region graph",
        "Target-location hypotheses",
        "Joint route optimization",
        "Move and re-observe",
    ]
    box_width = 660
    box_height = 112
    gap = 138
    total_width = len(labels) * box_width + (len(labels) - 1) * gap
    x = (CANVAS_WIDTH - total_width) // 2
    for index, label in enumerate(labels):
        box_x = x + index * (box_width + gap)
        draw.rounded_rectangle(
            (box_x, y, box_x + box_width, y + box_height),
            radius=12,
            fill="#F7F8F9",
            outline="#7E878F",
            width=4,
        )
        label_width, label_height = text_size(draw, label, F_LABEL)
        draw.text(
            (box_x + (box_width - label_width) / 2, y + (box_height - label_height) / 2 - 3),
            label,
            font=F_LABEL,
            fill=INK,
        )
        if index < len(labels) - 1:
            draw_arrow(
                draw,
                (box_x + box_width + 18, y + box_height // 2),
                (box_x + box_width + gap - 18, y + box_height // 2),
                color="#6C737A",
                width=7,
            )
    draw.text(
        (90, y + box_height + 28),
        "Online closed loop: observations update the graph and hypotheses before each coordinated movement.",
        font=F_SMALL,
        fill=MUTED,
    )


def write_pdf(png_path: Path, pdf_path: Path) -> None:
    page_width = 7.16 * 72
    page_height = page_width * CANVAS_HEIGHT / CANVAS_WIDTH
    pdf = pdf_canvas.Canvas(str(pdf_path), pagesize=(page_width, page_height))
    pdf.drawImage(str(png_path), 0, 0, width=page_width, height=page_height)
    pdf.showPage()
    pdf.save()


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    canvas = Image.new("RGB", (CANVAS_WIDTH, CANVAS_HEIGHT), BACKGROUND)

    draw_step_row(
        canvas=canvas,
        step_index=1,
        row_y=70,
        panel_letters=("a", "b"),
        title="Step 1: distributed observations",
        pano_semantic_labels=[
            "Dining · courtyard · lounge · kitchen · stair hall",
            "Bedroom + desk · adjacent hallway",
            "Bathroom · windowed room",
        ],
    )
    draw_step_row(
        canvas=canvas,
        step_index=2,
        row_y=1370,
        panel_letters=("c", "d"),
        title="Step 2: new observations",
        pano_semantic_labels=[
            "Kitchen · courtyard · lounge",
            "Desk bedroom · viewpoint 9",
            "Wood bedroom · viewpoints 20 and 41",
        ],
    )
    draw_bottom_flow(canvas)

    png_path = OUTPUT_DIR / "proposed_framework_case_JF19kD82Mey_0030.png"
    pdf_path = OUTPUT_DIR / "proposed_framework_case_JF19kD82Mey_0030.pdf"
    canvas.save(png_path, dpi=(600, 600), optimize=True)
    write_pdf(png_path=png_path, pdf_path=pdf_path)
    print(png_path)
    print(pdf_path)


if __name__ == "__main__":
    main()
