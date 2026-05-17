from __future__ import annotations

import json

import pytest

from graph_visualizer.loader import load_visualization_steps


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_step(
    root,
    instance_name,
    step_index,
    *,
    target_found,
    semantic=True,
    user_message=True,
):
    suffix = "%04d" % int(step_index)
    raw_dir = root / "mllm_raw_outputs" / instance_name
    debug_dir = root / "mllm_debug_outputs" / instance_name

    _write_json(
        debug_dir / ("graph_layout_step_%s.json" % suffix),
        {
            "observation_step": step_index,
            "nodes": [],
            "edges": [],
            "agent_current_vp_ids": {},
        },
    )
    _write_json(
        debug_dir / ("hypothesis_step_%s.json" % suffix),
        {
            "target_found": target_found,
            "targets": [],
            "nodes": [],
            "edges": [],
        },
    )
    _write_json(
        raw_dir / ("detection_step_%s.json" % suffix),
        {"detections": []},
    )

    if semantic:
        _write_json(
            raw_dir / ("semantic_step_%s.json" % suffix),
            {"visible_region_nodes": []},
        )

    if user_message:
        (raw_dir / ("user_message_step_%s.txt" % suffix)).write_text(
            "prompt text",
            encoding="utf-8",
        )


def test_load_visualization_step_with_all_raw_files(tmp_path):
    _write_step(
        tmp_path,
        "case",
        0,
        target_found={"0": False},
    )

    steps = load_visualization_steps("case", project_root=tmp_path)

    assert len(steps) == 1
    assert steps[0]["semantic"] == {"visible_region_nodes": []}
    assert steps[0]["user_message"] == "prompt text"


def test_load_terminal_detection_only_step_without_semantic_or_user_message(tmp_path):
    _write_step(
        tmp_path,
        "case",
        0,
        target_found={"0": True, "1": True},
        semantic=False,
        user_message=False,
    )

    steps = load_visualization_steps("case", project_root=tmp_path)

    assert len(steps) == 1
    assert steps[0]["semantic"] is None
    assert steps[0]["user_message"] == ""
    assert steps[0]["files"]["semantic"] == (
        "mllm_raw_outputs/case/semantic_step_0000.json"
    )
    assert steps[0]["files"]["user_message"] == (
        "mllm_raw_outputs/case/user_message_step_0000.txt"
    )


def test_load_nonterminal_step_without_semantic_still_crashes(tmp_path):
    _write_step(
        tmp_path,
        "case",
        0,
        target_found={"0": False, "1": True},
        semantic=False,
    )

    with pytest.raises(FileNotFoundError):
        load_visualization_steps("case", project_root=tmp_path)
