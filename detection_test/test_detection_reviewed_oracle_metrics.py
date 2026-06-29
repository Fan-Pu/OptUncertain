import csv
from pathlib import Path

import pytest

from detection_test.build_detection_visual_oracle import build_oracle_rows
from detection_test.evaluate_detection_reviewed_oracle_metrics import (
    MethodSpec,
    evaluate_methods,
    read_reviewed_oracle,
    score_method_rows,
)


def _target_row(
    *,
    case_id="case_001",
    scan_id="scan_a",
    agent_id="agent0",
    viewpoint_id="vp1",
    viewpoint_index="7",
    target_id="0",
    target_description="the red mug on the counter",
    oracle_visible="0",
    predicted="0",
    outcome="tn",
):
    return {
        "case_id": case_id,
        "scan_id": scan_id,
        "agent_id": agent_id,
        "viewpoint_id": viewpoint_id,
        "viewpoint_index": viewpoint_index,
        "target_id": target_id,
        "target_description": target_description,
        "oracle_visible": oracle_visible,
        "predicted": predicted,
        "target_center_x": "",
        "outcome": outcome,
    }


def _write_csv(path, rows, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as file_handle:
        writer = csv.DictWriter(file_handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_build_oracle_rows_collapses_duplicate_visual_keys():
    rows = [
        _target_row(case_id="case_a", agent_id="agent0", oracle_visible="0"),
        _target_row(case_id="case_b", agent_id="agent3", oracle_visible="1"),
        _target_row(
            case_id="case_c",
            agent_id="agent1",
            viewpoint_id="vp2",
            target_description="the blue vase",
            oracle_visible="0",
        ),
    ]

    debug_root = Path("debug_root")
    oracle_rows = build_oracle_rows(rows, debug_root=debug_root)

    assert len(oracle_rows) == 2
    assert oracle_rows[0]["scan_id"] == "scan_a"
    assert oracle_rows[0]["viewpoint_id"] == "vp1"
    assert oracle_rows[0]["target_description"] == "the red mug on the counter"
    assert oracle_rows[0]["row_count"] == 2
    assert oracle_rows[0]["original_oracle_visible_values"] == "0;1"
    assert (
        oracle_rows[0]["representative_image_path"]
        == str(
            debug_root
            / "case_a"
            / "detection_input_step_0001_agent_agent0_full_raw_panorama.jpg"
        ).replace("\\", "/")
    )
    assert oracle_rows[0]["reviewed_visible"] == ""


def test_score_method_rows_uses_reviewed_oracle_for_metrics():
    oracle = {
        ("scan_a", "vp1", "target one"): 1,
        ("scan_a", "vp2", "target two"): 0,
        ("scan_a", "vp3", "target three"): 1,
        ("scan_a", "vp4", "target four"): 0,
    }
    rows = [
        _target_row(
            viewpoint_id="vp1",
            target_description="target one",
            oracle_visible="0",
            predicted="1",
            outcome="fp",
        ),
        _target_row(
            viewpoint_id="vp2",
            target_description="target two",
            oracle_visible="0",
            predicted="1",
            outcome="fp",
        ),
        _target_row(
            viewpoint_id="vp3",
            target_description="target three",
            oracle_visible="1",
            predicted="0",
            outcome="fn",
        ),
        _target_row(
            viewpoint_id="vp4",
            target_description="target four",
            oracle_visible="0",
            predicted="0",
            outcome="tn",
        ),
    ]

    target_rows, case_rows, method_row, disagreements = score_method_rows(
        "ModelA",
        rows,
        oracle,
    )

    assert [row["reviewed_outcome"] for row in target_rows] == [
        "tp",
        "fp",
        "fn",
        "tn",
    ]
    assert method_row["agent_target_pairs"] == 4
    assert method_row["tp"] == 1
    assert method_row["fp"] == 1
    assert method_row["fn"] == 1
    assert method_row["tn"] == 1
    assert method_row["precision"] == 0.5
    assert method_row["recall"] == 0.5
    assert method_row["f1"] == 0.5
    assert len(case_rows) == 1
    assert len(disagreements) == 1
    assert disagreements[0]["target_description"] == "target one"
    assert disagreements[0]["original_oracle_visible"] == 0
    assert disagreements[0]["reviewed_visible"] == 1


def test_score_method_rows_fails_for_unmatched_oracle_key():
    with pytest.raises(KeyError):
        score_method_rows("ModelA", [_target_row()], {})


def test_read_reviewed_oracle_requires_completed_labels(tmp_path):
    path = tmp_path / "oracle.csv"
    _write_csv(
        path,
        [
            {
                "scan_id": "scan_a",
                "viewpoint_id": "vp1",
                "target_description": "target one",
                "reviewed_visible": "",
            }
        ],
        ["scan_id", "viewpoint_id", "target_description", "reviewed_visible"],
    )

    with pytest.raises(ValueError):
        read_reviewed_oracle(path)


def test_evaluate_methods_requires_expected_pair_count(tmp_path):
    method_root = tmp_path / "method"
    metrics_path = (
        method_root
        / "batch_test"
        / "detection_metrics"
        / "detection_target_metrics.csv"
    )
    row = _target_row(
        scan_id="scan_a",
        viewpoint_id="vp1",
        target_description="target one",
        oracle_visible="1",
        predicted="1",
        outcome="tp",
    )
    _write_csv(metrics_path, [row], list(row))

    with pytest.raises(ValueError):
        evaluate_methods(
            [MethodSpec("ModelA", method_root)],
            {("scan_a", "vp1", "target one"): 1},
            batch_id="batch_test",
            expected_pairs=440,
        )
