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


def test_region_target_update_excludes_found_targets_removed_from_nodes():
    graph = HypothesisGraph(
        targets=[
            {"target_id": "0", "description": "active target"},
            {"target_id": "1", "description": "found target"},
        ],
    )
    graph.add_or_update_node(
        node_id=1,
        label="vp1",
        node_type=TYPE_VP,
        target_probs={"0": 0.2, "1": 0.4},
        raw_target_probs={"0": 2.0, "1": 4.0},
    )
    graph.add_or_update_node(
        node_id=2,
        label="vp2",
        node_type=TYPE_VP,
        target_probs={"0": 0.4, "1": 0.6},
        raw_target_probs={"0": 4.0, "1": 6.0},
    )
    graph.add_or_update_node(
        node_id=100,
        label="assigned region",
        node_type=TYPE_REGION,
        exist_prob=1.0,
        target_probs={"0": 0.0, "1": 0.2},
        raw_target_probs={"0": 0.0, "1": 2.0},
    )
    graph.add_or_update_node(
        node_id=101,
        label="unassigned region",
        node_type=TYPE_REGION,
        exist_prob=1.0,
        target_probs={"0": 0.0, "1": 0.8},
        raw_target_probs={"0": 0.0, "1": 8.0},
    )
    graph.region_to_viewpoints = {100: {1, 2}}
    graph.mark_target_found("1")
    graph._remove_found_target_probs_from_nodes()

    graph._apply_region_target_probabilities(
        region_target_scores={101: {"0": 0.6}},
        previous_type1_region_ids=set(),
    )

    assert graph.nodes[100].raw_target_probs["0"] == pytest.approx(0.3)
    assert graph.nodes[101].raw_target_probs["0"] == pytest.approx(0.6)
    assert graph.nodes[100].target_probs["0"] == pytest.approx(1.0 / 3.0)
    assert graph.nodes[101].target_probs["0"] == pytest.approx(2.0 / 3.0)
    for node in graph.nodes.values():
        assert "1" not in node.target_probs
        assert "1" not in node.raw_target_probs


def test_region_merge_excludes_found_targets_removed_from_nodes():
    graph = HypothesisGraph(
        targets=[
            {"target_id": "0", "description": "active target"},
            {"target_id": "1", "description": "found target"},
        ],
    )
    graph.add_or_update_node(
        node_id=100,
        label="canonical region",
        node_type=TYPE_REGION,
        exist_prob=0.5,
        target_probs={"0": 0.2, "1": 0.4},
        raw_target_probs={"0": 0.3, "1": 0.5},
    )
    graph.add_or_update_node(
        node_id=101,
        label="merged region",
        node_type=TYPE_REGION,
        exist_prob=0.7,
        target_probs={"0": 0.6, "1": 0.8},
        raw_target_probs={"0": 0.9, "1": 1.0},
    )
    graph.mark_target_found("1")
    graph._remove_found_target_probs_from_nodes()

    graph._merge_region_nodes(canonical_id=100, merged_id=101)

    assert 101 not in graph.nodes
    assert graph.nodes[100].target_probs["0"] == pytest.approx(0.6)
    assert graph.nodes[100].raw_target_probs["0"] == pytest.approx(0.9)
    assert "1" not in graph.nodes[100].target_probs
    assert "1" not in graph.nodes[100].raw_target_probs
