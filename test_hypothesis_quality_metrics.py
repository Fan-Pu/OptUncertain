from __future__ import annotations

import pytest

from evaluate_hypothesis_quality_metrics import (
    LastUngroundedEdgePrediction,
    _aggregate_common_support,
    _select_common_support,
    compute_target_balanced_episode_pwgs,
    compute_target_time_pwgs,
    edge_jnll_status,
    eligible_target_distribution,
    last_ungrounded_edge_predictions,
)


def _viewpoint(
    node_id,
    label,
    probability,
    *,
    grounded=False,
    visits=0,
):
    return {
        "id": node_id,
        "label": label,
        "type": "viewpoint",
        "grounded": grounded,
        "node_visit_times": visits,
        "target_probs": {"target": probability},
    }


def _snapshot(nodes, edges=()):
    return {
        "nodes": list(nodes),
        "edges": list(edges),
        "target_found": {"target": False},
    }


def _edge(source, target, *, grounded, probability, mean, variance):
    return {
        "i": source,
        "j": target,
        "type": "vv",
        "grounded": grounded,
        "cond_exist_prob": probability,
        "distance_mean": mean,
        "distance_var": variance,
    }


def test_pwgs_on_known_weighted_oracle_distances():
    score = compute_target_time_pwgs(
        probabilities_by_viewpoint={"oracle": 0.25, "middle": 0.50, "far": 0.25},
        distance_to_oracle_by_viewpoint={
            "oracle": 0.0,
            "middle": 2.0,
            "far": 4.0,
        },
        max_oracle_distance=4.0,
    )

    assert score == pytest.approx(0.5)


def test_eligible_distribution_excludes_grounded_current_visited_and_inactive():
    snapshot = _snapshot(
        [
            _viewpoint(0, "eligible", 1.0),
            _viewpoint(1, "grounded", 0.0, grounded=True),
            _viewpoint(2, "visited", 0.0, visits=1),
            _viewpoint(3, "current", 0.0),
            {
                "id": 4,
                "label": "region",
                "type": "region",
                "grounded": False,
                "node_visit_times": 0,
                "target_probs": {"target": 0.0},
            },
        ]
    )

    assert eligible_target_distribution(snapshot, "target", [3]) == {
        "eligible": 1.0
    }
    snapshot["target_found"]["target"] = True
    active_target_ids = [
        target_id
        for target_id, found in snapshot["target_found"].items()
        if not found
    ]
    assert active_target_ids == []


def test_pwgs_refuses_to_renormalize_non_normalized_distribution():
    with pytest.raises(ValueError, match="refusing to renormalize"):
        compute_target_time_pwgs(
            probabilities_by_viewpoint={"a": 0.2, "b": 0.7},
            distance_to_oracle_by_viewpoint={"a": 0.0, "b": 1.0},
            max_oracle_distance=1.0,
        )


def test_target_balanced_pwgs_averages_time_then_targets():
    score = compute_target_balanced_episode_pwgs(
        {
            "target_a": [0.2, 0.3, 0.4, 0.5],
            "target_b": [0.9],
        }
    )

    assert score == pytest.approx(0.625)


def test_target_balanced_pwgs_requires_an_evaluable_target():
    with pytest.raises(ValueError, match="at least one evaluable target"):
        compute_target_balanced_episode_pwgs(
            {
                "target_a": [],
                "target_b": [],
            }
        )


def test_common_subset_uses_equal_episode_weighting():
    methods = ["A", "B"]
    case_order = ["single_1", "single_2", "multi_1"]
    rows = [
        {
            "method": "A",
            "case_id": "single_1",
            "agent_group": "single",
            "evaluation_status": "evaluable",
            "episode_pwgs": 0.2,
            "episode_target_balanced_pwgs": 0.3,
            "ungrounded_edge_candidate_count": 0,
        },
        {
            "method": "A",
            "case_id": "single_2",
            "agent_group": "single",
            "evaluation_status": "evaluable",
            "episode_pwgs": 0.8,
            "episode_target_balanced_pwgs": 0.7,
            "ungrounded_edge_candidate_count": 0,
        },
        {
            "method": "A",
            "case_id": "multi_1",
            "agent_group": "multi",
            "evaluation_status": "evaluable",
            "episode_pwgs": 0.4,
            "episode_target_balanced_pwgs": 0.5,
            "ungrounded_edge_candidate_count": 0,
        },
        {
            "method": "B",
            "case_id": "single_1",
            "agent_group": "single",
            "evaluation_status": "evaluable",
            "episode_pwgs": 0.6,
            "episode_target_balanced_pwgs": 0.4,
            "ungrounded_edge_candidate_count": 0,
        },
        {
            "method": "B",
            "case_id": "single_2",
            "agent_group": "single",
            "evaluation_status": "not_applicable_no_target_hypothesis",
            "episode_pwgs": "",
            "episode_target_balanced_pwgs": "",
            "ungrounded_edge_candidate_count": 0,
        },
        {
            "method": "B",
            "case_id": "multi_1",
            "agent_group": "multi",
            "evaluation_status": "evaluable",
            "episode_pwgs": 0.9,
            "episode_target_balanced_pwgs": 0.8,
            "ungrounded_edge_candidate_count": 0,
        },
    ]

    common, exclusions = _select_common_support(rows, methods, case_order)
    assert common == {"single": {"single_1"}, "multi": {"multi_1"}}
    assert exclusions[0]["case_id"] == "single_2"

    summary = _aggregate_common_support(rows, methods, common)
    values = {
        (row["method"], row["agent_group"]): row["pwgs"] for row in summary
    }
    assert values[("A", "single")] == pytest.approx(0.2)
    assert values[("B", "single")] == pytest.approx(0.6)
    assert values[("A", "multi")] == pytest.approx(0.4)
    assert values[("B", "multi")] == pytest.approx(0.9)
    target_balanced_values = {
        (row["method"], row["agent_group"]): row["target_balanced_pwgs"]
        for row in summary
    }
    assert target_balanced_values[("A", "single")] == pytest.approx(0.3)
    assert target_balanced_values[("B", "single")] == pytest.approx(0.4)
    assert target_balanced_values[("A", "multi")] == pytest.approx(0.5)
    assert target_balanced_values[("B", "multi")] == pytest.approx(0.8)


def test_edge_lifecycle_uses_final_ungrounded_and_ignores_later_grounding():
    nodes = [
        _viewpoint(0, "vp_a", 0.5),
        _viewpoint(1, "vp_b", 0.5),
    ]
    snapshots = [
        (
            1,
            _snapshot(
                nodes,
                [_edge(0, 1, grounded=False, probability=0.4, mean=3.0, variance=4.0)],
            ),
        ),
        (
            2,
            _snapshot(
                nodes,
                [_edge(0, 1, grounded=False, probability=0.7, mean=2.5, variance=2.0)],
            ),
        ),
        (
            3,
            _snapshot(
                nodes,
                [_edge(0, 1, grounded=True, probability=1.0, mean=2.0, variance=0.0)],
            ),
        ),
    ]

    result = last_ungrounded_edge_predictions(snapshots)

    assert result[("vp_a", "vp_b")] == LastUngroundedEdgePrediction(
        step_index=2,
        endpoint_labels=("vp_a", "vp_b"),
        cond_exist_prob=0.7,
        distance_mean=2.5,
        distance_var=2.0,
    )


def test_no_ungrounded_predictions_is_not_a_perfect_numeric_score():
    status = edge_jnll_status(iter(()))

    assert status == "not_estimable_no_ungrounded_predictions"
    assert status != 0.0
