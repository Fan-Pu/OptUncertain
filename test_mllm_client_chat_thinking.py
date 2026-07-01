import pytest

from semantic_persistence.mllm_client import MLLMClient


def _client_without_api():
    return object.__new__(MLLMClient)


def test_chat_completion_enable_thinking_format_sets_dashscope_extra_body():
    client = _client_without_api()

    kwargs = client._build_completion_request_kwargs(
        messages=[{"role": "user", "content": "Who are you?"}],
        model_name="qwen3.5-plus",
        request_type="graph",
        thinking_mode="enabled",
        thinking_format="enable_thinking",
    )

    assert kwargs["extra_body"]["enable_thinking"] is True
    assert "thinking" not in kwargs["extra_body"]


def test_chat_completion_enable_thinking_format_can_disable_thinking():
    client = _client_without_api()

    kwargs = client._build_completion_request_kwargs(
        messages=[{"role": "user", "content": "Who are you?"}],
        model_name="qwen3.5-plus",
        request_type="graph",
        thinking_mode="disabled",
        thinking_format="enable_thinking",
    )

    assert kwargs["extra_body"]["enable_thinking"] is False


def test_chat_completion_enable_thinking_format_rejects_adaptive_mode():
    client = _client_without_api()

    with pytest.raises(ValueError, match="cannot use thinking format"):
        client._build_completion_request_kwargs(
            messages=[{"role": "user", "content": "Who are you?"}],
            model_name="qwen3.5-plus",
            request_type="graph",
            thinking_mode="adaptive",
            thinking_format="enable_thinking",
        )


def test_chat_completion_thinking_type_can_enable_reasoning_split():
    client = _client_without_api()

    kwargs = client._build_completion_request_kwargs(
        messages=[{"role": "user", "content": "Who are you?"}],
        model_name="MiniMaxAI/MiniMax-M3:together",
        request_type="graph",
        thinking_mode="enabled",
        thinking_format="thinking_type",
        reasoning_split=True,
    )

    assert kwargs["extra_body"]["thinking"] == {"type": "enabled"}
    assert kwargs["extra_body"]["reasoning_split"] is True
