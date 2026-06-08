from semantic_persistence.hypothesis_graph import HypothesisGraph


def test_hypothesis_snapshot_omits_targets_but_mllm_summary_keeps_them():
    targets = [{"target_id": "0", "description": "target zero"}]
    graph = HypothesisGraph(targets=targets)

    assert "targets" not in graph.get_hypothesis_snapshot()
    assert graph.get_mllm_summary()["targets"] == targets


class _Scorer:
    def score_images_text(self, images, text):
        return 0.0


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
