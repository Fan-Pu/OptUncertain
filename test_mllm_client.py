import copy
import base64
import io
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from semantic_persistence.mllm_client import (
    DETECTION_IMAGE_MAX_WIDTH,
    GraphValidationError,
    MLLMClient,
)
from semantic_persistence.hypothesis_graph import HypothesisGraph


TARGETS = [
    {"target_id": "2", "description": "small blue chair beside the bed"},
    {"target_id": "3", "description": "white fist-print skateboard above the bed"},
]


def _client():
    return MLLMClient(read_saved_raw_outputs=True)


def _agent_observations():
    return [
        {
            "agent_id": "agent0",
            "current_viewpoint_index": 38,
            "current_xy": [0.0, 0.0],
            "visible_viewpoints": [
                {
                    "viewpoint_index": 11,
                    "distance": 2.042,
                    "xy": [1.0, 0.0],
                }
            ],
        },
        {
            "agent_id": "agent1",
            "current_viewpoint_index": 37,
            "current_xy": [2.0, 0.0],
            "visible_viewpoints": [],
        },
    ]


def _image_agent_observations():
    raw_panorama = np.zeros((20, 100, 3), dtype=np.uint8)
    raw_panorama[:, :] = [200, 10, 20]
    annotated_panorama = np.zeros((20, 100, 3), dtype=np.uint8)
    annotated_panorama[:, :] = [10, 20, 200]
    return [
        {
            "agent_id": "agent0",
            "current_viewpoint_index": 38,
            "current_xy": [0.0, 0.0],
            "horizon_headings": [0.0],
            "raw_panorama": raw_panorama,
            "annotated_panorama": annotated_panorama,
            "visible_viewpoints": [],
        }
    ]


def _large_image_agent_observations():
    raw_panorama = np.zeros((1200, 3264, 3), dtype=np.uint8)
    raw_panorama[:, :] = [200, 10, 20]
    annotated_panorama = np.zeros((1200, 3264, 3), dtype=np.uint8)
    annotated_panorama[:, :] = [10, 20, 200]
    return [
        {
            "agent_id": "agent0",
            "current_viewpoint_index": 38,
            "current_xy": [0.0, 0.0],
            "horizon_headings": [0.0],
            "raw_panorama": raw_panorama,
            "annotated_panorama": annotated_panorama,
            "visible_viewpoints": [],
        }
    ]


def _decode_image_url(image_url):
    data_url = image_url["url"]
    encoded = data_url.split(",", 1)[1]
    return np.array(Image.open(io.BytesIO(base64.b64decode(encoded))).convert("RGB"))


def test_completion_usage_formatter_reports_cached_tokens_without_estimated_cost():
    usage = SimpleNamespace(
        completion_tokens=6,
        prompt_tokens=1875,
        total_tokens=1881,
        completion_tokens_details=None,
        prompt_tokens_details=SimpleNamespace(cached_tokens=1024),
        estimated_cost=0.00024602999999999995,
    )

    formatted = MLLMClient._format_completion_usage(usage)

    assert "estimated_cost" not in formatted
    assert formatted == (
        "CompletionUsage(completion_tokens=6, prompt_tokens=1875, "
        "total_tokens=1881, completion_tokens_details=None, "
        "prompt_tokens_details=namespace(cached_tokens=1024), "
        "cached_tokens=1024)"
    )


def test_completion_usage_formatter_defaults_cached_tokens_to_zero():
    usage = SimpleNamespace(
        completion_tokens=6,
        prompt_tokens=1875,
        total_tokens=1881,
        completion_tokens_details=None,
        prompt_tokens_details=None,
        estimated_cost=0.00024602999999999995,
    )

    formatted = MLLMClient._format_completion_usage(usage)

    assert "estimated_cost" not in formatted
    assert formatted.endswith("cached_tokens=0)")


def _graph_summary():
    return {
        "nodes": [
            {
                "id": 37,
                "type": "viewpoint",
                "grounded": False,
                "node_visit_times": 0,
                "raw_target_probs": {"2": 0.05, "3": 0.05},
            },
            {
                "id": 38,
                "type": "viewpoint",
                "grounded": False,
                "node_visit_times": 0,
                "raw_target_probs": {"2": 0.1, "3": 0.1},
            },
            {
                "id": 52,
                "type": "region",
                "label": "staircase area with concrete wall",
                "assigned_viewpoint_ids": [38],
                "raw_target_probs": {"2": 0.1, "3": 0.1},
            },
            {
                "id": 55,
                "type": "region",
                "label": "outdoor dining area with red chairs",
                "assigned_viewpoint_ids": [37],
                "raw_target_probs": {"2": 0.05, "3": 0.05},
            },
            {
                "id": 56,
                "type": "region",
                "label": "indoor hallway area near staircase",
                "assigned_viewpoint_ids": [],
                "raw_target_probs": {"2": 0.2, "3": 0.2},
            },
        ],
        "edges": [],
        "viewpoint_to_region": {"37": 55, "38": 52},
    }


def _valid_payload():
    return {
        "current_viewpoints_reassignment": [],
        "visible_region_nodes": [],
        "invisible_region_nodes": [],
        "viewpoint_target_scores": [
            {
                "id": 11,
                "target_scores": {
                    "2": {
                        "raw_score": 0.7,
                        "evidence_strength": "medium",
                        "basis": "marker is near the staircase leading to upstairs rooms",
                    },
                    "3": {
                        "raw_score": 0.7,
                        "evidence_strength": "medium",
                        "basis": "marker is near the staircase leading to upstairs rooms",
                    },
                },
            }
        ],
        "region_target_scores": [],
        "viewpoint_node_assigns": [
            {
                "region_node_id": 52,
                "assigned_viewpoint_node_indices": [11],
            }
        ],
        "new_edges": [],
        "edge_distance_variances": {
            "viewpoint_viewpoint": 1.0,
            "viewpoint_region": 4.0,
        },
    }


def _validate(payload):
    return _client()._validate_payload(
        payload=copy.deepcopy(payload),
        agent_observations=_agent_observations(),
        targets=TARGETS,
        graph_summary=_graph_summary(),
        semantic_payload_contract="graph_mllm",
    )


def test_current_viewpoints_with_prior_regions_are_not_required_assignments():
    contract_sets = MLLMClient._graph_mllm_contract_sets(
        agent_observations=_agent_observations(),
        graph_summary=_graph_summary(),
    )

    assert contract_sets["assignment_required_viewpoint_ids"] == {11}

    validated = _validate(_valid_payload())

    assert validated["current_viewpoints_reassignment"] == []
    assert validated["viewpoint_node_assigns"] == [
        {
            "region_node_id": 52,
            "assigned_viewpoint_node_indices": [11],
        }
    ]


def test_region_target_scores_rejects_final_assigned_region():
    payload = _valid_payload()
    payload["region_target_scores"] = [
        {"id": 52, "target_scores": {"2": 0.2, "3": 0.2}}
    ]

    with pytest.raises(GraphValidationError) as exc_info:
        _validate(payload)

    message = str(exc_info.value)
    assert exc_info.value.category == "region target scores"
    assert "Invalid region_target_scores contract" in message
    assert "remove region_target_scores for regions with final assigned viewpoints [52]" in message


def test_region_target_scores_required_when_prior_assigned_region_becomes_unassigned():
    payload = _valid_payload()
    payload["current_viewpoints_reassignment"] = [
        {"viewpoint_id": 38, "new_assigned_region_id": 56}
    ]
    payload["viewpoint_node_assigns"] = [
        {
            "region_node_id": 56,
            "assigned_viewpoint_node_indices": [11],
        }
    ]

    with pytest.raises(GraphValidationError) as exc_info:
        _validate(payload)

    message = str(exc_info.value)
    assert exc_info.value.category == "region target scores"
    assert "Invalid region_target_scores contract" in message
    assert (
        "add complete region_target_scores for prior assigned regions that became "
        "unassigned {52: ['2', '3']}"
    ) in message


def test_top_level_schema_feedback_includes_required_keys():
    payload = _valid_payload()
    del payload["new_edges"]

    with pytest.raises(GraphValidationError) as exc_info:
        _validate(payload)

    error = exc_info.value
    assert error.category == "top-level schema"
    assert "new_edges" in error.details["required_top_level_keys"]
    assert "Return exactly the required graph JSON top-level keys." in error.retry_guidance


def test_region_node_feedback_reports_region_namespace():
    payload = _valid_payload()
    payload["visible_region_nodes"] = [
        {
            "id": 52,
            "label": "nearby hallway area",
            "exist_prob": 1.0,
            "target_probs": {"2": 0.2, "3": 0.2},
        }
    ]

    with pytest.raises(GraphValidationError) as exc_info:
        _validate(payload)

    error = exc_info.value
    assert error.category == "region nodes"
    assert 52 in error.details["graph_region_ids"]
    assert "New region node ids must be unique" in error.retry_guidance[0]


def test_graph_prompt_includes_target_location_cue_scoring_rules():
    system_message, user_message = _client()._build_instruction(
        agent_observations=_agent_observations(),
        targets=TARGETS,
        graph_summary=_graph_summary(),
    )
    prompt_text = system_message + "\n" + user_message

    assert "floor or level cues" in prompt_text
    assert "contradicts an explicit target floor or room cue" in prompt_text
    assert "target-bearing candidates" in prompt_text
    assert "weak normalized filler locations" in prompt_text


def test_detection_prompt_includes_multi_elevation_panorama_rules():
    system_message, user_message = _client()._build_detection_instruction(
        agent_observations=_agent_observations(),
        targets=TARGETS,
    )
    prompt_text = system_message + "\n" + user_message

    assert "smooth multi-elevation 360-degree view" in prompt_text
    assert "vertical axis is camera pitch/elevation" in prompt_text
    assert "Ignore the target's vertical pitch position" in prompt_text


def test_detection_prompt_includes_single_raw_panorama_rules():
    detection_image_records = [
        {
            "agent_id": "agent0",
            "current_viewpoint_index": 38,
            "image_index": 0,
            "image_role": "full_raw_panorama",
            "x_range": [0.0, 1.0],
        }
    ]

    system_message, user_message = _client()._build_detection_instruction(
        agent_observations=_agent_observations(),
        targets=TARGETS,
        detection_image_records=detection_image_records,
    )
    prompt_text = system_message + "\n" + user_message

    assert "exactly one clean unannotated" in prompt_text
    assert "full_raw_panorama" in prompt_text
    assert "x_range" in prompt_text


def test_detection_prompt_allows_small_context_confirmed_targets():
    system_message, user_message = _client()._build_detection_instruction(
        agent_observations=_agent_observations(),
        targets=TARGETS,
    )
    prompt_text = system_message + "\n" + user_message

    assert "strongest visual match" in prompt_text
    assert "support-object and relative-location cues" in prompt_text
    assert "small bust on a wooden cabinet near a patio window" in prompt_text
    assert "could reasonably be a different object" not in prompt_text
    assert "prefer false negative" not in prompt_text


def test_detection_image_content_uses_raw_panorama_not_annotated(tmp_path):
    client = MLLMClient(
        read_saved_raw_outputs=True,
        raw_debug_dir=str(tmp_path),
    )
    content, records = client._build_detection_image_content(
        agent_observations=_image_agent_observations(),
        step_index=1,
    )

    full_image = _decode_image_url(content[1]["image_url"])

    assert len(records) == 1
    assert len(content) == 2
    assert records[0]["image_role"] == "full_raw_panorama"
    assert full_image[:, :, 0].mean() > 180
    assert full_image[:, :, 2].mean() < 60
    assert (
        tmp_path / "detection_input_step_0001_agent_agent0_full_raw_panorama.jpg"
    ).exists()


def test_detection_image_content_sends_one_image_per_agent(tmp_path):
    client = MLLMClient(
        read_saved_raw_outputs=True,
        raw_debug_dir=str(tmp_path),
    )
    observations = _image_agent_observations() + [
        {
            **_image_agent_observations()[0],
            "agent_id": "agent1",
            "current_viewpoint_index": 37,
        }
    ]
    content, records = client._build_detection_image_content(
        agent_observations=observations,
        step_index=1,
    )

    assert len(records) == len(observations)
    assert len(content) == 2 * len(observations)
    assert [record["agent_id"] for record in records] == ["agent0", "agent1"]
    assert all(record["image_role"] == "full_raw_panorama" for record in records)
    assert all(record["x_range"] == [0.0, 1.0] for record in records)


def test_detection_uses_raw_and_graph_uses_annotated_panorama(tmp_path):
    client = MLLMClient(
        read_saved_raw_outputs=True,
        raw_debug_dir=str(tmp_path),
    )
    detection_content, records = client._build_detection_image_content(
        agent_observations=_image_agent_observations(),
        step_index=1,
    )
    graph_content = client._build_graph_image_content(
        agent_observations=_image_agent_observations(),
        step_index=1,
    )

    assert len(records) == 1
    assert records[0]["image_role"] == "full_raw_panorama"
    detection_image = _decode_image_url(detection_content[1]["image_url"])
    graph_image = _decode_image_url(graph_content[1]["image_url"])
    assert detection_image[:, :, 0].mean() > 180
    assert graph_image[:, :, 2].mean() > 180
    assert (
        detection_content[1]["image_url"]["url"]
        != graph_content[1]["image_url"]["url"]
    )


def test_detection_images_are_resized_to_request_budget(tmp_path):
    client = MLLMClient(
        read_saved_raw_outputs=True,
        raw_debug_dir=str(tmp_path),
    )
    content, records = client._build_detection_image_content(
        agent_observations=_large_image_agent_observations(),
        step_index=1,
    )
    decoded_images = [
        _decode_image_url(content[item_index]["image_url"])
        for item_index in range(1, len(content), 2)
    ]

    for decoded_image in decoded_images:
        assert decoded_image.shape[1] <= DETECTION_IMAGE_MAX_WIDTH

    assert len(records) == 1
    assert len(decoded_images) == 1
    assert decoded_images[0].shape[1] == DETECTION_IMAGE_MAX_WIDTH
    assert (
        abs(decoded_images[0].shape[1] / decoded_images[0].shape[0] - 3264 / 1200.0)
        < 0.02
    )


def test_graph_prompt_includes_multi_elevation_panorama_rules():
    system_message, user_message = _client()._build_instruction(
        agent_observations=_agent_observations(),
        targets=TARGETS,
        graph_summary=_graph_summary(),
    )
    prompt_text = system_message + "\n" + user_message

    assert "Vertical position is camera pitch/elevation evidence" in prompt_text
    assert "not a different physical location" in prompt_text
    assert "upper and lower pitch/elevation evidence" in prompt_text


def test_graph_prompt_warns_target_scores_are_not_route_utility():
    system_message, user_message = _client()._build_instruction(
        agent_observations=_agent_observations(),
        targets=TARGETS,
        graph_summary=_graph_summary(),
    )
    prompt_text = system_message + "\n" + user_message

    assert "not route utility" in prompt_text
    assert "Do not give high target raw_score to stairs, landings" in prompt_text
    assert "unassigned target-bearing regions or unvisited candidate viewpoints" in prompt_text


def test_detection_fixed_viewpoint_raw_and_normalized_probs_zeroed():
    graph = HypothesisGraph(targets=TARGETS)
    graph.add_or_update_node(
        node_id=38,
        label="visited stair viewpoint",
        node_type=1,
        exist_prob=1.0,
        grounded=True,
        target_probs={"2": 0.7, "3": 0.7},
        raw_target_probs={"2": 9.0, "3": 9.0},
        node_visit_times=2,
    )
    graph.add_or_update_node(
        node_id=11,
        label="unvisited upstairs candidate",
        node_type=1,
        exist_prob=1.0,
        grounded=False,
        target_probs={"2": 0.3, "3": 0.3},
        raw_target_probs={"2": 1.0, "3": 1.0},
        node_visit_times=0,
    )

    graph._apply_mllm_viewpoint_target_probabilities(
        viewpoint_initial_probs={11: {"2": 1.0, "3": 1.0}},
        current_viewpoint_ids={38},
    )

    assert graph.nodes[38].target_probs["2"] == 0.0
    assert graph.nodes[38].target_probs["3"] == 0.0
    assert graph.nodes[38].raw_target_probs["2"] == 0.0
    assert graph.nodes[38].raw_target_probs["3"] == 0.0


def test_viewpoint_target_score_feedback_reports_detection_fixed_ids():
    payload = _valid_payload()
    payload["viewpoint_target_scores"][0]["id"] = 38

    with pytest.raises(GraphValidationError) as exc_info:
        _validate(payload)

    error = exc_info.value
    assert error.category == "viewpoint target scores"
    assert 38 in error.details["detection_fixed_viewpoint_ids"]
    assert 11 in error.details["required_mllm_viewpoint_target_ids"]


def test_zero_sum_viewpoint_target_feedback_includes_scores_and_basis():
    payload = _valid_payload()
    payload["viewpoint_target_scores"][0]["target_scores"]["2"]["raw_score"] = 0.0
    payload["viewpoint_target_scores"][0]["target_scores"]["2"][
        "evidence_strength"
    ] = "high"
    payload["viewpoint_target_scores"][0]["target_scores"]["2"][
        "basis"
    ] = "no bed is visible from this marker"

    with pytest.raises(GraphValidationError) as exc_info:
        _validate(payload)

    error = exc_info.value
    assert error.category == "viewpoint target scores"
    assert error.details["zero_sum_target_id"] == "2"
    assert error.details["zero_sum_target_description"] == (
        "small blue chair beside the bed"
    )
    assert error.details["raw_scores_by_viewpoint"]["11"]["raw_score"] == 0.0
    assert (
        error.details["raw_scores_by_viewpoint"]["11"]["basis"]
        == "no bed is visible from this marker"
    )
    assert any("positive raw_score" in item for item in error.retry_guidance)


def test_assignment_feedback_reports_expected_and_returned_ids():
    payload = _valid_payload()
    payload["viewpoint_node_assigns"] = []

    with pytest.raises(GraphValidationError) as exc_info:
        _validate(payload)

    error = exc_info.value
    assert error.category == "assignments"
    assert error.details["expected_assignment_viewpoint_ids"] == [11]
    assert error.details["returned_assignment_viewpoint_ids"] == []
    assert error.details["missing_assignment_viewpoint_ids"] == [11]


def test_edge_feedback_reports_current_step_context():
    payload = _valid_payload()
    payload["new_edges"] = [
        {
            "i": 38,
            "j": 11,
            "edge_type": "VV",
            "exist_prob": 0.8,
            "dist": 2.0,
        }
    ]

    with pytest.raises(GraphValidationError) as exc_info:
        _validate(payload)

    error = exc_info.value
    assert error.category == "edges"
    assert 38 in error.details["current_viewpoint_ids"]
    assert 11 in error.details["visible_viewpoint_ids"]
    assert any("Drop illegal optional new_edges" in item for item in error.retry_guidance)


def test_numeric_key_type_feedback_preserves_original_message():
    error = _client()._graph_validation_error_from_exception(
        exc=ValueError("some.path must contain exactly ['a'], got ['b']."),
        payload=_valid_payload(),
        agent_observations=_agent_observations(),
        targets=TARGETS,
        graph_summary=_graph_summary(),
        semantic_payload_contract="graph_mllm",
    )

    assert error.category == "numeric/key/type"
    assert "some.path must contain exactly" in str(error)
    assert "Fix the exact JSON path named in the error." in error.retry_guidance


def test_retry_feedback_groups_and_deduplicates_structured_errors():
    error = GraphValidationError(
        category="assignments",
        message="Returned assigned viewpoint ids [] do not match expected ids [11].",
        details={
            "expected_assignment_viewpoint_ids": [11],
            "returned_assignment_viewpoint_ids": [],
        },
        retry_guidance=[
            "Make viewpoint_node_assigns contain exactly the expected assignment viewpoint ids."
        ],
    )

    retry_message = MLLMClient._build_validation_retry_user_message(
        user_message="BASE PROMPT",
        validation_errors=[error, error],
        attempt_index=1,
        max_validation_retries=2,
    )

    assert retry_message.startswith("BASE PROMPT")
    assert retry_message.count("Returned assigned viewpoint ids []") == 1
    assert "[assignments]" in retry_message
    assert "expected_assignment_viewpoint_ids" in retry_message
    assert (
        "Make viewpoint_node_assigns contain exactly the expected assignment viewpoint ids."
        in retry_message
    )
