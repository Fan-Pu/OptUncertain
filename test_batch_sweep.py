import json
from pathlib import Path

import pytest

import run_batch_sweep as sweep


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as file_handle:
        json.dump(payload, file_handle, indent=2)
        file_handle.write("\n")


def _default_config(graph_models=None):
    return {
        "mllm": {
            "detection_model_name": "gpt-5.4-2026-03-05",
            "detection_api_type": "openai_responses",
            "detection_base_url": "",
            "detection_api_key_env": "OPENAI_API_KEY",
            "detection_reasoning_effort": "medium",
            "detection_service_tier": "flex",
            "graph_model_name": "old-graph",
            "graph_api_type": "chat_completions",
            "graph_base_url": "old-base",
            "graph_api_key_env": "OLD_KEY",
            "graph_reasoning_effort": "low",
            "graph_service_tier": "flex",
            "request_timeout": 900,
            "read_saved_raw_outputs": True,
        },
        "bayes": {},
        "optimizer": {},
        "batch_sweep": {
            "sample_count": 100,
            "sample_seed": 0,
            "sample_balance": "param_config",
            "hide_agent_views": True,
            "run_id_prefix": "balanced100",
            "selected_graph_model_label": "GPT54Medium",
            "graph_models": graph_models
            or [
                {
                    "label": "MiniMaxM3",
                    "graph_model_name": "MiniMaxAI/MiniMax-M3:together",
                    "graph_api_type": "chat_completions",
                    "graph_base_url": "https://router.huggingface.co/v1",
                    "graph_api_key_env": "HF_TOKEN",
                },
                {
                    "label": "GPT54Medium",
                    "graph_model_name": "gpt-5.4-2026-03-05",
                    "graph_api_type": "openai_responses",
                    "graph_api_key_env": "OPENAI_API_KEY",
                    "graph_reasoning_effort": "medium",
                }
            ],
        },
    }


def _batch_config():
    return {
        "max_steps": 40,
        "agent_num_selections": [{"agent_number": 1, "case_number": 1}],
        "target_num_selections": [{"target_number": 1, "case_number": 1}],
        "mllm": {
            "detection_model_name": "batch-override-detection",
            "graph_model_name": "batch-override-graph",
        },
        "scans": [
            {
                "scan_id": "scan_a",
                "targets": [
                    {
                        "target_id": "0",
                        "description": "target zero",
                        "detectable_viewpoint_ids": ["vp0"],
                    }
                ],
            }
        ],
    }


def test_graph_model_list_is_read_from_default_config():
    models = sweep._graph_models(
        _default_config(
            [
                {
                    "label": "MiniMaxM3",
                    "graph_model_name": "MiniMaxAI/MiniMax-M3:together",
                    "graph_api_type": "chat_completions",
                },
                {
                    "label": "GPT54Medium",
                    "graph_model_name": "gpt-5.4-2026-03-05",
                    "graph_api_type": "openai_responses",
                    "graph_api_key_env": "OPENAI_API_KEY",
                    "graph_reasoning_effort": "medium",
                },
            ]
        )
    )

    assert [model["label"] for model in models] == ["MiniMaxM3", "GPT54Medium"]


def test_selected_graph_model_is_read_from_default_config():
    model = sweep.selected_graph_model(_default_config())

    assert model["label"] == "GPT54Medium"
    assert model["graph_model_name"] == "gpt-5.4-2026-03-05"


def test_duplicate_graph_model_labels_fail_directly():
    config = _default_config(
        [
            {
                "label": "MiniMaxM3",
                "graph_model_name": "model-a",
                "graph_api_type": "chat_completions",
            },
            {
                "label": "MiniMaxM3",
                "graph_model_name": "model-b",
                "graph_api_type": "chat_completions",
            },
        ]
    )

    with pytest.raises(ValueError, match="Duplicate graph model label"):
        sweep._graph_models(config)


def test_sweep_batch_config_locks_detection_and_varies_only_graph_fields():
    default_config = _default_config()
    minimax = {
        "label": "MiniMaxM3",
        "graph_model_name": "MiniMaxAI/MiniMax-M3:together",
        "graph_api_type": "chat_completions",
        "graph_base_url": "https://router.huggingface.co/v1",
        "graph_api_key_env": "HF_TOKEN",
    }
    gpt = {
        "label": "GPT54Medium",
        "graph_model_name": "gpt-5.4-2026-03-05",
        "graph_api_type": "openai_responses",
        "graph_api_key_env": "OPENAI_API_KEY",
        "graph_reasoning_effort": "medium",
    }

    minimax_config = sweep.build_sweep_batch_config(
        _batch_config(),
        default_config,
        minimax,
    )
    gpt_config = sweep.build_sweep_batch_config(
        _batch_config(),
        default_config,
        gpt,
    )

    for config in (minimax_config, gpt_config):
        assert config["mllm"]["detection_model_name"] == "gpt-5.4-2026-03-05"
        assert config["mllm"]["detection_api_type"] == "openai_responses"
        assert config["mllm"]["detection_reasoning_effort"] == "medium"
        assert config["mllm"]["detection_service_tier"] == "flex"

    assert minimax_config["mllm"]["graph_model_name"] == minimax["graph_model_name"]
    assert minimax_config["mllm"]["graph_api_key_env"] == "HF_TOKEN"
    assert gpt_config["mllm"]["graph_model_name"] == gpt["graph_model_name"]
    assert gpt_config["mllm"]["graph_api_key_env"] == "OPENAI_API_KEY"
    assert gpt_config["mllm"]["graph_reasoning_effort"] == "medium"
    assert gpt_config["mllm"]["graph_service_tier"] is None


def test_run_batch_sweep_uses_balanced_100_sample_and_distinct_run_ids(
    tmp_path,
    monkeypatch,
):
    default_config = _default_config(
        [
            {
                "label": "MiniMaxM3",
                "graph_model_name": "MiniMaxAI/MiniMax-M3:together",
                "graph_api_type": "chat_completions",
            },
            {
                "label": "GPT54Medium",
                "graph_model_name": "gpt-5.4-2026-03-05",
                "graph_api_type": "openai_responses",
                "graph_api_key_env": "OPENAI_API_KEY",
                "graph_reasoning_effort": "medium",
            },
        ]
    )
    default_config_path = tmp_path / "default_config.json"
    batch_config_path = tmp_path / "batch_test.json"
    _write_json(default_config_path, default_config)
    _write_json(batch_config_path, _batch_config())

    calls = []

    def fake_run_batch_config(
        batch_config_path,
        show_agent_views,
        sample_count,
        sample_seed,
        sample_balance,
        run_id,
    ):
        temp_config = sweep._read_json(batch_config_path)
        calls.append(
            {
                "show_agent_views": show_agent_views,
                "sample_count": sample_count,
                "sample_seed": sample_seed,
                "sample_balance": sample_balance,
                "run_id": run_id,
                "mllm": temp_config["mllm"],
            }
        )
        return {"status": "completed"}

    monkeypatch.setattr(sweep, "run_batch_config", fake_run_batch_config)

    result = sweep.run_batch_sweep(
        batch_config_path=batch_config_path,
        default_config_path=default_config_path,
    )

    assert result["status"] == "completed"
    assert [call["run_id"] for call in calls] == ["balanced100_GPT54Medium"]
    for call in calls:
        assert call["show_agent_views"] is False
        assert call["sample_count"] == 100
        assert call["sample_seed"] == 0
        assert call["sample_balance"] == "param_config"
        assert call["mllm"]["detection_model_name"] == "gpt-5.4-2026-03-05"
        assert call["mllm"]["detection_reasoning_effort"] == "medium"
        assert call["mllm"]["request_timeout"] == 900

    assert calls[0]["mllm"]["graph_model_name"] == "gpt-5.4-2026-03-05"
    assert calls[0]["mllm"]["graph_service_tier"] is None
