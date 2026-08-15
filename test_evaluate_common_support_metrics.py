from __future__ import annotations

import math

from evaluate_common_support_metrics import calculate_matched_metrics


def test_calculate_matched_metrics_uses_equal_episode_means_and_micro_f1():
    method_specs = [("A", "task_A"), ("B", "task_B")]
    hypothesis_rows = []
    task_rows = []
    for report_method, task_method in method_specs:
        for group, agent_number in (("single", 1), ("multi", 3)):
            for index, case_id in enumerate(
                (f"{group}_case_1", f"{group}_case_2")
            ):
                hypothesis_rows.append(
                    {
                        "method": report_method,
                        "case_id": case_id,
                        "agent_group": group,
                        "in_common_support": "1",
                        "episode_target_balanced_pwgs": str(0.2 + 0.4 * index),
                    }
                )
                task_rows.append(
                    {
                        "method": task_method,
                        "case_id": case_id,
                        "agent_number": str(agent_number),
                        "target_number": "2",
                        "progress": str(0.25 + 0.5 * index),
                        "team_ppl_total": str(0.1 + 0.2 * index),
                        "team_ppl_makespan": str(0.15 + 0.2 * index),
                        "total_distance": str(10 + 10 * index),
                        "maximum_agent_distance": str(5 + 5 * index),
                        "tp": str(1 + index),
                        "fp": str(index),
                        "fn": str(2 - index),
                    }
                )

    case_rows, summary_rows, common_by_group = calculate_matched_metrics(
        method_specs=method_specs,
        task_rows=task_rows,
        hypothesis_rows=hypothesis_rows,
    )

    assert len(case_rows) == 8
    assert common_by_group == {
        "single": ["single_case_1", "single_case_2"],
        "multi": ["multi_case_1", "multi_case_2"],
    }
    for row in summary_rows:
        assert row["case_count"] == 2
        assert math.isclose(row["progress"], 0.5)
        assert math.isclose(row["team_ppl_total"], 0.2)
        assert math.isclose(row["team_ppl_makespan"], 0.25)
        assert math.isclose(row["target_balanced_pwgs"], 0.4)
        assert math.isclose(row["f1"], 6 / 10)
        assert row["tp"] == 3
        assert row["fp"] == 1
        assert row["fn"] == 3


def test_task_only_benchmark_uses_common_ids_and_has_no_pwgs():
    method_specs = [("Graph", "task_graph")]
    benchmark_specs = [
        ("VLFM-G", "task_vlfm", frozenset({"single", "multi"})),
        ("Dec-Graph", "task_dec", frozenset({"multi"})),
    ]
    hypothesis_rows = []
    task_rows = []
    for group, agent_number in (("single", 1), ("multi", 3)):
        case_id = f"{group}_case"
        hypothesis_rows.append(
            {
                "method": "Graph",
                "case_id": case_id,
                "agent_group": group,
                "in_common_support": "1",
                "episode_target_balanced_pwgs": "0.75",
            }
        )
        for task_method in ("task_graph", "task_vlfm", "task_dec"):
            task_rows.append(
                {
                    "method": task_method,
                    "case_id": case_id,
                    "agent_number": str(agent_number),
                    "target_number": "2",
                    "progress": "0.5",
                    "team_ppl_total": "0.25",
                    "team_ppl_makespan": "0.3",
                    "total_distance": "10",
                    "maximum_agent_distance": "5",
                    "tp": "2",
                    "fp": "1",
                    "fn": "1",
                }
            )

    case_rows, summary_rows, _ = calculate_matched_metrics(
        method_specs=method_specs,
        task_rows=task_rows,
        hypothesis_rows=hypothesis_rows,
        benchmark_specs=benchmark_specs,
    )

    assert len(case_rows) == 5
    benchmark_rows = [
        row
        for row in summary_rows
        if row["method"] in {"VLFM-G", "Dec-Graph"}
    ]
    assert [(row["method"], row["agent_group"]) for row in benchmark_rows] == [
        ("VLFM-G", "single"),
        ("VLFM-G", "multi"),
        ("Dec-Graph", "multi"),
    ]
    assert all(row["target_balanced_pwgs"] == "" for row in benchmark_rows)
