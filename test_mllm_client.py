import base64

import numpy as np
import pytest

from semantic_persistence.mllm_client import (
    GRAPH_IMAGE_JPEG_QUALITY,
    GRAPH_IMAGE_MAX_WIDTH,
    MLLMClient,
)


def _client_without_api():
    return MLLMClient.__new__(MLLMClient)


def _synthetic_panorama(seed, width=2000, height=720):
    rng = np.random.default_rng(seed)
    return rng.integers(0, 256, size=(height, width, 3), dtype=np.uint8)


def _graph_request_size(client, image_content):
    messages = [
        {"role": "system", "content": "system"},
        {
            "role": "user",
            "content": [{"type": "text", "text": "user"}] + image_content,
        },
    ]
    request_kwargs = client._build_completion_request_kwargs(
        messages=messages,
        model_name="test-model",
        request_type="graph",
        thinking_mode="enabled",
    )
    return client._request_payload_size_bytes(request_kwargs)


def _manual_graph_image_content(images, jpeg_quality):
    image_content = []
    for image_index, image in enumerate(images):
        image_bytes = MLLMClient._resize_panorama_array(
            image,
            max_width=GRAPH_IMAGE_MAX_WIDTH,
            jpeg_quality=jpeg_quality,
        )
        image_content.extend(
            [
                {
                    "type": "text",
                    "text": "Image index %s. Agent agent%s. Current viewpoint %s."
                    % (image_index, image_index, image_index),
                },
                {
                    "type": "image_url",
                    "image_url": {"url": MLLMClient._image_to_data_url(image_bytes)},
                },
            ]
        )
    return image_content


@pytest.mark.parametrize("thinking_mode", ["enabled", "adaptive", "disabled"])
def test_completion_kwargs_send_object_shaped_thinking(thinking_mode):
    client = _client_without_api()

    request_kwargs = client._build_completion_request_kwargs(
        messages=[{"role": "user", "content": "test"}],
        model_name="test-model",
        request_type="graph",
        thinking_mode=thinking_mode,
    )

    assert request_kwargs["extra_body"]["thinking"] == {"type": thinking_mode}


def test_completion_kwargs_omit_thinking_when_absent():
    client = _client_without_api()

    request_kwargs = client._build_completion_request_kwargs(
        messages=[{"role": "user", "content": "test"}],
        model_name="test-model",
        request_type="graph",
        thinking_mode=None,
    )

    assert "thinking" not in request_kwargs["extra_body"]


@pytest.mark.parametrize("empty_value", [None, ""])
def test_empty_thinking_config_normalizes_to_absent(empty_value):
    assert MLLMClient._normalize_thinking_mode(empty_value, "graph_thinking") is None


def test_invalid_thinking_config_raises():
    with pytest.raises(ValueError, match="graph_thinking"):
        MLLMClient._normalize_thinking_mode("auto", "graph_thinking")


def test_detection_and_graph_thinking_are_normalized_separately():
    client = MLLMClient(
        read_saved_raw_outputs=True,
        detection_thinking="disabled",
        graph_thinking="adaptive",
    )

    assert client.detection_thinking == "disabled"
    assert client.graph_thinking == "adaptive"


def test_graph_image_content_uses_graph_jpeg_budget(tmp_path):
    client = _client_without_api()
    client.raw_output_dir = str(tmp_path / "raw")
    client.raw_debug_dir = str(tmp_path / "debug")
    panorama = _synthetic_panorama(seed=0)

    content = client._build_graph_image_content(
        agent_observations=[
            {
                "agent_id": "agent0",
                "current_viewpoint_index": 7,
                "annotated_panorama": panorama,
            }
        ],
        step_index=3,
    )

    encoded_image = content[1]["image_url"]["url"].split(",", 1)[1]
    actual_image_bytes = base64.b64decode(encoded_image)
    expected_image_bytes = MLLMClient._resize_panorama_array(
        panorama,
        max_width=GRAPH_IMAGE_MAX_WIDTH,
        jpeg_quality=GRAPH_IMAGE_JPEG_QUALITY,
    )
    quality_100_image_bytes = MLLMClient._resize_panorama_array(
        panorama,
        max_width=GRAPH_IMAGE_MAX_WIDTH,
        jpeg_quality=100,
    )

    assert actual_image_bytes == expected_image_bytes
    assert len(actual_image_bytes) < len(quality_100_image_bytes)
    assert (
        tmp_path / "debug" / "observation_step_0003_agent_agent0.jpg"
    ).read_bytes() == expected_image_bytes


def test_graph_request_payload_size_reflects_bounded_image_encoding(tmp_path):
    client = _client_without_api()
    client.raw_output_dir = str(tmp_path / "raw")
    client.raw_debug_dir = str(tmp_path / "debug")
    observations = [
        {
            "agent_id": "agent%s" % index,
            "current_viewpoint_index": index,
            "annotated_panorama": _synthetic_panorama(seed=index),
        }
        for index in range(5)
    ]

    bounded_content = client._build_graph_image_content(
        agent_observations=observations,
        step_index=1,
    )
    quality_100_content = _manual_graph_image_content(
        [observation["annotated_panorama"] for observation in observations],
        jpeg_quality=100,
    )

    assert _graph_request_size(client, bounded_content) < _graph_request_size(
        client,
        quality_100_content,
    )
