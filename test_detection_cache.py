from pathlib import Path

from semantic_persistence.detection_cache import (
    DETECTION_PROMPT_VERSION,
    DetectionCache,
    DetectionCacheConflictError,
)
from semantic_persistence.mllm_client import MLLMClient


def _client(tmp_path: Path) -> MLLMClient:
    return MLLMClient(
        graph_model_name="gpt-5.4-2026-03-05",
        detection_model_name="gpt-5.4-2026-03-05",
        graph_api_type="openai_responses",
        detection_api_type="openai_responses",
        graph_api_key_env="OPENAI_API_KEY",
        detection_api_key_env="OPENAI_API_KEY",
        read_saved_raw_outputs=True,
        raw_output_dir=str(tmp_path / "raw"),
        raw_debug_dir=str(tmp_path / "debug"),
        scan_id="scan_a",
        case_id="scan_a_case_0001",
        batch_id="batch_test",
        detection_cache_enabled=True,
        detection_cache_dir=str(tmp_path / "cache"),
    )


def _observation():
    return {
        "agent_id": "agent0",
        "current_viewpoint_id": "vp_a",
        "current_viewpoint_index": 7,
    }


def _record():
    return {
        "agent_id": "agent0",
        "current_viewpoint_id": "vp_a",
        "current_viewpoint_index": 7,
        "image_index": 0,
        "image_role": "full_raw_panorama",
        "x_range": [0.0, 1.0],
        "image_sha256": "image_hash_a",
    }


def _target():
    return {
        "target_id": "0",
        "description": "the small red cup on the table",
    }


def _other_target():
    return {
        "target_id": "1",
        "description": "the blue book on the shelf",
    }


def test_detection_cache_hit_avoids_request_completion(tmp_path):
    cache = DetectionCache(tmp_path / "cache", "batch_test")
    cache.append_step(
        scan_id="scan_a",
        case_id="seed_case",
        step_index=1,
        agent_observations=[_observation()],
        targets=[_target()],
        detection_image_records=[_record()],
        detections=[
            {
                "agent_id": "agent0",
                "found_target_indices": ["0"],
                "target_center_xs": [0.42],
            }
        ],
        detection_model="gpt-5.4-2026-03-05",
        prompt_version=DETECTION_PROMPT_VERSION,
        service_tier=None,
    )

    client = _client(tmp_path)

    def fail_request(*_args, **_kwargs):
        raise AssertionError("cache hit should not request the MLLM")

    client._request_completion = fail_request

    detections = client._detect_targets(
        agent_observations=[_observation()],
        targets=[_target()],
        image_content=[],
        step_index=1,
        detection_image_records=[_record()],
    )

    assert detections == [
        {
            "agent_id": "agent0",
            "found_target_indices": ["0"],
            "target_center_xs": [0.42],
        }
    ]
    assert (tmp_path / "raw" / "detection_step_0001.json").exists()


def test_detection_cache_key_ignores_active_target_set(tmp_path):
    cache = DetectionCache(tmp_path / "cache", "batch_test")
    common = {
        "scan_id": "scan_a",
        "case_id": "seed_case",
        "agent_observations": [_observation()],
        "detection_image_records": [_record()],
        "detection_model": "gpt-5.4-2026-03-05",
        "prompt_version": DETECTION_PROMPT_VERSION,
        "service_tier": None,
    }
    cache.append_step(
        **common,
        step_index=1,
        targets=[_target()],
        detections=[
            {
                "agent_id": "agent0",
                "found_target_indices": ["0"],
                "target_center_xs": [0.42],
            }
        ],
    )
    cache.append_step(
        **common,
        step_index=2,
        targets=[_other_target()],
        detections=[],
    )

    assert cache.lookup_step(
        scan_id="scan_a",
        agent_observations=[_observation()],
        targets=[_target(), _other_target()],
        detection_image_records=[_record()],
        detection_model="gpt-5.4-2026-03-05",
        prompt_version=DETECTION_PROMPT_VERSION,
    ) == [
        {
            "agent_id": "agent0",
            "found_target_indices": ["0"],
            "target_center_xs": [0.42],
        }
    ]


def test_detection_cache_miss_requests_and_writes_negative_entry(tmp_path):
    client = _client(tmp_path)
    calls = []

    def fake_request(*_args, **_kwargs):
        calls.append(1)
        return '{"detections":[]}'

    client._request_completion = fake_request

    detections = client._detect_targets(
        agent_observations=[_observation()],
        targets=[_target()],
        image_content=[],
        step_index=1,
        detection_image_records=[_record()],
    )

    assert detections == []
    assert len(calls) == 1
    assert client.detection_cache.lookup_step(
        scan_id="scan_a",
        agent_observations=[_observation()],
        targets=[_target()],
        detection_image_records=[_record()],
        detection_model="gpt-5.4-2026-03-05",
        prompt_version=DETECTION_PROMPT_VERSION,
    ) == []


def test_detection_cache_retry_success_is_not_cached(tmp_path):
    client = _client(tmp_path)
    calls = []

    def fake_request(*_args, **_kwargs):
        calls.append(1)
        if len(calls) == 1:
            return (
                '{"detections":[{"agent_id":"agent0",'
                '"found_target_indices":["inactive"],'
                '"target_center_xs":[0.5]}]}'
            )
        return '{"detections":[]}'

    client._request_completion = fake_request

    detections = client._detect_targets(
        agent_observations=[_observation()],
        targets=[_target()],
        image_content=[],
        step_index=1,
        detection_image_records=[_record()],
    )

    assert detections == []
    assert len(calls) == 2
    assert (tmp_path / "raw" / "detection_step_0001.json").exists()
    assert (tmp_path / "raw" / "detection_step_0001_attempt_00_error.txt").exists()
    assert client.detection_cache.lookup_step(
        scan_id="scan_a",
        agent_observations=[_observation()],
        targets=[_target()],
        detection_image_records=[_record()],
        detection_model="gpt-5.4-2026-03-05",
        prompt_version=DETECTION_PROMPT_VERSION,
    ) is None


def test_detection_cache_conflicting_duplicate_raises(tmp_path):
    cache = DetectionCache(tmp_path / "cache", "batch_test")
    common = {
        "scan_id": "scan_a",
        "case_id": "seed_case",
        "step_index": 1,
        "agent_observations": [_observation()],
        "targets": [_target()],
        "detection_image_records": [_record()],
        "detection_model": "gpt-5.4-2026-03-05",
        "prompt_version": DETECTION_PROMPT_VERSION,
        "service_tier": None,
    }
    cache.append_step(
        **common,
        detections=[
            {
                "agent_id": "agent0",
                "found_target_indices": ["0"],
                "target_center_xs": [0.42],
            }
        ],
    )

    try:
        cache.append_step(
            **common,
            detections=[
                {
                    "agent_id": "agent0",
                    "found_target_indices": ["0"],
                    "target_center_xs": [0.51],
                }
            ],
        )
    except DetectionCacheConflictError:
        return
    raise AssertionError("conflicting cache entry did not raise")


def test_detection_cache_conflicting_duplicate_quarantines_key(tmp_path):
    cache = DetectionCache(
        tmp_path / "cache",
        "batch_test",
        conflict_policy="quarantine",
    )
    common = {
        "scan_id": "scan_a",
        "case_id": "seed_case",
        "step_index": 1,
        "agent_observations": [_observation()],
        "targets": [_target()],
        "detection_image_records": [_record()],
        "detection_model": "gpt-5.4-2026-03-05",
        "prompt_version": DETECTION_PROMPT_VERSION,
        "service_tier": None,
    }
    assert cache.append_step(
        **common,
        detections=[],
    ) == 1

    assert cache.append_step(
        **{
            **common,
            "case_id": "incoming_case",
            "step_index": 2,
        },
        detections=[
            {
                "agent_id": "agent0",
                "found_target_indices": ["0"],
                "target_center_xs": [0.51],
            }
        ],
    ) == 0

    assert cache.conflict_path.exists()
    assert cache.lookup_step(
        scan_id="scan_a",
        agent_observations=[_observation()],
        targets=[_target()],
        detection_image_records=[_record()],
        detection_model="gpt-5.4-2026-03-05",
        prompt_version=DETECTION_PROMPT_VERSION,
    ) is None
