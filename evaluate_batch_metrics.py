from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

from route_plotter import load_environment_graph


STEP_FILE_RE = re.compile(r"detection_step_(\d{4})\.json$")


@dataclass(frozen=True)
class MethodSpec:
    name: str
    debug_root: Path
    raw_root: Path


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    out_dir = _resolve_path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    batch_config = _read_json(_resolve_path(args.batch_config))
    generated_cases = _read_json(_resolve_path(args.generated_cases))
    oracle_summaries = _read_json(_resolve_path(args.oracle_summaries))
    method_specs = [_parse_method_spec(item) for item in args.method]
    connectivity_dir = _resolve_path(args.connectivity_dir)

    scan_targets = _scan_target_detectable_viewpoints(batch_config)
    case_order = [str(case_id) for case_id in generated_cases["case_order"]]
    generated_case_by_id = generated_cases["cases"]
    oracle_summary_by_case = oracle_summaries["cases"]

    case_rows: List[Dict[str, object]] = []
    oracle_case_rows: List[Dict[str, object]] = []
    for case_id in case_order:
        generated_case = generated_case_by_id[case_id]
        oracle_summary = oracle_summary_by_case[case_id]
        oracle_row = _oracle_case_metrics(
            case_id=case_id,
            generated_case=generated_case,
            oracle_summary=oracle_summary,
        )
        oracle_case_rows.append(oracle_row)
        case_rows.append(oracle_row)

    for method in method_specs:
        for case_id in case_order:
            generated_case = generated_case_by_id[case_id]
            oracle_summary = oracle_summary_by_case[case_id]
            case_rows.append(
                _method_case_metrics(
                    method=method,
                    case_id=case_id,
                    generated_case=generated_case,
                    oracle_summary=oracle_summary,
                    scan_targets=scan_targets,
                    connectivity_dir=connectivity_dir,
                )
            )

    method_rows = _aggregate_method_metrics(case_rows)
    group_rows = _aggregate_group_metrics(case_rows)

    _write_csv(out_dir / "case_metrics.csv", case_rows, CASE_METRIC_FIELDS)
    _write_csv(out_dir / "method_metrics.csv", method_rows, AGGREGATE_FIELDS)
    _write_csv(
        out_dir / "group_metrics_by_agent_target.csv",
        group_rows,
        GROUP_AGGREGATE_FIELDS,
    )

    _plot_task_metrics(method_rows, out_dir)
    _plot_detection_metrics(method_rows, out_dir)
    _plot_grouped_metrics(group_rows, out_dir)

    print("Wrote case metrics to %s" % (out_dir / "case_metrics.csv"))
    print("Wrote method metrics to %s" % (out_dir / "method_metrics.csv"))
    print(
        "Wrote grouped metrics to %s"
        % (out_dir / "group_metrics_by_agent_target.csv")
    )
    print("Wrote figures to %s" % out_dir)
    return 0


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compute batch_test evaluation metrics and plot method-comparison "
            "figures from saved route summaries, detection outputs, and oracle "
            "summaries."
        )
    )
    parser.add_argument("--batch-config", required=True)
    parser.add_argument("--generated-cases", required=True)
    parser.add_argument("--oracle-summaries", required=True)
    parser.add_argument("--connectivity-dir", default="connectivity")
    parser.add_argument(
        "--method",
        required=True,
        action="append",
        help=(
            "Method spec in NAME=DEBUG_ROOT form, for example "
            "Proposed=mllm_debug_outputs."
        ),
    )
    parser.add_argument("--out", required=True)
    return parser.parse_args(argv)


def _resolve_path(path: str | Path) -> Path:
    path = Path(path)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path


def _read_json(path: Path) -> object:
    with open(path, "r", encoding="utf-8") as file_handle:
        return json.load(file_handle)


def _parse_method_spec(spec: str) -> MethodSpec:
    if "=" not in spec:
        raise ValueError("--method must use NAME=DEBUG_ROOT form: %s" % spec)
    name, debug_root_raw = spec.split("=", 1)
    if not name:
        raise ValueError("Method name cannot be empty in %s." % spec)
    debug_root = _resolve_path(debug_root_raw)
    raw_root = _raw_root_for_debug_root(debug_root)
    return MethodSpec(name=name, debug_root=debug_root, raw_root=raw_root)


def _raw_root_for_debug_root(debug_root: Path) -> Path:
    if debug_root.name == "mllm_debug_outputs":
        return debug_root.with_name("mllm_raw_outputs")
    if "debug_outputs" in debug_root.name:
        return debug_root.with_name(debug_root.name.replace("debug_outputs", "raw_outputs"))
    raise ValueError(
        "Cannot infer raw-output root for %s. Use a debug root named like "
        "mllm_debug_outputs." % str(debug_root)
    )


def _scan_target_detectable_viewpoints(
    batch_config: Dict[str, object],
) -> Dict[str, Dict[str, set[str]]]:
    mapping: Dict[str, Dict[str, set[str]]] = {}
    for scan in batch_config["scans"]:
        scan_id = str(scan["scan_id"])
        mapping[scan_id] = {}
        for target in scan["targets"]:
            target_id = str(target["target_id"])
            mapping[scan_id][target_id] = {
                str(viewpoint_id)
                for viewpoint_id in target["detectable_viewpoint_ids"]
            }
    return mapping


def _oracle_case_metrics(
    case_id: str,
    generated_case: Dict[str, object],
    oracle_summary: Dict[str, object],
) -> Dict[str, object]:
    return {
        "method": "Oracle",
        "case_id": case_id,
        "scan_id": str(generated_case["scan_id"]),
        "agent_number": int(generated_case["agent_number"]),
        "target_number": int(generated_case["target_number"]),
        "status": "oracle",
        "stop_reason": "oracle",
        "verified_success": 1.0,
        "progress": 1.0,
        "team_ppl_total": 1.0,
        "team_ppl_makespan": 1.0,
        "total_distance": float(oracle_summary["total_distance"]),
        "maximum_agent_distance": float(oracle_summary["maximum_agent_distance"]),
        "oracle_total_distance": float(oracle_summary["total_distance"]),
        "oracle_maximum_agent_distance": float(
            oracle_summary["maximum_agent_distance"]
        ),
        "tp": "",
        "fp": "",
        "fn": "",
        "precision": "",
        "recall": "",
        "f1": "",
    }


def _method_case_metrics(
    method: MethodSpec,
    case_id: str,
    generated_case: Dict[str, object],
    oracle_summary: Dict[str, object],
    scan_targets: Dict[str, Dict[str, set[str]]],
    connectivity_dir: Path,
) -> Dict[str, object]:
    summary_path = (
        method.debug_root
        / case_id
        / ("%s_mllm_route_summary.txt" % case_id)
    )
    summary = _read_json(summary_path)
    target_ids = [str(target["target_id"]) for target in generated_case["targets"]]
    scan_id = str(generated_case["scan_id"])
    detectable_by_target_id = {
        target_id: scan_targets[scan_id][target_id] for target_id in target_ids
    }
    detection_counts, verified_found_target_ids = _evaluate_detection_outputs(
        method=method,
        case_id=case_id,
        target_ids=target_ids,
        detectable_by_target_id=detectable_by_target_id,
        viewpoint_id_by_index=load_environment_graph(
            scan_id=scan_id,
            connectivity_dir=connectivity_dir,
        ).viewpoint_id_by_index,
    )

    progress = len(verified_found_target_ids) / len(target_ids)
    verified_success = 1.0 if len(verified_found_target_ids) == len(target_ids) else 0.0
    total_distance = float(summary["total_distance"])
    maximum_agent_distance = float(summary["maximum_agent_distance"])
    oracle_total_distance = float(oracle_summary["total_distance"])
    oracle_maximum_agent_distance = float(oracle_summary["maximum_agent_distance"])
    team_ppl_total = _progress_weighted_path_length(
        progress=progress,
        actual_distance=total_distance,
        oracle_distance=oracle_total_distance,
    )
    team_ppl_makespan = _progress_weighted_path_length(
        progress=progress,
        actual_distance=maximum_agent_distance,
        oracle_distance=oracle_maximum_agent_distance,
    )
    tp = detection_counts["tp"]
    fp = detection_counts["fp"]
    fn = detection_counts["fn"]

    return {
        "method": method.name,
        "case_id": case_id,
        "scan_id": scan_id,
        "agent_number": int(generated_case["agent_number"]),
        "target_number": int(generated_case["target_number"]),
        "status": str(summary["status"]),
        "stop_reason": str(summary["stop_reason"]),
        "verified_success": verified_success,
        "progress": progress,
        "team_ppl_total": team_ppl_total,
        "team_ppl_makespan": team_ppl_makespan,
        "total_distance": total_distance,
        "maximum_agent_distance": maximum_agent_distance,
        "oracle_total_distance": oracle_total_distance,
        "oracle_maximum_agent_distance": oracle_maximum_agent_distance,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": _ratio_or_empty(tp, tp + fp),
        "recall": _ratio_or_empty(tp, tp + fn),
        "f1": _ratio_or_empty(2 * tp, 2 * tp + fp + fn),
    }


def _evaluate_detection_outputs(
    method: MethodSpec,
    case_id: str,
    target_ids: Sequence[str],
    detectable_by_target_id: Dict[str, set[str]],
    viewpoint_id_by_index: Dict[int, str],
) -> Tuple[Dict[str, int], set[str]]:
    raw_case_dir = method.raw_root / case_id
    debug_case_dir = method.debug_root / case_id
    detection_paths = _detection_paths(raw_case_dir)
    active_target_ids = set(target_ids)
    all_target_ids = set(target_ids)
    verified_found_target_ids: set[str] = set()
    counts = {"tp": 0, "fp": 0, "fn": 0}

    for step_index, detection_path in detection_paths:
        episode_state_path = debug_case_dir / (
            "episode_state_step_%04d.json" % step_index
        )
        layout_path = (
            episode_state_path
            if episode_state_path.exists()
            else debug_case_dir / ("graph_layout_step_%04d.json" % step_index)
        )
        layout = _read_json(layout_path)
        agent_current_vp_ids = {
            str(agent_id): int(node_id)
            for agent_id, node_id in layout["agent_current_vp_ids"].items()
        }
        predicted_by_agent = _detection_predictions(_read_json(detection_path))
        claimed_target_ids_this_step: set[str] = set()

        for agent_id, predicted_target_ids in predicted_by_agent.items():
            if agent_id not in agent_current_vp_ids:
                raise ValueError(
                    "%s step %s has detection for unknown agent %s."
                    % (case_id, step_index, agent_id)
                )
            unknown_target_ids = set(predicted_target_ids).difference(all_target_ids)
            if unknown_target_ids:
                raise ValueError(
                    "%s step %s has detection for unknown target ids %s."
                    % (case_id, step_index, sorted(unknown_target_ids))
                )
            inactive_target_ids = set(predicted_target_ids).difference(
                active_target_ids
            )
            if inactive_target_ids:
                raise ValueError(
                    "%s step %s has detection for inactive target ids %s."
                    % (case_id, step_index, sorted(inactive_target_ids))
                )
            claimed_target_ids_this_step.update(predicted_target_ids)

        for agent_id, current_node_id in agent_current_vp_ids.items():
            viewpoint_label = str(viewpoint_id_by_index[current_node_id])
            predicted_target_ids = predicted_by_agent.get(agent_id, set())
            for target_id in sorted(active_target_ids):
                predicted = target_id in predicted_target_ids
                oracle_visible = (
                    viewpoint_label in detectable_by_target_id[target_id]
                )
                if predicted and oracle_visible:
                    counts["tp"] += 1
                    verified_found_target_ids.add(target_id)
                elif predicted and not oracle_visible:
                    counts["fp"] += 1
                elif (not predicted) and oracle_visible:
                    counts["fn"] += 1

        active_target_ids.difference_update(claimed_target_ids_this_step)

    return counts, verified_found_target_ids


def _detection_paths(raw_case_dir: Path) -> List[Tuple[int, Path]]:
    paths: List[Tuple[int, Path]] = []
    for path in raw_case_dir.glob("detection_step_*.json"):
        match = STEP_FILE_RE.match(path.name)
        if match is None:
            continue
        paths.append((int(match.group(1)), path))
    if not paths:
        raise FileNotFoundError("No detection_step_XXXX.json files in %s" % raw_case_dir)
    return sorted(paths)


def _detection_predictions(payload: Dict[str, object]) -> Dict[str, set[str]]:
    predictions: Dict[str, set[str]] = {}
    for detection in payload["detections"]:
        agent_id = str(detection["agent_id"])
        if "found_target_indices" in detection:
            found_target_ids = {
                str(target_id) for target_id in detection["found_target_indices"]
            }
        else:
            found_target_ids = {
                str(target_id)
                for target_id, found in zip(
                    detection["target_indices"],
                    detection["founds"],
                )
                if bool(found)
            }
        predictions.setdefault(agent_id, set()).update(found_target_ids)
    return predictions


def _aggregate_method_metrics(
    case_rows: Sequence[Dict[str, object]],
) -> List[Dict[str, object]]:
    grouped: Dict[str, List[Dict[str, object]]] = {}
    for row in case_rows:
        grouped.setdefault(str(row["method"]), []).append(row)
    return [
        _aggregate_rows(method, rows, extra_fields={})
        for method, rows in grouped.items()
    ]


def _aggregate_group_metrics(
    case_rows: Sequence[Dict[str, object]],
) -> List[Dict[str, object]]:
    grouped: Dict[Tuple[str, int, int], List[Dict[str, object]]] = {}
    for row in case_rows:
        key = (
            str(row["method"]),
            int(row["agent_number"]),
            int(row["target_number"]),
        )
        grouped.setdefault(key, []).append(row)
    rows = []
    for (method, agent_number, target_number), group_rows in sorted(grouped.items()):
        rows.append(
            _aggregate_rows(
                method,
                group_rows,
                extra_fields={
                    "agent_number": agent_number,
                    "target_number": target_number,
                },
            )
        )
    return rows


def _aggregate_rows(
    method: str,
    rows: Sequence[Dict[str, object]],
    extra_fields: Dict[str, object],
) -> Dict[str, object]:
    case_count = len(rows)
    aggregate = {
        "method": method,
        **extra_fields,
        "case_count": case_count,
        "verified_success_rate": _mean(rows, "verified_success"),
        "progress": _mean(rows, "progress"),
        "team_ppl_total": _mean(rows, "team_ppl_total"),
        "team_ppl_makespan": _mean(rows, "team_ppl_makespan"),
        "mean_total_distance": _mean(rows, "total_distance"),
        "mean_maximum_agent_distance": _mean(rows, "maximum_agent_distance"),
    }
    if method == "Oracle":
        aggregate.update(
            {
                "tp": "",
                "fp": "",
                "fn": "",
                "precision": "",
                "recall": "",
                "f1": "",
            }
        )
    else:
        tp = sum(int(row["tp"]) for row in rows)
        fp = sum(int(row["fp"]) for row in rows)
        fn = sum(int(row["fn"]) for row in rows)
        aggregate.update(
            {
                "tp": tp,
                "fp": fp,
                "fn": fn,
                "precision": _ratio_or_empty(tp, tp + fp),
                "recall": _ratio_or_empty(tp, tp + fn),
                "f1": _ratio_or_empty(2 * tp, 2 * tp + fp + fn),
            }
        )
    return aggregate


def _ratio_or_empty(numerator: int, denominator: int) -> float | str:
    if denominator == 0:
        return ""
    return numerator / denominator


def _progress_weighted_path_length(
    progress: float,
    actual_distance: float,
    oracle_distance: float,
) -> float:
    denominator = max(actual_distance, oracle_distance)
    if denominator == 0.0:
        return progress
    return progress * oracle_distance / denominator


def _mean(rows: Sequence[Dict[str, object]], field: str) -> float:
    return sum(float(row[field]) for row in rows) / len(rows)


def _write_csv(
    path: Path,
    rows: Sequence[Dict[str, object]],
    fieldnames: Sequence[str],
) -> None:
    with open(path, "w", encoding="utf-8", newline="") as file_handle:
        writer = csv.DictWriter(file_handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _csv_value(row.get(field, "")) for field in fieldnames})


def _csv_value(value: object) -> object:
    if isinstance(value, float):
        return "%.10g" % value
    return value


def _plot_task_metrics(rows: Sequence[Dict[str, object]], out_dir: Path) -> None:
    metrics = [
        ("verified_success_rate", "VSR"),
        ("progress", "Progress"),
        ("team_ppl_total", "Team-PPL total"),
        ("team_ppl_makespan", "Team-PPL max"),
    ]
    _plot_metric_bars(
        rows=rows,
        metrics=metrics,
        out_prefix=out_dir / "method_comparison_task_metrics",
        ylabel="Score",
        ylim=(0.0, 1.05),
    )


def _plot_detection_metrics(rows: Sequence[Dict[str, object]], out_dir: Path) -> None:
    method_rows = [row for row in rows if str(row["method"]) != "Oracle"]
    metrics = [
        ("precision", "Precision"),
        ("recall", "Recall"),
        ("f1", "F1"),
    ]
    _plot_metric_bars(
        rows=method_rows,
        metrics=metrics,
        out_prefix=out_dir / "method_comparison_detection_metrics",
        ylabel="Score",
        ylim=(0.0, 1.05),
    )


def _plot_metric_bars(
    rows: Sequence[Dict[str, object]],
    metrics: Sequence[Tuple[str, str]],
    out_prefix: Path,
    ylabel: str,
    ylim: Tuple[float, float],
) -> None:
    image = _draw_bar_chart(
        rows=rows,
        metrics=metrics,
        ylabel=ylabel,
        ylim=ylim,
        width=1800,
        height=900,
    )
    _save_image_figure(image, out_prefix)


def _plot_grouped_metrics(
    rows: Sequence[Dict[str, object]],
    out_dir: Path,
) -> None:
    methods = _ordered_unique(str(row["method"]) for row in rows)
    groups = sorted(
        {
            (int(row["agent_number"]), int(row["target_number"]))
            for row in rows
        }
    )
    row_by_key = {
        (str(row["method"]), int(row["agent_number"]), int(row["target_number"])): row
        for row in rows
    }
    labels = ["%dA/%dT" % (agent_number, target_number) for agent_number, target_number in groups]
    panels = [
        ("verified_success_rate", "VSR"),
        ("team_ppl_total", "Team-PPL total"),
    ]

    panel_rows = []
    for metric_field, ylabel in panels:
        panel_rows.append(
            {
                "metric_field": metric_field,
                "ylabel": ylabel,
                "rows": [
                    {
                        "method": method,
                        **{
                            label: float(
                                row_by_key[
                                    (method, agent_number, target_number)
                                ][metric_field]
                            )
                            for label, (agent_number, target_number) in zip(
                                labels,
                                groups,
                            )
                        },
                    }
                    for method in methods
                ],
            }
        )
    image = _draw_grouped_panels(
        panel_rows=panel_rows,
        labels=labels,
        methods=methods,
        width=2100,
        height=1300,
    )
    _save_image_figure(image, out_dir / "grouped_metrics_by_agent_target")


def _draw_bar_chart(
    rows: Sequence[Dict[str, object]],
    metrics: Sequence[Tuple[str, str]],
    ylabel: str,
    ylim: Tuple[float, float],
    width: int,
    height: int,
):
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    fonts = _plot_fonts()
    colors = _plot_colors(len(rows))
    margins = {"left": 145, "right": 55, "top": 110, "bottom": 145}
    plot = _plot_box(width, height, margins)

    _draw_axes_and_grid(image, draw, plot, ylim, ylabel, fonts)
    metric_count = len(metrics)
    method_count = len(rows)
    group_width = plot["width"] / metric_count
    bar_width = min(120.0, group_width * 0.72 / max(1, method_count))
    y_min, y_max = ylim

    for metric_index, (field, label) in enumerate(metrics):
        group_center = plot["left"] + group_width * (metric_index + 0.5)
        _draw_centered_text(
            draw,
            (group_center, plot["bottom"] + 42),
            label,
            fonts["tick"],
            fill=(0, 0, 0),
        )
        for method_index, row in enumerate(rows):
            value = float(row[field])
            bar_center = group_center + (
                method_index - (method_count - 1) / 2.0
            ) * bar_width
            x0 = int(round(bar_center - bar_width * 0.42))
            x1 = int(round(bar_center + bar_width * 0.42))
            y1 = plot["bottom"]
            y0 = _value_to_y(value, y_min, y_max, plot)
            draw.rectangle(
                [x0, y0, x1, y1],
                fill=colors[method_index],
                outline=(0, 0, 0),
                width=2,
            )
            _draw_centered_text(
                draw,
                ((x0 + x1) / 2, y0 - 18),
                _format_score(value),
                fonts["small"],
                fill=(0, 0, 0),
            )

    _draw_legend(
        draw=draw,
        labels=[str(row["method"]) for row in rows],
        colors=colors,
        x=plot["left"],
        y=38,
        fonts=fonts,
    )
    return image


def _draw_grouped_panels(
    panel_rows: Sequence[Dict[str, object]],
    labels: Sequence[str],
    methods: Sequence[str],
    width: int,
    height: int,
):
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    fonts = _plot_fonts()
    colors = _plot_colors(len(methods))
    left = 145
    right = 55
    top = 120
    bottom = 105
    panel_gap = 95
    panel_height = int((height - top - bottom - panel_gap) / len(panel_rows))

    _draw_legend(
        draw=draw,
        labels=list(methods),
        colors=colors,
        x=left,
        y=38,
        fonts=fonts,
    )

    for panel_index, panel in enumerate(panel_rows):
        panel_top = top + panel_index * (panel_height + panel_gap)
        plot = {
            "left": left,
            "right": width - right,
            "top": panel_top,
            "bottom": panel_top + panel_height,
        }
        plot["width"] = plot["right"] - plot["left"]
        plot["height"] = plot["bottom"] - plot["top"]
        _draw_axes_and_grid(image, draw, plot, (0.0, 1.05), str(panel["ylabel"]), fonts)

        group_count = len(labels)
        method_count = len(methods)
        group_width = plot["width"] / group_count
        bar_width = min(55.0, group_width * 0.72 / max(1, method_count))
        rows_by_method = {
            str(row["method"]): row for row in panel["rows"]
        }
        for group_index, label in enumerate(labels):
            group_center = plot["left"] + group_width * (group_index + 0.5)
            if panel_index == len(panel_rows) - 1:
                _draw_centered_text(
                    draw,
                    (group_center, plot["bottom"] + 38),
                    label,
                    fonts["small"],
                    fill=(0, 0, 0),
                )
            for method_index, method in enumerate(methods):
                value = float(rows_by_method[method][label])
                bar_center = group_center + (
                    method_index - (method_count - 1) / 2.0
                ) * bar_width
                x0 = int(round(bar_center - bar_width * 0.42))
                x1 = int(round(bar_center + bar_width * 0.42))
                y1 = plot["bottom"]
                y0 = _value_to_y(value, 0.0, 1.05, plot)
                draw.rectangle(
                    [x0, y0, x1, y1],
                    fill=colors[method_index],
                    outline=(0, 0, 0),
                    width=1,
                )
    _draw_centered_text(
        draw,
        (width / 2, height - 35),
        "Agent/target setting",
        fonts["label"],
        fill=(0, 0, 0),
    )
    return image


def _plot_fonts() -> Dict[str, object]:
    from PIL import ImageFont

    return {
        "tick": ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 32
        ),
        "small": ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 26
        ),
        "label": ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 34
        ),
        "legend": ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 31
        ),
    }


def _plot_colors(count: int) -> List[Tuple[int, int, int]]:
    palette = [
        (76, 114, 176),
        (221, 132, 82),
        (85, 168, 104),
        (196, 78, 82),
        (129, 114, 179),
        (147, 120, 96),
    ]
    return [palette[index % len(palette)] for index in range(count)]


def _plot_box(width: int, height: int, margins: Dict[str, int]) -> Dict[str, int]:
    left = margins["left"]
    right = width - margins["right"]
    top = margins["top"]
    bottom = height - margins["bottom"]
    return {
        "left": left,
        "right": right,
        "top": top,
        "bottom": bottom,
        "width": right - left,
        "height": bottom - top,
    }


def _draw_axes_and_grid(
    image,
    draw,
    plot: Dict[str, int],
    ylim: Tuple[float, float],
    ylabel: str,
    fonts: Dict[str, object],
) -> None:
    y_min, y_max = ylim
    draw.line(
        [(plot["left"], plot["top"]), (plot["left"], plot["bottom"])],
        fill=(0, 0, 0),
        width=3,
    )
    draw.line(
        [(plot["left"], plot["bottom"]), (plot["right"], plot["bottom"])],
        fill=(0, 0, 0),
        width=3,
    )
    for tick in [0.0, 0.25, 0.5, 0.75, 1.0]:
        y = _value_to_y(tick, y_min, y_max, plot)
        draw.line(
            [(plot["left"], y), (plot["right"], y)],
            fill=(210, 210, 210),
            width=1,
        )
        draw.line(
            [(plot["left"] - 10, y), (plot["left"], y)],
            fill=(0, 0, 0),
            width=2,
        )
        _draw_right_text(
            draw,
            (plot["left"] - 18, y),
            _format_score(tick),
            fonts["tick"],
            fill=(0, 0, 0),
        )
    _draw_rotated_text(
        image,
        (48, (plot["top"] + plot["bottom"]) / 2),
        ylabel,
        fonts["label"],
        fill=(0, 0, 0),
    )


def _value_to_y(
    value: float,
    y_min: float,
    y_max: float,
    plot: Dict[str, int],
) -> int:
    fraction = (value - y_min) / (y_max - y_min)
    return int(round(plot["bottom"] - fraction * plot["height"]))


def _draw_centered_text(draw, center, text: str, font, fill) -> None:
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    draw.text(
        (center[0] - text_width / 2, center[1] - text_height / 2),
        text,
        fill=fill,
        font=font,
    )


def _draw_rotated_text(image, center, text: str, font, fill) -> None:
    from PIL import Image, ImageDraw

    measure = Image.new("RGBA", (1, 1), (255, 255, 255, 0))
    measure_draw = ImageDraw.Draw(measure)
    bbox = measure_draw.textbbox((0, 0), text, font=font)
    width = bbox[2] - bbox[0] + 12
    height = bbox[3] - bbox[1] + 12
    text_image = Image.new("RGBA", (width, height), (255, 255, 255, 0))
    text_draw = ImageDraw.Draw(text_image)
    text_draw.text(
        (6 - bbox[0], 6 - bbox[1]),
        text,
        fill=fill,
        font=font,
    )
    rotated = text_image.rotate(90, expand=True)
    image.paste(
        rotated,
        (
            int(round(center[0] - rotated.size[0] / 2)),
            int(round(center[1] - rotated.size[1] / 2)),
        ),
        rotated,
    )


def _draw_right_text(draw, center, text: str, font, fill) -> None:
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    draw.text(
        (center[0] - text_width, center[1] - text_height / 2),
        text,
        fill=fill,
        font=font,
    )


def _draw_legend(
    draw,
    labels: Sequence[str],
    colors: Sequence[Tuple[int, int, int]],
    x: int,
    y: int,
    fonts: Dict[str, object],
) -> None:
    cursor_x = x
    for label, color in zip(labels, colors):
        draw.rectangle(
            [cursor_x, y + 6, cursor_x + 34, y + 34],
            fill=color,
            outline=(0, 0, 0),
            width=1,
        )
        draw.text((cursor_x + 46, y), label, fill=(0, 0, 0), font=fonts["legend"])
        text_bbox = draw.textbbox((0, 0), label, font=fonts["legend"])
        cursor_x += 78 + text_bbox[2] - text_bbox[0]


def _format_score(value: float) -> str:
    return "%.2f" % value


def _save_image_figure(image, out_prefix: Path) -> None:
    image.save(out_prefix.with_suffix(".png"))
    image.save(out_prefix.with_suffix(".pdf"), "PDF", resolution=300.0)


def _ordered_unique(values: Iterable[str]) -> List[str]:
    seen = set()
    unique = []
    for value in values:
        if value not in seen:
            seen.add(value)
            unique.append(value)
    return unique


CASE_METRIC_FIELDS = [
    "method",
    "case_id",
    "scan_id",
    "agent_number",
    "target_number",
    "status",
    "stop_reason",
    "verified_success",
    "progress",
    "team_ppl_total",
    "team_ppl_makespan",
    "total_distance",
    "maximum_agent_distance",
    "oracle_total_distance",
    "oracle_maximum_agent_distance",
    "tp",
    "fp",
    "fn",
    "precision",
    "recall",
    "f1",
]

AGGREGATE_FIELDS = [
    "method",
    "case_count",
    "verified_success_rate",
    "progress",
    "team_ppl_total",
    "team_ppl_makespan",
    "mean_total_distance",
    "mean_maximum_agent_distance",
    "tp",
    "fp",
    "fn",
    "precision",
    "recall",
    "f1",
]

GROUP_AGGREGATE_FIELDS = [
    "method",
    "agent_number",
    "target_number",
    "case_count",
    "verified_success_rate",
    "progress",
    "team_ppl_total",
    "team_ppl_makespan",
    "mean_total_distance",
    "mean_maximum_agent_distance",
    "tp",
    "fp",
    "fn",
    "precision",
    "recall",
    "f1",
]


if __name__ == "__main__":
    raise SystemExit(main())
