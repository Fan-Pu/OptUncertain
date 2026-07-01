from types import SimpleNamespace

from evaluate_detection_model import _init_detection_client
from semantic_persistence.mllm_client import (
    DETECTION_MAX_NEW_TOKENS,
    GRAPH_MAX_NEW_TOKENS,
    MLLMClient,
)


class FakePart:
    def __init__(self, kind, text=None, data=None, mime_type=None):
        self.kind = kind
        self.text = text
        self.data = data
        self.mime_type = mime_type

    @classmethod
    def from_text(cls, text):
        return cls("text", text=text)

    @classmethod
    def from_bytes(cls, data, mime_type):
        return cls("bytes", data=data, mime_type=mime_type)


class FakeContent:
    def __init__(self, role, parts):
        self.role = role
        self.parts = parts


class FakeGenerateContentConfig:
    def __init__(self, **kwargs):
        self.kwargs = dict(kwargs)
        for key, value in kwargs.items():
            setattr(self, key, value)


class FakeTypes:
    Part = FakePart
    Content = FakeContent
    GenerateContentConfig = FakeGenerateContentConfig


class FakeGenAI:
    calls = []

    class Client:
        def __init__(self, **kwargs):
            FakeGenAI.calls.append(kwargs)


def _fake_google_modules():
    return FakeGenAI, FakeTypes


def _client_without_api():
    return MLLMClient.__new__(MLLMClient)


def test_google_api_type_aliases_normalize():
    assert MLLMClient._normalize_api_type("google_genai", "api_type") == "google_genai"
    assert MLLMClient._normalize_api_type("gemini", "api_type") == "google_genai"
    assert MLLMClient._normalize_api_type("google", "api_type") == "google_genai"


def test_google_client_uses_gemini_api_key(monkeypatch):
    FakeGenAI.calls = []
    monkeypatch.setenv("GEMINI_API_KEY", "test-google-key")
    monkeypatch.setattr(
        MLLMClient,
        "_google_genai_modules",
        staticmethod(_fake_google_modules),
    )

    client = _client_without_api()
    client.read_saved_raw_outputs = False

    created = client._create_api_client(
        api_type="google_genai",
        base_url="",
        api_key_env="GEMINI_API_KEY",
        router_name="detection",
    )

    assert isinstance(created, FakeGenAI.Client)
    assert FakeGenAI.calls == [{"api_key": "test-google-key"}]


def test_detection_benchmark_reads_google_provider_config():
    scenario = {
        "mllm": {
            "graph_model_name": "graph-model",
            "detection_model_name": "gemini-3.5-flash",
            "detection_api_type": "google_genai",
            "read_saved_raw_outputs": True,
            "raw_output_dir": "raw",
            "debug_output_dir": "debug",
        }
    }

    client = _init_detection_client(scenario)

    assert client.detection_model_name == "gemini-3.5-flash"
    assert client.detection_api_type == "google_genai"
    assert client.detection_base_url == ""
    assert client.detection_api_key_env == "GEMINI_API_KEY"


def test_google_request_converts_system_text_and_data_url(monkeypatch):
    monkeypatch.setattr(
        MLLMClient,
        "_google_genai_modules",
        staticmethod(_fake_google_modules),
    )
    client = _client_without_api()
    messages = [
        {"role": "system", "content": "Return JSON only."},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Find targets."},
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/jpeg;base64,YWJj"},
                },
            ],
        },
        {"role": "assistant", "content": "Previous answer."},
    ]

    request_kwargs = client._build_google_genai_request_kwargs(
        messages=messages,
        model_name="gemini-3.5-flash",
        request_type="detection",
    )

    assert request_kwargs["model"] == "gemini-3.5-flash"
    assert request_kwargs["config"].system_instruction == "Return JSON only."
    assert request_kwargs["config"].response_mime_type == "application/json"
    assert request_kwargs["config"].max_output_tokens == DETECTION_MAX_NEW_TOKENS
    assert len(request_kwargs["contents"]) == 2
    assert request_kwargs["contents"][0].role == "user"
    assert request_kwargs["contents"][0].parts[0].kind == "text"
    assert request_kwargs["contents"][0].parts[0].text == "Find targets."
    assert request_kwargs["contents"][0].parts[1].kind == "bytes"
    assert request_kwargs["contents"][0].parts[1].data == b"abc"
    assert request_kwargs["contents"][0].parts[1].mime_type == "image/jpeg"
    assert request_kwargs["contents"][1].role == "model"
    assert request_kwargs["contents"][1].parts[0].text == "Previous answer."


def test_google_graph_request_uses_graph_token_limit(monkeypatch):
    monkeypatch.setattr(
        MLLMClient,
        "_google_genai_modules",
        staticmethod(_fake_google_modules),
    )
    client = _client_without_api()

    request_kwargs = client._build_google_genai_request_kwargs(
        messages=[{"role": "user", "content": "Build graph."}],
        model_name="gemini-3.5-flash",
        request_type="graph",
    )

    assert request_kwargs["config"].max_output_tokens == GRAPH_MAX_NEW_TOKENS


def test_request_completion_uses_google_genai_for_detection(monkeypatch):
    monkeypatch.setattr(
        MLLMClient,
        "_google_genai_modules",
        staticmethod(_fake_google_modules),
    )

    class FakeModels:
        def __init__(self):
            self.calls = []

        def generate_content(self, **kwargs):
            self.calls.append(kwargs)
            return SimpleNamespace(
                text='{"detections":[]}',
                usage_metadata=SimpleNamespace(prompt_token_count=10),
            )

    fake_models = FakeModels()
    client = _client_without_api()
    client.detection_client = SimpleNamespace(models=fake_models)
    client.detection_api_key_env = "GEMINI_API_KEY"
    client.detection_api_type = "google_genai"
    client.detection_reasoning_effort = None

    decoded = client._request_completion(
        messages=[{"role": "user", "content": "Detect."}],
        model_name="gemini-3.5-flash",
        request_type="detection",
    )

    assert decoded == '{"detections":[]}'
    assert len(fake_models.calls) == 1
    assert fake_models.calls[0]["model"] == "gemini-3.5-flash"
    assert fake_models.calls[0]["config"].max_output_tokens == DETECTION_MAX_NEW_TOKENS
