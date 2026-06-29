from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple


ORACLE_KEY_FIELDS = ("scan_id", "viewpoint_id", "target_description")
ORACLE_FIELDNAMES = [
    "scan_id",
    "viewpoint_id",
    "viewpoint_index",
    "target_description",
    "representative_case_id",
    "representative_agent_id",
    "representative_image_path",
    "row_count",
    "original_oracle_visible_values",
    "reviewed_visible",
    "review_notes",
]


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


def _oracle_key(row: Dict[str, str]) -> Tuple[str, str, str]:
    return tuple(str(row[field]) for field in ORACLE_KEY_FIELDS)


def _representative_image_path(debug_root: Path, case_id: str, agent_id: str) -> str:
    image_name = "detection_input_step_0001_agent_%s_full_raw_panorama.jpg" % agent_id
    return (debug_root / case_id / image_name).as_posix()


def build_oracle_rows(
    reference_rows: Iterable[Dict[str, str]],
    debug_root: Path,
) -> List[Dict[str, object]]:
    grouped: Dict[Tuple[str, str, str], Dict[str, object]] = {}
    ordered_keys: List[Tuple[str, str, str]] = []

    for row in reference_rows:
        key = _oracle_key(row)
        if key not in grouped:
            grouped[key] = {
                "scan_id": row["scan_id"],
                "viewpoint_id": row["viewpoint_id"],
                "viewpoint_index": row["viewpoint_index"],
                "target_description": row["target_description"],
                "representative_case_id": row["case_id"],
                "representative_agent_id": row["agent_id"],
                "representative_image_path": _representative_image_path(
                    debug_root,
                    row["case_id"],
                    row["agent_id"],
                ),
                "row_count": 0,
                "original_oracle_visible_values": set(),
                "reviewed_visible": "",
                "review_notes": "",
            }
            ordered_keys.append(key)

        grouped_row = grouped[key]
        grouped_row["row_count"] = int(grouped_row["row_count"]) + 1
        grouped_row["original_oracle_visible_values"].add(row["oracle_visible"])

    oracle_rows = []
    for key in ordered_keys:
        row = dict(grouped[key])
        row["original_oracle_visible_values"] = ";".join(
            sorted(str(value) for value in row["original_oracle_visible_values"])
        )
        oracle_rows.append(row)
    return oracle_rows


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a visual-review oracle template from detection target metrics."
        )
    )
    parser.add_argument("--reference-metrics", required=True)
    parser.add_argument("--debug-root", required=True)
    parser.add_argument("--out", required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    reference_metrics = Path(args.reference_metrics)
    debug_root = Path(args.debug_root)
    out_path = Path(args.out)

    reference_rows = _read_csv(reference_metrics)
    oracle_rows = build_oracle_rows(reference_rows, debug_root)
    _write_csv(out_path, oracle_rows, ORACLE_FIELDNAMES)

    print(
        "Wrote %d unique visual oracle rows to %s."
        % (len(oracle_rows), str(out_path))
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
