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
        semantic_payload_contract="graph_mllm",
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
            semantic_payload_contract="graph_mllm",
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
