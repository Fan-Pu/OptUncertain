import pytest

from Helper import TYPE_REGION, TYPE_VP
from semantic_persistence.hypothesis_graph import HypothesisGraph


def _graph(bayes_config):
    graph = HypothesisGraph(
        targets=[{"target_id": "target", "description": "target"}],
        bayes_config=bayes_config,
    )
    for node_id in (1, 2, 3):
        graph.add_or_update_node(
            node_id=node_id,
            label="vp%s" % node_id,
            node_type=TYPE_VP,
            exist_prob=1.0,
            grounded=False,
            target_probs={"target": 0.0},
            raw_target_probs={"target": 0.0},
        )
    graph.add_or_update_edge(
        source_node_id=1,
        target_node_id=2,
        distance_mean=2.0,
        distance_var=0.0,
        cond_exist_prob=1.0,
        exist_prob=1.0,
        grounded=True,
    )
    graph.add_or_update_edge(
        source_node_id=2,
        target_node_id=3,
        distance_mean=5.0,
        distance_var=4.0,
        cond_exist_prob=0.5,
        exist_prob=0.5,
        grounded=False,
    )
    return graph


def _add_second_grounded_vv_edge(graph):
    graph.add_or_update_node(
        node_id=4,
        label="vp4",
        node_type=TYPE_VP,
        exist_prob=1.0,
        grounded=False,
        target_probs={"target": 0.0},
        raw_target_probs={"target": 0.0},
    )
    graph.add_or_update_edge(
        source_node_id=1,
        target_node_id=4,
        distance_mean=4.0,
        distance_var=0.0,
        cond_exist_prob=1.0,
        exist_prob=1.0,
        grounded=True,
    )


def test_hypothesis_graph_accepts_only_retained_bayes_parameters():
    graph = HypothesisGraph(
        targets=[{"target_id": "target", "description": "target"}],
        bayes_config={
            "sigma_vv2": 4.0,
            "kappa_vv": 1.0,
            "varrho": 0.7,
            "epsilon": 1e-6,
        },
    )

    assert graph.bayes_config == {
        "sigma_vv2": 4.0,
        "kappa_vv": 1.0,
        "varrho": 0.7,
        "epsilon": 1e-6,
    }


def test_vv_distance_update_uses_sigma_vv2_kappa_vv_and_epsilon():
    no_region_coupling = _graph(
        {
            "sigma_vv2": 4.0,
            "kappa_vv": 0.0,
            "varrho": 0.7,
            "epsilon": 1e-3,
        }
    )
    with_region_coupling = _graph(
        {
            "sigma_vv2": 4.0,
            "kappa_vv": 3.0,
            "varrho": 0.7,
            "epsilon": 1e-3,
        }
    )
    no_region_coupling.viewpoint_to_region = {2: 10, 3: 10}
    with_region_coupling.viewpoint_to_region = {2: 10, 3: 10}
    _add_second_grounded_vv_edge(no_region_coupling)
    _add_second_grounded_vv_edge(with_region_coupling)

    for graph in (no_region_coupling, with_region_coupling):
        graph._update_edge_distance_posteriors(
            existing_edge_ids={(2, 3)},
            previous_distance_means={(2, 3): 5.0},
            previous_distance_vars={},
            previous_cond_exist_probs={(2, 3): 0.5},
            scorer=None,
        )

    assert no_region_coupling.edges[(2, 3)].distance_var > 0.0
    assert (
        with_region_coupling.edges[(2, 3)].distance_var
        < no_region_coupling.edges[(2, 3)].distance_var
    )
    assert with_region_coupling.edges[(2, 3)].distance_mean < 5.0


def test_vv_existence_update_uses_varrho_and_region_assignment():
    same_region = _graph(
        {
            "sigma_vv2": 4.0,
            "kappa_vv": 1.0,
            "varrho": 0.8,
            "epsilon": 1e-6,
        }
    )
    different_region = _graph(
        {
            "sigma_vv2": 4.0,
            "kappa_vv": 1.0,
            "varrho": 0.8,
            "epsilon": 1e-6,
        }
    )
    same_region.viewpoint_to_region = {2: 10, 3: 10}
    different_region.viewpoint_to_region = {2: 10, 3: 11}

    for graph in (same_region, different_region):
        graph._update_edge_existence_posteriors(
            existing_edge_ids={(2, 3)},
            previous_distance_means={(2, 3): 2.0},
            previous_cond_exist_probs={(2, 3): 0.5},
            scorer=None,
        )

    assert same_region.edges[(2, 3)].cond_exist_prob > 0.5
    assert different_region.edges[(2, 3)].cond_exist_prob < 0.5


def test_bayes_updates_reject_non_vv_edges():
    graph = HypothesisGraph(
        targets=[{"target_id": "target", "description": "target"}],
        bayes_config={
            "sigma_vv2": 4.0,
            "kappa_vv": 1.0,
            "varrho": 0.7,
            "epsilon": 1e-6,
        },
    )
    graph.add_or_update_node(
        node_id=1,
        label="vp1",
        node_type=TYPE_VP,
        exist_prob=1.0,
        grounded=False,
    )
    graph.add_or_update_node(
        node_id=10,
        label="region",
        node_type=TYPE_REGION,
        exist_prob=1.0,
        grounded=False,
    )
    graph.add_or_update_edge(
        source_node_id=1,
        target_node_id=10,
        distance_mean=1.0,
        distance_var=1.0,
        cond_exist_prob=0.5,
        exist_prob=0.5,
        grounded=False,
    )

    with pytest.raises(ValueError, match="only supports VV edges"):
        graph._update_edge_distance_posteriors(
            existing_edge_ids={(1, 10)},
            previous_distance_means={(1, 10): 1.0},
            previous_distance_vars={(1, 10): 1.0},
            previous_cond_exist_probs={(1, 10): 0.5},
            scorer=None,
        )
    with pytest.raises(ValueError, match="only supports VV edges"):
        graph._update_edge_existence_posteriors(
            existing_edge_ids={(1, 10)},
            previous_distance_means={(1, 10): 1.0},
            previous_cond_exist_probs={(1, 10): 0.5},
            scorer=None,
        )
