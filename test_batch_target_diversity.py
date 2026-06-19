import random

import pytest

from route_plotter import EnvironmentGraph

import main


def _targets(count):
    return [
        {
            "target_id": str(index),
            "description": "target %s" % index,
        }
        for index in range(count)
    ]


def _target_key(selection):
    return tuple(sorted(str(target["target_id"]) for target in selection))


def _line_graph(node_count):
    return EnvironmentGraph(
        scan_id="scan",
        viewpoint_id_by_index={
            node_index: "vp%s" % node_index for node_index in range(node_count)
        },
        coords_by_node_id={
            node_index: (float(node_index), 0.0) for node_index in range(node_count)
        },
        edge_distances={
            (node_index, node_index + 1): 1.0
            for node_index in range(node_count - 1)
        },
    )


def _line_graph_with_isolated_node():
    return EnvironmentGraph(
        scan_id="scan",
        viewpoint_id_by_index={
            0: "vp0",
            1: "vp1",
            2: "vp2",
            3: "isolated",
        },
        coords_by_node_id={
            0: (0.0, 0.0),
            1: (1.0, 0.0),
            2: (2.0, 0.0),
            3: (10.0, 0.0),
        },
        edge_distances={
            (0, 1): 1.0,
            (1, 2): 1.0,
        },
    )


def test_diverse_target_selections_use_each_combination_once():
    selections = main._build_diverse_target_selections(
        targets=_targets(4),
        target_number=2,
        selection_count=6,
        random_source=random.Random(3),
    )
    selection_keys = [_target_key(selection) for selection in selections]

    assert len(selection_keys) == 6
    assert len(set(selection_keys)) == 6


def test_diverse_target_selections_repeat_after_full_combination_deck():
    selections = main._build_diverse_target_selections(
        targets=_targets(3),
        target_number=2,
        selection_count=5,
        random_source=random.Random(5),
    )
    selection_keys = [_target_key(selection) for selection in selections]

    assert len(selection_keys) == 5
    assert len(set(selection_keys[:3])) == 3
    assert set(selection_keys[:3]) == {
        ("0", "1"),
        ("0", "2"),
        ("1", "2"),
    }


def test_diverse_target_selections_rng_changes_order_but_preserves_coverage():
    first = main._build_diverse_target_selections(
        targets=_targets(4),
        target_number=2,
        selection_count=6,
        random_source=random.Random(1),
    )
    second = main._build_diverse_target_selections(
        targets=_targets(4),
        target_number=2,
        selection_count=6,
        random_source=random.Random(2),
    )
    first_keys = [_target_key(selection) for selection in first]
    second_keys = [_target_key(selection) for selection in second]

    assert first_keys != second_keys
    assert set(first_keys) == set(second_keys)


def test_generate_batch_scenarios_diversifies_targets_across_agent_counts(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        main,
        "load_environment_graph",
        lambda scan_id, connectivity_dir: _line_graph(4),
    )
    batch_config = {
        "scans": [
            {
                "scan_id": "scan",
                "targets": _targets(4),
            }
        ],
        "agent_num_selections": [
            {
                "agent_number": 1,
                "case_number": 2,
            },
            {
                "agent_number": 2,
                "case_number": 1,
            },
        ],
        "target_num_selections": [
            {
                "target_number": 2,
                "case_number": 2,
            }
        ],
    }

    scenarios, summary = main.generate_batch_scenarios(
        batch_config=batch_config,
        batch_id="batch",
        project_root=tmp_path,
        default_config={"mllm": {}, "bayes": {}, "optimizer": {}},
        rng=random.Random(7),
    )

    generated_cases = list(summary["cases"].values())
    target_keys = [_target_key(case["targets"]) for case in generated_cases]
    assert len(scenarios) == 6
    assert len(target_keys) == 6
    assert len(set(target_keys)) == 6
    assert all(case["target_number"] == 2 for case in generated_cases)
    assert all("target_selection_index" in case for case in generated_cases)
    assert all("targets" in case for case in generated_cases)


def test_select_spread_viewpoint_ids_excludes_isolated_nodes():
    selected_viewpoint_ids = main._select_spread_viewpoint_ids(
        environment_graph=_line_graph_with_isolated_node(),
        agent_number=3,
        random_source=random.Random(1),
    )

    assert sorted(selected_viewpoint_ids) == ["vp0", "vp1", "vp2"]
    assert "isolated" not in selected_viewpoint_ids


def test_select_spread_viewpoint_ids_requires_navigable_start_capacity():
    with pytest.raises(
        ValueError,
        match="Requested 4 agents but only 3 navigable start viewpoints exist.",
    ):
        main._select_spread_viewpoint_ids(
            environment_graph=_line_graph_with_isolated_node(),
            agent_number=4,
            random_source=random.Random(1),
        )
