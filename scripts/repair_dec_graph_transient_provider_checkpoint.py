#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEBUG_ROOT = PROJECT_ROOT / "mllm_debug_outputs_balanced100_DecGraph"
PROGRESS_PATH = DEBUG_ROOT / "batch_test" / "batch_progress.json"
SKIPPED_PATH = DEBUG_ROOT / "batch_test" / "skipped_cases.json"
EVENTS_PATH = PROJECT_ROOT / "batch_logs" / "DecGraph_progress_events.jsonl"
TRANSIENT_MARKERS = (
    "504 Gateway Timeout",
    "Gateway Timeout",
    "502 Bad Gateway",
    "503 Service Unavailable",
    "Internal Server Error",
    "EngineCore encountered an issue",
)


def read_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return payload


def write_json(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def is_transient_provider_failure(record: object) -> bool:
    if not isinstance(record, dict):
        return False
    if record.get("reason") != "dec_graph_agent_phase_error":
        return False
    error = str(record.get("error", ""))
    return any(marker in error for marker in TRANSIENT_MARKERS)


def move_if_present(source: Path, quarantine: Path, moved: list[str]) -> None:
    if not source.exists():
        return
    destination = quarantine / source.relative_to(PROJECT_ROOT)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(destination))
    moved.append(str(source.relative_to(PROJECT_ROOT)))


def main() -> int:
    progress = read_json(PROGRESS_PATH)
    skipped = read_json(SKIPPED_PATH)
    progress_skips = dict(progress.get("skipped_cases", {}))
    ledger_skips = dict(skipped.get("cases", {}))
    invalid_ids = [
        str(case_id)
        for case_id in progress.get("case_order", [])
        if is_transient_provider_failure(progress_skips.get(str(case_id)))
    ]
    if not invalid_ids:
        raise RuntimeError("No Dec-Graph transient-provider failures were found")
    ledger_invalid_ids = {
        case_id
        for case_id, record in ledger_skips.items()
        if is_transient_provider_failure(record)
    }
    if set(invalid_ids) != ledger_invalid_ids:
        raise RuntimeError(
            "Progress and skip ledger disagree on transient-provider failures"
        )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    quarantine = (
        PROJECT_ROOT / "batch_logs" / f"DecGraph_transient_quarantine_{stamp}"
    )
    quarantine.mkdir(parents=True, exist_ok=False)
    shutil.copy2(PROGRESS_PATH, quarantine / "batch_progress.original.json")
    shutil.copy2(SKIPPED_PATH, quarantine / "skipped_cases.original.json")
    if EVENTS_PATH.exists():
        shutil.copy2(EVENTS_PATH, quarantine / "progress_events.original.jsonl")

    moved: list[str] = []
    for case_id in invalid_ids:
        failed_step = int(progress_skips[case_id]["failed_step_index"])
        case_dir = DEBUG_ROOT / case_id
        move_if_present(
            case_dir / f"dec_graph_step_{failed_step:04d}.json",
            quarantine,
            moved,
        )
        move_if_present(
            case_dir / f"{case_id}_mllm_route_summary.txt",
            quarantine,
            moved,
        )
        del progress_skips[case_id]
        del ledger_skips[case_id]

    progress["skipped_cases"] = progress_skips
    progress["skipped_case_count"] = len(progress_skips)
    progress["completed_case_count"] = len(progress.get("completed_cases", {}))
    accounted_ids = set(progress.get("completed_cases", {})) | set(progress_skips)
    progress["next_case_id"] = next(
        (
            str(case_id)
            for case_id in progress["case_order"]
            if str(case_id) not in accounted_ids
        ),
        None,
    )
    progress["status"] = "running"
    progress["terminated_case"] = None
    skipped["cases"] = ledger_skips
    skipped["skipped_case_count"] = len(ledger_skips)

    if EVENTS_PATH.exists():
        invalid_id_set = set(invalid_ids)
        kept_lines = []
        for line in EVENTS_PATH.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            if str(json.loads(line).get("case_id")) not in invalid_id_set:
                kept_lines.append(line)
        temporary = EVENTS_PATH.with_suffix(EVENTS_PATH.suffix + ".tmp")
        temporary.write_text(
            "\n".join(kept_lines) + ("\n" if kept_lines else ""),
            encoding="utf-8",
        )
        temporary.replace(EVENTS_PATH)

    write_json(PROGRESS_PATH, progress)
    write_json(SKIPPED_PATH, skipped)
    audit = {
        "repair": "remove_dec_graph_transient_provider_checkpoints",
        "invalid_case_ids": invalid_ids,
        "new_completed_case_count": progress["completed_case_count"],
        "new_skipped_case_count": progress["skipped_case_count"],
        "new_next_case_id": progress["next_case_id"],
        "preserved_detection_outputs_and_caches": True,
        "moved_files": moved,
    }
    write_json(quarantine / "repair_audit.json", audit)
    print(json.dumps(audit, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
