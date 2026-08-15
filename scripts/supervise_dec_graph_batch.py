#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = PROJECT_ROOT / "batch_logs"
BATCH_CONFIG = "scenarios/batch_test.json"
LABEL = "DecGraph"
PROGRESS_PATH = (
    PROJECT_ROOT
    / "mllm_debug_outputs_balanced100_DecGraph"
    / "batch_test"
    / "batch_progress.json"
)
EVENTS_PATH = LOG_DIR / f"{LABEL}_progress_events.jsonl"
DONE_PATH = LOG_DIR / f"{LABEL}_supervisor.done"

RATE_LIMIT_MARKERS = (
    "rate_limit_exceeded",
    "RateLimitError",
    "Error code: 429",
    "429 Too Many Requests",
)
TRANSIENT_PROVIDER_MARKERS = (
    "InternalServerError",
    "Error code: 500",
    "Internal Error",
    "Error code: 502",
    "502 Bad Gateway",
    "Error code: 503",
    "503 Service Unavailable",
    "Error code: 504",
    "504 Gateway Timeout",
    "Gateway Timeout",
    "ReadTimeout",
    "ConnectError",
    "RemoteProtocolError",
)
OPENGL_MARKER = "OpenGL error 0x501"


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def load_progress() -> dict:
    if not PROGRESS_PATH.exists():
        return {}
    return json.loads(PROGRESS_PATH.read_text(encoding="utf-8"))


def accounted(progress: dict) -> int:
    return int(progress.get("completed_case_count", 0)) + int(
        progress.get("skipped_case_count", 0)
    )


def is_complete(progress: dict) -> bool:
    return progress.get("status") == "completed" and accounted(progress) >= 100


def kill_stale_debugpy() -> None:
    for pattern in ("[d]ebugpy_attach_continue.py", "[d]ebugpy/adapter"):
        subprocess.run(
            ["pkill", "-f", pattern],
            cwd=PROJECT_ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )


def read_tail(path: Path, max_chars: int = 24000) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")[-max_chars:]


def reported_case_ids() -> set[str]:
    if not EVENTS_PATH.exists():
        return set()
    return {
        str(json.loads(line)["case_id"])
        for line in EVENTS_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def case_log_section(log_path: Path, case_id: str) -> str:
    if not log_path.exists():
        return ""
    text = log_path.read_text(encoding="utf-8", errors="replace")
    marker = f"Running generated batch case {case_id}."
    start = text.rfind(marker)
    if start < 0:
        return ""
    next_start = text.find("Running generated batch case ", start + len(marker))
    return text[start:] if next_start < 0 else text[start:next_start]


def case_runtime_stats(log_path: Path, case_id: str) -> dict:
    section = case_log_section(log_path, case_id)
    return {
        "detection_cache_hits": section.count(
            "Reading shared detection cache for step"
        ),
        "detection_cache_misses": section.count(
            "Shared detection cache miss for step"
        ),
        "saved_detection_replays": section.count(
            "Reading saved detection raw output for step"
        ),
        "detection_cache_updates": section.count("Detection cache updated with"),
        "graph_requests": section.count("Requesting graph MLLM completion"),
        "normal_detection_responses": section.count(
            "request_type: detection\nrequested_service_tier: None"
        ),
        "flex_detection_responses": section.count(
            "request_type: detection\nrequested_service_tier: flex"
        ),
    }


def emit_case_progress(
    progress: dict,
    log_path: Path,
    reported: set[str],
) -> None:
    completed = dict(progress.get("completed_cases", {}))
    skipped = dict(progress.get("skipped_cases", {}))
    for case_id in progress.get("case_order", []):
        case_id = str(case_id)
        if case_id in reported:
            continue
        if case_id in completed:
            disposition = "completed"
            record = completed[case_id]
        elif case_id in skipped:
            disposition = "skipped"
            record = skipped[case_id]
        else:
            continue

        stats = case_runtime_stats(log_path, case_id)
        event = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "progress": len(reported) + 1,
            "total": len(progress.get("case_order", [])),
            "case_id": case_id,
            "disposition": disposition,
            "reason": record.get("reason"),
            "steps_completed": record.get("steps_completed"),
            **stats,
        }
        with EVENTS_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")
        reported.add(case_id)
        print(
            f"[{event['timestamp']}] case {event['progress']}/{event['total']} "
            f"{case_id} {disposition} reason={event['reason']} "
            f"steps={event['steps_completed']} cache_hits="
            f"{stats['detection_cache_hits']} cache_misses="
            f"{stats['detection_cache_misses']} saved_detection="
            f"{stats['saved_detection_replays']} graph_requests="
            f"{stats['graph_requests']} normal_detections="
            f"{stats['normal_detection_responses']} flex_detections="
            f"{stats['flex_detection_responses']}",
            flush=True,
        )


def attach_debugpy(run_stamp: str) -> subprocess.Popen:
    path = LOG_DIR / f"{LABEL}_debug_attach_{run_stamp}.log"
    handle = path.open("wb")
    return subprocess.Popen(
        [sys.executable, "scripts/debugpy_attach_continue.py"],
        cwd=PROJECT_ROOT,
        stdout=handle,
        stderr=subprocess.STDOUT,
    )


def run_batch_once(reported: set[str]) -> tuple[int, Path]:
    run_stamp = timestamp()
    log_path = LOG_DIR / f"{LABEL}_batch_{run_stamp}.log"
    status_path = LOG_DIR / f"{LABEL}_batch_{run_stamp}.status"
    latest_path = LOG_DIR / f"{LABEL}_latest_paths.txt"
    latest_path.write_text(
        f"{log_path.relative_to(PROJECT_ROOT)}\n"
        f"{status_path.relative_to(PROJECT_ROOT)}\n",
        encoding="utf-8",
    )
    print(
        f"[{datetime.now().isoformat(timespec='seconds')}] starting "
        f"{log_path.relative_to(PROJECT_ROOT)}",
        flush=True,
    )

    with log_path.open("wb") as log_handle:
        proc = subprocess.Popen(
            [
                sys.executable,
                "-u",
                "run_benchmark_sweep.py",
                "--batch-config",
                BATCH_CONFIG,
                "--method",
                "dec_graph",
            ],
            cwd=PROJECT_ROOT,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
        )
        time.sleep(8)
        attach_proc = attach_debugpy(run_stamp)
        while proc.poll() is None:
            emit_case_progress(load_progress(), log_path, reported)
            time.sleep(5)
        code = int(proc.returncode)
        emit_case_progress(load_progress(), log_path, reported)
        status_path.write_text(f"{code}\n", encoding="utf-8")
        attach_proc.terminate()
        try:
            attach_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            attach_proc.kill()
    kill_stale_debugpy()
    return code, log_path


def main() -> int:
    LOG_DIR.mkdir(exist_ok=True)
    reported = reported_case_ids()
    repeated_errors: dict[tuple[int, str], int] = {}
    progress = load_progress()
    if is_complete(progress):
        print("Dec-Graph 100-case batch already complete", flush=True)
        return 0

    while True:
        kill_stale_debugpy()
        before = load_progress()
        code, log_path = run_batch_once(reported)
        progress = load_progress()
        if is_complete(progress):
            DONE_PATH.write_text(
                f"completed at {datetime.now().isoformat()}\n",
                encoding="utf-8",
            )
            print("Dec-Graph 100-case batch complete", flush=True)
            return 0

        tail = read_tail(log_path)
        key = (accounted(progress), str(progress.get("next_case_id") or ""))
        if any(marker in tail for marker in RATE_LIMIT_MARKERS):
            print("rate limit exit; cooling down 300 seconds", flush=True)
            time.sleep(300)
            continue
        if any(marker in tail for marker in TRANSIENT_PROVIDER_MARKERS):
            print("transient provider exit; cooling down 300 seconds", flush=True)
            time.sleep(300)
            continue
        if OPENGL_MARKER in tail:
            repeated_errors[key] = repeated_errors.get(key, 0) + 1
            if repeated_errors[key] < 3:
                print("OpenGL exit; resuming from saved progress", flush=True)
                time.sleep(5)
                continue
        if code == 0 and accounted(progress) > accounted(before):
            print("early clean exit after progress; resuming", flush=True)
            continue

        print(
            f"non-retryable exit code={code} progress={accounted(progress)}/100 "
            f"next={progress.get('next_case_id')} log={log_path}",
            flush=True,
        )
        return code or 1


if __name__ == "__main__":
    raise SystemExit(main())
