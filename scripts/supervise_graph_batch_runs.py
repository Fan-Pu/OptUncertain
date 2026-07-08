#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "config" / "default_config.json"
BATCH_CONFIG = "scenarios/batch_test.json"
LOG_DIR = PROJECT_ROOT / "batch_logs"
MODELS = [
    "GPT54Medium",
    "Gemma431BThinking",
    "Qwen36_35BA3BThinking",
]

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
    "Error code: 504",
    "504 Gateway Timeout",
    "Gateway Timeout",
    "model_not_supported",
    "not supported by any provider you have enabled",
)
OPENGL_MARKER = "OpenGL error 0x501"


def progress_path(model_label: str) -> Path:
    return (
        PROJECT_ROOT
        / f"mllm_debug_outputs_balanced100_{model_label}"
        / "batch_test"
        / "batch_progress.json"
    )


def load_progress(model_label: str) -> dict:
    path = progress_path(model_label)
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def accounted(progress: dict) -> int:
    return sum(
        progress.get(key) or 0
        for key in (
            "completed_case_count",
            "skipped_case_count",
            "failed_case_count",
        )
    )


def is_complete(progress: dict) -> bool:
    return progress.get("status") == "completed" and accounted(progress) >= 100


def progress_key(progress: dict) -> tuple[int, str]:
    return accounted(progress), progress.get("next_case_id") or ""


def set_selected_model(model_label: str) -> None:
    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    batch_sweep = config.setdefault("batch_sweep", {})
    if batch_sweep.get("selected_graph_model_label") == model_label:
        return
    batch_sweep["selected_graph_model_label"] = model_label
    tmp_path = CONFIG_PATH.with_suffix(".json.tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=2)
        handle.write("\n")
    os.replace(tmp_path, CONFIG_PATH)


def kill_stale_debugpy() -> None:
    for pattern in ("[d]ebugpy_attach_continue.py", "[d]ebugpy/adapter"):
        subprocess.run(
            ["pkill", "-f", pattern],
            cwd=PROJECT_ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def read_tail(path: Path, max_chars: int = 24000) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    return text[-max_chars:]


def write_latest_paths(model_label: str, log_path: Path, status_path: Path) -> None:
    latest_path = LOG_DIR / f"{model_label}_latest_paths.txt"
    latest_path.write_text(
        f"{log_path.relative_to(PROJECT_ROOT)}\n"
        f"{status_path.relative_to(PROJECT_ROOT)}\n",
        encoding="utf-8",
    )


def attach_debugpy(model_label: str, run_stamp: str) -> subprocess.Popen:
    attach_log = LOG_DIR / f"{model_label}_debug_attach_{run_stamp}.log"
    handle = attach_log.open("wb")
    return subprocess.Popen(
        [sys.executable, "scripts/debugpy_attach_continue.py"],
        cwd=PROJECT_ROOT,
        stdout=handle,
        stderr=subprocess.STDOUT,
    )


def run_batch_once(model_label: str) -> tuple[int, Path]:
    run_stamp = timestamp()
    log_path = LOG_DIR / f"{model_label}_supervised_{run_stamp}.log"
    status_path = LOG_DIR / f"{model_label}_supervised_{run_stamp}.status"
    write_latest_paths(model_label, log_path, status_path)
    print(
        f"[{datetime.now().isoformat(timespec='seconds')}] "
        f"starting {model_label}: {log_path.relative_to(PROJECT_ROOT)}",
        flush=True,
    )

    with log_path.open("wb") as log_handle:
        proc = subprocess.Popen(
            [
                sys.executable,
                "run_batch_sweep.py",
                "--batch-config",
                BATCH_CONFIG,
            ],
            cwd=PROJECT_ROOT,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
        )
        time.sleep(8)
        attach_proc = attach_debugpy(model_label, run_stamp)
        code = proc.wait()
        status_path.write_text(f"{code}\n", encoding="utf-8")
        attach_proc.terminate()
        try:
            attach_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            attach_proc.kill()
    kill_stale_debugpy()
    print(
        f"[{datetime.now().isoformat(timespec='seconds')}] "
        f"{model_label} exited with {code}",
        flush=True,
    )
    return code, log_path


def should_retry_after_error(
    model_label: str,
    code: int,
    log_tail: str,
    repeated_errors: dict[tuple[int, str], int],
) -> bool:
    progress = load_progress(model_label)
    key = progress_key(progress)
    if OPENGL_MARKER in log_tail:
        repeated_errors[key] = repeated_errors.get(key, 0) + 1
        if repeated_errors[key] >= 3:
            print(
                f"OpenGL crash repeated {repeated_errors[key]} times at "
                f"progress {key}; stopping for inspection",
                flush=True,
            )
            return False
        print(
            f"OpenGL render crash after checkpoint for {model_label} at "
            f"progress {key}; restarting from saved progress",
            flush=True,
        )
        time.sleep(5)
        return True

    if any(marker in log_tail for marker in RATE_LIMIT_MARKERS):
        print(
            f"rate limit marker seen for {model_label}; cooling down 300 seconds",
            flush=True,
        )
        time.sleep(300)
        return True

    if any(marker in log_tail for marker in TRANSIENT_PROVIDER_MARKERS):
        print(
            f"transient provider error seen for {model_label}; "
            f"cooling down 300 seconds",
            flush=True,
        )
        time.sleep(300)
        return True

    if code == 0:
        print(
            f"{model_label} exited 0 before completion; rerunning once from progress",
            flush=True,
        )
        return True

    return False


def supervise_model(model_label: str) -> int:
    progress = load_progress(model_label)
    if is_complete(progress):
        print(
            f"{model_label} already complete: {accounted(progress)}/100 accounted",
            flush=True,
        )
        return 0

    set_selected_model(model_label)
    repeated_errors: dict[tuple[int, str], int] = {}
    while True:
        progress = load_progress(model_label)
        print(
            f"{model_label} progress before run: {accounted(progress)}/100 "
            f"next={progress.get('next_case_id')}",
            flush=True,
        )
        kill_stale_debugpy()
        code, log_path = run_batch_once(model_label)
        progress = load_progress(model_label)
        print(
            f"{model_label} progress after run: {accounted(progress)}/100 "
            f"completed={progress.get('completed_case_count')} "
            f"skipped={progress.get('skipped_case_count')} "
            f"failed={progress.get('failed_case_count')} "
            f"status={progress.get('status')}",
            flush=True,
        )
        if is_complete(progress):
            print(f"{model_label} complete", flush=True)
            return 0

        log_tail = read_tail(log_path)
        if should_retry_after_error(model_label, code, log_tail, repeated_errors):
            continue

        print(
            f"Stopping on non-retryable {model_label} error. "
            f"See {log_path.relative_to(PROJECT_ROOT)}",
            flush=True,
        )
        return code or 1


def main() -> int:
    LOG_DIR.mkdir(exist_ok=True)
    for model_label in MODELS:
        code = supervise_model(model_label)
        if code != 0:
            return code
    done_path = LOG_DIR / "graph_batch_supervisor.done"
    done_path.write_text(
        f"completed all graph model batch runs at {datetime.now().isoformat()}\n",
        encoding="utf-8",
    )
    print("All graph model batch runs complete", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
