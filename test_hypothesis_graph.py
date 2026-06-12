import pytest

from Helper import TYPE_REGION, TYPE_VP
from semantic_persistence import HypothesisGraph


def test_region_targets_use_assigned_viewpoint_mean_and_union_normalization():
    graph = HypothesisGraph(
        targets=[{"target_id": "0", "description": "target"}],
    )
    graph.add_or_update_node(
        node_id=1,
        label="vp1",
        node_type=TYPE_VP,
        target_probs={"0": 0.2},
        raw_target_probs={"0": 2.0},
    )
    graph.add_or_update_node(
        node_id=2,
        label="vp2",
        node_type=TYPE_VP,
        target_probs={"0": 0.4},
        raw_target_probs={"0": 4.0},
    )
    graph.add_or_update_node(
        node_id=100,
        label="assigned region",
        node_type=TYPE_REGION,
        exist_prob=1.0,
        target_probs={"0": 0.0},
        raw_target_probs={"0": 0.0},
    )
    graph.add_or_update_node(
        node_id=101,
        label="unassigned region",
        node_type=TYPE_REGION,
        exist_prob=1.0,
        target_probs={"0": 0.0},
        raw_target_probs={"0": 0.0},
    )
    graph.region_to_viewpoints = {100: {1, 2}}

    graph._apply_region_target_probabilities(
        region_target_scores={101: {"0": 0.6}},
        previous_type1_region_ids=set(),
    )

    assert graph.nodes[100].raw_target_probs["0"] == pytest.approx(0.3)
    assert graph.nodes[101].raw_target_probs["0"] == pytest.approx(0.6)
    assert graph.nodes[100].target_probs["0"] == pytest.approx(1.0 / 3.0)
    assert graph.nodes[101].target_probs["0"] == pytest.approx(2.0 / 3.0)
