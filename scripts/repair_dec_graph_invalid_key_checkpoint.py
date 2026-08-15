#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEBUG_ROOT = PROJECT_ROOT / "mllm_debug_outputs_balanced100_DecGraph"
RAW_ROOT = PROJECT_ROOT / "mllm_raw_outputs_balanced100_DecGraph"
PROGRESS_PATH = DEBUG_ROOT / "batch_test" / "batch_progress.json"
SKIPPED_PATH = DEBUG_ROOT / "batch_test" / "skipped_cases.json"
EVENTS_PATH = PROJECT_ROOT / "batch_logs" / "DecGraph_progress_events.jsonl"


def read_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return payload


def write_json(path: Path, payload: dict) -> None:
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(payload, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    temp_path.replace(path)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def is_invalid_openai_key_failure(record: object) -> bool:
    if not isinstance(record, dict):
        return False
    error = str(record.get("error", ""))
    return (
        record.get("reason") == "mllm_retry_exhausted"
        and record.get("mllm_stage") == "detection"
        and "invalid_api_key" in error
        and "Incorrect API key provided: hf_" in error
    )


def main() -> int:
    progress = read_json(PROGRESS_PATH)
    skipped = read_json(SKIPPED_PATH)
    skipped_cases = dict(progress["skipped_cases"])
    ledger_cases = dict(skipped["cases"])

    invalid_ids = [
        str(case_id)
        for case_id in progress["case_order"]
        if is_invalid_openai_key_failure(skipped_cases.get(str(case_id)))
    ]
    if invalid_ids != [
        "r47D5H71a5s_case_0008",
        "r47D5H71a5s_case_0009",
        "r47D5H71a5s_case_0010",
    ]:
        raise RuntimeError(
            "Unexpected invalid-key checkpoint set: %s" % invalid_ids
        )
    for case_id in invalid_ids:
        if ledger_cases.get(case_id) != skipped_cases[case_id]:
            raise RuntimeError(
                "Skipped ledger differs from batch progress for %s" % case_id
            )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    quarantine = (
        PROJECT_ROOT
        / "batch_logs"
        / ("DecGraph_invalid_key_quarantine_%s" % stamp)
    )
    quarantine.mkdir(parents=True)

    source_hashes = {
        str(path.relative_to(PROJECT_ROOT)): sha256(path)
        for path in (PROGRESS_PATH, SKIPPED_PATH, EVENTS_PATH)
    }
    for path in (PROGRESS_PATH, SKIPPED_PATH, EVENTS_PATH):
        shutil.copy2(path, quarantine / path.name)

    moved_files: list[str] = []
    for case_id in invalid_ids:
        case_quarantine = quarantine / case_id
        case_quarantine.mkdir()
        route_summary = DEBUG_ROOT / case_id / (
            "%s_mllm_route_summary.txt" % case_id
        )
        if not route_summary.is_file():
            raise FileNotFoundError(route_summary)
        destination = case_quarantine / route_summary.name
        shutil.move(str(route_summary), str(destination))
        moved_files.append(str(route_summary.relative_to(PROJECT_ROOT)))

        failed_step = int(skipped_cases[case_id]["failed_step_index"])
        raw_case_root = RAW_ROOT / case_id
        error_files = sorted(
            raw_case_root.glob(
                "detection_step_%04d_attempt_*_error.txt" % failed_step
            )
        )
        if len(error_files) != int(skipped_cases[case_id]["mllm_attempts"]):
            raise RuntimeError(
                "Expected %s error attempts for %s step %s, found %s"
                % (
                    skipped_cases[case_id]["mllm_attempts"],
                    case_id,
                    failed_step,
                    len(error_files),
                )
            )
        raw_quarantine = case_quarantine / "raw_errors"
        raw_quarantine.mkdir()
        for error_path in error_files:
            shutil.move(str(error_path), str(raw_quarantine / error_path.name))
            moved_files.append(str(error_path.relative_to(PROJECT_ROOT)))

    for case_id in invalid_ids:
        del skipped_cases[case_id]
        del ledger_cases[case_id]
    progress["skipped_cases"] = skipped_cases
    progress["skipped_case_count"] = len(skipped_cases)
    skipped["cases"] = ledger_cases
    skipped["skipped_case_count"] = len(ledger_cases)

    completed_ids = set(progress["completed_cases"])
    skipped_ids = set(skipped_cases)
    progress["next_case_id"] = next(
        str(case_id)
        for case_id in progress["case_order"]
        if str(case_id) not in completed_ids and str(case_id) not in skipped_ids
    )
    progress["status"] = "running"
    progress["terminated_case"] = None

    event_lines = [
        line
        for line in EVENTS_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    kept_events = [
        line
        for line in event_lines
        if str(json.loads(line)["case_id"]) not in set(invalid_ids)
    ]
    if len(event_lines) - len(kept_events) != len(invalid_ids):
        raise RuntimeError("Progress-event ledger does not match invalid cases")

    write_json(PROGRESS_PATH, progress)
    write_json(SKIPPED_PATH, skipped)
    events_temp = EVENTS_PATH.with_suffix(EVENTS_PATH.suffix + ".tmp")
    events_temp.write_text("\n".join(kept_events) + "\n", encoding="utf-8")
    events_temp.replace(EVENTS_PATH)

    audit = {
        "repair": "remove_dec_graph_openai_401_invalid_key_checkpoints",
        "invalid_case_ids": invalid_ids,
        "preserved_valid_skipped_case_ids": sorted(skipped_cases),
        "new_skipped_case_count": len(skipped_cases),
        "new_next_case_id": progress["next_case_id"],
        "source_sha256": source_hashes,
        "moved_files": moved_files,
    }
    write_json(quarantine / "repair_audit.json", audit)
    print(json.dumps(audit, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
