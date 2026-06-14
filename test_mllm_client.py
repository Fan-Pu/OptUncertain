import pytest

import Helper
from semantic_persistence.mllm_client import (
    MLLMClient,
    MLLMProviderCreditError,
    MLLMRetryExhaustedError,
)


class _InvalidDetectionClient(MLLMClient):
    def _request_completion(self, **kwargs):
        return (
            '{"detections":[{"agent_id":"agent0","found_target_indices":["0"],'
            '"target_center_xs":[]}]}'
        )


class _InvalidGraphClient(MLLMClient):
    def _request_completion(self, **kwargs):
        return "{}"

    def _resize_panorama_array(self, image):
        return b"jpeg"

    def _write_observation_image(self, step_index, agent_id, image_bytes):
        return None

    def _image_to_data_url(self, image_bytes):
        return "data:image/jpeg;base64,AA=="

    def _detect_targets(self, agent_observations, targets, image_content, step_index):
        return []

    def _build_instruction(self, agent_observations, targets, graph_summary):
        return "system", "user"

    def _repair_graph_mllm_payload(
        self,
        payload,
        agent_observations,
        targets,
        graph_summary,
    ):
        return []

    def _validate_payload(
        self,
        payload,
        agent_observations,
        targets,
        graph_summary,
        scorer=None,
        semantic_payload_contract="graph_mllm",
    ):
        raise ValueError("invalid graph payload")


class _GraphStub:
    target_found = {"0": False}

    def get_mllm_summary(self):
        return {"target_found": {"0": False}}


class _FakeAPIError(Exception):
    def __init__(self, status_code=None, body=None, message="provider error"):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


def test_provider_credit_error_detects_http_402():
    error = MLLMClient._provider_credit_error_from_exception(
        exc=_FakeAPIError(
            status_code=402,
            body={"error": {"code": "payment_required", "message": "pay first"}},
        ),
        stage="graph",
        router="graph",
        model="model",
    )

    assert isinstance(error, MLLMProviderCreditError)
    assert error.status_code == 402
    assert error.provider_code == "payment_required"
    assert error.stage == "graph"
    assert error.router == "graph"
    assert error.model == "model"


def test_provider_credit_error_detects_balance_code_without_402():
    error = MLLMClient._provider_credit_error_from_exception(
        exc=_FakeAPIError(
            status_code=400,
            body={"code": "balance_not_enough", "message": "balance not enough"},
        ),
        stage="detection",
        router="detection",
        model="detector",
    )

    assert isinstance(error, MLLMProviderCreditError)
    assert error.status_code == 400
    assert error.provider_code == "balance_not_enough"


def test_provider_credit_error_ignores_unrelated_provider_error():
    error = MLLMClient._provider_credit_error_from_exception(
        exc=_FakeAPIError(
            status_code=404,
            body={"code": "model_not_found", "message": "model missing"},
        ),
        stage="graph",
        router="graph",
        model="model",
    )

    assert error is None


def test_detection_retry_exhaustion_raises_typed_error_and_writes_attempts(tmp_path):
    client = _InvalidDetectionClient(
        read_saved_raw_outputs=True,
        raw_output_dir=str(tmp_path),
        max_validation_retries=1,
    )

    with pytest.raises(MLLMRetryExhaustedError) as exc_info:
        client._detect_targets(
            agent_observations=[
                {"agent_id": "agent0", "current_viewpoint_index": 1}
            ],
            targets=[{"target_id": "0", "description": "target"}],
            image_content=[],
            step_index=3,
        )

    assert exc_info.value.stage == "detection"
    assert exc_info.value.step_index == 3
    assert exc_info.value.attempts == 2
    assert "same length" in exc_info.value.last_error
    assert (tmp_path / "detection_step_0003_attempt_00_error.txt").exists()
    assert (tmp_path / "detection_step_0003_attempt_01_error.txt").exists()


def test_graph_retry_exhaustion_raises_typed_error_and_writes_attempts(tmp_path):
    client = _InvalidGraphClient(
        read_saved_raw_outputs=True,
        raw_output_dir=str(tmp_path),
        raw_debug_dir=str(tmp_path),
        max_validation_retries=1,
    )

    with pytest.raises(MLLMRetryExhaustedError) as exc_info:
        client.propose_semantic_nodes(
            agent_observations=[
                {
                    "agent_id": "agent0",
                    "current_viewpoint_index": 1,
                    "annotated_panorama": object(),
                }
            ],
            targets=[{"target_id": "0", "description": "target"}],
            graph=_GraphStub(),
            scorer=None,
        )

    assert exc_info.value.stage == "graph"
    assert exc_info.value.step_index == 1
    assert exc_info.value.attempts == 2
    assert "invalid graph payload" in exc_info.value.last_error
    assert (tmp_path / "semantic_step_0001_attempt_00_error.txt").exists()
    assert (tmp_path / "semantic_step_0001_attempt_01_error.txt").exists()


def test_saved_payload_region_probs_use_type1_mean_and_union_normalization(
    monkeypatch,
):
    monkeypatch.setattr(
        Helper,
        "viewpoint_vp_label_by_index",
        {0: "vp0", 1: "vp1", 2: "vp2"},
        raising=False,
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

