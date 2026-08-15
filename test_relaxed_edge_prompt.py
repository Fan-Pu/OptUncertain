from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.run_relaxed_edge_smoke import build_relaxed_edge_scenario
from semantic_persistence.mllm_client import GraphValidationError, MLLMClient


PROMPT_VARIANT_PATH = Path(
    "prompts/graph_relaxed_newly_observed_edges.json"
).resolve()


def _observations():
    return [
        {
            "current_viewpoint_index": 0,
            "visible_viewpoints": [
                {
                    "viewpoint_index": 1,
                },
                {
                    "viewpoint_index": 2,
                },
                {
                    "viewpoint_index": 3,
                },
            ],
        }
    ]


def _first_step_validation_observations():
    return [
        {
            "agent_id": "agent0",
            "current_viewpoint_index": 0,
            "visible_viewpoints": [
                {
                    "viewpoint_index": 1,
                },
                {
                    "viewpoint_index": 2,
                },
            ],
        }
    ]


def _first_step_materialized_payload():
    return {
        "current_viewpoints_reassignment": [],
        "visible_region_nodes": [{"id": 3, "label": "open living area"}],
        "viewpoint_target_probs": [
            {
                "id": 1,
                "target_probs": {"0": 0.5},
                "raw_target_probs": {"0": 1.0},
            },
            {
                "id": 2,
                "target_probs": {"0": 0.5},
                "raw_target_probs": {"0": 1.0},
            },
        ],
        "viewpoint_target_score_basis": [
            {"id": 1, "score_basis": {"0": "candidate one"}},
            {"id": 2, "score_basis": {"0": "candidate two"}},
        ],
        "viewpoint_node_assigns": [
            {
                "region_node_id": 3,
                "assigned_viewpoint_node_indices": [0, 1, 2],
            }
        ],
        "new_edges": [
            {
                "i": 1,
                "j": 2,
                "edge_type": "VV",
                "exist_prob": 0.7,
                "dist": 1.5,
            }
        ],
        "edge_distance_variances": {"viewpoint_viewpoint": 4.0},
    }


def _empty_first_step_graph_summary():
    return {
        "agent_current_vp_ids": {"agent0": 0},
        "nodes": [],
        "edges": [],
        "viewpoint_to_region": {},
        "target_found": {"0": False},
    }


def test_original_prompt_behavior_remains_default():
    client = MLLMClient()
    status_by_id = {}

    client._augment_edge_endpoint_statuses_from_current_observations(
        graph_viewpoint_status_by_id=status_by_id,
        agent_observations=_observations(),
    )

    assert status_by_id == {}
    assert client.graph_prompt_variant_id == ""
    assert client.graph_prompt_variant_text == ""
    assert client.graph_allow_newly_observed_edge_endpoints is False


def test_relaxed_prompt_exposes_newly_observed_endpoint_status():
    client = MLLMClient(
        graph_prompt_variant_path=str(PROMPT_VARIANT_PATH),
    )
    status_by_id = {}

    client._augment_edge_endpoint_statuses_from_current_observations(
        graph_viewpoint_status_by_id=status_by_id,
        agent_observations=_observations(),
    )

    assert client.graph_prompt_variant_id == (
        "relaxed_newly_observed_edge_endpoints_v1"
    )
    assert client.graph_allow_newly_observed_edge_endpoints is True
    assert status_by_id[1]["prior_grounded"] is False
    assert status_by_id[1]["prior_visit_times"] == 0
    assert status_by_id[2]["prior_grounded"] is False
    assert status_by_id[3]["prior_visit_times"] == 0


def test_first_step_new_edge_is_rejected_by_original_and_accepted_by_variant(
    monkeypatch,
):
    import Helper

    monkeypatch.setattr(
        Helper,
        "viewpoint_vp_label_by_index",
        {0: "vp0", 1: "vp1", 2: "vp2"},
    )
    observations = _first_step_validation_observations()
    targets = [{"target_id": "0", "description": "target zero"}]
    graph_summary = _empty_first_step_graph_summary()

    original_client = MLLMClient()
    with pytest.raises(GraphValidationError, match="prior visit-state"):
        original_client._validate_payload(
            payload=_first_step_materialized_payload(),
            agent_observations=observations,
            targets=targets,
            graph_summary=graph_summary,
            semantic_payload_contract="saved_materialized",
        )

    relaxed_client = MLLMClient(
        graph_prompt_variant_path=str(PROMPT_VARIANT_PATH),
    )
    validated = relaxed_client._validate_payload(
        payload=_first_step_materialized_payload(),
        agent_observations=observations,
        targets=targets,
        graph_summary=graph_summary,
        semantic_payload_contract="saved_materialized",
    )

    assert validated["new_edges"] == [
        {
            "i": 1,
            "j": 2,
            "edge_type": "VV",
            "exist_prob": 0.7,
            "dist": 1.5,
        }
    ]


def test_relaxed_runner_keeps_frozen_case_and_qwen_thinking_parameters():
    default_config = json.loads(
        Path("config/default_config.json").read_text(encoding="utf-8")
    )
    batch_config = json.loads(
        Path("scenarios/batch_test.json").read_text(encoding="utf-8")
    )

    scenario = build_relaxed_edge_scenario(
        case_id="RPmz2sHmrrY_case_0030",
        default_config=default_config,
        batch_config=batch_config,
        prompt_variant_path=PROMPT_VARIANT_PATH,
    )

    assert scenario["benchmark"]["method"] == "proposed"
    assert len(scenario["agents"]) == 3
    assert scenario["max_steps"] == 30
    assert scenario["mllm"]["graph_model_name"] == "Qwen/Qwen3.6-35B-A3B"
    assert scenario["mllm"]["graph_extra_body_enabled"] is False
    assert scenario["mllm"]["graph_presence_penalty_enabled"] is False
    assert scenario["mllm"]["graph_prompt_variant_path"] == str(
        PROMPT_VARIANT_PATH
    )
    assert scenario["mllm"]["read_saved_raw_outputs"] is False
    assert scenario["mllm"]["detection_cache_read"] is True
    assert scenario["mllm"]["detection_cache_write"] is False
    assert scenario["mllm"]["raw_output_dir"].startswith(
        "mllm_raw_outputs_smoke_QwenThinkingRelaxedNewEdges/"
    )
    assert scenario["mllm"]["debug_output_dir"].startswith(
        "mllm_debug_outputs_smoke_QwenThinkingRelaxedNewEdges/"
    )
