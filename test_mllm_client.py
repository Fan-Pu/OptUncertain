import pytest

import Helper
from semantic_persistence.mllm_client import MLLMClient


def test_saved_payload_region_probs_use_type1_mean_and_union_normalization(
    monkeypatch,
):
    monkeypatch.setattr(
        Helper,
        "viewpoint_vp_label_by_index",
        {0: "vp0", 1: "vp1", 2: "vp2"},
    )

    client = MLLMClient(read_saved_raw_outputs=True)
    payload = {
        "current_viewpoints_reassignment": [],
        "visible_region_nodes": [
            {
                "id": 100,
                "label": "bright study area near the table",
                "exist_prob": 1.0,
                "target_probs": {"0": 0.0},
            },
            {
                "id": 101,
                "label": "quiet hallway beyond the study doorway",
                "exist_prob": 0.8,
                "target_probs": {"0": 0.5},
            },
        ],
        "invisible_region_nodes": [],
        "region_target_scores": [
            {
                "id": 101,
                "target_scores": {"0": 0.5},
            }
        ],
        "viewpoint_target_probs": [
            {
                "id": 1,
                "target_probs": {"0": 0.25},
                "raw_target_probs": {"0": 1.0},
            },
            {
                "id": 2,
                "target_probs": {"0": 0.75},
                "raw_target_probs": {"0": 3.0},
            },
        ],
        "viewpoint_target_score_basis": [
            {"id": 1, "score_basis": {"0": "lower evidence"}},
            {"id": 2, "score_basis": {"0": "higher evidence"}},
        ],
        "viewpoint_node_assigns": [
            {
                "region_node_id": 100,
                "assigned_viewpoint_node_indices": [1, 2],
            }
        ],
        "new_edges": [],
        "edge_distance_variances": {
            "viewpoint_viewpoint": 1.0,
            "viewpoint_region": 4.0,
        },
    }
    graph_summary = {
        "viewpoint_to_region": {"0": 102},
        "nodes": [
            {
                "id": 0,
                "type": "viewpoint",
                "grounded": True,
                "node_visit_times": 1,
                "raw_target_probs": {"0": 0.0},
            },
            {
                "id": 102,
                "type": "region",
                "assigned_viewpoint_ids": [0],
                "raw_target_probs": {"0": 0.0},
                "target_probs": {"0": 0.0},
            },
        ],
    }

    validated = client._validate_payload(
        payload=payload,
        agent_observations=[
            {
                "agent_id": "agent0",
                "current_viewpoint_index": 0,
                "visible_viewpoints": [
                    {"viewpoint_index": 1},
                    {"viewpoint_index": 2},
                ],
            }
        ],
        targets=[{"target_id": "0", "description": "target"}],
        graph_summary=graph_summary,
        semantic_payload_contract="saved_materialized",
    )

    region_by_id = {
        int(region["id"]): region for region in validated["visible_region_nodes"]
    }
    assert region_by_id[100]["target_probs"]["0"] == pytest.approx(0.5)
    assert region_by_id[101]["target_probs"]["0"] == pytest.approx(0.5)
    assert validated["region_target_scores"] == [
        {"id": 101, "target_scores": {"0": 0.5}}
    ]

