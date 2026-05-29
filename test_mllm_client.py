import json
from types import SimpleNamespace

import numpy as np
import pytest
from openai import APITimeoutError

from semantic_persistence.mllm_client import MLLMClient


def _client():
    return MLLMClient(read_saved_raw_outputs=True)


def _targets():
    return [{"target_id": "0", "description": "the target object"}]


def _agent_observations(visible=True):
    visible_viewpoints = []
    if visible:
        visible_viewpoints.append(
            {"viewpoint_index": 2, "distance": 1.0, "xy": [1.0, 0.0]}
        )
    return [
        {
            "agent_id": "agent0",
            "current_viewpoint_index": 1,
            "current_xy": [0.0, 0.0],
            "visible_viewpoints": visible_viewpoints,
        }
    ]


def _new_graph_payload():
    return {
        "current_viewpoints_reassignment": [],
        "visible_region_nodes": [
            {
                "id": 10,
                "label": "bright kitchen area near doorway",
                "exist_prob": 1.0,
                "target_probs": {"0": 0.8},
            }
        ],
        "invisible_region_nodes": [],
        "viewpoint_target_probs": [
            {"id": 2, "target_probs": {"0": 0.4}},
        ],
        "viewpoint_node_assigns": [
            {"region_node_id": 10, "assigned_viewpoint_node_indices": [1, 2]},
        ],
        "new_edges": [],
        "edge_distance_variances": {
            "viewpoint_viewpoint": 1.0,
            "viewpoint_region": 4.0,
        },
    }


def _empty_graph_summary():
    return {"nodes": [], "edges": [], "viewpoint_to_region": {}}


def _prior_graph_summary(region_id=10, grounded=True, visit_times=1):
    return {
        "nodes": [
            {
                "id": 1,
                "type": "viewpoint",
                "grounded": grounded,
                "node_visit_times": visit_times,
            },
            {
                "id": region_id,
                "type": "region",
                "label": "old kitchen area",
                "exist_prob": 1.0,
                "target_probs": {"0": 0.5},
                "assigned_viewpoint_ids": [1],
            },
        ],
        "edges": [],
        "viewpoint_to_region": {"1": region_id},
    }


class _FakeGraph:
    def __init__(self, graph_summary):
        self.graph_summary = graph_summary
        self.target_found = {}

    def get_mllm_summary(self):
        return self.graph_summary


def _repair_and_validate(payload, agent_observations, graph_summary):
    client = _client()
    client._repair_graph_mllm_payload(
        payload=payload,
        agent_observations=agent_observations,
        targets=_targets(),
        graph_summary=graph_summary,
    )
    return client._validate_payload(
        payload=payload,
        agent_observations=agent_observations,
        targets=_targets(),
        graph_summary=graph_summary,
    )


def test_graph_payload_rejects_agents_top_level_key():
    payload = _new_graph_payload()
    payload["agents"] = []

    with pytest.raises(KeyError, match="Unexpected top-level keys"):
        _client()._validate_payload(
            payload=payload,
            agent_observations=_agent_observations(),
            targets=_targets(),
            graph_summary=_empty_graph_summary(),
        )


def test_graph_payload_accepts_new_contract_and_derives_current_region():
    payload = _client()._validate_payload(
        payload=_new_graph_payload(),
        agent_observations=_agent_observations(),
        targets=_targets(),
        graph_summary=_empty_graph_summary(),
    )

    assert set(payload) == {
        "current_viewpoints_reassignment",
        "visible_region_nodes",
        "invisible_region_nodes",
        "viewpoint_target_probs",
        "viewpoint_node_assigns",
        "new_edges",
        "edge_distance_variances",
    }
    assert payload["viewpoint_node_assigns"] == [
        {"region_node_id": 10, "assigned_viewpoint_node_indices": [1, 2]}
    ]


def test_graph_payload_accepts_current_region_reassignment():
    payload = {
        "current_viewpoints_reassignment": [
            {"viewpoint_id": 1, "new_assigned_region_id": 11}
        ],
        "visible_region_nodes": [
            {
                "id": 11,
                "label": "bright living area beside hallway",
                "exist_prob": 1.0,
                "target_probs": {"0": 0.7},
            }
        ],
        "invisible_region_nodes": [],
        "viewpoint_target_probs": [],
        "viewpoint_node_assigns": [],
        "new_edges": [],
        "edge_distance_variances": {
            "viewpoint_viewpoint": 1.0,
            "viewpoint_region": 4.0,
        },
    }

    normalized = _client()._validate_payload(
        payload=payload,
        agent_observations=_agent_observations(visible=False),
        targets=_targets(),
        graph_summary=_prior_graph_summary(),
    )

    assert normalized["current_viewpoints_reassignment"] == [
        {"viewpoint_id": 1, "new_assigned_region_id": 11}
    ]


def test_graph_payload_rejects_conflicting_assignment_and_reassignment():
    payload = {
        "current_viewpoints_reassignment": [
            {"viewpoint_id": 1, "new_assigned_region_id": 12}
        ],
        "visible_region_nodes": [
            {
                "id": 11,
                "label": "bright living area beside hallway",
                "exist_prob": 1.0,
                "target_probs": {"0": 0.7},
            },
            {
                "id": 12,
                "label": "narrow hallway beside living area",
                "exist_prob": 1.0,
                "target_probs": {"0": 0.3},
            },
        ],
        "invisible_region_nodes": [],
        "viewpoint_target_probs": [],
        "viewpoint_node_assigns": [
            {"region_node_id": 11, "assigned_viewpoint_node_indices": [1]},
        ],
        "new_edges": [],
        "edge_distance_variances": {
            "viewpoint_viewpoint": 1.0,
            "viewpoint_region": 4.0,
        },
    }

    with pytest.raises(ValueError, match="viewpoint_node_assigns assigns region"):
        _client()._validate_payload(
            payload=payload,
            agent_observations=_agent_observations(visible=False),
            targets=_targets(),
            graph_summary=_prior_graph_summary(grounded=False, visit_times=0),
        )


def test_graph_payload_repair_materializes_existing_graph_region():
    graph_summary = _prior_graph_summary()
    graph_summary["nodes"].append(
        {
            "id": 11,
            "type": "region",
            "label": "bright living area beside hallway",
            "exist_prob": 1.0,
            "target_probs": {"0": 0.7},
            "assigned_viewpoint_ids": [],
        }
    )

    payload = {
        "current_viewpoints_reassignment": [
            {"viewpoint_id": 1, "new_assigned_region_id": 11}
        ],
        "visible_region_nodes": [],
        "invisible_region_nodes": [],
        "viewpoint_target_probs": [],
        "viewpoint_node_assigns": [],
        "new_edges": [],
        "edge_distance_variances": {
            "viewpoint_viewpoint": 1.0,
            "viewpoint_region": 4.0,
        },
    }

    normalized = _repair_and_validate(
        payload=payload,
        agent_observations=_agent_observations(visible=False),
        graph_summary=graph_summary,
    )

    assert normalized["visible_region_nodes"] == [
        {
            "id": 11,
            "label": "bright living area beside hallway",
            "exist_prob": 1.0,
            "target_probs": {"0": 0.7},
        }
    ]


def test_graph_payload_repair_derives_missing_current_reassignment():
    payload = {
        "current_viewpoints_reassignment": [],
        "visible_region_nodes": [
            {
                "id": 11,
                "label": "bright living area beside hallway",
                "exist_prob": 1.0,
                "target_probs": {"0": 0.7},
            }
        ],
        "invisible_region_nodes": [],
        "viewpoint_target_probs": [],
        "viewpoint_node_assigns": [
            {"region_node_id": 11, "assigned_viewpoint_node_indices": [1]},
        ],
        "new_edges": [],
        "edge_distance_variances": {
            "viewpoint_viewpoint": 1.0,
            "viewpoint_region": 4.0,
        },
    }

    normalized = _repair_and_validate(
        payload=payload,
        agent_observations=_agent_observations(visible=False),
        graph_summary=_prior_graph_summary(),
    )

    assert normalized["current_viewpoints_reassignment"] == [
        {"viewpoint_id": 1, "new_assigned_region_id": 11}
    ]
    assert normalized["viewpoint_node_assigns"] == []


def test_graph_payload_repair_removes_noop_current_reassignment():
    payload = {
        "current_viewpoints_reassignment": [
            {"viewpoint_id": 1, "new_assigned_region_id": 10}
        ],
        "visible_region_nodes": [
            {
                "id": 10,
                "label": "old kitchen area",
                "exist_prob": 1.0,
                "target_probs": {"0": 0.5},
            }
        ],
        "invisible_region_nodes": [],
        "viewpoint_target_probs": [],
        "viewpoint_node_assigns": [],
        "new_edges": [],
        "edge_distance_variances": {
            "viewpoint_viewpoint": 1.0,
            "viewpoint_region": 4.0,
        },
    }

    normalized = _repair_and_validate(
        payload=payload,
        agent_observations=_agent_observations(visible=False),
        graph_summary=_prior_graph_summary(),
    )

    assert normalized["current_viewpoints_reassignment"] == []


def test_graph_payload_repair_drops_invalid_optional_vz_edge():
    payload = _new_graph_payload()
    payload["new_edges"] = [
        {
            "i": 2,
            "j": 10,
            "edge_type": "VZ",
            "exist_prob": 0.8,
            "dist": 2.0,
        }
    ]

    normalized = _repair_and_validate(
        payload=payload,
        agent_observations=_agent_observations(),
        graph_summary=_empty_graph_summary(),
    )

    assert normalized["new_edges"] == []


def test_graph_payload_repair_preserves_unknown_new_region_failure():
    payload = _new_graph_payload()
    payload["visible_region_nodes"] = []
    payload["viewpoint_node_assigns"] = [
        {"region_node_id": 11, "assigned_viewpoint_node_indices": [1, 2]},
    ]

    client = _client()
    client._repair_graph_mllm_payload(
        payload=payload,
        agent_observations=_agent_observations(),
        targets=_targets(),
        graph_summary=_empty_graph_summary(),
    )

    with pytest.raises(ValueError, match="unknown region_node_id 11"):
        client._validate_payload(
            payload=payload,
            agent_observations=_agent_observations(),
            targets=_targets(),
            graph_summary=_empty_graph_summary(),
        )


def test_graph_payload_repair_preserves_missing_target_probs_failure():
    payload = _new_graph_payload()
    payload["viewpoint_target_probs"] = []

    client = _client()
    client._repair_graph_mllm_payload(
        payload=payload,
        agent_observations=_agent_observations(),
        targets=_targets(),
        graph_summary=_empty_graph_summary(),
    )

    with pytest.raises(ValueError, match="Missing required newly observed"):
        client._validate_payload(
            payload=payload,
            agent_observations=_agent_observations(),
            targets=_targets(),
            graph_summary=_empty_graph_summary(),
        )


def test_saved_semantic_replay_uses_incremental_graph_contract(tmp_path):
    client = MLLMClient(
        read_saved_raw_outputs=True,
        raw_output_dir=str(tmp_path / "raw"),
        raw_debug_dir=str(tmp_path / "debug"),
        max_validation_retries=0,
    )

    def fail_request_completion(*args, **kwargs):
        raise AssertionError("Saved replay must not request MLLM completion.")

    client._request_completion = fail_request_completion
    client._write_detection_raw_output(1, json.dumps({"detections": []}))

    saved_payload = {
        "current_viewpoints_reassignment": [],
        "visible_region_nodes": [
            {
                "id": 10,
                "label": "old kitchen area",
                "exist_prob": 1.0,
                "target_probs": {"0": 0.5},
            }
        ],
        "invisible_region_nodes": [],
        "viewpoint_target_probs": [
            {"id": 2, "target_probs": {"0": 0.4}},
        ],
        "viewpoint_node_assigns": [
            {"region_node_id": 10, "assigned_viewpoint_node_indices": [2]},
        ],
        "new_edges": [],
        "edge_distance_variances": {
            "viewpoint_viewpoint": 1.0,
            "viewpoint_region": 4.0,
        },
    }
    client._write_semantic_raw_output(1, json.dumps(saved_payload))

    agent_observations = _agent_observations()
    agent_observations[0]["annotated_panorama"] = np.zeros((4, 4, 3), dtype=np.uint8)

    replayed_payload = client.propose_semantic_nodes(
        agent_observations=agent_observations,
        targets=_targets(),
        graph=_FakeGraph(_prior_graph_summary()),
        scorer=None,
    )

    assert replayed_payload["viewpoint_node_assigns"] == [
        {"region_node_id": 10, "assigned_viewpoint_node_indices": [2]}
    ]
    assert client.semantic_raw_output_index == 2


class _FakeCompletions:
    def __init__(self, completion):
        self.completion = completion
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.completion, list):
            result = self.completion.pop(0)
            if isinstance(result, Exception):
                raise result
            return result
        if isinstance(self.completion, Exception):
            raise self.completion
        return self.completion


class _FakeClient:
    def __init__(self, completion):
        self.completions = _FakeCompletions(completion)
        self.chat = SimpleNamespace(completions=self.completions)


def _completion(tool_calls):
    return SimpleNamespace(
        usage=None,
        model="fake-model",
        choices=[
            SimpleNamespace(
                finish_reason="tool_calls",
                message=SimpleNamespace(tool_calls=tool_calls, content=None),
            )
        ],
    )


def _graph_completion(payload):
    return SimpleNamespace(
        usage=None,
        model="fake-model",
        choices=[
            SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(content=json.dumps(payload)),
            )
        ],
    )


def _timeout_error():
    try:
        return APITimeoutError(request=None)
    except TypeError:
        return APITimeoutError("Request timed out.")


def _tool_call(name="report_target_detections", arguments=None):
    if arguments is None:
        arguments = json.dumps(
            {
                "detections": [
                    {
                        "agent_id": "agent0",
                        "found_target_indices": ["0"],
                        "target_center_xs": [0.52],
                    }
                ]
            }
        )
    return SimpleNamespace(
        type="function",
        function=SimpleNamespace(name=name, arguments=arguments),
    )


def _valid_incremental_graph_payload():
    payload = _new_graph_payload()
    payload["viewpoint_node_assigns"] = [
        {"region_node_id": 10, "assigned_viewpoint_node_indices": [2]}
    ]
    return payload


def test_graph_request_retries_once_after_timeout(tmp_path):
    client = MLLMClient(
        read_saved_raw_outputs=True,
        raw_output_dir=str(tmp_path / "raw"),
        raw_debug_dir=str(tmp_path / "debug"),
        max_validation_retries=0,
        max_request_timeout_retries=1,
    )
    client._write_detection_raw_output(1, json.dumps({"detections": []}))
    client.graph_client = _FakeClient(
        [_timeout_error(), _graph_completion(_valid_incremental_graph_payload())]
    )

    agent_observations = _agent_observations()
    agent_observations[0]["annotated_panorama"] = np.zeros((4, 4, 3), dtype=np.uint8)

    payload = client.propose_semantic_nodes(
        agent_observations=agent_observations,
        targets=_targets(),
        graph=_FakeGraph(_prior_graph_summary()),
        scorer=None,
    )

    calls = client.graph_client.completions.calls
    assert len(calls) == 2
    assert calls[0] == calls[1]
    assert payload["viewpoint_node_assigns"] == [
        {"region_node_id": 10, "assigned_viewpoint_node_indices": [2]}
    ]


def test_graph_request_timeout_propagates_after_retry_limit(tmp_path):
    client = MLLMClient(
        read_saved_raw_outputs=True,
        raw_output_dir=str(tmp_path / "raw"),
        raw_debug_dir=str(tmp_path / "debug"),
        max_validation_retries=0,
        max_request_timeout_retries=1,
    )
    client._write_detection_raw_output(1, json.dumps({"detections": []}))
    client.graph_client = _FakeClient([_timeout_error(), _timeout_error()])

    agent_observations = _agent_observations()
    agent_observations[0]["annotated_panorama"] = np.zeros((4, 4, 3), dtype=np.uint8)

    with pytest.raises(APITimeoutError):
        client.propose_semantic_nodes(
            agent_observations=agent_observations,
            targets=_targets(),
            graph=_FakeGraph(_prior_graph_summary()),
            scorer=None,
        )

    assert len(client.graph_client.completions.calls) == 2


def test_detection_request_uses_forced_strict_tool_call():
    client = _client()
    client.detection_client = _FakeClient(_completion([_tool_call()]))

    arguments = client._request_completion(
        messages=[{"role": "user", "content": "detect"}],
        model_name="fake-model",
        request_type="detection",
    )
    payload = client._parse_json_strict(arguments)
    detections = client._validate_detection_payload(
        payload=payload,
        agent_observations=_agent_observations(visible=False),
        targets=_targets(),
    )

    call = client.detection_client.completions.calls[0]
    assert "response_format" not in call
    assert call["parallel_tool_calls"] is False
    assert call["tool_choice"] == {
        "type": "function",
        "function": {"name": "report_target_detections"},
    }
    assert call["tools"][0]["function"]["strict"] is True
    assert detections == [
        {
            "agent_id": "agent0",
            "found_target_indices": ["0"],
            "target_center_xs": [0.52],
        }
    ]


def test_detection_tool_call_rejects_missing_wrong_or_multiple_calls():
    with pytest.raises(ValueError, match="did not call"):
        MLLMClient._extract_detection_tool_arguments(_completion([]))

    with pytest.raises(ValueError, match="unexpected function"):
        MLLMClient._extract_detection_tool_arguments(
            _completion([_tool_call(name="wrong_function")])
        )

    with pytest.raises(ValueError, match="exactly once"):
        MLLMClient._extract_detection_tool_arguments(
            _completion([_tool_call(), _tool_call()])
        )


def test_detection_tool_call_malformed_arguments_fail_strict_json_parse():
    client = _client()
    client.detection_client = _FakeClient(
        _completion([_tool_call(arguments='{"detections": ]}')])
    )

    arguments = client._request_completion(
        messages=[{"role": "user", "content": "detect"}],
        model_name="fake-model",
        request_type="detection",
    )

    with pytest.raises(ValueError, match="not valid JSON"):
        client._parse_json_strict(arguments)
