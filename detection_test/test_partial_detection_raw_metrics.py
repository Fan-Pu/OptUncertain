import csv
import json

from detection_test import evaluate_partial_detection_raw_metrics as partial


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as file_handle:
        json.dump(payload, file_handle)


def _write_csv(path, rows, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as file_handle:
        writer = csv.DictWriter(file_handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _summary():
    return {
        "case_order": ["scan_a_case_0001", "scan_a_case_0002"],
        "cases": {
            "scan_a_case_0001": {
                "test_case": "scan_a_case_0001",
                "scan_id": "scan_a",
                "agents": [
                    {
                        "id": "agent0",
                        "start_viewpoint_id": "vp1",
                    }
                ],
                "targets": [
                    {
                        "target_id": "0",
                        "description": "target one",
                    }
                ],
            },
            "scan_a_case_0002": {
                "test_case": "scan_a_case_0002",
                "scan_id": "scan_a",
                "agents": [
                    {
                        "id": "agent0",
                        "start_viewpoint_id": "vp2",
                    }
                ],
                "targets": [
                    {
                        "target_id": "0",
                        "description": "target one",
                    }
                ],
            },
        },
    }


def _batch_config():
    return {
        "scans": [
            {
                "scan_id": "scan_a",
                "targets": [
                    {
                        "target_id": "0",
                        "description": "target one",
                        "detectable_viewpoint_ids": ["vp1"],
                    }
                ],
            }
        ]
    }


def test_partial_raw_metrics_excludes_missing_cases_and_scores_reviewed_oracle(
    tmp_path,
    monkeypatch,
):
    raw_root = tmp_path / "raw"
    _write_json(
        raw_root / "scan_a_case_0001" / "detection_step_0001.json",
        {
            "detections": [
                {
                    "agent_id": "agent0",
                    "found_target_indices": ["0"],
                    "target_center_xs": [0.5],
                }
            ]
        },
    )
    monkeypatch.setattr(
        partial,
        "_viewpoint_indexes_by_scan",
        lambda summary, connectivity_dir: {"scan_a": {"vp1": 3, "vp2": 4}},
    )

    target_rows, missing_cases = partial.build_partial_target_rows(
        summary=_summary(),
        batch_config=_batch_config(),
        raw_root=raw_root,
        connectivity_dir=tmp_path / "connectivity",
    )

    assert missing_cases == ["scan_a_case_0002"]
    assert len(target_rows) == 1
    assert target_rows[0]["case_id"] == "scan_a_case_0001"
    assert target_rows[0]["viewpoint_index"] == 3
    assert target_rows[0]["oracle_visible"] == 1
    assert target_rows[0]["predicted"] == 1
    assert target_rows[0]["outcome"] == "tp"

    oracle_path = tmp_path / "oracle.csv"
    _write_csv(
        oracle_path,
        [
            {
                "scan_id": "scan_a",
                "viewpoint_id": "vp1",
                "target_description": "target one",
                "reviewed_visible": "1",
            }
        ],
        ["scan_id", "viewpoint_id", "target_description", "reviewed_visible"],
    )
    out_dir = tmp_path / "out"
    method_row = partial.write_partial_reviewed_metrics(
        method_name="ModelPartial",
        target_rows=target_rows,
        missing_cases=missing_cases,
        oracle_path=oracle_path,
        out_dir=out_dir,
    )

    assert method_row["case_count"] == 1
    assert method_row["agent_target_pairs"] == 1
    assert method_row["precision"] == 1.0
    assert (out_dir / "reviewed_detection_method_metrics.csv").exists()
    assert (out_dir / "reviewed_detection_case_metrics.csv").exists()
    assert (out_dir / "reviewed_detection_target_metrics.csv").exists()
    assert (out_dir / "missing_cases.txt").read_text(encoding="utf-8") == (
        "scan_a_case_0002\n"
    )
