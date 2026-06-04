import copy
import importlib

import pytest


def _minimal_agent_observations():
    return [
        {
            "agent_id": "agent0",
            "current_viewpoint_index": 0,
            "visible_viewpoints": [
                {
                    "viewpoint_index": 1,
                    "distance": 1.0,
                }
            ],
        }
    ]


def _minimal_graph_summary(raw_target_probs=None):
    if raw_target_probs is None:
        raw_target_probs = {"4": 0.2}

    return {
        "nodes": [
            {
                "id": 0,
                "type": "viewpoint",
                "grounded": True,
                "node_visit_times": 1,
                "raw_target_probs": {"4": 0.0},
            },
            {
                "id": 1,
                "type": "viewpoint",
                "grounded": False,
                "node_visit_times": 0,
                "raw_target_probs": raw_target_probs,
            },
            {
                "id": 95,
                "type": "region",
                "label": "office room",
                "assigned_viewpoint_ids": [0],
                "target_probs": {"4": 1.0},
                "raw_target_probs": {"4": 1.0},
            },
        ],
        "target_found": {"4": False},
        "targets": [{"target_id": "4", "description": "helmet"}],
        "viewpoint_to_region": {"0": 95},
    }


def _payload_with_stale_target_keys():
    return {
        "current_viewpoints_reassignment": [],
        "visible_region_nodes": [
            {
                "id": 97,
                "label": "office room",
                "exist_prob": 1.0,
                "target_probs": {"1": 0.2, "4": 0.8},
            }
        ],
        "invisible_region_nodes": [
            {
                "id": 98,
                "label": "unseen storage area",
                "exist_prob": 0.5,
                "target_probs": {"1": 0.7, "4": 0.3},
            }
        ],
        "viewpoint_target_probs": [
            {
                "id": 1,
                "target_probs": {"1": 0.4, "4": 0.6},
                "raw_target_probs": {"1": 0.4, "4": 0.6},
            }
        ],
        "viewpoint_node_assigns": [],
        "new_edges": [],
        "edge_distance_variances": {
            "viewpoint_region": 1.0,
            "viewpoint_viewpoint": 1.0,
        },
    }


def test_project_saved_payload_to_target_ids_removes_stale_target_keys():
    mllm_client = importlib.import_module("semantic_persistence.mllm_client")
    payload = _payload_with_stale_target_keys()
    original_payload = copy.deepcopy(payload)

    projected = mllm_client.MLLMClient._project_saved_payload_to_target_ids(
        payload=payload,
        target_ids=["4"],
    )

    assert payload == original_payload
    assert projected["viewpoint_target_probs"][0]["target_probs"] == {"4": 0.6}
    assert projected["viewpoint_target_probs"][0]["raw_target_probs"] == {"4": 0.6}
    assert projected["visible_region_nodes"][0]["target_probs"] == {"4": 0.8}
    assert projected["invisible_region_nodes"][0]["target_probs"] == {"4": 0.3}
    assert projected["viewpoint_target_probs"][0]["id"] == 1


def test_projected_saved_payload_validates_against_active_target_set(monkeypatch):
    Helper = importlib.import_module("Helper")
    mllm_client = importlib.import_module("semantic_persistence.mllm_client")
    client = object.__new__(mllm_client.MLLMClient)
    payload = mllm_client.MLLMClient._project_saved_payload_to_target_ids(
        payload=_payload_with_stale_target_keys(),
        target_ids=["4"],
    )

    monkeypatch.setattr(Helper, "viewpoint_vp_label_by_index", {0: "vp0", 1: "vp1"})

    validated = client._validate_payload(
        payload=payload,
        agent_observations=_minimal_agent_observations(),
        targets=[{"target_id": "4", "description": "helmet"}],
        graph_summary=_minimal_graph_summary(),
        scorer=None,
        semantic_payload_contract="graph_mllm",
    )

    assert validated["viewpoint_target_probs"][0]["target_probs"] == {"4": 1.0}
    assert validated["viewpoint_target_probs"][0]["raw_target_probs"] == {"4": 0.6}


def test_projected_saved_payload_missing_active_target_still_fails(monkeypatch):
    Helper = importlib.import_module("Helper")
    mllm_client = importlib.import_module("semantic_persistence.mllm_client")
    client = object.__new__(mllm_client.MLLMClient)
    payload = _payload_with_stale_target_keys()
    payload["viewpoint_target_probs"][0]["target_probs"] = {"1": 0.4}
    payload["viewpoint_target_probs"][0]["raw_target_probs"] = {"1": 0.4}
    payload = mllm_client.MLLMClient._project_saved_payload_to_target_ids(
        payload=payload,
        target_ids=["4"],
    )

    monkeypatch.setattr(Helper, "viewpoint_vp_label_by_index", {0: "vp0", 1: "vp1"})

    with pytest.raises(ValueError, match="Missing required MLLM-updatable"):
        client._validate_payload(
            payload=payload,
            agent_observations=_minimal_agent_observations(),
            targets=[{"target_id": "4", "description": "helmet"}],
            graph_summary=_minimal_graph_summary(raw_target_probs={}),
            scorer=None,
            semantic_payload_contract="graph_mllm",
        )
