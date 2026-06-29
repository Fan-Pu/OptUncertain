from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple


ORACLE_KEY_FIELDS = ("scan_id", "viewpoint_id", "target_description")
REVIEWED_TARGET_FIELDNAMES = [
    "method",
    "case_id",
    "scan_id",
    "agent_id",
    "viewpoint_id",
    "viewpoint_index",
    "target_id",
    "target_description",
    "original_oracle_visible",
    "reviewed_visible",
    "predicted",
    "target_center_x",
    "original_outcome",
    "reviewed_outcome",
]
REVIEWED_CASE_FIELDNAMES = [
    "method",
    "case_id",
    "scan_id",
    "agent_target_pairs",
    "tp",
    "fp",
    "fn",
    "tn",
    "precision",
    "recall",
    "f1",
]
REVIEWED_METHOD_FIELDNAMES = [
    "method",
    "case_count",
    "agent_target_pairs",
    "tp",
    "fp",
    "fn",
    "tn",
    "precision",
    "recall",
    "f1",
]
ORACLE_DISAGREEMENT_FIELDNAMES = [
    "method",
    "case_id",
    "scan_id",
    "agent_id",
    "viewpoint_id",
    "viewpoint_index",
    "target_id",
    "target_description",
    "original_oracle_visible",
    "reviewed_visible",
    "predicted",
    "original_outcome",
    "reviewed_outcome",
]


@dataclass(frozen=True)
class MethodSpec:
    name: str
    debug_root: Path


def _ratio(numerator: int, denominator: int) -> float:
    return float(numerator) / float(denominator) if int(denominator) else 0.0


def _f1(tp: int, fp: int, fn: int) -> float:
    denominator = 2 * int(tp) + int(fp) + int(fn)
    return float(2 * int(tp)) / float(denominator) if denominator else 0.0


def _read_csv(path: Path) -> List[Dict[str, str]]:
    with open(path, "r", encoding="utf-8", newline="") as file_handle:
        return list(csv.DictReader(file_handle))


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


def _parse_binary(value: str, field_name: str) -> int:
    if value not in ("0", "1", 0, 1):
        raise ValueError("%s must be 0 or 1; got %r." % (field_name, value))
    return int(value)


def _oracle_key(row: Dict[str, str]) -> Tuple[str, str, str]:
    return tuple(str(row[field]) for field in ORACLE_KEY_FIELDS)


def read_reviewed_oracle(path: Path) -> Dict[Tuple[str, str, str], int]:
    oracle: Dict[Tuple[str, str, str], int] = {}
    for row in _read_csv(path):
        key = _oracle_key(row)
        if key in oracle:
            raise ValueError("Duplicate reviewed oracle key: %r." % (key,))
        reviewed_visible = str(row["reviewed_visible"]).strip()
        oracle[key] = _parse_binary(reviewed_visible, "reviewed_visible")
    return oracle


def _outcome(predicted: int, visible: int) -> str:
    if predicted and visible:
        return "tp"
    if predicted and not visible:
        return "fp"
    if (not predicted) and visible:
        return "fn"
    return "tn"


def _empty_counts() -> Dict[str, int]:
    return {"tp": 0, "fp": 0, "fn": 0, "tn": 0}


def _metric_row(prefix: Dict[str, object], counts: Dict[str, int]) -> Dict[str, object]:
    tp = int(counts["tp"])
    fp = int(counts["fp"])
    fn = int(counts["fn"])
    tn = int(counts["tn"])
    row = dict(prefix)
    row.update(
        {
            "agent_target_pairs": tp + fp + fn + tn,
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "tn": tn,
            "precision": _ratio(tp, tp + fp),
            "recall": _ratio(tp, tp + fn),
            "f1": _f1(tp, fp, fn),
        }
    )
    return row


def score_method_rows(
    method_name: str,
    target_rows: Iterable[Dict[str, str]],
    reviewed_oracle: Dict[Tuple[str, str, str], int],
) -> tuple[
    List[Dict[str, object]],
    List[Dict[str, object]],
    Dict[str, object],
    List[Dict[str, object]],
]:
    reviewed_target_rows: List[Dict[str, object]] = []
    disagreement_rows: List[Dict[str, object]] = []
    case_counts: Dict[Tuple[str, str], Dict[str, int]] = {}
    method_counts = _empty_counts()

    for row in target_rows:
        key = _oracle_key(row)
        if key not in reviewed_oracle:
            raise KeyError("No reviewed oracle label for key %r." % (key,))

        original_visible = _parse_binary(
            str(row["oracle_visible"]).strip(),
            "oracle_visible",
        )
        reviewed_visible = reviewed_oracle[key]
        predicted = _parse_binary(str(row["predicted"]).strip(), "predicted")
        reviewed_outcome = _outcome(predicted, reviewed_visible)
        original_outcome = str(row["outcome"])

        case_key = (row["case_id"], row["scan_id"])
        if case_key not in case_counts:
            case_counts[case_key] = _empty_counts()
        case_counts[case_key][reviewed_outcome] += 1
        method_counts[reviewed_outcome] += 1

        reviewed_row = {
            "method": method_name,
            "case_id": row["case_id"],
            "scan_id": row["scan_id"],
            "agent_id": row["agent_id"],
            "viewpoint_id": row["viewpoint_id"],
            "viewpoint_index": row["viewpoint_index"],
            "target_id": row["target_id"],
            "target_description": row["target_description"],
            "original_oracle_visible": original_visible,
            "reviewed_visible": reviewed_visible,
            "predicted": predicted,
            "target_center_x": row.get("target_center_x", ""),
            "original_outcome": original_outcome,
            "reviewed_outcome": reviewed_outcome,
        }
        reviewed_target_rows.append(reviewed_row)

        if original_visible != reviewed_visible:
            disagreement_rows.append(
                {
                    field: reviewed_row[field]
                    for field in ORACLE_DISAGREEMENT_FIELDNAMES
                }
            )

    case_rows = [
        _metric_row(
            {
                "method": method_name,
                "case_id": case_id,
                "scan_id": scan_id,
            },
            counts,
        )
        for (case_id, scan_id), counts in case_counts.items()
    ]
    method_row = _metric_row(
        {
            "method": method_name,
            "case_count": len(case_rows),
        },
        method_counts,
    )
    return reviewed_target_rows, case_rows, method_row, disagreement_rows


def _parse_method_spec(spec: str) -> MethodSpec:
    if "=" not in spec:
        raise ValueError("--method must use NAME=DEBUG_ROOT form: %s" % spec)
    name, debug_root_raw = spec.split("=", 1)
    if not name:
        raise ValueError("Method name cannot be empty in %s." % spec)
    return MethodSpec(name=name, debug_root=Path(debug_root_raw))


def _target_metrics_path(method: MethodSpec, batch_id: str) -> Path:
    return (
        method.debug_root
        / batch_id
        / "detection_metrics"
        / "detection_target_metrics.csv"
    )


def evaluate_methods(
    method_specs: Sequence[MethodSpec],
    reviewed_oracle: Dict[Tuple[str, str, str], int],
    batch_id: str,
    expected_pairs: int,
) -> tuple[
    List[Dict[str, object]],
    List[Dict[str, object]],
    List[Dict[str, object]],
    List[Dict[str, object]],
]:
    all_target_rows: List[Dict[str, object]] = []
    all_case_rows: List[Dict[str, object]] = []
    method_rows: List[Dict[str, object]] = []
    all_disagreement_rows: List[Dict[str, object]] = []

    for method in method_specs:
        target_rows = _read_csv(_target_metrics_path(method, batch_id))
        (
            reviewed_target_rows,
            case_rows,
            method_row,
            disagreement_rows,
        ) = score_method_rows(method.name, target_rows, reviewed_oracle)
        if int(method_row["agent_target_pairs"]) != int(expected_pairs):
            raise ValueError(
                "%s evaluated %d pairs; expected %d."
                % (
                    method.name,
                    int(method_row["agent_target_pairs"]),
                    int(expected_pairs),
                )
            )
        all_target_rows.extend(reviewed_target_rows)
        all_case_rows.extend(case_rows)
        method_rows.append(method_row)
        all_disagreement_rows.extend(disagreement_rows)

    return all_target_rows, all_case_rows, method_rows, all_disagreement_rows


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Recompute saved detection metrics against a reviewed oracle."
    )
    parser.add_argument("--oracle", required=True)
    parser.add_argument(
        "--method",
        required=True,
        action="append",
        help="Method spec in NAME=DEBUG_ROOT form.",
    )
    parser.add_argument("--batch-id", default="batch_test")
    parser.add_argument("--expected-pairs", type=int, default=440)
    parser.add_argument("--out", required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    reviewed_oracle = read_reviewed_oracle(Path(args.oracle))
    method_specs = [_parse_method_spec(spec) for spec in args.method]
    (
        target_rows,
        case_rows,
        method_rows,
        disagreement_rows,
    ) = evaluate_methods(
        method_specs=method_specs,
        reviewed_oracle=reviewed_oracle,
        batch_id=str(args.batch_id),
        expected_pairs=int(args.expected_pairs),
    )

    out_dir = Path(args.out)
    _write_csv(
        out_dir / "reviewed_detection_target_metrics.csv",
        target_rows,
        REVIEWED_TARGET_FIELDNAMES,
    )
    _write_csv(
        out_dir / "reviewed_detection_case_metrics.csv",
        case_rows,
        REVIEWED_CASE_FIELDNAMES,
    )
    _write_csv(
        out_dir / "reviewed_detection_method_metrics.csv",
        method_rows,
        REVIEWED_METHOD_FIELDNAMES,
    )
    _write_csv(
        out_dir / "oracle_disagreements.csv",
        disagreement_rows,
        ORACLE_DISAGREEMENT_FIELDNAMES,
    )

    print(
        "Wrote reviewed detection method metrics to %s."
        % str(out_dir / "reviewed_detection_method_metrics.csv")
    )
    print(
        "Wrote reviewed detection target metrics to %s."
        % str(out_dir / "reviewed_detection_target_metrics.csv")
    )
    print("Wrote oracle disagreements to %s." % str(out_dir / "oracle_disagreements.csv"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
