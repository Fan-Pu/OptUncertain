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
                "observed_region_node_ids": [100],
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


class FakeScorer:
    def __init__(self, scores):
        self.scores = dict(scores)
        self.calls = []

    def score_images_text(self, images, text):
        image = images[0]
        self.calls.append((image, text))
        return self.scores[(image, text)]


def _graph_summary(region_labels, *, viewpoint_to_region=None):
    return {
        "viewpoint_to_region": {
            str(viewpoint_id): int(region_id)
            for viewpoint_id, region_id in (viewpoint_to_region or {}).items()
        },
        "nodes": [
            {
                "id": int(region_id),
                "type": "region",
                "label": label,
                "exist_prob": 1.0,
                "target_probs": {
                    "0": 0.5,
                },
                "assigned_viewpoint_ids": [],
            }
            for region_id, label in region_labels.items()
        ],
    }


def _visible_region_ids(payload):
    return {int(region["id"]) for region in payload["visible_region_nodes"]}


def _assigned_region(payload, viewpoint_id):
    for item in payload["viewpoint_node_assigns"]:
        assigned_ids = {
            int(value) for value in item["assigned_viewpoint_node_indices"]
        }
        if int(viewpoint_id) in assigned_ids:
            return int(item["region_node_id"])
    raise AssertionError("Missing assignment for viewpoint %s." % viewpoint_id)


def _validate(
    payload,
    *,
    semantic_payload_contract="graph_mllm",
    agent_observations=None,
    graph_summary=None,
    fixed_detections=None,
    scorer=None,
):
    return _client()._validate_payload(
        payload=copy.deepcopy(payload),
        agent_observations=(
            copy.deepcopy(agent_observations)
            if agent_observations is not None
            else _agent_observations()
        ),
        targets=_targets(),
        graph_summary=copy.deepcopy(graph_summary),
        fixed_detections=(
            copy.deepcopy(fixed_detections)
            if fixed_detections is not None
            else _fixed_detections()
        ),
        scorer=scorer,
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


def test_graph_mllm_payload_ignores_current_viewpoint_target_probs():
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


def test_illegal_vz_edge_is_removed_from_optional_new_edges():
    payload = _base_payload()
    payload["new_edges"] = [
        {
            "i": 1,
            "j": 2,
            "edge_type": "VZ",
            "exist_prob": 0.5,
            "dist": 3.0,
        }
    ]

    validated = _validate(payload)

    assert validated["new_edges"] == []


def test_repair_prompt_returns_corrected_current_payload_only():
    prompt = MLLMClient._build_semantic_payload_repair_user_message(
        payload=_base_payload(),
        validation_errors=["Unexpected top-level keys: ['current_payload']."],
        agent_observations=_agent_observations(),
        targets=_targets(),
        graph_summary=_graph_summary({100: "bedroom"}),
        fixed_detections=_fixed_detections(),
    )

    assert "Return only the corrected current_payload JSON object." in prompt
    assert "Do not return repair_context" in prompt
    assert "The returned object must contain exactly these top-level keys" in prompt
    assert "Repair context for reference only; do not return this object" in prompt
    assert "Current payload to repair. Return this object after applying" in prompt
    assert '"agent_context"' in prompt
    assert '"graph_context"' in prompt
    assert '"current_payload"' in prompt


def test_siglip_uses_only_agent_observed_visible_regions():
    payload = _base_payload()
    payload["agents"][0]["observed_region_node_ids"] = [100, 101]
    payload["visible_region_nodes"].append(
        {
            "id": 101,
            "label": "kitchen",
            "exist_prob": 1.0,
            "target_probs": {
                "0": 0.5,
            },
        }
    )
    observations = _agent_observations()
    observations[0]["raw_panorama"] = "panorama0"
    graph_summary = _graph_summary(
        {
            100: "bedroom",
            999: "graph-only perfect match",
        },
        viewpoint_to_region={
            0: 100,
        },
    )
    scorer = FakeScorer(
        {
            ("panorama0", "bedroom"): 0.1,
            ("panorama0", "kitchen"): 0.9,
        }
    )

    validated = _validate(
        payload,
        agent_observations=observations,
        graph_summary=graph_summary,
        scorer=scorer,
    )

    assert validated["agents"] == [
        {
            "agent_id": "agent0",
            "current_region_node_id": 101,
            "observed_region_node_ids": [100, 101],
        }
    ]
    assert 101 in _visible_region_ids(validated)
    assert _assigned_region(validated, 0) == 101
    assert _assigned_region(validated, 1) == 100
    assert scorer.calls == [
        ("panorama0", "bedroom"),
        ("panorama0", "kitchen"),
    ]
    assert validated["current_viewpoints_reassignment"] == [
        {
            "viewpoint_id": 0,
            "new_assigned_region_id": 101,
        }
    ]


def test_siglip_visible_region_can_beat_prior_graph_region():
    payload = _base_payload()
    payload["agents"][0]["observed_region_node_ids"] = [100, 102]
    payload["visible_region_nodes"].append(
        {
            "id": 102,
            "label": "office",
            "exist_prob": 1.0,
            "target_probs": {
                "0": 0.5,
            },
        }
    )
    observations = _agent_observations()
    observations[0]["raw_panorama"] = "panorama0"
    graph_summary = _graph_summary(
        {
            100: "bedroom",
        },
        viewpoint_to_region={
            0: 100,
        },
    )
    scorer = FakeScorer(
        {
            ("panorama0", "bedroom"): 0.2,
            ("panorama0", "office"): 0.8,
        }
    )

    validated = _validate(
        payload,
        agent_observations=observations,
        graph_summary=graph_summary,
        scorer=scorer,
    )

    assert validated["agents"][0]["current_region_node_id"] == 102
    assert _assigned_region(validated, 0) == 102
    assert validated["current_viewpoints_reassignment"] == [
        {
            "viewpoint_id": 0,
            "new_assigned_region_id": 102,
        }
    ]


def test_siglip_scores_every_current_viewpoint_without_prior_assignments():
    payload = _base_payload()
    payload["agents"][0]["observed_region_node_ids"] = [100, 101]
    payload["agents"].append(
        {
            "agent_id": "agent1",
            "current_region_node_id": 100,
            "observed_region_node_ids": [100, 101],
        }
    )
    payload["visible_region_nodes"].append(
        {
            "id": 101,
            "label": "kitchen",
            "exist_prob": 1.0,
            "target_probs": {
                "0": 0.5,
            },
        }
    )
    payload["detections"].append(
        {
            "agent_id": "agent1",
            "target_indices": ["0"],
            "founds": [False],
        }
    )
    payload["viewpoint_node_assigns"][0]["assigned_viewpoint_node_indices"].append(2)

    observations = [
        {
            "agent_id": "agent0",
            "current_viewpoint_index": 0,
            "visible_viewpoints": [
                {
                    "viewpoint_index": 1,
                    "distance": 2.0,
                }
            ],
            "raw_panorama": "panorama0",
        },
        {
            "agent_id": "agent1",
            "current_viewpoint_index": 2,
            "visible_viewpoints": [],
            "raw_panorama": "panorama2",
        },
    ]
    graph_summary = _graph_summary(
        {
            100: "bedroom",
            101: "kitchen",
        }
    )
    fixed_detections = [
        {
            "agent_id": "agent0",
            "target_indices": ["0"],
            "founds": [True],
        },
        {
            "agent_id": "agent1",
            "target_indices": ["0"],
            "founds": [False],
        },
    ]
    scorer = FakeScorer(
        {
            ("panorama0", "bedroom"): 0.1,
            ("panorama0", "kitchen"): 0.9,
            ("panorama2", "bedroom"): 0.8,
            ("panorama2", "kitchen"): 0.2,
        }
    )

    validated = _validate(
        payload,
        agent_observations=observations,
        graph_summary=graph_summary,
        fixed_detections=fixed_detections,
        scorer=scorer,
    )

    assert sorted(scorer.calls) == sorted(
        [
            ("panorama0", "bedroom"),
            ("panorama0", "kitchen"),
            ("panorama2", "bedroom"),
            ("panorama2", "kitchen"),
        ]
    )
    assert _assigned_region(validated, 0) == 101
    assert _assigned_region(validated, 2) == 100
    assert validated["current_viewpoints_reassignment"] == []


def test_siglip_reassignment_not_emitted_when_prior_region_stays_selected():
    payload = _base_payload()
    payload["agents"][0]["observed_region_node_ids"] = [100, 101]
    payload["current_viewpoints_reassignment"] = [
        {
            "viewpoint_id": 0,
            "new_assigned_region_id": 101,
        }
    ]
    payload["visible_region_nodes"].append(
        {
            "id": 101,
            "label": "kitchen",
            "exist_prob": 1.0,
            "target_probs": {
                "0": 0.5,
            },
        }
    )
    observations = _agent_observations()
    observations[0]["raw_panorama"] = "panorama0"
    graph_summary = _graph_summary(
        {
            100: "bedroom",
            101: "kitchen",
        },
        viewpoint_to_region={
            0: 100,
        },
    )
    scorer = FakeScorer(
        {
            ("panorama0", "bedroom"): 0.9,
            ("panorama0", "kitchen"): 0.1,
        }
    )

    validated = _validate(
        payload,
        agent_observations=observations,
        graph_summary=graph_summary,
        scorer=scorer,
    )

    assert validated["agents"][0]["current_region_node_id"] == 100
    assert _assigned_region(validated, 0) == 100
    assert validated["current_viewpoints_reassignment"] == []


def test_siglip_rejects_empty_observed_region_ids():
    payload = _base_payload()
    payload["agents"][0]["observed_region_node_ids"] = []

    with pytest.raises(ValueError, match="observed_region_node_ids must be nonempty"):
        _validate(payload)


def test_siglip_rejects_missing_observed_region_ids():
    payload = _base_payload()
    del payload["agents"][0]["observed_region_node_ids"]

    with pytest.raises(KeyError, match="observed_region_node_ids"):
        _validate(payload)


def test_siglip_rejects_observed_region_id_not_in_visible_regions():
    payload = _base_payload()
    payload["agents"][0]["observed_region_node_ids"] = [100, 101]

    with pytest.raises(ValueError, match="not in visible_region_nodes"):
        _validate(payload)
