import copy
import json
from pathlib import Path

import pytest

from detection_test.refresh_batch_case_manifest import refresh_manifest
from main import (
    _batch_case_generation_hash,
    _batch_visibility_hash,
    _legacy_batch_config_hash_for_generation_config,
    _validate_batch_summary_hash,
)


def _batch_config(
    *,
    target_zero_description="target zero",
    target_zero_viewpoints=("vp0", "vp1"),
    target_selection_case_number=2,
):
    return {
        "max_steps": 5,
        "agent_num_selections": [
            {
                "agent_number": 2,
                "case_number": 1,
            }
        ],
        "target_num_selections": [
            {
                "target_number": 1,
                "case_number": target_selection_case_number,
            }
        ],
        "scans": [
            {
                "scan_id": "scan_a",
                "targets": [
                    {
                        "target_id": "0",
                        "description": target_zero_description,
                        "detectable_viewpoint_ids": list(target_zero_viewpoints),
                    },
                    {
                        "target_id": "1",
                        "description": "target one",
                        "detectable_viewpoint_ids": ["vp2"],
                    },
                ],
            }
        ],
    }


def _agents():
    return [
        {
            "id": "agent0",
            "start_viewpoint_id": "start0",
            "heading": 0.0,
            "elevation": 0.0,
        },
        {
            "id": "agent1",
            "start_viewpoint_id": "start1",
            "heading": 0.0,
            "elevation": 0.0,
        },
    ]


def _summary_for_config(batch_config):
    case_generation_hash = _batch_case_generation_hash(batch_config)
    cases = {
        "scan_a_case_0001": {
            "test_case": "scan_a_case_0001",
            "scan_id": "scan_a",
            "agent_number": 2,
            "agent_selection_index": 0,
            "target_number": 1,
            "target_selection_index": 0,
            "agents": _agents(),
            "targets": [
                {
                    "target_id": "0",
                    "description": batch_config["scans"][0]["targets"][0][
                        "description"
                    ],
                }
            ],
            "raw_output_dir": "mllm_raw_outputs/scan_a_case_0001",
            "debug_output_dir": "mllm_debug_outputs/scan_a_case_0001",
            "max_steps": 5,
        },
        "scan_a_case_0002": {
            "test_case": "scan_a_case_0002",
            "scan_id": "scan_a",
            "agent_number": 2,
            "agent_selection_index": 0,
            "target_number": 1,
            "target_selection_index": 1,
            "agents": _agents(),
            "targets": [
                {
                    "target_id": "1",
                    "description": batch_config["scans"][0]["targets"][1][
                        "description"
                    ],
                }
            ],
            "raw_output_dir": "mllm_raw_outputs/scan_a_case_0002",
            "debug_output_dir": "mllm_debug_outputs/scan_a_case_0002",
            "max_steps": 5,
        },
    }
    return {
        "batch_id": "batch_test",
        "batch_config_hash": case_generation_hash,
        "batch_case_generation_hash": case_generation_hash,
        "batch_visibility_hash": _batch_visibility_hash(batch_config),
        "generated_case_count": len(cases),
        "case_order": list(cases),
        "cases": cases,
    }


def _write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as file_handle:
        json.dump(payload, file_handle, indent=2)
        file_handle.write("\n")


def test_visibility_only_edit_keeps_case_generation_hash():
    original_config = _batch_config(target_zero_viewpoints=("vp0", "vp1"))
    revised_config = _batch_config(target_zero_viewpoints=("vp0",))
    summary = _summary_for_config(original_config)

    assert _batch_case_generation_hash(original_config) == _batch_case_generation_hash(
        revised_config
    )
    assert _batch_visibility_hash(original_config) != _batch_visibility_hash(
        revised_config
    )

    _validate_batch_summary_hash(
        summary=summary,
        batch_config=revised_config,
        batch_id="batch_test",
        summary_path=Path("generated_cases.json"),
    )


def test_target_definition_edit_invalidates_saved_summary():
    original_config = _batch_config()
    changed_config = _batch_config(target_zero_description="renamed target zero")
    summary = _summary_for_config(original_config)

    assert _batch_case_generation_hash(original_config) != _batch_case_generation_hash(
        changed_config
    )

    with pytest.raises(ValueError, match="target 0 definition changed"):
        _validate_batch_summary_hash(
            summary=summary,
            batch_config=changed_config,
            batch_id="batch_test",
            summary_path=Path("generated_cases.json"),
        )


def test_selection_edit_invalidates_saved_summary():
    original_config = _batch_config()
    changed_config = _batch_config(target_selection_case_number=1)
    summary = _summary_for_config(original_config)

    with pytest.raises(ValueError, match="case order does not match"):
        _validate_batch_summary_hash(
            summary=summary,
            batch_config=changed_config,
            batch_id="batch_test",
            summary_path=Path("generated_cases.json"),
        )


def test_refresh_manifest_updates_hash_metadata_without_rewriting_cases(tmp_path):
    original_config = _batch_config(target_zero_viewpoints=("vp0", "vp1"))
    revised_config = _batch_config(target_zero_viewpoints=("vp0",))
    stale_summary = _summary_for_config(original_config)
    stale_summary.pop("batch_case_generation_hash")
    stale_summary.pop("batch_visibility_hash")
    stale_summary["batch_config_hash"] = _legacy_batch_config_hash_for_generation_config(
        original_config
    )
    original_cases = copy.deepcopy(stale_summary["cases"])

    batch_config_path = tmp_path / "batch_test.json"
    manifest_path = tmp_path / "generated_cases.json"
    _write_json(batch_config_path, revised_config)
    _write_json(manifest_path, stale_summary)

    refresh_manifest(
        batch_config_path=batch_config_path,
        manifest_path=manifest_path,
    )

    with open(manifest_path, "r", encoding="utf-8") as file_handle:
        refreshed = json.load(file_handle)

    assert refreshed["batch_config_hash"] == _batch_case_generation_hash(
        revised_config
    )
    assert refreshed["batch_case_generation_hash"] == _batch_case_generation_hash(
        revised_config
    )
    assert refreshed["batch_visibility_hash"] == _batch_visibility_hash(revised_config)
    assert refreshed["cases"] == original_cases
