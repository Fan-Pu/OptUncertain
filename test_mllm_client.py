from __future__ import annotations

import copy
import sys
import types

import pytest

if "openai" not in sys.modules:
    openai_stub = types.ModuleType("openai")

    class BadRequestError(Exception):
        pass

    class OpenAI:
        def __init__(self, *args, **kwargs):
            pass

    openai_stub.BadRequestError = BadRequestError
    openai_stub.OpenAI = OpenAI
    sys.modules["openai"] = openai_stub

if "Helper" not in sys.modules:
    helper_stub = types.ModuleType("Helper")
    helper_stub.viewpoint_vp_label_by_index = {}
    sys.modules["Helper"] = helper_stub

from semantic_persistence.mllm_client import MLLMClient


def _client():
    return MLLMClient(read_saved_raw_outputs=True)


def _agent_observations():
    return [
        {
            "agent_id": "agent0",
            "current_viewpoint_index": 0,
            "visible_viewpoints": [
                {
                    "viewpoint_index": 1,
                    "distance": 2.0,
                }
            ],
        }
    ]


def _targets():
    return [
        {
            "target_id": "0",
            "description": "target",
        }
    ]


def _fixed_detections():
    return [
        {
            "agent_id": "agent0",
            "target_indices": ["0"],
            "founds": [True],
        }
    ]


def _base_payload():
    return {
        "agents": [
            {
                "agent_id": "agent0",
                "current_region_node_id": 100,
            }
        ],
        "current_viewpoints_reassignment": [],
        "detections": _fixed_detections(),
        "visible_region_nodes": [
            {
                "id": 100,
                "label": "bedroom",
                "exist_prob": 1.0,
                "target_probs": {
                    "0": 0.5,
                },
            }
        ],
        "invisible_region_nodes": [],
        "viewpoint_target_probs": [
            {
                "id": 1,
                "target_probs": {
                    "0": 0.25,
                },
            }
        ],
        "viewpoint_node_assigns": [
            {
                "region_node_id": 100,
                "assigned_viewpoint_node_indices": [0, 1],
            }
        ],
        "new_edges": [],
        "edge_distance_variances": {
            "viewpoint_viewpoint": 1.0,
            "viewpoint_region": 4.0,
        },
    }


def _validate(payload, *, semantic_payload_contract="graph_mllm"):
    return _client()._validate_payload(
        payload=copy.deepcopy(payload),
        agent_observations=_agent_observations(),
        targets=_targets(),
        graph_summary=None,
        fixed_detections=_fixed_detections(),
        semantic_payload_contract=semantic_payload_contract,
    )


def test_graph_mllm_payload_materializes_current_viewpoint_target_probs():
    payload = _base_payload()

    validated = _validate(payload)

    assert validated["viewpoint_target_probs"] == [
        {
            "id": 0,
            "target_probs": {
                "0": 1.0,
            },
        },
        {
            "id": 1,
            "target_probs": {
                "0": 0.25,
            },
        },
    ]


def test_graph_mllm_payload_rejects_current_viewpoint_target_probs():
    payload = _base_payload()
    payload["viewpoint_target_probs"].insert(
        0,
        {
            "id": 0,
            "target_probs": {
                "0": 1.0,
            },
        },
    )

    with pytest.raises(ValueError, match="must not be returned by the graph MLLM"):
        _validate(payload)


def test_saved_materialized_payload_accepts_matching_current_viewpoint_target_probs():
    payload = _base_payload()
    payload["viewpoint_target_probs"].insert(
        0,
        {
            "id": 0,
            "target_probs": {
                "0": 1.0,
            },
        },
    )

    validated = _validate(
        payload,
        semantic_payload_contract="saved_materialized",
    )

    assert validated["viewpoint_target_probs"] == [
        {
            "id": 0,
            "target_probs": {
                "0": 1.0,
            },
        },
        {
            "id": 1,
            "target_probs": {
                "0": 0.25,
            },
        },
    ]


def test_saved_materialized_payload_rejects_mismatched_current_viewpoint_target_probs():
    payload = _base_payload()
    payload["viewpoint_target_probs"].insert(
        0,
        {
            "id": 0,
            "target_probs": {
                "0": 0.0,
            },
        },
    )

    with pytest.raises(ValueError, match="does not match direct detection"):
        _validate(
            payload,
            semantic_payload_contract="saved_materialized",
        )
