from collections import Counter
import json

from main import (
    _batch_param_config_key,
    _sample_marginal_batch_case_ids,
    sample_batch_case_ids,
    write_sampled_batch_manifests,
)


def _synthetic_225_case_summary():
    scans = [
        "r47D5H71a5s",
        "zsNo4HB9uLZ",
        "JF19kD82Mey",
        "RPmz2sHmrrY",
        "17DRP5sb8fy",
    ]
    agent_numbers = [1, 3, 5]
    agent_selection_indices = [0, 1, 2]
    target_selection_indices_by_target_number = {
        1: [0, 1],
        4: [0, 1],
        8: [0],
    }
    cases = {}
    case_order = []
    for scan_id in scans:
        case_index = 1
        for agent_number in agent_numbers:
            for target_number in [1, 4, 8]:
                for agent_selection_index in agent_selection_indices:
                    for target_selection_index in (
                        target_selection_indices_by_target_number[target_number]
                    ):
                        case_id = "%s_case_%04d" % (scan_id, case_index)
                        cases[case_id] = {
                            "test_case": case_id,
                            "scan_id": scan_id,
                            "agent_number": agent_number,
                            "agent_selection_index": agent_selection_index,
                            "target_number": target_number,
                            "target_selection_index": target_selection_index,
                        }
                        case_order.append(case_id)
                        case_index += 1
    return {
        "batch_id": "batch_test",
        "generated_case_count": len(case_order),
        "case_order": case_order,
        "cases": cases,
    }


def _selected_cases(summary, case_ids):
    return [summary["cases"][case_id] for case_id in case_ids]


def _assert_balanced_100(summary, case_ids):
    cases = _selected_cases(summary, case_ids)
    assert len(case_ids) == 100
    assert Counter(case["scan_id"] for case in cases) == {
        "r47D5H71a5s": 20,
        "zsNo4HB9uLZ": 20,
        "JF19kD82Mey": 20,
        "RPmz2sHmrrY": 20,
        "17DRP5sb8fy": 20,
    }
    assert Counter(int(case["target_number"]) for case in cases) == {
        1: 40,
        4: 40,
        8: 20,
    }

    agent_counts = Counter(int(case["agent_number"]) for case in cases)
    assert set(agent_counts) == {1, 3, 5}
    assert set(agent_counts.values()) <= {33, 34}
    assert sum(agent_counts.values()) == 100

    combo_counts = Counter(
        (int(case["agent_number"]), int(case["target_number"])) for case in cases
    )
    assert set(combo_counts) == {
        (1, 1),
        (1, 4),
        (1, 8),
        (3, 1),
        (3, 4),
        (3, 8),
        (5, 1),
        (5, 4),
        (5, 8),
    }
    for (agent_number, target_number), count in combo_counts.items():
        if target_number in (1, 4):
            assert count in (13, 14)
        else:
            assert count in (6, 7)

    param_counts = Counter(_batch_param_config_key(case) for case in cases)
    assert len(param_counts) == 45
    assert set(param_counts.values()) <= {2, 3}


def test_param_config_sample_balances_synthetic_batch_test_shape():
    summary = _synthetic_225_case_summary()

    case_ids = sample_batch_case_ids(
        summary,
        sample_count=100,
        sample_seed=0,
        sample_balance="param_config",
    )

    _assert_balanced_100(summary, case_ids)


def test_param_config_sample_is_deterministic_and_seeded():
    summary = _synthetic_225_case_summary()

    seed_zero = sample_batch_case_ids(
        summary,
        sample_count=100,
        sample_seed=0,
        sample_balance="param_config",
    )
    seed_zero_again = sample_batch_case_ids(
        summary,
        sample_count=100,
        sample_seed=0,
        sample_balance="param_config",
    )
    seed_one = sample_batch_case_ids(
        summary,
        sample_count=100,
        sample_seed=1,
        sample_balance="param_config",
    )

    assert seed_zero == seed_zero_again
    assert seed_zero != seed_one
    _assert_balanced_100(summary, seed_one)


def test_default_sample_balance_preserves_marginal_sampler():
    summary = _synthetic_225_case_summary()

    assert sample_batch_case_ids(
        summary,
        sample_count=30,
        sample_seed=0,
    ) == _sample_marginal_batch_case_ids(
        summary,
        sample_count=30,
        sample_seed=0,
    )


def test_sampled_manifest_records_param_config_diagnostics(tmp_path):
    summary = _synthetic_225_case_summary()
    case_ids = sample_batch_case_ids(
        summary,
        sample_count=100,
        sample_seed=0,
        sample_balance="param_config",
    )

    sampled_cases_path, _sampled_summary_path = write_sampled_batch_manifests(
        batch_id="batch_test",
        summary=summary,
        sampled_case_ids=case_ids,
        sample_count=100,
        sample_seed=0,
        project_root=tmp_path,
        run_id="balanced100",
        sample_balance="param_config",
    )

    with open(sampled_cases_path, "r", encoding="utf-8") as file_handle:
        manifest = json.load(file_handle)

    assert manifest["sample_balance"] == "param_config"
    assert set(manifest["distribution"]) == {
        "scan_id",
        "agent_number",
        "target_number",
        "agent_target_combo",
        "param_config",
    }
    assert manifest["distribution"]["target_number"] == {
        "1": 40,
        "4": 40,
        "8": 20,
    }
    assert len(manifest["distribution"]["param_config"]) == 45
