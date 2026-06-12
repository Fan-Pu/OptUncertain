from semantic_persistence.hypothesis_graph import HypothesisGraph
import math


def test_hypothesis_snapshot_omits_targets_but_mllm_summary_keeps_them():
    targets = [{"target_id": "0", "description": "target zero"}]
    graph = HypothesisGraph(targets=targets)

    assert "targets" not in graph.get_hypothesis_snapshot()
    assert graph.get_mllm_summary()["targets"] == targets


class _Scorer:
    def score_images_text(self, images, text):
        return 0.0


class _PositiveScorer:
    def score_images_text(self, images, text):
        return 1.0


def _base_payload(region_id, assigned_viewpoints, target_prob_viewpoints):
    return {
        "current_viewpoints_reassignment": [],
        "visible_region_nodes": [
            {
                "id": region_id,
                "label": "visible room",
                "exist_prob": 0.2,
                "target_probs": {"0": 1.0},
            }
        ],
        "invisible_region_nodes": [],
        "viewpoint_target_probs": [
            {
                "id": viewpoint_id,
                "target_probs": {"0": 1.0},
                "raw_target_probs": {"0": 1.0},
            }
            for viewpoint_id in target_prob_viewpoints
        ],
        "viewpoint_target_score_basis": [
            {
                "id": viewpoint_id,
                "score_basis": {"0": "candidate viewpoint remains possible"},
            }
            for viewpoint_id in target_prob_viewpoints
        ],
        "viewpoint_node_assigns": [
            {
                "region_node_id": region_id,
                "assigned_viewpoint_node_indices": assigned_viewpoints,
            }
        ],
        "new_edges": [],
        "edge_distance_variances": {
            "viewpoint_region": 1.0,
            "viewpoint_viewpoint": 1.0,
        },
    }


def test_hypothesis_snapshot_saves_target_score_basis(monkeypatch):
    import Helper

    monkeypatch.setattr(Helper, "viewpoint_vp_label_by_index", {0: "vp0", 1: "vp1"})

    graph = HypothesisGraph(targets=[{"target_id": "0", "description": "target zero"}])
    graph.update_from_mllm(
        mllm_output={
            "current_viewpoints_reassignment": [],
            "visible_region_nodes": [
                {
                    "id": 95,
                    "label": "visible room",
                    "exist_prob": 1.0,
                    "target_probs": {"0": 1.0},
                }
            ],
            "invisible_region_nodes": [],
            "viewpoint_target_probs": [
                {
                    "id": 1,
                    "target_probs": {"0": 1.0},
                    "raw_target_probs": {"0": 0.7},
                }
            ],
            "viewpoint_target_score_basis": [
                {
                    "id": 1,
                    "score_basis": {"0": "red marker is in the visible room"},
                }
            ],
            "viewpoint_node_assigns": [
                {"region_node_id": 95, "assigned_viewpoint_node_indices": [0, 1]}
            ],
            "new_edges": [],
            "edge_distance_variances": {
                "viewpoint_region": 1.0,
                "viewpoint_viewpoint": 1.0,
            },
        },
        agent_observations=[
            {
                "agent_id": "agent0",
                "current_viewpoint_index": 0,
                "raw_panorama": "image",
                "visible_viewpoints": [{"viewpoint_index": 1, "distance": 1.0}],
            }
        ],
        scorer=_Scorer(),
    )

    nodes = {
        node["id"]: node for node in graph.get_hypothesis_snapshot()["nodes"]
    }
    assert nodes[1]["target_score_basis"] == {
        "0": "red marker is in the visible room"
    }

    graph.mark_target_found("0")
    graph._remove_found_target_probs_from_nodes()

    nodes = {
        node["id"]: node for node in graph.get_hypothesis_snapshot()["nodes"]
    }
    assert nodes[1]["target_score_basis"] == {}
    assert "0" not in nodes[95]["target_probs"]
    assert "0" not in nodes[95]["raw_target_probs"]


def test_region_reassignment_recomputes_grounding_and_restores_latent_existence(
    monkeypatch,
):
    import Helper

    monkeypatch.setattr(
        Helper,
        "viewpoint_vp_label_by_index",
        {0: "vp0", 1: "vp1", 2: "vp2"},
    )

    graph = HypothesisGraph(targets=[{"target_id": "0", "description": "target zero"}])
    graph.update_from_mllm(
        mllm_output=_base_payload(
            region_id=95,
            assigned_viewpoints=[0, 1],
            target_prob_viewpoints=[1],
        ),
        agent_observations=[
            {
                "agent_id": "agent0",
                "current_viewpoint_index": 0,
                "raw_panorama": "image0",
                "visible_viewpoints": [{"viewpoint_index": 1, "distance": 1.0}],
            }
        ],
        scorer=_PositiveScorer(),
    )

    first_nodes = {
        node["id"]: node for node in graph.get_hypothesis_snapshot()["nodes"]
    }
    assert first_nodes[95]["grounded"] is True
    assert first_nodes[95]["exist_prob"] == 1.0
    assert first_nodes[95]["latent_exist_prob"] == 0.2
    assert first_nodes[95]["assigned_viewpoint_ids"] == [0, 1]

    second_payload = _base_payload(
        region_id=96,
        assigned_viewpoints=[],
        target_prob_viewpoints=[1],
    )
    second_payload["visible_region_nodes"][0]["exist_prob"] = 0.4
    second_payload["visible_region_nodes"][0]["label"] = "new visible room"
    second_payload["current_viewpoints_reassignment"] = [
        {"viewpoint_id": 0, "new_assigned_region_id": 96}
    ]
    second_payload["viewpoint_node_assigns"] = []

    graph.update_from_mllm(
        mllm_output=second_payload,
        agent_observations=[
            {
                "agent_id": "agent0",
                "current_viewpoint_index": 0,
                "raw_panorama": "image1",
                "visible_viewpoints": [],
            }
        ],
        scorer=_Scorer(),
    )

    nodes = {node["id"]: node for node in graph.get_hypothesis_snapshot()["nodes"]}
    assert graph.region_to_viewpoints[95] == {1}
    assert graph.region_to_viewpoints[96] == {0}
    assert nodes[95]["grounded"] is False
    assert nodes[95]["exist_prob"] == 0.2
    assert nodes[95]["latent_exist_prob"] == 0.2
    assert nodes[96]["grounded"] is True
    assert nodes[96]["exist_prob"] == 1.0
    assert nodes[96]["latent_exist_prob"] == 0.4


def test_region_target_probs_normalize_only_across_unassigned_regions(monkeypatch):
    import Helper

    monkeypatch.setattr(Helper, "viewpoint_vp_label_by_index", {0: "vp0", 1: "vp1"})

    graph = HypothesisGraph(targets=[{"target_id": "0", "description": "target zero"}])
    graph.update_from_mllm(
        mllm_output={
            "current_viewpoints_reassignment": [],
            "visible_region_nodes": [
                {
                    "id": 95,
                    "label": "visible room",
                    "exist_prob": 1.0,
                    "target_probs": {"0": 0.9},
                }
            ],
            "invisible_region_nodes": [
                {
                    "id": 97,
                    "label": "unseen room",
                    "exist_prob": 0.5,
                    "target_probs": {"0": 0.25},
                },
                {
                    "id": 98,
                    "label": "hidden hallway",
                    "exist_prob": 0.5,
                    "target_probs": {"0": 0.75},
                },
            ],
            "region_target_scores": [
                {"id": 97, "target_scores": {"0": 0.25}},
                {"id": 98, "target_scores": {"0": 0.75}},
            ],
            "viewpoint_target_probs": [
                {
                    "id": 1,
                    "target_probs": {"0": 1.0},
                    "raw_target_probs": {"0": 1.0},
                }
            ],
            "viewpoint_target_score_basis": [
                {"id": 1, "score_basis": {"0": "candidate viewpoint"}}
            ],
            "viewpoint_node_assigns": [
                {"region_node_id": 95, "assigned_viewpoint_node_indices": [0, 1]}
            ],
            "new_edges": [],
            "edge_distance_variances": {
                "viewpoint_region": 1.0,
                "viewpoint_viewpoint": 1.0,
            },
        },
        agent_observations=[
            {
                "agent_id": "agent0",
                "current_viewpoint_index": 0,
                "raw_panorama": "image0",
                "visible_viewpoints": [{"viewpoint_index": 1, "distance": 1.0}],
            }
        ],
        scorer=_Scorer(),
    )

    nodes = {node["id"]: node for node in graph.get_hypothesis_snapshot()["nodes"]}
    assert nodes[95]["target_probs"]["0"] == 0.0
    assert nodes[95]["raw_target_probs"]["0"] == 0.0
    assert nodes[97]["target_probs"]["0"] == 0.25
    assert nodes[97]["raw_target_probs"]["0"] == 0.25
    assert nodes[98]["target_probs"]["0"] == 0.75
    assert nodes[98]["raw_target_probs"]["0"] == 0.75


def test_region_losing_all_viewpoints_gets_fresh_region_target_scores(monkeypatch):
    import Helper

    monkeypatch.setattr(Helper, "viewpoint_vp_label_by_index", {0: "vp0", 1: "vp1"})

    graph = HypothesisGraph(targets=[{"target_id": "0", "description": "target zero"}])
    graph.update_from_mllm(
        mllm_output={
            "current_viewpoints_reassignment": [],
            "visible_region_nodes": [
                {
                    "id": 95,
                    "label": "old room",
                    "exist_prob": 1.0,
                    "target_probs": {"0": 1.0},
                },
                {
                    "id": 94,
                    "label": "neighbor room",
                    "exist_prob": 1.0,
                    "target_probs": {"0": 1.0},
                }
            ],
            "invisible_region_nodes": [],
            "region_target_scores": [],
            "viewpoint_target_probs": [
                {
                    "id": 1,
                    "target_probs": {"0": 1.0},
                    "raw_target_probs": {"0": 1.0},
                }
            ],
            "viewpoint_target_score_basis": [
                {"id": 1, "score_basis": {"0": "candidate viewpoint"}}
            ],
            "viewpoint_node_assigns": [
                {"region_node_id": 94, "assigned_viewpoint_node_indices": [1]},
                {"region_node_id": 95, "assigned_viewpoint_node_indices": [0]},
            ],
            "new_edges": [],
            "edge_distance_variances": {
                "viewpoint_region": 1.0,
                "viewpoint_viewpoint": 1.0,
            },
        },
        agent_observations=[
            {
                "agent_id": "agent0",
                "current_viewpoint_index": 0,
                "raw_panorama": "image0",
                "visible_viewpoints": [{"viewpoint_index": 1, "distance": 1.0}],
            }
        ],
        scorer=_Scorer(),
    )

    graph.update_from_mllm(
        mllm_output={
            "current_viewpoints_reassignment": [
                {"viewpoint_id": 0, "new_assigned_region_id": 96}
            ],
            "visible_region_nodes": [
                {
                    "id": 96,
                    "label": "new room",
                    "exist_prob": 1.0,
                    "target_probs": {"0": 0.4},
                }
            ],
            "invisible_region_nodes": [],
            "region_target_scores": [{"id": 95, "target_scores": {"0": 0.6}}],
            "viewpoint_target_probs": [
                {
                    "id": 1,
                    "target_probs": {"0": 1.0},
                    "raw_target_probs": {"0": 1.0},
                }
            ],
            "viewpoint_target_score_basis": [
                {"id": 1, "score_basis": {"0": "candidate viewpoint"}}
            ],
            "viewpoint_node_assigns": [],
            "new_edges": [],
            "edge_distance_variances": {
                "viewpoint_region": 1.0,
                "viewpoint_viewpoint": 1.0,
            },
        },
        agent_observations=[
            {
                "agent_id": "agent0",
                "current_viewpoint_index": 0,
                "raw_panorama": "image1",
                "visible_viewpoints": [],
            }
        ],
        scorer=_Scorer(),
    )

    nodes = {node["id"]: node for node in graph.get_hypothesis_snapshot()["nodes"]}
    assert graph.region_to_viewpoints[95] == set()
    assert graph.region_to_viewpoints[96] == {0}
    assert nodes[95]["target_probs"]["0"] == 1.0
    assert nodes[95]["raw_target_probs"]["0"] == 0.6
    assert nodes[96]["target_probs"]["0"] == 0.0
    assert nodes[96]["raw_target_probs"]["0"] == 0.0


def test_update_without_mllm_preserves_region_target_invariant(monkeypatch):
    import Helper

    monkeypatch.setattr(Helper, "viewpoint_vp_label_by_index", {0: "vp0", 1: "vp1"})

    graph = HypothesisGraph(targets=[{"target_id": "0", "description": "target zero"}])
    graph.add_or_update_node(
        node_id=0,
        label="vp0",
        node_type=Helper.TYPE_VP,
        exist_prob=1.0,
        grounded=False,
        target_probs={"0": 0.0},
    )
    graph.add_or_update_node(
        node_id=95,
        label="assigned room",
        node_type=Helper.TYPE_REGION,
        exist_prob=1.0,
        grounded=False,
        target_probs={"0": 0.8},
        raw_target_probs={"0": 0.8},
    )
    graph.add_or_update_node(
        node_id=96,
        label="unassigned room",
        node_type=Helper.TYPE_REGION,
        exist_prob=0.5,
        grounded=False,
        target_probs={"0": 0.4},
        raw_target_probs={"0": 0.4},
    )
    graph._set_viewpoint_region(0, 95)

    graph.update_without_mllm(
        agent_observations=[
            {
                "agent_id": "agent0",
                "current_viewpoint_index": 0,
                "raw_panorama": "image0",
                "visible_viewpoints": [{"viewpoint_index": 1, "distance": 1.0}],
            }
        ]
    )

    nodes = {node["id"]: node for node in graph.get_hypothesis_snapshot()["nodes"]}
    assert nodes[95]["target_probs"]["0"] == 0.0
    assert nodes[95]["raw_target_probs"]["0"] == 0.0
    assert nodes[96]["target_probs"]["0"] == 1.0
    assert nodes[96]["raw_target_probs"]["0"] == 0.4


def test_hypothesized_vv_edge_is_removed_when_endpoint_becomes_grounded(monkeypatch):
    import Helper

    monkeypatch.setattr(
        Helper,
        "viewpoint_vp_label_by_index",
        {0: "vp0", 1: "vp1", 2: "vp2"},
    )

    graph = HypothesisGraph(targets=[{"target_id": "0", "description": "target zero"}])
    payload = _base_payload(
        region_id=95,
        assigned_viewpoints=[0, 1],
        target_prob_viewpoints=[1, 2],
    )
    payload["new_edges"] = [
        {"i": 1, "j": 2, "edge_type": "VV", "exist_prob": 0.8, "dist": 2.0}
    ]

    graph.update_from_mllm(
        mllm_output=payload,
        agent_observations=[
            {
                "agent_id": "agent0",
                "current_viewpoint_index": 0,
                "raw_panorama": "image0",
                "visible_viewpoints": [{"viewpoint_index": 1, "distance": 1.0}],
            }
        ],
        scorer=_Scorer(),
    )
    assert (1, 2) in graph.edges
    assert graph.edges[(1, 2)].grounded is False
    assert graph.edges[(1, 2)].distance_mean == 2.0
    assert graph.edges[(1, 2)].distance_var == 1.0
    assert graph.edges[(1, 2)].cond_exist_prob == 0.8
    assert graph.edges[(1, 2)].exist_prob == 0.8

    second_payload = _base_payload(
        region_id=96,
        assigned_viewpoints=[2],
        target_prob_viewpoints=[1],
    )
    graph.update_from_mllm(
        mllm_output=second_payload,
        agent_observations=[
            {
                "agent_id": "agent0",
                "current_viewpoint_index": 2,
                "raw_panorama": "image1",
                "visible_viewpoints": [],
            }
        ],
        scorer=_Scorer(),
    )

    assert (1, 2) not in graph.edges


def test_hypothesized_vv_edge_becomes_grounded_only_when_observed(monkeypatch):
    import Helper

    monkeypatch.setattr(
        Helper,
        "viewpoint_vp_label_by_index",
        {0: "vp0", 1: "vp1", 2: "vp2"},
    )

    graph = HypothesisGraph(targets=[{"target_id": "0", "description": "target zero"}])
    payload = _base_payload(
        region_id=95,
        assigned_viewpoints=[0, 1],
        target_prob_viewpoints=[1, 2],
    )
    payload["new_edges"] = [
        {"i": 1, "j": 2, "edge_type": "VV", "exist_prob": 0.8, "dist": 2.0}
    ]
    graph.update_from_mllm(
        mllm_output=payload,
        agent_observations=[
            {
                "agent_id": "agent0",
                "current_viewpoint_index": 0,
                "raw_panorama": "image0",
                "visible_viewpoints": [{"viewpoint_index": 1, "distance": 1.0}],
            }
        ],
        scorer=_Scorer(),
    )

    second_payload = _base_payload(
        region_id=96,
        assigned_viewpoints=[2],
        target_prob_viewpoints=[1],
    )
    graph.update_from_mllm(
        mllm_output=second_payload,
        agent_observations=[
            {
                "agent_id": "agent0",
                "current_viewpoint_index": 2,
                "raw_panorama": "image1",
                "visible_viewpoints": [{"viewpoint_index": 1, "distance": 1.5}],
            }
        ],
        scorer=_Scorer(),
    )

    assert (1, 2) in graph.edges
    assert graph.edges[(1, 2)].grounded is True
    assert graph.edges[(1, 2)].distance_mean == 1.5


def test_empirical_grounded_vv_stats_requires_grounded_vv_evidence(monkeypatch):
    import Helper

    monkeypatch.setattr(
        Helper,
        "viewpoint_vp_label_by_index",
        {0: "vp0", 1: "vp1"},
    )

    graph = HypothesisGraph(targets=[{"target_id": "0", "description": "target zero"}])
    graph.add_or_update_node(
        node_id=0,
        label="vp0",
        node_type=Helper.TYPE_VP,
        exist_prob=1.0,
        grounded=False,
        target_probs={"0": 1.0},
    )
    graph.add_or_update_node(
        node_id=1,
        label="vp1",
        node_type=Helper.TYPE_VP,
        exist_prob=1.0,
        grounded=False,
        target_probs={"0": 1.0},
    )
    graph.add_or_update_edge(
        source_node_id=0,
        target_node_id=1,
        distance_mean=2.0,
        distance_var=1.0,
        cond_exist_prob=0.5,
        exist_prob=0.5,
        grounded=False,
    )

    try:
        graph._empirical_grounded_vv_stats()
    except ValueError as exc:
        assert "without grounded viewpoint-viewpoint distance evidence" in str(exc)
    else:
        raise AssertionError("Expected missing grounded VV evidence to raise.")


def test_vv_edge_non_existence_likelihood_uses_paper_mismatch_term(monkeypatch):
    import Helper

    monkeypatch.setattr(
        Helper,
        "viewpoint_vp_label_by_index",
        {0: "vp0", 1: "vp1", 2: "vp2", 3: "vp3", 4: "vp4"},
    )

    graph = HypothesisGraph(
        targets=[{"target_id": "0", "description": "target zero"}],
        bayes_config={"epsilon": 1e-6, "varrho": 0.75},
    )
    for node_id in range(5):
        graph.add_or_update_node(
            node_id=node_id,
            label="vp%s" % node_id,
            node_type=Helper.TYPE_VP,
            exist_prob=1.0,
            grounded=node_id in {0, 1, 2},
            target_probs={"0": 1.0},
        )

    graph.add_or_update_edge(
        source_node_id=0,
        target_node_id=1,
        distance_mean=1.0,
        distance_var=0.0,
        cond_exist_prob=1.0,
        exist_prob=1.0,
        grounded=True,
    )
    graph.add_or_update_edge(
        source_node_id=1,
        target_node_id=2,
        distance_mean=3.0,
        distance_var=0.0,
        cond_exist_prob=1.0,
        exist_prob=1.0,
        grounded=True,
    )
    graph.add_or_update_edge(
        source_node_id=3,
        target_node_id=4,
        distance_mean=4.0,
        distance_var=1.0,
        cond_exist_prob=0.6,
        exist_prob=0.6,
        grounded=False,
    )

    graph.viewpoint_to_region = {3: 95, 4: 96}
    graph.region_to_viewpoints = {95: {3}, 96: {4}}

    graph._update_edge_existence_posteriors(
        existing_edge_ids={(0, 1), (1, 2), (3, 4)},
        previous_distance_means={(3, 4): 4.0},
        previous_cond_exist_probs={(3, 4): 0.6},
        scorer=_Scorer(),
    )

    empirical_mean = 2.0
    empirical_var = 1.0 + 1e-6
    prior_distance = 4.0
    prior = 0.6
    varrho = 0.75
    assignment_indicator = 0
    edge_comp_score = math.log(varrho / (1.0 - varrho)) * (
        2.0 * assignment_indicator - 1.0
    ) - ((prior_distance - empirical_mean) ** 2) / (2.0 * empirical_var)
    exist_likelihood = math.exp(0.5 * edge_comp_score)
    non_exist_likelihood = math.exp(-0.5 * edge_comp_score)
    expected = (
        exist_likelihood
        * prior
        / (exist_likelihood * prior + non_exist_likelihood * (1.0 - prior))
    )

    assert math.isclose(
        graph.edges[(3, 4)].cond_exist_prob,
        expected,
        rel_tol=1e-12,
        abs_tol=1e-12,
    )


def test_vv_edge_update_without_grounded_vv_uses_assignment_only(monkeypatch):
    import Helper

    monkeypatch.setattr(
        Helper,
        "viewpoint_vp_label_by_index",
        {0: "vp0", 1: "vp1"},
    )

    graph = HypothesisGraph(
        targets=[{"target_id": "0", "description": "target zero"}],
        bayes_config={"epsilon": 1e-6, "varrho": 0.75},
    )
    for node_id in (0, 1):
        graph.add_or_update_node(
            node_id=node_id,
            label="vp%s" % node_id,
            node_type=Helper.TYPE_VP,
            exist_prob=1.0,
            grounded=False,
            target_probs={"0": 1.0},
        )
    graph.add_or_update_edge(
        source_node_id=0,
        target_node_id=1,
        distance_mean=5.0,
        distance_var=2.0,
        cond_exist_prob=0.4,
        exist_prob=0.4,
        grounded=False,
    )
    graph.viewpoint_to_region = {0: 95, 1: 95}
    graph.region_to_viewpoints = {95: {0, 1}}

    graph._update_edge_distance_posteriors(
        existing_edge_ids={(0, 1)},
        previous_distance_means={(0, 1): 5.0},
        previous_distance_vars={(0, 1): 2.0},
        previous_cond_exist_probs={(0, 1): 0.4},
        scorer=_Scorer(),
    )
    graph._update_edge_existence_posteriors(
        existing_edge_ids={(0, 1)},
        previous_distance_means={(0, 1): 5.0},
        previous_cond_exist_probs={(0, 1): 0.4},
        scorer=_Scorer(),
    )

    assert graph.edges[(0, 1)].distance_mean == 5.0
    assert graph.edges[(0, 1)].distance_var == 2.0
    edge_comp_score = math.log(0.75 / 0.25)
    exist_likelihood = math.exp(0.5 * edge_comp_score)
    non_exist_likelihood = math.exp(-0.5 * edge_comp_score)
    expected = (
        exist_likelihood
        * 0.4
        / (exist_likelihood * 0.4 + non_exist_likelihood * 0.6)
    )

    assert math.isclose(
        graph.edges[(0, 1)].cond_exist_prob,
        expected,
        rel_tol=1e-12,
        abs_tol=1e-12,
    )


def test_vz_existence_uses_semantic_score_only(monkeypatch):
    import Helper

    monkeypatch.setattr(Helper, "viewpoint_vp_label_by_index", {0: "vp0"})

    graph = HypothesisGraph(
        targets=[{"target_id": "0", "description": "target zero"}],
        bayes_config={"eta_vz": 2.0},
    )
    graph.add_or_update_node(
        node_id=0,
        label="vp0",
        node_type=Helper.TYPE_VP,
        exist_prob=1.0,
        grounded=True,
        target_probs={"0": 0.0},
    )
    graph.add_or_update_node(
        node_id=95,
        label="bright kitchen",
        node_type=Helper.TYPE_REGION,
        exist_prob=0.5,
        grounded=False,
        target_probs={"0": 1.0},
    )
    graph.add_or_update_edge(
        source_node_id=0,
        target_node_id=95,
        distance_mean=6.0,
        distance_var=2.0,
        cond_exist_prob=0.25,
        exist_prob=0.125,
        grounded=False,
    )
    graph.viewpoint_rgb_evidence[0] = ["image"]

    graph._update_edge_existence_posteriors(
        existing_edge_ids={(0, 95)},
        previous_distance_means={(0, 95): 100.0},
        previous_cond_exist_probs={(0, 95): 0.25},
        scorer=_PositiveScorer(),
    )

    exist_likelihood = math.exp(2.0)
    non_exist_likelihood = math.exp(-2.0)
    expected_cond = (
        exist_likelihood
        * 0.25
        / (exist_likelihood * 0.25 + non_exist_likelihood * 0.75)
    )

    assert math.isclose(
        graph.edges[(0, 95)].cond_exist_prob,
        expected_cond,
        rel_tol=1e-12,
        abs_tol=1e-12,
    )
    assert math.isclose(
        graph.edges[(0, 95)].exist_prob,
        expected_cond * 0.5,
        rel_tol=1e-12,
        abs_tol=1e-12,
    )
