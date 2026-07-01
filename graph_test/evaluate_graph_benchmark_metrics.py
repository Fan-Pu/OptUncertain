from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from evaluate_batch_metrics import (  # noqa: E402
    _method_case_metrics,
    _oracle_case_metrics,
    _raw_root_for_debug_root,
    _scan_target_detectable_viewpoints,
)
from graph_test.evaluate_graph_model import (  # noqa: E402
    DEFAULT_GRAPH_TEST_CASE_ID,
    GRAPH_TEST_MAX_STEPS,
)


CASE_FIELDS = [
    "method",
    "case_id",
    "scan_id",
    "agent_number",
    "target_number",
    "max_steps",
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
    "graph_call_count",
    "detection_call_count",
    "graph_validation_error_count",
    "detection_validation_error_count",
]

METHOD_FIELDS = [
    "method",
    "case_count",
    "max_steps",
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
    "graph_call_count",
    "detection_call_count",
    "graph_validation_error_count",
    "detection_validation_error_count",
]


@dataclass(frozen=True)
class GraphMethodSpec:
    name: str
    debug_root: Path
    raw_root: Path


def _resolve_path(path: str | Path) -> Path:
    path = Path(path)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path


def _read_json(path: Path) -> object:
    with open(path, "r", encoding="utf-8") as file_handle:
        return json.load(file_handle)


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


def _parse_method_spec(spec: str) -> GraphMethodSpec:
    if "=" not in spec:
        raise ValueError("--method must use NAME=DEBUG_ROOT form: %s" % spec)
    name, debug_root_raw = spec.split("=", 1)
    if not name:
        raise ValueError("Method name cannot be empty in %s." % spec)
    debug_root = _resolve_path(debug_root_raw)
    return GraphMethodSpec(
        name=name,
        debug_root=debug_root,
        raw_root=_raw_root_for_debug_root(debug_root),
    )


def _sampled_manifest_path(method: GraphMethodSpec, batch_id: str) -> Path:
    return method.debug_root / batch_id / "sampled_generated_cases.json"


def _route_summary_path(method: GraphMethodSpec, case_id: str) -> Path:
    return method.debug_root / case_id / ("%s_mllm_route_summary.txt" % case_id)


def _case_identity(case: Dict[str, object]) -> Dict[str, object]:
    return {
        "test_case": str(case["test_case"]),
        "scan_id": str(case["scan_id"]),
        "agent_number": int(case["agent_number"]),
        "target_number": int(case["target_number"]),
        "max_steps": int(case["max_steps"]),
        "agents": case["agents"],
        "targets": case["targets"],
    }


def _load_method_case(
    method: GraphMethodSpec,
    batch_id: str,
    case_id: str,
    max_steps: int,
) -> Dict[str, object]:
    manifest = _read_json(_sampled_manifest_path(method, batch_id))
    if not isinstance(manifest, dict):
        raise TypeError("%s must contain a JSON object." % _sampled_manifest_path(method, batch_id))
    case_order = [str(value) for value in manifest["case_order"]]
    if case_order != [str(case_id)]:
        raise ValueError(
            "%s must contain exactly case_order [%s]; got %s."
            % (_sampled_manifest_path(method, batch_id), case_id, case_order)
        )
    case = manifest["cases"][str(case_id)]
    if int(case["agent_number"]) != 3:
        raise ValueError("%s must have exactly 3 agents." % case_id)
    if int(case["max_steps"]) != int(max_steps):
        raise ValueError(
            "%s generated case max_steps is %s; expected %s."
            % (method.name, int(case["max_steps"]), int(max_steps))
        )
    route_summary = _read_json(_route_summary_path(method, case_id))
    if int(route_summary["max_steps"]) != int(max_steps):
        raise ValueError(
            "%s route summary max_steps is %s; expected %s."
            % (method.name, int(route_summary["max_steps"]), int(max_steps))
        )
    return case


def _count_files(path: Path, pattern: str) -> int:
    return len(list(path.glob(pattern)))


def _call_count_fields(method: GraphMethodSpec, case_id: str) -> Dict[str, int]:
    raw_case_dir = method.raw_root / case_id
    return {
        "graph_call_count": _count_files(raw_case_dir, "semantic_step_*.json"),
        "detection_call_count": _count_files(raw_case_dir, "detection_step_*.json"),
        "graph_validation_error_count": _count_files(
            raw_case_dir,
            "semantic_step_*_attempt_*_error.txt",
        ),
        "detection_validation_error_count": _count_files(
            raw_case_dir,
            "detection_step_*_attempt_*_error.txt",
        ),
    }


def _ratio_or_empty(numerator: int, denominator: int) -> float | str:
    if int(denominator) == 0:
        return ""
    return float(numerator) / float(denominator)


def _mean(rows: Sequence[Dict[str, object]], field: str) -> float:
    return sum(float(row[field]) for row in rows) / len(rows)


def _aggregate_method_rows(case_rows: Sequence[Dict[str, object]]) -> List[Dict[str, object]]:
    grouped: Dict[str, List[Dict[str, object]]] = {}
    for row in case_rows:
        grouped.setdefault(str(row["method"]), []).append(row)

    rows = []
    for method, group in grouped.items():
        aggregate: Dict[str, object] = {
            "method": method,
            "case_count": len(group),
            "max_steps": int(group[0]["max_steps"]),
            "verified_success_rate": _mean(group, "verified_success"),
            "progress": _mean(group, "progress"),
            "team_ppl_total": _mean(group, "team_ppl_total"),
            "team_ppl_makespan": _mean(group, "team_ppl_makespan"),
            "mean_total_distance": _mean(group, "total_distance"),
            "mean_maximum_agent_distance": _mean(group, "maximum_agent_distance"),
            "graph_call_count": sum(int(row["graph_call_count"]) for row in group),
            "detection_call_count": sum(
                int(row["detection_call_count"]) for row in group
            ),
            "graph_validation_error_count": sum(
                int(row["graph_validation_error_count"]) for row in group
            ),
            "detection_validation_error_count": sum(
                int(row["detection_validation_error_count"]) for row in group
            ),
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
            tp = sum(int(row["tp"]) for row in group)
            fp = sum(int(row["fp"]) for row in group)
            fn = sum(int(row["fn"]) for row in group)
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
        rows.append(aggregate)
    return rows


def evaluate_graph_methods(
    *,
    batch_config: Dict[str, object],
    oracle_summaries: Dict[str, object],
    method_specs: Sequence[GraphMethodSpec],
    batch_id: str,
    case_id: str,
    max_steps: int,
    connectivity_dir: Path,
) -> tuple[List[Dict[str, object]], List[Dict[str, object]]]:
    if int(max_steps) != GRAPH_TEST_MAX_STEPS:
        raise ValueError("Graph benchmark max_steps must be exactly 10.")
    if not method_specs:
        raise ValueError("At least one --method is required.")

    scan_targets = _scan_target_detectable_viewpoints(batch_config)
    oracle_summary = oracle_summaries["cases"][str(case_id)]
    reference_case = _load_method_case(method_specs[0], batch_id, case_id, max_steps)
    reference_identity = _case_identity(reference_case)

    case_rows: List[Dict[str, object]] = []
    oracle_row = _oracle_case_metrics(
        case_id=case_id,
        generated_case=reference_case,
        oracle_summary=oracle_summary,
    )
    oracle_row.update(
        {
            "max_steps": max_steps,
            "graph_call_count": 0,
            "detection_call_count": 0,
            "graph_validation_error_count": 0,
            "detection_validation_error_count": 0,
        }
    )
    case_rows.append(oracle_row)

    for method in method_specs:
        generated_case = _load_method_case(method, batch_id, case_id, max_steps)
        if _case_identity(generated_case) != reference_identity:
            raise ValueError("%s did not use the same generated case." % method.name)
        method_row = _method_case_metrics(
            method=method,
            case_id=case_id,
            generated_case=generated_case,
            oracle_summary=oracle_summary,
            scan_targets=scan_targets,
            connectivity_dir=connectivity_dir,
        )
        method_row["max_steps"] = max_steps
        method_row.update(_call_count_fields(method, case_id))
        case_rows.append(method_row)

    return case_rows, _aggregate_method_rows(case_rows)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare saved single-case graph benchmark runs."
    )
    parser.add_argument("--batch-config", required=True)
    parser.add_argument("--case-id", default=DEFAULT_GRAPH_TEST_CASE_ID)
    parser.add_argument("--max-steps", type=int, default=GRAPH_TEST_MAX_STEPS)
    parser.add_argument("--oracle-summaries", required=True)
    parser.add_argument("--connectivity-dir", default="connectivity")
    parser.add_argument("--batch-id", default="batch_test")
    parser.add_argument("--method", required=True, action="append")
    parser.add_argument("--out", required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    batch_config = _read_json(_resolve_path(args.batch_config))
    if not isinstance(batch_config, dict):
        raise TypeError("Batch config must be a JSON object.")
    oracle_summaries = _read_json(_resolve_path(args.oracle_summaries))
    if not isinstance(oracle_summaries, dict):
        raise TypeError("Oracle summaries must be a JSON object.")
    method_specs = [_parse_method_spec(spec) for spec in args.method]
    case_rows, method_rows = evaluate_graph_methods(
        batch_config=batch_config,
        oracle_summaries=oracle_summaries,
        method_specs=method_specs,
        batch_id=str(args.batch_id),
        case_id=str(args.case_id),
        max_steps=int(args.max_steps),
        connectivity_dir=_resolve_path(args.connectivity_dir),
    )
    out_dir = _resolve_path(args.out)
    _write_csv(out_dir / "graph_case_metrics.csv", case_rows, CASE_FIELDS)
    _write_csv(out_dir / "graph_method_metrics.csv", method_rows, METHOD_FIELDS)
    print("Wrote graph case metrics to %s." % (out_dir / "graph_case_metrics.csv"))
    print("Wrote graph method metrics to %s." % (out_dir / "graph_method_metrics.csv"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
