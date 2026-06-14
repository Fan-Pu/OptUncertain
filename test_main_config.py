import json
from pathlib import Path
import random

import pytest

import main


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _default_config():
    return {
        "mllm": {
            "detection_model_name": "detector",
            "graph_model_name": "graph",
            "read_saved_raw_outputs": True,
            "max_validation_retries": 4,
        },
        "bayes": {
            "sigma_vv2": 4.0,
            "sigma_vz2": 9.0,
            "kappa_vv": 1.0,
            "kappa_vz": 1.0,
            "varrho": 0.75,
            "eta_vz": 5.0,
            "epsilon": 1e-6,
        },
        "optimizer": {
            "goal_weight": 0.5,
            "dist_weight": 0.2,
            "arc_weight": 0.05,
            "node_weight": 0.05,
            "visit_weight": 0.2,
        },
    }


def _pose(x, y, z):
    pose = [0.0] * 16
    pose[3] = x
    pose[7] = y
    pose[11] = z
    return pose


def _write_connectivity(root, scan_id, viewpoint_count):
    records = []
    for index in range(viewpoint_count):
        records.append(
            {
                "image_id": "vp%s" % index,
                "included": True,
                "pose": _pose(float(index), 0.0, 0.0),
                "unobstructed": [
                    other_index != index and abs(other_index - index) == 1
                    for other_index in range(viewpoint_count)
                ],
            }
        )
    _write_json(root / "connectivity" / ("%s_connectivity.json" % scan_id), records)


def test_single_scenario_merges_central_config_and_infers_output_dirs(tmp_path):
    _write_json(tmp_path / "config" / "default_config.json", _default_config())
    scenario_path = tmp_path / "scenarios" / "case_a.json"
    _write_json(
        scenario_path,
        {
            "scan_id": "scan",
            "agents": [
                {
                    "id": "agent0",
                    "start_viewpoint_id": "vp0",
                    "heading": 0.0,
                    "elevation": 0.0,
                }
            ],
            "targets": [{"target_id": "0", "description": "target"}],
        },
    )

    scenario = main.load_scenario_config(
        scenario_path,
        default_config=main.load_default_config(tmp_path),
    )

    assert scenario["test_case"] == "case_a"
    assert scenario["mllm"]["detection_model_name"] == "detector"
    assert scenario["mllm"]["raw_output_dir"] == "mllm_raw_outputs/case_a"
    assert scenario["mllm"]["debug_output_dir"] == "mllm_debug_outputs/case_a"
    assert scenario["bayes"] == _default_config()["bayes"]
    assert scenario["optimizer"] == _default_config()["optimizer"]


def test_batch_generator_groups_case_ids_and_writes_summary(tmp_path):
    _write_json(tmp_path / "config" / "default_config.json", _default_config())
    _write_connectivity(tmp_path, "scanA", 4)
    _write_connectivity(tmp_path, "scanB", 4)
    batch_config = {
        "scans": [
            {
                "scan_id": "scanA",
                "targets": [
                    {"target_id": "0", "description": "target zero"},
                    {"target_id": "1", "description": "target one"},
                ],
            },
            {
                "scan_id": "scanB",
                "targets": [
                    {"target_id": "0", "description": "target zero"},
                    {"target_id": "1", "description": "target one"},
                ],
            },
        ],
        "agent_num_selections": [{"agent_number": 2, "case_number": 2}],
        "target_num_selections": [{"target_number": 1, "case_number": 2}],
        "max_steps": 7,
    }

    scenarios, summary = main.generate_batch_scenarios(
        batch_config=batch_config,
        batch_id="batch",
        project_root=tmp_path,
        default_config=main.load_default_config(tmp_path),
        rng=random.Random(0),
    )
    summary_path = main.write_batch_case_summary(
        "batch",
        summary,
        project_root=tmp_path,
    )

    case_ids = list(summary["cases"])
    assert case_ids == [
        "scanA_case_0001",
        "scanA_case_0002",
        "scanA_case_0003",
        "scanA_case_0004",
        "scanB_case_0001",
        "scanB_case_0002",
        "scanB_case_0003",
        "scanB_case_0004",
    ]
    assert len(scenarios) == 8
    assert summary["cases"]["scanA_case_0001"]["agents"][0]["id"] == "agent0"
    assert scenarios[0]["max_steps"] == 7
    assert summary["cases"]["scanA_case_0001"]["max_steps"] == 7
    assert summary["cases"]["scanA_case_0001"]["debug_output_dir"] == (
        "mllm_debug_outputs/scanA_case_0001"
    )
    assert json.loads(summary_path.read_text(encoding="utf-8")) == summary


def test_batch_generator_fails_when_target_number_exceeds_scan_targets(tmp_path):
    _write_json(tmp_path / "config" / "default_config.json", _default_config())
    _write_connectivity(tmp_path, "scan", 4)
    batch_config = {
        "scans": [
            {
                "scan_id": "scan",
                "targets": [{"target_id": "0", "description": "target zero"}],
            }
        ],
        "agent_num_selections": [{"agent_number": 1, "case_number": 1}],
        "target_num_selections": [{"target_number": 2, "case_number": 1}],
    }

    with pytest.raises(ValueError, match="requested 2 targets"):
        main.generate_batch_scenarios(
            batch_config=batch_config,
            batch_id="batch",
            project_root=tmp_path,
            default_config=main.load_default_config(tmp_path),
            rng=random.Random(0),
        )


def test_batch_schema_detection():
    assert main.is_batch_config(
        {
            "scans": [],
            "agent_num_selections": [],
            "target_num_selections": [],
        }
    )


def test_max_steps_reached_treats_none_as_unlimited():
    assert not main._max_steps_reached(step_index=100, max_steps=None)
    assert not main._max_steps_reached(step_index=1, max_steps=3)
    assert main._max_steps_reached(step_index=2, max_steps=3)


def test_run_batch_config_continues_after_max_step_results(tmp_path, monkeypatch):
    _write_json(tmp_path / "config" / "default_config.json", _default_config())
    _write_connectivity(tmp_path, "scan", 4)
    batch_config_path = tmp_path / "scenarios" / "batch.json"
    _write_json(
        batch_config_path,
        {
            "scans": [
                {
                    "scan_id": "scan",
                    "targets": [
                        {"target_id": "0", "description": "target zero"},
                        {"target_id": "1", "description": "target one"},
                    ],
                }
            ],
            "agent_num_selections": [{"agent_number": 1, "case_number": 2}],
            "target_num_selections": [{"target_number": 1, "case_number": 1}],
            "max_steps": 4,
        },
    )
    monkeypatch.setattr(main, "_project_root", lambda: tmp_path)

    seen_case_ids = []
    seen_max_steps = []

    def fake_run_scenario(scenario, show_agent_views, default_config):
        seen_case_ids.append(str(scenario["test_case"]))
        seen_max_steps.append(int(scenario["max_steps"]))
        return {
            "target_found": {"0": False},
            "status": "incomplete",
            "stop_reason": "max_steps",
            "steps_completed": int(scenario["max_steps"]),
            "max_steps": int(scenario["max_steps"]),
        }

    monkeypatch.setattr(main, "run_scenario", fake_run_scenario)

    result = main.run_batch_config(
        batch_config_path=batch_config_path,
        show_agent_views=False,
    )

    assert seen_case_ids == ["scan_case_0001", "scan_case_0002"]
    assert seen_max_steps == [4, 4]
    assert list(result["results"]) == ["scan_case_0001", "scan_case_0002"]
    assert all(
        case_result["stop_reason"] == "max_steps"
        for case_result in result["results"].values()
    )
    skipped_cases = json.loads(
        (tmp_path / "mllm_debug_outputs" / "batch" / "skipped_cases.json").read_text(
            encoding="utf-8"
        )
    )
    assert skipped_cases["skipped_case_count"] == 2
    assert skipped_cases["cases"]["scan_case_0001"]["reason"] == "max_steps"
    assert skipped_cases["cases"]["scan_case_0001"]["max_steps"] == 4


def test_run_batch_config_records_mllm_retry_exhausted_skip(tmp_path, monkeypatch):
    _write_json(tmp_path / "config" / "default_config.json", _default_config())
    _write_connectivity(tmp_path, "scan", 4)
    batch_config_path = tmp_path / "scenarios" / "batch.json"
    _write_json(
        batch_config_path,
        {
            "scans": [
                {
                    "scan_id": "scan",
                    "targets": [{"target_id": "0", "description": "target zero"}],
                }
            ],
            "agent_num_selections": [{"agent_number": 1, "case_number": 1}],
            "target_num_selections": [{"target_number": 1, "case_number": 1}],
        },
    )
    monkeypatch.setattr(main, "_project_root", lambda: tmp_path)

    def fake_run_scenario(scenario, show_agent_views, default_config):
        return {
            "target_found": {"0": False},
            "status": "incomplete",
            "stop_reason": "mllm_retry_exhausted",
            "steps_completed": 2,
            "failed_step_index": 3,
            "mllm_stage": "graph",
            "mllm_attempts": 5,
            "error": "invalid graph payload",
        }

    monkeypatch.setattr(main, "run_scenario", fake_run_scenario)

    result = main.run_batch_config(
        batch_config_path=batch_config_path,
        show_agent_views=False,
    )

    skipped_cases_path = Path(result["skipped_cases_path"])
    skipped_cases = json.loads(skipped_cases_path.read_text(encoding="utf-8"))
    record = skipped_cases["cases"]["scan_case_0001"]
    assert record["reason"] == "mllm_retry_exhausted"
    assert record["steps_completed"] == 2
    assert record["failed_step_index"] == 3
    assert record["mllm_stage"] == "graph"
    assert record["mllm_attempts"] == 5
    assert record["error"] == "invalid graph payload"


def test_run_batch_config_does_not_write_skip_ledger_for_completed_cases(
    tmp_path,
    monkeypatch,
):
    _write_json(tmp_path / "config" / "default_config.json", _default_config())
    _write_connectivity(tmp_path, "scan", 4)
    batch_config_path = tmp_path / "scenarios" / "batch.json"
    _write_json(
        batch_config_path,
        {
            "scans": [
                {
                    "scan_id": "scan",
                    "targets": [{"target_id": "0", "description": "target zero"}],
                }
            ],
            "agent_num_selections": [{"agent_number": 1, "case_number": 1}],
            "target_num_selections": [{"target_number": 1, "case_number": 1}],
        },
    )
    monkeypatch.setattr(main, "_project_root", lambda: tmp_path)

    def fake_run_scenario(scenario, show_agent_views, default_config):
        return {
            "target_found": {"0": True},
            "status": "completed",
            "stop_reason": "all_targets_found",
            "steps_completed": 1,
        }

    monkeypatch.setattr(main, "run_scenario", fake_run_scenario)

    result = main.run_batch_config(
        batch_config_path=batch_config_path,
        show_agent_views=False,
    )

    assert result["results"]["scan_case_0001"]["status"] == "completed"
    progress = json.loads(
        (tmp_path / "mllm_debug_outputs" / "batch" / "batch_progress.json").read_text(
            encoding="utf-8"
        )
    )
    assert progress["status"] == "completed"
    assert list(progress["completed_cases"]) == ["scan_case_0001"]
    assert not (
        tmp_path / "mllm_debug_outputs" / "batch" / "skipped_cases.json"
    ).exists()


def test_run_batch_config_terminates_on_provider_credit_result(tmp_path, monkeypatch):
    _write_json(tmp_path / "config" / "default_config.json", _default_config())
    _write_connectivity(tmp_path, "scan", 4)
    batch_config_path = tmp_path / "scenarios" / "batch.json"
    _write_json(
        batch_config_path,
        {
            "scans": [
                {
                    "scan_id": "scan",
                    "targets": [{"target_id": "0", "description": "target zero"}],
                }
            ],
            "agent_num_selections": [{"agent_number": 1, "case_number": 2}],
            "target_num_selections": [{"target_number": 1, "case_number": 1}],
        },
    )
    monkeypatch.setattr(main, "_project_root", lambda: tmp_path)

    seen_case_ids = []

    def fake_run_scenario(scenario, show_agent_views, default_config):
        seen_case_ids.append(str(scenario["test_case"]))
        return {
            "target_found": {"0": False},
            "status": "terminated",
            "stop_reason": "provider_credit_exhausted",
            "steps_completed": 0,
            "failed_step_index": 1,
            "mllm_stage": "detection",
            "mllm_router": "detection",
            "mllm_model": "detector",
            "provider_status_code": 402,
            "provider_code": "insufficient_balance",
            "provider_type": "billing_error",
            "error": "balance is not enough",
        }

    monkeypatch.setattr(main, "run_scenario", fake_run_scenario)

    result = main.run_batch_config(
        batch_config_path=batch_config_path,
        show_agent_views=False,
    )

    assert result["status"] == "terminated"
    assert seen_case_ids == ["scan_case_0001"]
    termination = json.loads(
        (tmp_path / "mllm_debug_outputs" / "batch" / "batch_termination.json").read_text(
            encoding="utf-8"
        )
    )
    assert termination["reason"] == "provider_credit_exhausted"
    assert termination["test_case"] == "scan_case_0001"
    assert termination["provider_status_code"] == 402
    assert termination["provider_code"] == "insufficient_balance"
    progress = json.loads(
        (tmp_path / "mllm_debug_outputs" / "batch" / "batch_progress.json").read_text(
            encoding="utf-8"
        )
    )
    assert progress["status"] == "terminated"
    assert progress["terminated_case"] == "scan_case_0001"
    assert progress["next_case_id"] == "scan_case_0001"


def test_run_batch_config_resume_starts_from_terminated_case(tmp_path, monkeypatch):
    _write_json(tmp_path / "config" / "default_config.json", _default_config())
    _write_connectivity(tmp_path, "scan", 4)
    batch_config_path = tmp_path / "scenarios" / "batch.json"
    _write_json(
        batch_config_path,
        {
            "scans": [
                {
                    "scan_id": "scan",
                    "targets": [{"target_id": "0", "description": "target zero"}],
                }
            ],
            "agent_num_selections": [{"agent_number": 1, "case_number": 3}],
            "target_num_selections": [{"target_number": 1, "case_number": 1}],
        },
    )
    monkeypatch.setattr(main, "_project_root", lambda: tmp_path)

    first_run_seen = []

    def first_run_scenario(scenario, show_agent_views, default_config):
        test_case = str(scenario["test_case"])
        first_run_seen.append(test_case)
        if test_case == "scan_case_0001":
            return {
                "target_found": {"0": True},
                "status": "completed",
                "stop_reason": "all_targets_found",
                "steps_completed": 1,
            }
        return {
            "target_found": {"0": False},
            "status": "terminated",
            "stop_reason": "provider_credit_exhausted",
            "steps_completed": 0,
            "failed_step_index": 1,
            "mllm_stage": "graph",
            "mllm_router": "graph",
            "mllm_model": "graph",
            "provider_status_code": 402,
            "provider_code": "insufficient_quota",
            "provider_type": "billing_error",
            "error": "quota exhausted",
        }

    monkeypatch.setattr(main, "run_scenario", first_run_scenario)
    first_result = main.run_batch_config(
        batch_config_path=batch_config_path,
        show_agent_views=False,
    )
    assert first_result["status"] == "terminated"
    assert first_run_seen == ["scan_case_0001", "scan_case_0002"]

    second_run_seen = []

    def second_run_scenario(scenario, show_agent_views, default_config):
        test_case = str(scenario["test_case"])
        second_run_seen.append(test_case)
        return {
            "target_found": {"0": True},
            "status": "completed",
            "stop_reason": "all_targets_found",
            "steps_completed": 1,
        }

    monkeypatch.setattr(main, "run_scenario", second_run_scenario)
    second_result = main.run_batch_config(
        batch_config_path=batch_config_path,
        show_agent_views=False,
    )

    assert second_result["status"] == "completed"
    assert second_run_seen == ["scan_case_0002", "scan_case_0003"]
    progress = json.loads(
        (tmp_path / "mllm_debug_outputs" / "batch" / "batch_progress.json").read_text(
            encoding="utf-8"
        )
    )
    assert progress["status"] == "completed"
    assert list(progress["completed_cases"]) == [
        "scan_case_0001",
        "scan_case_0002",
        "scan_case_0003",
    ]


def test_run_batch_config_rejects_generated_cases_from_different_config(
    tmp_path,
    monkeypatch,
):
    _write_json(tmp_path / "config" / "default_config.json", _default_config())
    _write_connectivity(tmp_path, "scan", 4)
    batch_config_path = tmp_path / "scenarios" / "batch.json"
    _write_json(
        batch_config_path,
        {
            "scans": [
                {
                    "scan_id": "scan",
                    "targets": [{"target_id": "0", "description": "target zero"}],
                }
            ],
            "agent_num_selections": [{"agent_number": 1, "case_number": 1}],
            "target_num_selections": [{"target_number": 1, "case_number": 1}],
        },
    )
    monkeypatch.setattr(main, "_project_root", lambda: tmp_path)

    def fake_run_scenario(scenario, show_agent_views, default_config):
        return {
            "target_found": {"0": True},
            "status": "completed",
            "stop_reason": "all_targets_found",
            "steps_completed": 1,
        }

    monkeypatch.setattr(main, "run_scenario", fake_run_scenario)
    main.run_batch_config(
        batch_config_path=batch_config_path,
        show_agent_views=False,
    )

    _write_json(
        batch_config_path,
        {
            "scans": [
                {
                    "scan_id": "scan",
                    "targets": [{"target_id": "0", "description": "target zero"}],
                }
            ],
            "agent_num_selections": [{"agent_number": 1, "case_number": 2}],
            "target_num_selections": [{"target_number": 1, "case_number": 1}],
        },
    )

    with pytest.raises(ValueError, match="different batch config"):
        main.run_batch_config(
            batch_config_path=batch_config_path,
            show_agent_views=False,
        )


def test_debugger_listens_once_for_repeated_scenario_runs(monkeypatch):
    class FakeDebugpy:
        def __init__(self):
            self.listen_calls = []
            self.wait_calls = 0
            self.connected = False

        def listen(self, address):
            self.listen_calls.append(address)

        def is_client_connected(self):
            return self.connected

        def wait_for_client(self):
            self.wait_calls += 1
            self.connected = True

    fake_debugpy = FakeDebugpy()
    monkeypatch.setattr(main, "DEBUGPY_LISTENING", False)
    monkeypatch.setattr(main, "debugpy", fake_debugpy)

    main._wait_for_debugger()
    main._wait_for_debugger()

    assert fake_debugpy.listen_calls == [("0.0.0.0", 5678)]
    assert fake_debugpy.wait_calls == 1
    assert not main.is_batch_config(
        {
            "scan_id": "scan",
            "agents": [],
            "targets": [],
        }
    )
