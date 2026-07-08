#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import os
import shutil
import sys
from pathlib import Path
from typing import Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from semantic_persistence.detection_cache import (
    DETECTION_PROMPT_VERSION,
    DetectionCache,
)


def _read_json(path: Path) -> Dict[str, object]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _case_order(summary: Dict[str, object]) -> List[str]:
    if "case_order" in summary:
        return [str(case_id) for case_id in summary["case_order"]]
    return [str(case_id) for case_id in summary["cases"]]


def _source_summary_path(source_run_id: str, batch_id: str) -> Path:
    batch_dir = PROJECT_ROOT / ("mllm_debug_outputs_%s" % source_run_id) / batch_id
    sampled_path = batch_dir / "sampled_generated_cases.json"
    if sampled_path.exists():
        return sampled_path
    return batch_dir / "generated_cases.json"


def _completed_case_ids(source_run_id: str, batch_id: str) -> set[str]:
    progress_path = (
        PROJECT_ROOT
        / ("mllm_debug_outputs_%s" % source_run_id)
        / batch_id
        / "batch_progress.json"
    )
    if not progress_path.exists():
        return set()
    progress = _read_json(progress_path)
    completed_cases = progress.get("completed_cases", {})
    if not isinstance(completed_cases, dict):
        return set()
    return {str(case_id) for case_id in completed_cases}


def _step_index(path: Path) -> int:
    match = re.fullmatch(r"detection_step_(\d+)\.json", path.name)
    if match is None:
        raise ValueError("Unexpected detection step filename %s." % str(path))
    return int(match.group(1))


def _normalize_detection_payload(
    payload: Dict[str, object],
    agent_ids: List[str],
    targets: List[Dict[str, object]],
) -> List[Dict[str, object]]:
    if set(payload) != {"detections"}:
        raise KeyError("Detection payload must contain exactly ['detections'].")
    detections = payload["detections"]
    if not isinstance(detections, list):
        raise TypeError("detections must be a list.")

    valid_agent_ids = {str(agent_id) for agent_id in agent_ids}
    valid_target_ids = {str(target["target_id"]) for target in targets}
    normalized = []
    seen_agents = set()

    for detection in detections:
        if not isinstance(detection, dict):
            raise TypeError("Detection entries must be objects.")
        if set(detection) != {
            "agent_id",
            "found_target_indices",
            "target_center_xs",
        }:
            raise KeyError("Detection entry has unexpected keys.")
        agent_id = str(detection["agent_id"])
        if agent_id not in valid_agent_ids:
            raise ValueError("Detection uses unknown agent id %s." % agent_id)
        if agent_id in seen_agents:
            raise ValueError("Duplicate detection entry for %s." % agent_id)
        seen_agents.add(agent_id)

        found_target_indices = detection["found_target_indices"]
        target_center_xs = detection["target_center_xs"]
        if len(found_target_indices) != len(target_center_xs):
            raise ValueError("Detection target ids and center_xs length mismatch.")
        if not found_target_indices:
            raise ValueError("Detection entry for %s is empty." % agent_id)

        found_ids = []
        centers = []
        seen_targets = set()
        for target_id_raw, center_x_raw in zip(found_target_indices, target_center_xs):
            target_id = str(target_id_raw)
            if target_id not in valid_target_ids:
                raise ValueError("Detection uses inactive target id %s." % target_id)
            if target_id in seen_targets:
                raise ValueError("Duplicate target id %s for %s." % (target_id, agent_id))
            center_x = float(center_x_raw)
            if not (0.0 <= center_x <= 1.0):
                raise ValueError("target_center_x must be in [0, 1].")
            seen_targets.add(target_id)
            found_ids.append(target_id)
            centers.append(center_x)

        normalized.append(
            {
                "agent_id": agent_id,
                "found_target_indices": found_ids,
                "target_center_xs": centers,
            }
        )

    return sorted(normalized, key=lambda item: item["agent_id"])


def _viewpoint_labels_by_index(layout: Dict[str, object]) -> Dict[int, str]:
    labels = {}
    for node in layout.get("nodes", []):
        if not isinstance(node, dict):
            continue
        if node.get("type") != "viewpoint":
            continue
        labels[int(node["id"])] = str(node["label"])
    return labels


def _detection_image_records(
    debug_dir: Path,
    step_index: int,
    layout: Dict[str, object],
) -> List[Dict[str, object]]:
    current_vp_ids = layout.get("agent_current_vp_ids")
    if not isinstance(current_vp_ids, dict):
        raise KeyError("graph layout missing agent_current_vp_ids.")
    labels_by_index = _viewpoint_labels_by_index(layout)
    records = []

    for image_index, agent_id in enumerate(sorted(str(key) for key in current_vp_ids)):
        viewpoint_index = int(current_vp_ids[agent_id])
        viewpoint_id = labels_by_index[viewpoint_index]
        image_path = (
            debug_dir
            / (
                "detection_input_step_%04d_agent_%s_full_raw_panorama.jpg"
                % (step_index, agent_id)
            )
        )
        if not image_path.exists():
            raise FileNotFoundError(str(image_path))
        records.append(
            {
                "agent_id": agent_id,
                "current_viewpoint_id": viewpoint_id,
                "current_viewpoint_index": viewpoint_index,
                "image_index": image_index,
                "image_role": "full_raw_panorama",
                "x_range": [0.0, 1.0],
                "image_sha256": DetectionCache.sha256_bytes(image_path.read_bytes()),
            }
        )
    return records


def seed_source_run(
    *,
    cache: DetectionCache,
    source_run_id: str,
    batch_id: str,
    detection_model: str,
    prompt_version: str,
) -> Dict[str, int]:
    summary_path = _source_summary_path(source_run_id, batch_id)
    summary = _read_json(summary_path)
    cases = summary["cases"]
    completed_case_ids = _completed_case_ids(source_run_id, batch_id)
    stats = {
        "cases_seen": 0,
        "cases_skipped_not_completed": 0,
        "steps_seen": 0,
        "steps_seeded": 0,
        "entries_added": 0,
        "steps_skipped_missing_artifacts": 0,
    }

    for case_id in _case_order(summary):
        if str(case_id) not in completed_case_ids:
            stats["cases_skipped_not_completed"] += 1
            continue
        case = cases[case_id]
        stats["cases_seen"] += 1
        scan_id = str(case["scan_id"])
        raw_dir = PROJECT_ROOT / str(case["raw_output_dir"])
        debug_dir = PROJECT_ROOT / str(case["debug_output_dir"])
        if not raw_dir.exists() or not debug_dir.exists():
            continue

        targets = [
            {
                "target_id": str(target["target_id"]),
                "description": str(target["description"]),
            }
            for target in case["targets"]
        ]
        active_target_ids = {str(target["target_id"]) for target in targets}

        for detection_path in sorted(
            raw_dir.glob("detection_step_*.json"),
            key=_step_index,
        ):
            step_index = _step_index(detection_path)
            active_targets = [
                target
                for target in targets
                if str(target["target_id"]) in active_target_ids
            ]
            if not active_targets:
                break
            stats["steps_seen"] += 1
            layout_path = debug_dir / ("graph_layout_step_%04d.json" % step_index)
            if not layout_path.exists():
                stats["steps_skipped_missing_artifacts"] += 1
                continue

            try:
                layout = _read_json(layout_path)
                image_records = _detection_image_records(
                    debug_dir=debug_dir,
                    step_index=step_index,
                    layout=layout,
                )
                detections = _normalize_detection_payload(
                    payload=_read_json(detection_path),
                    agent_ids=[str(record["agent_id"]) for record in image_records],
                    targets=active_targets,
                )
            except (FileNotFoundError, KeyError, TypeError, ValueError):
                stats["steps_skipped_missing_artifacts"] += 1
                continue

            observations = [
                {
                    "agent_id": str(record["agent_id"]),
                    "current_viewpoint_id": str(record["current_viewpoint_id"]),
                }
                for record in image_records
            ]
            stats["entries_added"] += cache.append_step(
                scan_id=scan_id,
                case_id=str(case_id),
                step_index=step_index,
                agent_observations=observations,
                targets=active_targets,
                detection_image_records=image_records,
                detections=detections,
                detection_model=detection_model,
                prompt_version=prompt_version,
                service_tier=None,
                source_run_id=source_run_id,
            )
            stats["steps_seeded"] += 1

            for detection in detections:
                for target_id in detection["found_target_indices"]:
                    active_target_ids.discard(str(target_id))

    return stats


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the shared detection cache from finished batch outputs."
    )
    parser.add_argument("--batch-id", default="batch_test")
    parser.add_argument(
        "--source-run-id",
        action="append",
        required=True,
        help="Run id such as balanced100_GPT54Medium. Repeat for multiple runs.",
    )
    parser.add_argument("--cache-dir", default="mllm_detection_cache")
    parser.add_argument(
        "--detection-model",
        default=None,
        help="Defaults to config/default_config.json mllm.detection_model_name.",
    )
    parser.add_argument("--prompt-version", default=DETECTION_PROMPT_VERSION)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    detection_model = args.detection_model
    if detection_model is None:
        detection_model = str(
            _read_json(PROJECT_ROOT / "config" / "default_config.json")["mllm"][
                "detection_model_name"
            ]
        )

    cache = DetectionCache(cache_dir=args.cache_dir, batch_id=args.batch_id)
    staging_cache = DetectionCache(
        cache_dir=args.cache_dir,
        batch_id="%s.seed_tmp" % str(args.batch_id),
    )
    if staging_cache.path.exists():
        staging_cache.path.unlink()
    staging_cache.path.parent.mkdir(parents=True, exist_ok=True)
    if cache.path.exists():
        shutil.copyfile(cache.path, staging_cache.path)
    else:
        staging_cache.path.touch()

    try:
        for source_run_id in args.source_run_id:
            stats = seed_source_run(
                cache=staging_cache,
                source_run_id=str(source_run_id),
                batch_id=str(args.batch_id),
                detection_model=detection_model,
                prompt_version=str(args.prompt_version),
            )
            print("%s: %s" % (source_run_id, json.dumps(stats, sort_keys=True)))
        cache.path.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staging_cache.path, cache.path)
    except Exception:
        if staging_cache.path.exists():
            staging_cache.path.unlink()
        raise
    finally:
        try:
            staging_cache.path.parent.rmdir()
        except OSError:
            pass

    print("cache_path: %s" % str(cache.path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
