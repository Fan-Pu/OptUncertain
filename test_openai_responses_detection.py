from types import SimpleNamespace

import semantic_persistence.mllm_client as mllm_client
from evaluate_detection_model import _init_detection_client
from semantic_persistence.mllm_client import DETECTION_MAX_NEW_TOKENS, MLLMClient


def _client_without_api():
    return MLLMClient.__new__(MLLMClient)


def test_blank_base_url_uses_official_openai_client_defaults(monkeypatch):
    calls = []

    class FakeOpenAI:
        def __init__(self, **kwargs):
            calls.append(kwargs)

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(mllm_client, "OpenAI", FakeOpenAI)

    client = _client_without_api()
    client.read_saved_raw_outputs = False
    client.request_timeout = 12.0

    client._create_openai_client(
        base_url="",
        api_key_env="OPENAI_API_KEY",
        router_name="detection",
    )

    assert calls == [{"api_key": "test-key", "timeout": 12.0}]


def test_responses_request_converts_chat_multimodal_content():
    client = _client_without_api()
    messages = [
        {"role": "system", "content": "Return JSON only."},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Find targets."},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "data:image/jpeg;base64,abc",
                    },
                },
            ],
        },
    ]

    request_kwargs = client._build_responses_request_kwargs(
        messages=messages,
        model_name="gpt-5",
        request_type="detection",
    )

    assert request_kwargs["model"] == "gpt-5"
    assert request_kwargs["instructions"] == "Return JSON only."
    assert request_kwargs["max_output_tokens"] == DETECTION_MAX_NEW_TOKENS
    assert request_kwargs["text"] == {"format": {"type": "json_object"}}
    assert request_kwargs["input"] == [
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": "Find targets."},
                {
                    "type": "input_image",
                    "image_url": "data:image/jpeg;base64,abc",
                },
            ],
        }
    ]


def test_request_completion_uses_openai_responses_for_detection():
    class FakeResponses:
        def __init__(self):
            self.calls = []

        def create(self, **kwargs):
            self.calls.append(kwargs)
            return SimpleNamespace(
                output_text='{"detections":[]}',
                usage=SimpleNamespace(input_tokens=10, output_tokens=4),
                model=kwargs["model"],
                status="completed",
            )

    fake_responses = FakeResponses()
    client = _client_without_api()
    client.detection_client = SimpleNamespace(responses=fake_responses)
    client.detection_api_key_env = "OPENAI_API_KEY"
    client.detection_api_type = "openai_responses"
    client.detection_thinking = None

    decoded = client._request_completion(
        messages=[
            {"role": "system", "content": "Return JSON only."},
            {"role": "user", "content": [{"type": "text", "text": "Detect."}]},
        ],
        model_name="gpt-5",
        request_type="detection",
    )

    assert decoded == '{"detections":[]}'
    assert len(fake_responses.calls) == 1
    assert fake_responses.calls[0]["model"] == "gpt-5"
    assert "extra_body" not in fake_responses.calls[0]
    assert "messages" not in fake_responses.calls[0]


def test_detection_benchmark_reads_openai_provider_config():
    scenario = {
        "mllm": {
            "graph_model_name": "graph-model",
            "detection_model_name": "gpt-5",
            "detection_api_type": "openai_responses",
            "detection_base_url": "https://router.huggingface.co/v1",
            "detection_api_key_env": "HF_TOKEN",
            "read_saved_raw_outputs": True,
            "raw_output_dir": "raw",
            "debug_output_dir": "debug",
        }
    }

    client = _init_detection_client(scenario)

    assert client.detection_model_name == "gpt-5"
    assert client.detection_api_type == "openai_responses"
    assert client.detection_base_url == ""
    assert client.detection_api_key_env == "OPENAI_API_KEY"
