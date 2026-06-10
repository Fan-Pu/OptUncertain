import copy
import importlib
import json

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


def _vv_edge_validation_observations():
    return [
        {
            "agent_id": "agent0",
            "current_viewpoint_index": 0,
            "visible_viewpoints": [
                {"viewpoint_index": 1, "distance": 1.0},
                {"viewpoint_index": 2, "distance": 1.0},
            ],
        }
    ]


def _vv_edge_validation_graph_summary(
    endpoint2_grounded=False,
    endpoint2_visit_times=0,
):
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
                "raw_target_probs": {"4": 0.2},
            },
            {
                "id": 2,
                "type": "viewpoint",
                "grounded": endpoint2_grounded,
                "node_visit_times": endpoint2_visit_times,
                "raw_target_probs": {"4": 0.2},
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


def _vv_edge_validation_payload(edge):
    return {
        "current_viewpoints_reassignment": [],
        "visible_region_nodes": [],
        "invisible_region_nodes": [],
        "region_target_scores": [],
        "viewpoint_target_scores": [
            {
                "id": 1,
                "target_scores": {
                    "4": _structured_score(
                        raw_score=0.6,
                        evidence_strength="medium",
                        basis="helmet remains possible at viewpoint one",
                    )
                },
            }
        ],
        "viewpoint_node_assigns": [],
        "new_edges": [edge],
        "edge_distance_variances": {
            "viewpoint_region": 1.0,
            "viewpoint_viewpoint": 1.0,
        },
    }


class _GraphStub:
    def __init__(self, summary):
        self.summary = summary
        self.target_found = dict(summary.get("target_found", {}))

    def get_mllm_summary(self):
        return copy.deepcopy(self.summary)


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
        "viewpoint_target_score_basis": [
            {
                "id": 1,
                "score_basis": {
                    "1": "stale target score basis should be projected out",
                    "4": "helmet remains possible but not confirmed",
                },
            }
        ],
        "viewpoint_node_assigns": [],
        "new_edges": [],
        "edge_distance_variances": {
            "viewpoint_region": 1.0,
            "viewpoint_viewpoint": 1.0,
        },
    }


def _agent_observations_with_panorama():
    observations = _minimal_agent_observations()
    observations[0]["annotated_panorama"] = b"panorama"
    return observations


def _target_score_basis(target_ids):
    return {
        str(target_id): "raw score follows from score-basis clue for target %s"
        % target_id
        for target_id in target_ids
    }


def _structured_score(raw_score=0.6, evidence_strength="medium", basis=None):
    if basis is None:
        basis = "structured score follows from current evidence"
    return {
        "raw_score": raw_score,
        "evidence_strength": evidence_strength,
        "basis": basis,
    }


def _payload_with_structured_target_scores():
    return {
        "current_viewpoints_reassignment": [],
        "visible_region_nodes": [],
        "invisible_region_nodes": [],
        "region_target_scores": [],
        "viewpoint_target_scores": [
            {
                "id": 1,
                "target_scores": {
                    "4": _structured_score(
                        raw_score=0.6,
                        evidence_strength="medium",
                        basis="helmet remains possible but not confirmed",
                    )
                },
            }
        ],
        "viewpoint_node_assigns": [],
        "new_edges": [],
        "edge_distance_variances": {
            "viewpoint_region": 1.0,
            "viewpoint_viewpoint": 1.0,
        },
    }


def _hybrid_saved_payload_with_structured_scores():
    payload = _payload_with_stale_target_keys()
    payload["viewpoint_target_scores"] = [
        {
            "id": 1,
            "target_scores": {
                "4": _structured_score(
                    raw_score=0.6,
                    evidence_strength="medium",
                    basis="hybrid saved structured score should be ignored",
                )
            },
        }
    ]
    return payload


def _graph_summary_for_current_assignment_repair():
    return {
        "nodes": [
            {
                "id": 1,
                "type": "viewpoint",
                "grounded": False,
                "node_visit_times": 0,
                "raw_target_probs": {"4": 0.0},
            },
            {
                "id": 95,
                "type": "region",
                "label": "bedroom area",
                "assigned_viewpoint_ids": [1],
                "target_probs": {"4": 0.5},
                "raw_target_probs": {"4": 0.5},
            },
            {
                "id": 103,
                "type": "region",
                "label": "hallway area",
                "assigned_viewpoint_ids": [],
                "target_probs": {"4": 0.2},
                "raw_target_probs": {"4": 0.2},
            },
            {
                "id": 104,
                "type": "region",
                "label": "dining area",
                "assigned_viewpoint_ids": [],
                "target_probs": {"4": 0.1},
                "raw_target_probs": {"4": 0.1},
            },
        ],
        "target_found": {"4": False},
        "targets": [{"target_id": "4", "description": "helmet"}],
        "viewpoint_to_region": {"1": 95},
    }


def _current_assignment_repair_observations():
    return [
        {
            "agent_id": "agent0",
            "current_viewpoint_index": 1,
            "visible_viewpoints": [],
        }
    ]


def _current_assignment_repair_payload(assignment_region, reassignment_region):
    region_target_scores = []
    if assignment_region != 95:
        region_target_scores.append(
            {
                "id": 95,
                "target_scores": {"4": 0.3},
            }
        )

    return {
        "current_viewpoints_reassignment": [
            {
                "viewpoint_id": 1,
                "new_assigned_region_id": reassignment_region,
            }
        ],
        "visible_region_nodes": [],
        "invisible_region_nodes": [],
        "region_target_scores": region_target_scores,
        "viewpoint_target_scores": [],
        "viewpoint_node_assigns": [
            {
                "region_node_id": assignment_region,
                "assigned_viewpoint_node_indices": [1],
            }
        ],
        "new_edges": [],
        "edge_distance_variances": {
            "viewpoint_region": 1.0,
            "viewpoint_viewpoint": 1.0,
        },
    }


def _install_replay_stubs(monkeypatch, client, saved_payload, written_payloads):
    monkeypatch.setattr(client, "_resize_panorama_array", lambda panorama: panorama)
    monkeypatch.setattr(client, "_write_observation_image", lambda **kwargs: None)
    monkeypatch.setattr(
        client,
        "_image_to_data_url",
        lambda image: "data:image/png;base64,",
    )
    monkeypatch.setattr(client, "_detect_targets", lambda **kwargs: [])
    monkeypatch.setattr(
        client,
        "_build_instruction",
        lambda **kwargs: ("system", "user"),
    )
    monkeypatch.setattr(
        client,
        "_read_semantic_raw_output",
        lambda step_index: json.dumps(saved_payload),
    )
    monkeypatch.setattr(
        client,
        "_write_semantic_raw_output",
        lambda step_index, decoded: written_payloads.append(json.loads(decoded)),
    )
    monkeypatch.setattr(
        client,
        "_write_user_message",
        lambda step_index, user_message: None,
    )

    def fail_request_completion(**kwargs):
        raise AssertionError("saved semantic replay requested the graph MLLM")

    monkeypatch.setattr(client, "_request_completion", fail_request_completion)


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
    assert projected["viewpoint_target_score_basis"][0]["score_basis"].keys() == {
        "4"
    }
    assert projected["visible_region_nodes"][0]["target_probs"] == {"4": 0.8}
    assert projected["invisible_region_nodes"][0]["target_probs"] == {"4": 0.3}
    assert projected["viewpoint_target_probs"][0]["id"] == 1


def test_project_saved_payload_to_graph_contract_removes_detection_fixed_and_stale_ids(
    monkeypatch,
):
    Helper = importlib.import_module("Helper")
    mllm_client = importlib.import_module("semantic_persistence.mllm_client")
    payload = _payload_with_stale_target_keys()
    payload["viewpoint_target_probs"].extend(
        [
            {
                "id": 0,
                "target_probs": {"4": 0.9},
                "raw_target_probs": {"4": 0.9},
            },
            {
                "id": 99,
                "target_probs": {"4": 0.7},
                "raw_target_probs": {"4": 0.7},
            },
        ]
    )

    monkeypatch.setattr(Helper, "viewpoint_vp_label_by_index", {0: "vp0", 1: "vp1"})

    projected = mllm_client.MLLMClient._project_saved_payload_to_graph_mllm_contract(
        payload=payload,
        agent_observations=_minimal_agent_observations(),
        targets=[{"target_id": "4", "description": "helmet"}],
        graph_summary=_minimal_graph_summary(),
    )

    assert [item["id"] for item in projected["viewpoint_target_probs"]] == [1]
    assert projected["viewpoint_target_probs"][0]["raw_target_probs"] == {"4": 0.6}
    assert [item["id"] for item in projected["viewpoint_target_score_basis"]] == [1]
    assert projected["viewpoint_target_score_basis"][0]["score_basis"].keys() == {
        "4"
    }


def test_project_saved_hybrid_payload_strips_structured_scores_before_validation(
    monkeypatch,
):
    Helper = importlib.import_module("Helper")
    mllm_client = importlib.import_module("semantic_persistence.mllm_client")
    client = object.__new__(mllm_client.MLLMClient)
    payload = _hybrid_saved_payload_with_structured_scores()

    monkeypatch.setattr(Helper, "viewpoint_vp_label_by_index", {0: "vp0", 1: "vp1"})

    projected = mllm_client.MLLMClient._project_saved_payload_to_graph_mllm_contract(
        payload=payload,
        agent_observations=_minimal_agent_observations(),
        targets=[{"target_id": "4", "description": "helmet"}],
        graph_summary=_minimal_graph_summary(),
    )

    assert "viewpoint_target_scores" not in projected

    validated = client._validate_payload(
        payload=projected,
        agent_observations=_minimal_agent_observations(),
        targets=[{"target_id": "4", "description": "helmet"}],
        graph_summary=_minimal_graph_summary(),
        scorer=None,
        semantic_payload_contract="saved_materialized",
    )

    assert "viewpoint_target_scores" not in validated
    assert validated["viewpoint_target_probs"][0]["raw_target_probs"] == {"4": 0.6}


def test_repair_removes_contradictory_current_reassignment_when_assignment_is_prior_region(
    monkeypatch,
):
    Helper = importlib.import_module("Helper")
    mllm_client = importlib.import_module("semantic_persistence.mllm_client")
    client = object.__new__(mllm_client.MLLMClient)
    observations = _current_assignment_repair_observations()
    graph_summary = _graph_summary_for_current_assignment_repair()
    payload = _current_assignment_repair_payload(
        assignment_region=95,
        reassignment_region=104,
    )

    monkeypatch.setattr(Helper, "viewpoint_vp_label_by_index", {1: "vp1"})

    repair_messages = client._repair_graph_mllm_payload(
        payload=payload,
        agent_observations=observations,
        targets=[{"target_id": "4", "description": "helmet"}],
        graph_summary=graph_summary,
    )

    assert "removed contradictory current viewpoint reassignment for 1" in repair_messages
    assert payload["current_viewpoints_reassignment"] == []

    validated = client._validate_payload(
        payload=payload,
        agent_observations=observations,
        targets=[{"target_id": "4", "description": "helmet"}],
        graph_summary=graph_summary,
        scorer=None,
        semantic_payload_contract="graph_mllm",
    )

    assert validated["current_viewpoints_reassignment"] == []
    assert validated["viewpoint_node_assigns"] == [
        {
            "region_node_id": 95,
            "assigned_viewpoint_node_indices": [1],
        }
    ]


def test_repair_aligns_current_reassignment_to_required_assignment_region(
    monkeypatch,
):
    Helper = importlib.import_module("Helper")
    mllm_client = importlib.import_module("semantic_persistence.mllm_client")
    client = object.__new__(mllm_client.MLLMClient)
    observations = _current_assignment_repair_observations()
    graph_summary = _graph_summary_for_current_assignment_repair()
    payload = _current_assignment_repair_payload(
        assignment_region=104,
        reassignment_region=103,
    )

    monkeypatch.setattr(Helper, "viewpoint_vp_label_by_index", {1: "vp1"})

    repair_messages = client._repair_graph_mllm_payload(
        payload=payload,
        agent_observations=observations,
        targets=[{"target_id": "4", "description": "helmet"}],
        graph_summary=graph_summary,
    )

    assert (
        "aligned current viewpoint reassignment for 1 to required assignment"
        in repair_messages
    )
    assert payload["current_viewpoints_reassignment"] == [
        {
            "viewpoint_id": 1,
            "new_assigned_region_id": 104,
        }
    ]

    validated = client._validate_payload(
        payload=payload,
        agent_observations=observations,
        targets=[{"target_id": "4", "description": "helmet"}],
        graph_summary=graph_summary,
        scorer=None,
        semantic_payload_contract="graph_mllm",
    )

    assert validated["current_viewpoints_reassignment"] == [
        {
            "viewpoint_id": 1,
            "new_assigned_region_id": 104,
        }
    ]
    assert validated["viewpoint_node_assigns"] == [
        {
            "region_node_id": 104,
            "assigned_viewpoint_node_indices": [1],
        }
    ]


def test_projected_saved_graph_contract_validates_after_materialized_id_removal(
    monkeypatch,
):
    Helper = importlib.import_module("Helper")
    mllm_client = importlib.import_module("semantic_persistence.mllm_client")
    client = object.__new__(mllm_client.MLLMClient)
    payload = _payload_with_stale_target_keys()
    payload["viewpoint_target_probs"].append(
        {
            "id": 0,
            "target_probs": {"4": 0.9},
            "raw_target_probs": {"4": 0.9},
        }
    )

    monkeypatch.setattr(Helper, "viewpoint_vp_label_by_index", {0: "vp0", 1: "vp1"})

    projected = mllm_client.MLLMClient._project_saved_payload_to_graph_mllm_contract(
        payload=payload,
        agent_observations=_minimal_agent_observations(),
        targets=[{"target_id": "4", "description": "helmet"}],
        graph_summary=_minimal_graph_summary(),
    )
    validated = client._validate_payload(
        payload=projected,
        agent_observations=_minimal_agent_observations(),
        targets=[{"target_id": "4", "description": "helmet"}],
        graph_summary=_minimal_graph_summary(),
        scorer=None,
        semantic_payload_contract="saved_materialized",
    )

    assert [item["id"] for item in validated["viewpoint_target_probs"]] == [1]
    assert validated["viewpoint_target_probs"][0]["target_probs"] == {"4": 1.0}


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
        semantic_payload_contract="saved_materialized",
    )

    assert validated["viewpoint_target_probs"][0]["target_probs"] == {"4": 1.0}
    assert validated["viewpoint_target_probs"][0]["raw_target_probs"] == {"4": 0.6}


def test_saved_materialized_payload_accepts_missing_basis_for_inherited_prior_score(
    monkeypatch,
):
    Helper = importlib.import_module("Helper")
    mllm_client = importlib.import_module("semantic_persistence.mllm_client")
    client = object.__new__(mllm_client.MLLMClient)
    payload = _payload_with_stale_target_keys()
    payload["viewpoint_target_probs"][0]["target_probs"] = {"4": 1.0}
    payload["viewpoint_target_probs"][0]["raw_target_probs"] = {"4": 0.2}
    payload["viewpoint_target_score_basis"][0]["score_basis"] = {}
    payload = mllm_client.MLLMClient._project_saved_payload_to_target_ids(
        payload=payload,
        target_ids=["4"],
    )

    monkeypatch.setattr(Helper, "viewpoint_vp_label_by_index", {0: "vp0", 1: "vp1"})

    validated = client._validate_payload(
        payload=payload,
        agent_observations=_minimal_agent_observations(),
        targets=[{"target_id": "4", "description": "helmet"}],
        graph_summary=_minimal_graph_summary(raw_target_probs={"4": 0.2}),
        scorer=None,
        semantic_payload_contract="saved_materialized",
    )

    assert validated["viewpoint_target_probs"][0]["raw_target_probs"] == {"4": 0.2}
    assert validated["viewpoint_target_score_basis"][0]["score_basis"] == {}


def test_saved_materialized_payload_rejects_missing_basis_for_changed_score(
    monkeypatch,
):
    Helper = importlib.import_module("Helper")
    mllm_client = importlib.import_module("semantic_persistence.mllm_client")
    client = object.__new__(mllm_client.MLLMClient)
    payload = _payload_with_stale_target_keys()
    payload["viewpoint_target_probs"][0]["target_probs"] = {"4": 1.0}
    payload["viewpoint_target_probs"][0]["raw_target_probs"] = {"4": 0.3}
    payload["viewpoint_target_score_basis"][0]["score_basis"] = {}
    payload = mllm_client.MLLMClient._project_saved_payload_to_target_ids(
        payload=payload,
        target_ids=["4"],
    )

    monkeypatch.setattr(Helper, "viewpoint_vp_label_by_index", {0: "vp0", 1: "vp1"})

    with pytest.raises(ValueError, match="Missing required saved"):
        client._validate_payload(
            payload=payload,
            agent_observations=_minimal_agent_observations(),
            targets=[{"target_id": "4", "description": "helmet"}],
            graph_summary=_minimal_graph_summary(raw_target_probs={"4": 0.2}),
            scorer=None,
            semantic_payload_contract="saved_materialized",
        )


def test_saved_materialized_payload_rejects_missing_basis_without_prior_score(
    monkeypatch,
):
    Helper = importlib.import_module("Helper")
    mllm_client = importlib.import_module("semantic_persistence.mllm_client")
    client = object.__new__(mllm_client.MLLMClient)
    payload = _payload_with_stale_target_keys()
    payload["viewpoint_target_probs"][0]["target_probs"] = {"4": 1.0}
    payload["viewpoint_target_probs"][0]["raw_target_probs"] = {"4": 0.2}
    payload["viewpoint_target_score_basis"][0]["score_basis"] = {}
    payload = mllm_client.MLLMClient._project_saved_payload_to_target_ids(
        payload=payload,
        target_ids=["4"],
    )

    monkeypatch.setattr(Helper, "viewpoint_vp_label_by_index", {0: "vp0", 1: "vp1"})

    with pytest.raises(ValueError, match="Missing required saved"):
        client._validate_payload(
            payload=payload,
            agent_observations=_minimal_agent_observations(),
            targets=[{"target_id": "4", "description": "helmet"}],
            graph_summary=_minimal_graph_summary(raw_target_probs={}),
            scorer=None,
            semantic_payload_contract="saved_materialized",
        )


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
            semantic_payload_contract="saved_materialized",
        )


def test_projected_saved_graph_contract_missing_required_value_still_fails(
    monkeypatch,
):
    Helper = importlib.import_module("Helper")
    mllm_client = importlib.import_module("semantic_persistence.mllm_client")
    client = object.__new__(mllm_client.MLLMClient)
    payload = _payload_with_stale_target_keys()
    payload["viewpoint_target_probs"][0]["target_probs"] = {"1": 0.4}
    payload["viewpoint_target_probs"][0]["raw_target_probs"] = {"1": 0.4}

    monkeypatch.setattr(Helper, "viewpoint_vp_label_by_index", {0: "vp0", 1: "vp1"})

    projected = mllm_client.MLLMClient._project_saved_payload_to_graph_mllm_contract(
        payload=payload,
        agent_observations=_minimal_agent_observations(),
        targets=[{"target_id": "4", "description": "helmet"}],
        graph_summary=_minimal_graph_summary(raw_target_probs={}),
    )

    with pytest.raises(ValueError, match="Missing required MLLM-updatable"):
        client._validate_payload(
            payload=projected,
            agent_observations=_minimal_agent_observations(),
            targets=[{"target_id": "4", "description": "helmet"}],
            graph_summary=_minimal_graph_summary(raw_target_probs={}),
            scorer=None,
            semantic_payload_contract="saved_materialized",
        )


def test_saved_semantic_replay_repairs_locally_without_requesting_mllm(
    monkeypatch,
):
    Helper = importlib.import_module("Helper")
    mllm_client = importlib.import_module("semantic_persistence.mllm_client")
    client = mllm_client.MLLMClient(read_saved_raw_outputs=True)
    saved_payload = _payload_with_stale_target_keys()
    saved_payload["viewpoint_target_probs"].append(
        {
            "id": 0,
            "target_probs": {"4": 0.9},
            "raw_target_probs": {"4": 0.9},
        }
    )
    written_payloads = []

    monkeypatch.setattr(Helper, "viewpoint_vp_label_by_index", {0: "vp0", 1: "vp1"})
    _install_replay_stubs(monkeypatch, client, saved_payload, written_payloads)

    payload = client.propose_semantic_nodes(
        agent_observations=_agent_observations_with_panorama(),
        targets=[{"target_id": "4", "description": "helmet"}],
        graph=_GraphStub(_minimal_graph_summary()),
        scorer=None,
    )

    assert payload["viewpoint_target_probs"][0]["id"] == 1
    assert written_payloads[0]["viewpoint_target_probs"][0]["id"] == 1
    assert client.semantic_raw_output_index == 2


def test_saved_semantic_replay_accepts_inherited_score_without_basis(
    monkeypatch,
):
    Helper = importlib.import_module("Helper")
    mllm_client = importlib.import_module("semantic_persistence.mllm_client")
    client = mllm_client.MLLMClient(read_saved_raw_outputs=True)
    saved_payload = _payload_with_stale_target_keys()
    saved_payload["viewpoint_target_probs"][0]["target_probs"] = {"4": 1.0}
    saved_payload["viewpoint_target_probs"][0]["raw_target_probs"] = {"4": 0.2}
    saved_payload["viewpoint_target_score_basis"][0]["score_basis"] = {}
    written_payloads = []

    monkeypatch.setattr(Helper, "viewpoint_vp_label_by_index", {0: "vp0", 1: "vp1"})
    _install_replay_stubs(monkeypatch, client, saved_payload, written_payloads)

    payload = client.propose_semantic_nodes(
        agent_observations=_agent_observations_with_panorama(),
        targets=[{"target_id": "4", "description": "helmet"}],
        graph=_GraphStub(_minimal_graph_summary(raw_target_probs={"4": 0.2})),
        scorer=None,
    )

    assert payload["viewpoint_target_score_basis"][0]["score_basis"] == {}
    assert written_payloads[0]["viewpoint_target_score_basis"][0]["score_basis"] == {}
    assert client.semantic_raw_output_index == 2


def test_decode_saved_semantic_payload_accepts_hybrid_materialized_payload(
    monkeypatch,
):
    Helper = importlib.import_module("Helper")
    mllm_client = importlib.import_module("semantic_persistence.mllm_client")
    client = object.__new__(mllm_client.MLLMClient)
    saved_payload = _hybrid_saved_payload_with_structured_scores()

    monkeypatch.setattr(Helper, "viewpoint_vp_label_by_index", {0: "vp0", 1: "vp1"})

    payload, repair_messages = client._decode_saved_semantic_payload(
        decoded=json.dumps(saved_payload),
        agent_observations=_minimal_agent_observations(),
        targets=[{"target_id": "4", "description": "helmet"}],
        graph_summary=_minimal_graph_summary(),
        scorer=None,
    )

    assert repair_messages == []
    assert "viewpoint_target_scores" not in payload
    assert payload["viewpoint_target_probs"][0]["raw_target_probs"] == {"4": 0.6}
    assert payload["viewpoint_target_score_basis"][0]["score_basis"] == {
        "4": "helmet remains possible but not confirmed"
    }


def test_saved_semantic_replay_raises_instead_of_requesting_mllm_after_failed_repair(
    monkeypatch,
):
    Helper = importlib.import_module("Helper")
    mllm_client = importlib.import_module("semantic_persistence.mllm_client")
    client = mllm_client.MLLMClient(read_saved_raw_outputs=True)
    saved_payload = _payload_with_stale_target_keys()
    saved_payload["viewpoint_target_probs"][0]["target_probs"] = {"1": 0.4}
    saved_payload["viewpoint_target_probs"][0]["raw_target_probs"] = {"1": 0.4}
    written_payloads = []

    monkeypatch.setattr(Helper, "viewpoint_vp_label_by_index", {0: "vp0", 1: "vp1"})
    _install_replay_stubs(monkeypatch, client, saved_payload, written_payloads)

    with pytest.raises(ValueError, match="Missing required MLLM-updatable"):
        client.propose_semantic_nodes(
            agent_observations=_agent_observations_with_panorama(),
            targets=[{"target_id": "4", "description": "helmet"}],
            graph=_GraphStub(_minimal_graph_summary(raw_target_probs={})),
            scorer=None,
        )

    assert written_payloads == []


def test_validate_payload_requires_viewpoint_target_scores(monkeypatch):
    Helper = importlib.import_module("Helper")
    mllm_client = importlib.import_module("semantic_persistence.mllm_client")
    client = object.__new__(mllm_client.MLLMClient)
    payload = _payload_with_structured_target_scores()
    del payload["viewpoint_target_scores"]

    monkeypatch.setattr(Helper, "viewpoint_vp_label_by_index", {0: "vp0", 1: "vp1"})

    with pytest.raises(KeyError, match="Missing top-level keys"):
        client._validate_payload(
            payload=payload,
            agent_observations=_minimal_agent_observations(),
            targets=[{"target_id": "4", "description": "helmet"}],
            graph_summary=_minimal_graph_summary(),
            scorer=None,
            semantic_payload_contract="graph_mllm",
        )


def test_validate_payload_rejects_vv_edge_with_current_endpoint(monkeypatch):
    Helper = importlib.import_module("Helper")
    mllm_client = importlib.import_module("semantic_persistence.mllm_client")
    client = object.__new__(mllm_client.MLLMClient)
    payload = _vv_edge_validation_payload(
        {"i": 0, "j": 1, "edge_type": "VV", "exist_prob": 0.8, "dist": 2.0}
    )

    monkeypatch.setattr(
        Helper, "viewpoint_vp_label_by_index", {0: "vp0", 1: "vp1", 2: "vp2"}
    )

    with pytest.raises(ValueError, match="cannot use a current viewpoint"):
        client._validate_payload(
            payload=payload,
            agent_observations=_vv_edge_validation_observations(),
            targets=[{"target_id": "4", "description": "helmet"}],
            graph_summary=_vv_edge_validation_graph_summary(),
            scorer=None,
            semantic_payload_contract="graph_mllm",
        )


def test_validate_payload_rejects_vv_edge_with_grounded_endpoint(monkeypatch):
    Helper = importlib.import_module("Helper")
    mllm_client = importlib.import_module("semantic_persistence.mllm_client")
    client = object.__new__(mllm_client.MLLMClient)
    payload = _vv_edge_validation_payload(
        {"i": 1, "j": 2, "edge_type": "VV", "exist_prob": 0.8, "dist": 2.0}
    )

    monkeypatch.setattr(
        Helper, "viewpoint_vp_label_by_index", {0: "vp0", 1: "vp1", 2: "vp2"}
    )

    with pytest.raises(ValueError, match="ungrounded and unvisited"):
        client._validate_payload(
            payload=payload,
            agent_observations=_vv_edge_validation_observations(),
            targets=[{"target_id": "4", "description": "helmet"}],
            graph_summary=_vv_edge_validation_graph_summary(endpoint2_grounded=True),
            scorer=None,
            semantic_payload_contract="graph_mllm",
        )


def test_validate_payload_rejects_vv_edge_with_visited_endpoint(monkeypatch):
    Helper = importlib.import_module("Helper")
    mllm_client = importlib.import_module("semantic_persistence.mllm_client")
    client = object.__new__(mllm_client.MLLMClient)
    payload = _vv_edge_validation_payload(
        {"i": 1, "j": 2, "edge_type": "VV", "exist_prob": 0.8, "dist": 2.0}
    )

    monkeypatch.setattr(
        Helper, "viewpoint_vp_label_by_index", {0: "vp0", 1: "vp1", 2: "vp2"}
    )

    with pytest.raises(ValueError, match="ungrounded and unvisited"):
        client._validate_payload(
            payload=payload,
            agent_observations=_vv_edge_validation_observations(),
            targets=[{"target_id": "4", "description": "helmet"}],
            graph_summary=_vv_edge_validation_graph_summary(endpoint2_visit_times=1),
            scorer=None,
            semantic_payload_contract="graph_mllm",
        )


def test_validate_payload_materializes_graph_scores_without_returning_live_field(
    monkeypatch,
):
    Helper = importlib.import_module("Helper")
    mllm_client = importlib.import_module("semantic_persistence.mllm_client")
    client = object.__new__(mllm_client.MLLMClient)
    payload = _payload_with_structured_target_scores()

    monkeypatch.setattr(Helper, "viewpoint_vp_label_by_index", {0: "vp0", 1: "vp1"})

    validated = client._validate_payload(
        payload=payload,
        agent_observations=_minimal_agent_observations(),
        targets=[{"target_id": "4", "description": "helmet"}],
        graph_summary=_minimal_graph_summary(),
        scorer=None,
        semantic_payload_contract="graph_mllm",
    )

    assert "viewpoint_target_scores" not in validated
    assert validated["viewpoint_target_probs"] == [
        {
            "id": 1,
            "target_probs": {"4": 1.0},
            "raw_target_probs": {"4": 0.6},
        }
    ]
    assert validated["viewpoint_target_score_basis"] == [
        {
            "id": 1,
            "score_basis": {"4": "helmet remains possible but not confirmed"},
        }
    ]


def test_validate_payload_rejects_missing_structured_raw_score(monkeypatch):
    Helper = importlib.import_module("Helper")
    mllm_client = importlib.import_module("semantic_persistence.mllm_client")
    client = object.__new__(mllm_client.MLLMClient)
    payload = _payload_with_structured_target_scores()
    del payload["viewpoint_target_scores"][0]["target_scores"]["4"]["raw_score"]

    monkeypatch.setattr(Helper, "viewpoint_vp_label_by_index", {0: "vp0", 1: "vp1"})

    with pytest.raises(KeyError, match="raw_score"):
        client._validate_payload(
            payload=payload,
            agent_observations=_minimal_agent_observations(),
            targets=[{"target_id": "4", "description": "helmet"}],
            graph_summary=_minimal_graph_summary(),
            scorer=None,
            semantic_payload_contract="graph_mllm",
        )


def test_validate_payload_rejects_invalid_evidence_strength(monkeypatch):
    Helper = importlib.import_module("Helper")
    mllm_client = importlib.import_module("semantic_persistence.mllm_client")
    client = object.__new__(mllm_client.MLLMClient)
    payload = _payload_with_structured_target_scores()
    payload["viewpoint_target_scores"][0]["target_scores"]["4"][
        "evidence_strength"
    ] = "very_high"

    monkeypatch.setattr(Helper, "viewpoint_vp_label_by_index", {0: "vp0", 1: "vp1"})

    with pytest.raises(ValueError, match="evidence_strength"):
        client._validate_payload(
            payload=payload,
            agent_observations=_minimal_agent_observations(),
            targets=[{"target_id": "4", "description": "helmet"}],
            graph_summary=_minimal_graph_summary(),
            scorer=None,
            semantic_payload_contract="graph_mllm",
        )


def test_validate_payload_rejects_blank_structured_basis(monkeypatch):
    Helper = importlib.import_module("Helper")
    mllm_client = importlib.import_module("semantic_persistence.mllm_client")
    client = object.__new__(mllm_client.MLLMClient)
    payload = _payload_with_structured_target_scores()
    payload["viewpoint_target_scores"][0]["target_scores"]["4"]["basis"] = ""

    monkeypatch.setattr(Helper, "viewpoint_vp_label_by_index", {0: "vp0", 1: "vp1"})

    with pytest.raises(ValueError, match="basis"):
        client._validate_payload(
            payload=payload,
            agent_observations=_minimal_agent_observations(),
            targets=[{"target_id": "4", "description": "helmet"}],
            graph_summary=_minimal_graph_summary(),
            scorer=None,
            semantic_payload_contract="graph_mllm",
        )


def test_validate_payload_rejects_negative_structured_raw_score(monkeypatch):
    Helper = importlib.import_module("Helper")
    mllm_client = importlib.import_module("semantic_persistence.mllm_client")
    client = object.__new__(mllm_client.MLLMClient)
    payload = _payload_with_structured_target_scores()
    payload["viewpoint_target_scores"][0]["target_scores"]["4"]["raw_score"] = -0.1

    monkeypatch.setattr(Helper, "viewpoint_vp_label_by_index", {0: "vp0", 1: "vp1"})

    with pytest.raises(ValueError, match="raw_score"):
        client._validate_payload(
            payload=payload,
            agent_observations=_minimal_agent_observations(),
            targets=[{"target_id": "4", "description": "helmet"}],
            graph_summary=_minimal_graph_summary(),
            scorer=None,
            semantic_payload_contract="graph_mllm",
        )


def test_validate_payload_rejects_stale_structured_target_score(monkeypatch):
    Helper = importlib.import_module("Helper")
    mllm_client = importlib.import_module("semantic_persistence.mllm_client")
    client = object.__new__(mllm_client.MLLMClient)
    payload = _payload_with_structured_target_scores()
    payload["viewpoint_target_scores"][0]["target_scores"] = {
        "1": _structured_score()
    }

    monkeypatch.setattr(Helper, "viewpoint_vp_label_by_index", {0: "vp0", 1: "vp1"})

    with pytest.raises(ValueError, match="target_scores keys"):
        client._validate_payload(
            payload=payload,
            agent_observations=_minimal_agent_observations(),
            targets=[{"target_id": "4", "description": "helmet"}],
            graph_summary=_minimal_graph_summary(),
            scorer=None,
            semantic_payload_contract="graph_mllm",
        )


def test_validate_payload_preserves_distinct_raw_scores_before_normalization(
    monkeypatch,
):
    Helper = importlib.import_module("Helper")
    mllm_client = importlib.import_module("semantic_persistence.mllm_client")
    client = object.__new__(mllm_client.MLLMClient)
    observations = [
        {
            "agent_id": "agent0",
            "current_viewpoint_index": 0,
            "visible_viewpoints": [
                {"viewpoint_index": 1, "distance": 1.0},
                {"viewpoint_index": 2, "distance": 2.0},
            ],
        }
    ]
    graph_summary = {
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
                "raw_target_probs": {},
            },
            {
                "id": 2,
                "type": "viewpoint",
                "grounded": False,
                "node_visit_times": 0,
                "raw_target_probs": {},
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
    payload = {
        "current_viewpoints_reassignment": [],
        "visible_region_nodes": [],
        "invisible_region_nodes": [],
        "region_target_scores": [],
        "viewpoint_target_scores": [
            {
                "id": 1,
                "target_scores": {
                    "4": _structured_score(
                        raw_score=0.2,
                        evidence_strength="low",
                    )
                },
            },
            {
                "id": 2,
                "target_scores": {
                    "4": _structured_score(
                        raw_score=0.8,
                        evidence_strength="high",
                    )
                },
            },
        ],
        "viewpoint_node_assigns": [],
        "new_edges": [],
        "edge_distance_variances": {
            "viewpoint_region": 1.0,
            "viewpoint_viewpoint": 1.0,
        },
    }

    monkeypatch.setattr(
        Helper, "viewpoint_vp_label_by_index", {0: "vp0", 1: "vp1", 2: "vp2"}
    )

    validated = client._validate_payload(
        payload=payload,
        agent_observations=observations,
        targets=[{"target_id": "4", "description": "helmet"}],
        graph_summary=graph_summary,
        scorer=None,
        semantic_payload_contract="graph_mllm",
    )

    raw_scores = {
        item["id"]: item["raw_target_probs"]["4"]
        for item in validated["viewpoint_target_probs"]
    }
    normalized_scores = {
        item["id"]: item["target_probs"]["4"]
        for item in validated["viewpoint_target_probs"]
    }
    assert raw_scores == {1: 0.2, 2: 0.8}
    assert normalized_scores == {1: 0.2, 2: 0.8}


def test_validate_payload_repairs_low_score_above_high_score(monkeypatch):
    Helper = importlib.import_module("Helper")
    mllm_client = importlib.import_module("semantic_persistence.mllm_client")
    client = object.__new__(mllm_client.MLLMClient)
    observations = [
        {
            "agent_id": "agent0",
            "current_viewpoint_index": 0,
            "visible_viewpoints": [
                {"viewpoint_index": 1, "distance": 1.0},
                {"viewpoint_index": 2, "distance": 2.0},
            ],
        }
    ]
    graph_summary = {
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
                "raw_target_probs": {},
            },
            {
                "id": 2,
                "type": "viewpoint",
                "grounded": False,
                "node_visit_times": 0,
                "raw_target_probs": {},
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
    payload = {
        "current_viewpoints_reassignment": [],
        "visible_region_nodes": [],
        "invisible_region_nodes": [],
        "region_target_scores": [],
        "viewpoint_target_scores": [
            {
                "id": 1,
                "target_scores": {
                    "4": _structured_score(raw_score=0.85, evidence_strength="low")
                },
            },
            {
                "id": 2,
                "target_scores": {
                    "4": _structured_score(raw_score=0.05, evidence_strength="high")
                },
            },
        ],
        "viewpoint_node_assigns": [],
        "new_edges": [],
        "edge_distance_variances": {
            "viewpoint_region": 1.0,
            "viewpoint_viewpoint": 1.0,
        },
    }

    monkeypatch.setattr(
        Helper, "viewpoint_vp_label_by_index", {0: "vp0", 1: "vp1", 2: "vp2"}
    )

    validated = client._validate_payload(
        payload=payload,
        agent_observations=observations,
        targets=[{"target_id": "4", "description": "helmet"}],
        graph_summary=graph_summary,
        scorer=None,
        semantic_payload_contract="graph_mllm",
    )

    raw_scores = {
        item["id"]: item["raw_target_probs"]["4"]
        for item in validated["viewpoint_target_probs"]
    }
    assert raw_scores[1] <= raw_scores[2]
    assert raw_scores == pytest.approx({1: 0.45, 2: 0.45})


def test_validate_payload_repairs_three_strength_buckets_before_normalization(
    monkeypatch,
):
    Helper = importlib.import_module("Helper")
    mllm_client = importlib.import_module("semantic_persistence.mllm_client")
    client = object.__new__(mllm_client.MLLMClient)
    observations = [
        {
            "agent_id": "agent0",
            "current_viewpoint_index": 0,
            "visible_viewpoints": [
                {"viewpoint_index": 1, "distance": 1.0},
                {"viewpoint_index": 2, "distance": 2.0},
                {"viewpoint_index": 3, "distance": 3.0},
            ],
        }
    ]
    graph_summary = {
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
                "raw_target_probs": {},
            },
            {
                "id": 2,
                "type": "viewpoint",
                "grounded": False,
                "node_visit_times": 0,
                "raw_target_probs": {},
            },
            {
                "id": 3,
                "type": "viewpoint",
                "grounded": False,
                "node_visit_times": 0,
                "raw_target_probs": {},
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
    payload = {
        "current_viewpoints_reassignment": [],
        "visible_region_nodes": [],
        "invisible_region_nodes": [],
        "region_target_scores": [],
        "viewpoint_target_scores": [
            {
                "id": 1,
                "target_scores": {
                    "4": _structured_score(raw_score=0.1, evidence_strength="low")
                },
            },
            {
                "id": 2,
                "target_scores": {
                    "4": _structured_score(raw_score=0.9, evidence_strength="medium")
                },
            },
            {
                "id": 3,
                "target_scores": {
                    "4": _structured_score(raw_score=0.2, evidence_strength="high")
                },
            },
        ],
        "viewpoint_node_assigns": [],
        "new_edges": [],
        "edge_distance_variances": {
            "viewpoint_region": 1.0,
            "viewpoint_viewpoint": 1.0,
        },
    }

    monkeypatch.setattr(
        Helper,
        "viewpoint_vp_label_by_index",
        {0: "vp0", 1: "vp1", 2: "vp2", 3: "vp3"},
    )

    validated = client._validate_payload(
        payload=payload,
        agent_observations=observations,
        targets=[{"target_id": "4", "description": "helmet"}],
        graph_summary=graph_summary,
        scorer=None,
        semantic_payload_contract="graph_mllm",
    )

    raw_scores = {
        item["id"]: item["raw_target_probs"]["4"]
        for item in validated["viewpoint_target_probs"]
    }
    normalized_scores = {
        item["id"]: item["target_probs"]["4"]
        for item in validated["viewpoint_target_probs"]
    }
    assert raw_scores == pytest.approx({1: 0.1, 2: 0.55, 3: 0.55})
    assert normalized_scores == pytest.approx(
        {1: 0.08333333333333333, 2: 0.4583333333333333, 3: 0.4583333333333333}
    )


def test_validate_payload_normalizes_type2_region_target_scores(monkeypatch):
    Helper = importlib.import_module("Helper")
    mllm_client = importlib.import_module("semantic_persistence.mllm_client")
    client = object.__new__(mllm_client.MLLMClient)
    graph_summary = {
        "nodes": [
            {
                "id": 0,
                "type": "viewpoint",
                "grounded": True,
                "node_visit_times": 1,
                "raw_target_probs": {"4": 0.0},
            },
            {
                "id": 95,
                "type": "region",
                "label": "office room",
                "assigned_viewpoint_ids": [0],
                "target_probs": {"4": 0.0},
                "raw_target_probs": {"4": 0.0},
            },
            {
                "id": 103,
                "type": "region",
                "label": "hallway area",
                "assigned_viewpoint_ids": [],
                "target_probs": {"4": 0.2},
                "raw_target_probs": {"4": 0.2},
            },
            {
                "id": 104,
                "type": "region",
                "label": "storage area",
                "assigned_viewpoint_ids": [],
                "target_probs": {"4": 0.1},
                "raw_target_probs": {"4": 0.1},
            },
        ],
        "target_found": {"4": False},
        "targets": [{"target_id": "4", "description": "helmet"}],
        "viewpoint_to_region": {"0": 95},
    }
    payload = {
        "current_viewpoints_reassignment": [],
        "visible_region_nodes": [],
        "invisible_region_nodes": [
            {
                "id": 105,
                "label": "unseen laundry area",
                "exist_prob": 0.6,
                "target_probs": {"4": 0.5},
            }
        ],
        "region_target_scores": [{"id": 103, "target_scores": {"4": 0.4}}],
        "viewpoint_target_scores": [],
        "viewpoint_node_assigns": [],
        "new_edges": [],
        "edge_distance_variances": {
            "viewpoint_region": 1.0,
            "viewpoint_viewpoint": 1.0,
        },
    }

    monkeypatch.setattr(Helper, "viewpoint_vp_label_by_index", {0: "vp0"})

    validated = client._validate_payload(
        payload=payload,
        agent_observations=[
            {
                "agent_id": "agent0",
                "current_viewpoint_index": 0,
                "visible_viewpoints": [],
            }
        ],
        targets=[{"target_id": "4", "description": "helmet"}],
        graph_summary=graph_summary,
        scorer=None,
        semantic_payload_contract="graph_mllm",
    )

    region_raw = {
        item["id"]: item["target_scores"]["4"]
        for item in validated["region_target_scores"]
    }
    assert region_raw == pytest.approx({103: 0.4, 104: 0.1, 105: 0.5})
    assert validated["invisible_region_nodes"][0]["target_probs"] == {"4": 0.5}


def test_validate_payload_forces_assigned_region_target_probs_to_zero(monkeypatch):
    Helper = importlib.import_module("Helper")
    mllm_client = importlib.import_module("semantic_persistence.mllm_client")
    client = object.__new__(mllm_client.MLLMClient)
    payload = {
        "current_viewpoints_reassignment": [],
        "visible_region_nodes": [
            {
                "id": 95,
                "label": "bright kitchen area",
                "exist_prob": 1.0,
                "target_probs": {"4": 0.0},
            }
        ],
        "invisible_region_nodes": [],
        "region_target_scores": [],
        "viewpoint_target_scores": [],
        "viewpoint_node_assigns": [
            {"region_node_id": 95, "assigned_viewpoint_node_indices": [0]}
        ],
        "new_edges": [],
        "edge_distance_variances": {
            "viewpoint_region": 1.0,
            "viewpoint_viewpoint": 1.0,
        },
    }

    monkeypatch.setattr(Helper, "viewpoint_vp_label_by_index", {0: "vp0"})

    validated = client._validate_payload(
        payload=payload,
        agent_observations=[
            {
                "agent_id": "agent0",
                "current_viewpoint_index": 0,
                "visible_viewpoints": [],
            }
        ],
        targets=[{"target_id": "4", "description": "helmet"}],
        graph_summary={"nodes": [], "viewpoint_to_region": {}},
        scorer=None,
        semantic_payload_contract="graph_mllm",
    )

    assert validated["visible_region_nodes"][0]["target_probs"] == {"4": 0.0}
    assert validated["region_target_scores"] == []


def test_validate_payload_requires_scores_when_region_becomes_type2(monkeypatch):
    Helper = importlib.import_module("Helper")
    mllm_client = importlib.import_module("semantic_persistence.mllm_client")
    client = object.__new__(mllm_client.MLLMClient)
    payload = {
        "current_viewpoints_reassignment": [
            {"viewpoint_id": 0, "new_assigned_region_id": 96}
        ],
        "visible_region_nodes": [
            {
                "id": 96,
                "label": "new hallway area",
                "exist_prob": 1.0,
                "target_probs": {"4": 0.3},
            }
        ],
        "invisible_region_nodes": [],
        "region_target_scores": [],
        "viewpoint_target_scores": [],
        "viewpoint_node_assigns": [],
        "new_edges": [],
        "edge_distance_variances": {
            "viewpoint_region": 1.0,
            "viewpoint_viewpoint": 1.0,
        },
    }

    monkeypatch.setattr(Helper, "viewpoint_vp_label_by_index", {0: "vp0"})

    with pytest.raises(ValueError, match="changed from assigned to unassigned"):
        client._validate_payload(
            payload=payload,
            agent_observations=[
                {
                    "agent_id": "agent0",
                    "current_viewpoint_index": 0,
                    "visible_viewpoints": [],
                }
            ],
            targets=[{"target_id": "4", "description": "helmet"}],
            graph_summary={
                "nodes": [
                    {
                        "id": 0,
                        "type": "viewpoint",
                        "grounded": True,
                        "node_visit_times": 1,
                        "raw_target_probs": {"4": 0.0},
                    },
                    {
                        "id": 95,
                        "type": "region",
                        "label": "office room",
                        "assigned_viewpoint_ids": [0],
                        "target_probs": {"4": 0.0},
                        "raw_target_probs": {"4": 0.0},
                    },
                ],
                "target_found": {"4": False},
                "targets": [{"target_id": "4", "description": "helmet"}],
                "viewpoint_to_region": {"0": 95},
            },
            scorer=None,
            semantic_payload_contract="graph_mllm",
        )


def test_validate_payload_rejects_zero_raw_sum_for_type2_regions(monkeypatch):
    Helper = importlib.import_module("Helper")
    mllm_client = importlib.import_module("semantic_persistence.mllm_client")
    client = object.__new__(mllm_client.MLLMClient)
    graph_summary = {
        "nodes": [
            {
                "id": 0,
                "type": "viewpoint",
                "grounded": True,
                "node_visit_times": 1,
                "raw_target_probs": {"4": 0.0},
            },
            {
                "id": 95,
                "type": "region",
                "label": "office room",
                "assigned_viewpoint_ids": [0],
                "target_probs": {"4": 0.0},
                "raw_target_probs": {"4": 0.0},
            },
            {
                "id": 103,
                "type": "region",
                "label": "empty storage area",
                "assigned_viewpoint_ids": [],
                "target_probs": {"4": 0.0},
                "raw_target_probs": {"4": 0.0},
            },
        ],
        "target_found": {"4": False},
        "targets": [{"target_id": "4", "description": "helmet"}],
        "viewpoint_to_region": {"0": 95},
    }
    payload = _payload_with_structured_target_scores()
    payload["viewpoint_target_scores"] = []

    monkeypatch.setattr(Helper, "viewpoint_vp_label_by_index", {0: "vp0", 1: "vp1"})

    with pytest.raises(ValueError, match="Type-\\(2\\) region target probabilities"):
        client._validate_payload(
            payload=payload,
            agent_observations=[
                {
                    "agent_id": "agent0",
                    "current_viewpoint_index": 0,
                    "visible_viewpoints": [],
                }
            ],
            targets=[{"target_id": "4", "description": "helmet"}],
            graph_summary=graph_summary,
            scorer=None,
            semantic_payload_contract="graph_mllm",
        )


def test_build_instruction_uses_evidence_contract_without_random_score_templates(
    monkeypatch,
):
    Helper = importlib.import_module("Helper")
    mllm_client = importlib.import_module("semantic_persistence.mllm_client")
    client = object.__new__(mllm_client.MLLMClient)

    monkeypatch.setattr(Helper, "viewpoint_vp_label_by_index", {0: "vp0", 1: "vp1"})

    _, user_message = client._build_instruction(
        agent_observations=_minimal_agent_observations(),
        targets=[{"target_id": "4", "description": "helmet"}],
        graph_summary=_minimal_graph_summary(raw_target_probs={}),
    )

    assert "viewpoint_target_scores" in user_message
    assert "evidence_strength" in user_message
    assert "raw_score" in user_message
    assert "viewpoint_target_score_basis" not in user_message
    assert "target_evidence" not in user_message
    assert '"support"' not in user_message
    assert '"against"' not in user_message
    assert "support may be []" not in user_message
    assert "against may be []" not in user_message
    assert "<nonnegative raw score justified by evidence>" in user_message
    assert "<score in [0, 1] justified by evidence>" in user_message
    assert '"4": 0.6' not in user_message
    assert '"4": 0.8' not in user_message


def test_test4_saved_prompt_targets_match_current_scenario_when_present():
    scenario = json.load(open("scenarios/test4.json", encoding="utf-8"))
    scenario_targets = {
        str(item["target_id"]): str(item["description"])
        for item in scenario["targets"]
    }
    prompt_path = "mllm_raw_outputs/test4/user_message_step_0001.txt"
    try:
        prompt_text = open(prompt_path, encoding="utf-8").read()
    except FileNotFoundError:
        pytest.skip("%s is not present in this checkout" % prompt_path)

    start = prompt_text.index("[")
    end = prompt_text.index("]\n\nCompact shared graph summary:") + 1
    prompt_targets = {
        str(item["target_id"]): str(item["description"])
        for item in json.loads(prompt_text[start:end])
    }

    assert prompt_targets == scenario_targets
