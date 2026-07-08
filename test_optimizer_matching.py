from optimization_model.optimizer import RollingHorizonOptimizer
from semantic_persistence.hypothesis_graph import HypothesisGraph
from Helper import TYPE_VP


def test_full_agent_target_matching_requires_distinct_targets():
    assert RollingHorizonOptimizer._has_full_agent_target_matching(
        agent_ids=["agent0", "agent1", "agent2"],
        target_candidates_by_agent={
            "agent0": {"target0", "target1"},
            "agent1": {"target0", "target1"},
            "agent2": {"target0", "target1"},
        },
    ) is False


def test_full_agent_target_matching_allows_rematching():
    assert RollingHorizonOptimizer._has_full_agent_target_matching(
        agent_ids=["agent0", "agent1", "agent2"],
        target_candidates_by_agent={
            "agent0": {"target0"},
            "agent1": {"target0", "target1"},
            "agent2": {"target1", "target2"},
        },
    ) is True


def test_target_directed_unique_rewards_are_optional_when_first_hops_conflict():
    graph = HypothesisGraph(
        targets=[
            {"target_id": "0", "description": "target zero"},
            {"target_id": "3", "description": "target three"},
        ]
    )
    graph.add_or_update_node(
        node_id=25,
        label="start",
        node_type=TYPE_VP,
        grounded=True,
        target_probs={"0": 0.0, "3": 0.0},
        raw_target_probs={"0": 0.0, "3": 0.0},
        node_visit_times=1,
    )
    graph.add_or_update_node(
        node_id=37,
        label="left",
        node_type=TYPE_VP,
        grounded=False,
        target_probs={"0": 1.0, "3": 0.0},
        raw_target_probs={"0": 1.0, "3": 0.0},
    )
    graph.add_or_update_node(
        node_id=39,
        label="right",
        node_type=TYPE_VP,
        grounded=False,
        target_probs={"0": 0.0, "3": 1.0},
        raw_target_probs={"0": 0.0, "3": 1.0},
    )
    graph.add_or_update_edge(
        source_node_id=25,
        target_node_id=37,
        distance_mean=1.0,
        distance_var=0.0,
        cond_exist_prob=1.0,
        exist_prob=1.0,
        grounded=True,
    )
    graph.add_or_update_edge(
        source_node_id=25,
        target_node_id=39,
        distance_mean=1.0,
        distance_var=0.0,
        cond_exist_prob=1.0,
        exist_prob=1.0,
        grounded=True,
    )

    optimizer = RollingHorizonOptimizer(
        {
            "goal_weight": 1.0,
            "dist_weight": 0.0,
            "arc_weight": 0.0,
            "node_weight": 0.0,
            "visit_weight": 0.0,
            "target_directed_mode": True,
            "write_model_lp": False,
        }
    )

    result = optimizer.solve(
        hypothesis_graph=graph,
        agent_current_vp_ids={"agent0": 25},
        target_found_flags={"0": False, "3": False},
    )

    assert result["agent_paths"]["agent0"]["next_vp_node_id"] in {37, 39}
    assert len(result["target_assignments"]) == 1
