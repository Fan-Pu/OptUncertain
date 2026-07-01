from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


sys.path.insert(0, str(_project_root()))

from detection_test.evaluate_detection_reviewed_oracle_metrics import (  # noqa: E402
    REVIEWED_CASE_FIELDNAMES,
    REVIEWED_METHOD_FIELDNAMES,
    REVIEWED_TARGET_FIELDNAMES,
    read_reviewed_oracle,
    score_method_rows,
)
from route_plotter import load_environment_graph  # noqa: E402


TARGET_METRIC_FIELDNAMES = [
    "case_id",
    "scan_id",
    "agent_id",
    "viewpoint_id",
    "viewpoint_index",
    "target_id",
    "target_description",
    "oracle_visible",
    "predicted",
    "target_center_x",
    "outcome",
]


def _read_json(path: Path) -> Dict[str, object]:
    with open(path, "r", encoding="utf-8") as file_handle:
        data = json.load(file_handle)
    if not isinstance(data, dict):
        raise TypeError("%s must contain a JSON object." % str(path))
    return data


def _write_csv(
    path: Path,
    rows: Sequence[Dict[str, object]],
    fieldnames: Sequence[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as file_handle:
        writer = csv.DictWriter(file_handle, fieldnames=list(fieldnames))
        writer.writeheader()
        writer.writerows(rows)


def _visibility_by_scan(
    batch_config: Dict[str, object],
) -> Dict[str, Dict[str, set[str]]]:
    return {
        str(scan["scan_id"]): {
            str(target["target_id"]): {
                str(viewpoint_id)
                for viewpoint_id in target.get("detectable_viewpoint_ids", [])
            }
            for target in scan["targets"]
        }
        for scan in batch_config["scans"]
    }


def _viewpoint_indexes_by_scan(
    summary: Dict[str, object],
    connectivity_dir: Path,
) -> Dict[str, Dict[str, int]]:
    case_order = [str(case_id) for case_id in summary["case_order"]]
    scan_ids = sorted(
        {str(summary["cases"][case_id]["scan_id"]) for case_id in case_order}
    )
    indexes_by_scan: Dict[str, Dict[str, int]] = {}
    for scan_id in scan_ids:
        graph = load_environment_graph(
            scan_id=scan_id,
            connectivity_dir=connectivity_dir,
        )
        indexes_by_scan[scan_id] = {
            str(viewpoint_id): int(index)
            for index, viewpoint_id in graph.viewpoint_id_by_index.items()
        }
    return indexes_by_scan


def _prediction_map(detections: Iterable[Dict[str, object]]) -> Dict[str, set[str]]:
    predicted_by_agent: Dict[str, set[str]] = {}
    for detection in detections:
        agent_id = str(detection["agent_id"])
        predicted_by_agent.setdefault(agent_id, set()).update(
            str(target_id) for target_id in detection["found_target_indices"]
        )
    return predicted_by_agent


def _center_x_map(
    detections: Iterable[Dict[str, object]],
) -> Dict[Tuple[str, str], float]:
    centers: Dict[Tuple[str, str], float] = {}
    for detection in detections:
        agent_id = str(detection["agent_id"])
        for target_id, center_x in zip(
            detection["found_target_indices"],
            detection["target_center_xs"],
        ):
            centers[(agent_id, str(target_id))] = float(center_x)
    return centers


def _outcome(predicted: bool, visible: bool) -> str:
    if predicted and visible:
        return "tp"
    if predicted and not visible:
        return "fp"
    if (not predicted) and visible:
        return "fn"
    return "tn"


def build_partial_target_rows(
    summary: Dict[str, object],
    batch_config: Dict[str, object],
    raw_root: Path,
    connectivity_dir: Path,
) -> tuple[List[Dict[str, object]], List[str]]:
    visibility = _visibility_by_scan(batch_config)
    viewpoint_indexes = _viewpoint_indexes_by_scan(
        summary=summary,
        connectivity_dir=connectivity_dir,
    )
    rows: List[Dict[str, object]] = []
    missing_cases: List[str] = []

    for case_id in [str(value) for value in summary["case_order"]]:
        detection_path = raw_root / case_id / "detection_step_0001.json"
        if not detection_path.exists():
            missing_cases.append(case_id)
            continue

        case = summary["cases"][case_id]
        scan_id = str(case["scan_id"])
        detections = _read_json(detection_path)["detections"]
        predicted_by_agent = _prediction_map(detections)
        center_by_agent_target = _center_x_map(detections)
        targets = {
            str(target["target_id"]): target
            for target in case["targets"]
        }

        for agent in case["agents"]:
            agent_id = str(agent["id"])
            viewpoint_id = str(agent["start_viewpoint_id"])
            viewpoint_index = viewpoint_indexes[scan_id][viewpoint_id]
            predicted_target_ids = predicted_by_agent.get(agent_id, set())

            for target_id in sorted(targets):
                target = targets[target_id]
                visible = viewpoint_id in visibility[scan_id][target_id]
                predicted = target_id in predicted_target_ids
                rows.append(
                    {
                        "case_id": case_id,
                        "scan_id": scan_id,
                        "agent_id": agent_id,
                        "viewpoint_id": viewpoint_id,
                        "viewpoint_index": viewpoint_index,
                        "target_id": target_id,
                        "target_description": str(target["description"]),
                        "oracle_visible": int(visible),
                        "predicted": int(predicted),
                        "target_center_x": center_by_agent_target.get(
                            (agent_id, target_id),
                            "",
                        ),
                        "outcome": _outcome(predicted, visible),
                    }
                )

    return rows, missing_cases


def write_partial_reviewed_metrics(
    method_name: str,
    target_rows: Sequence[Dict[str, object]],
    missing_cases: Sequence[str],
    oracle_path: Path,
    out_dir: Path,
) -> Dict[str, object]:
    reviewed_oracle = read_reviewed_oracle(oracle_path)
    reviewed_target_rows, case_rows, method_row, _disagreements = score_method_rows(
        method_name,
        target_rows,
        reviewed_oracle,
    )

    _write_csv(
        out_dir / "reviewed_detection_target_metrics.csv",
        reviewed_target_rows,
        REVIEWED_TARGET_FIELDNAMES,
    )
    _write_csv(
        out_dir / "reviewed_detection_case_metrics.csv",
        case_rows,
        REVIEWED_CASE_FIELDNAMES,
    )
    _write_csv(
        out_dir / "reviewed_detection_method_metrics.csv",
        [method_row],
        REVIEWED_METHOD_FIELDNAMES,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "missing_cases.txt", "w", encoding="utf-8") as file_handle:
        for case_id in missing_cases:
            file_handle.write("%s\n" % str(case_id))
    return method_row


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Score partial saved detection raw outputs against reviewed oracle."
    )
    parser.add_argument("--method-name", default="GPT55Partial")
    parser.add_argument(
        "--manifest",
        default=(
            "mllm_debug_outputs_detection_eval_gpt-5.5-2026-04-23/"
            "batch_test/sampled_generated_cases.json"
        ),
    )
    parser.add_argument("--batch-config", default="scenarios/batch_test.json")
    parser.add_argument(
        "--raw-root",
        default="detection_test/mllm_raw_outputs_detection_eval_gpt-5.5-2026-04-23",
    )
    parser.add_argument(
        "--oracle",
        default=(
            "detection_test/mllm_debug_outputs_detection_reviewed_oracle_metrics/"
            "batch_test/detection_visual_oracle_review.csv"
        ),
    )
    parser.add_argument("--connectivity-dir", default="connectivity")
    parser.add_argument(
        "--out",
        default=(
            "detection_test/mllm_debug_outputs_detection_reviewed_oracle_metrics/"
            "batch_test_partial_gpt55"
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    summary = _read_json(Path(args.manifest))
    batch_config = _read_json(Path(args.batch_config))
    target_rows, missing_cases = build_partial_target_rows(
        summary=summary,
        batch_config=batch_config,
        raw_root=Path(args.raw_root),
        connectivity_dir=Path(args.connectivity_dir),
    )
    method_row = write_partial_reviewed_metrics(
        method_name=str(args.method_name),
        target_rows=target_rows,
        missing_cases=missing_cases,
        oracle_path=Path(args.oracle),
        out_dir=Path(args.out),
    )

    print(
        "Wrote partial reviewed metrics for %s: %d cases, %d pairs, F1 %.6f."
        % (
            str(args.method_name),
            int(method_row["case_count"]),
            int(method_row["agent_target_pairs"]),
            float(method_row["f1"]),
        )
    )
    print("Missing cases: %d." % len(missing_cases))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
