#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from semantic_persistence.detection_cache import DetectionCache


def has_retry_error(raw_output_dirs: Iterable[Path], case_id: str, step_index: int) -> bool:
    pattern = "detection_step_%04d_attempt_*_error.txt" % int(step_index)
    for raw_output_dir in raw_output_dirs:
        case_dir = raw_output_dir / str(case_id)
        if any(case_dir.glob(pattern)):
            return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Remove detection cache entries whose saved detection output came "
            "from a retry prompt. Retry-prompt outputs use a different prompt "
            "than the base detection prompt and must not be stored under the "
            "base prompt cache key."
        )
    )
    parser.add_argument("--cache-dir", default="mllm_detection_cache")
    parser.add_argument("--batch-id", default="batch_test")
    parser.add_argument(
        "--raw-output-dir",
        action="append",
        required=True,
        help="Raw output root containing case directories.",
    )
    args = parser.parse_args()

    cache = DetectionCache(args.cache_dir, args.batch_id)
    if not cache.path.exists():
        print("cache file does not exist: %s" % cache.path)
        return 0

    raw_output_dirs = [Path(path) for path in args.raw_output_dir]
    kept = []
    removed = []
    with cache.path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            entry = json.loads(line)
            if has_retry_error(
                raw_output_dirs,
                str(entry["case_id"]),
                int(entry["step_index"]),
            ):
                removed.append(entry)
            else:
                kept.append(entry)

    tmp_path = cache.path.with_suffix(".jsonl.tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        for entry in kept:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")
    os.replace(tmp_path, cache.path)

    cache._read_index()
    print(
        "pruned %s retry-prompt entries; kept %s entries in %s"
        % (len(removed), len(kept), cache.path)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
