from types import SimpleNamespace

from semantic_persistence.mllm_client import MLLMClient


class _FakeResponses:
    def __init__(self):
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            output_text="{}",
            usage=None,
            model=kwargs["model"],
            status="completed",
        )


class _FakeResponsesClient:
    def __init__(self):
        self.responses = _FakeResponses()


def _responses_client(**kwargs):
    return MLLMClient(
        graph_model_name="gpt-5.4-2026-03-05",
        graph_api_type="openai_responses",
        graph_api_key_env="OPENAI_API_KEY",
        read_saved_raw_outputs=True,
        **kwargs,
    )


def test_gpt54_responses_request_does_not_auto_add_flex_service_tier():
    client = _responses_client()
    fake_client = _FakeResponsesClient()
    client.graph_client = fake_client

    client._request_completion(
        [{"role": "user", "content": "Return an empty JSON object."}],
        model_name="gpt-5.4-2026-03-05",
        request_type="graph",
    )

    assert "service_tier" not in fake_client.responses.kwargs


def test_explicit_responses_service_tier_is_still_sent():
    client = _responses_client(graph_service_tier="flex")
    fake_client = _FakeResponsesClient()
    client.graph_client = fake_client

    client._request_completion(
        [{"role": "user", "content": "Return an empty JSON object."}],
        model_name="gpt-5.4-2026-03-05",
        request_type="graph",
    )

    assert fake_client.responses.kwargs["service_tier"] == "flex"


def test_detection_responses_service_tier_flex_is_sent():
    client = _responses_client(
        detection_model_name="gpt-5.4-2026-03-05",
        detection_api_type="openai_responses",
        detection_api_key_env="OPENAI_API_KEY",
        detection_service_tier="flex",
    )
    fake_client = _FakeResponsesClient()
    client.detection_client = fake_client

    client._request_completion(
        [{"role": "user", "content": "Return an empty JSON object."}],
        model_name="gpt-5.4-2026-03-05",
        request_type="detection",
    )

    assert fake_client.responses.kwargs["service_tier"] == "flex"


def test_direct_action_uses_explicit_flex_and_small_output_budget():
    client = _responses_client(
        graph_reasoning_effort="medium",
        graph_service_tier="flex",
    )
    fake_client = _FakeResponsesClient()
    client.graph_client = fake_client

    client.request_action_completion(
        [{"role": "user", "content": "Return one action as JSON."}]
    )

    assert fake_client.responses.kwargs["model"] == "gpt-5.4-2026-03-05"
    assert fake_client.responses.kwargs["max_output_tokens"] == 1024
    assert fake_client.responses.kwargs["reasoning"] == {"effort": "medium"}
    assert fake_client.responses.kwargs["service_tier"] == "flex"
