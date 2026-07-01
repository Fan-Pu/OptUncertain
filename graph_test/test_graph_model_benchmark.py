import json
from pathlib import Path

import pytest

from graph_test.evaluate_graph_benchmark_metrics import (
    GraphMethodSpec,
    _load_method_case,
)
from graph_test.evaluate_graph_model import (
    DEFAULT_GRAPH_TEST_CASE_ID,
    FIXED_DETECTION_CONFIG,
    GRAPH_TEST_MAX_STEPS,
    _run_id_for_graph_model,
    build_graph_benchmark_batch_config,
    graph_benchmark_summary_from_source,
    validate_selected_case,
)


def _read_json(path: str):
    with open(path, "r", encoding="utf-8") as file_handle:
        return json.load(file_handle)


def _minimal_batch_config():
    return {
        "max_steps": 40,
        "agent_num_selections": [
            {
                "agent_number": 3,
                "case_number": 1,
            }
        ],
        "target_num_selections": [
            {
                "target_number": 1,
                "case_number": 1,
            }
        ],
        "mllm": {
            "detection_model_name": "old-detection",
            "detection_api_type": "openai_responses",
            "detection_base_url": "",
            "detection_api_key_env": "OPENAI_API_KEY",
            "detection_reasoning_effort": "medium",
            "detection_service_tier": "flex",
            "graph_model_name": "old-graph",
            "graph_api_type": "chat_completions",
            "graph_base_url": "old-base",
            "graph_api_key_env": "OLD_KEY",
            "graph_service_tier": "flex",
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


def _case_record(case_id=DEFAULT_GRAPH_TEST_CASE_ID, max_steps=GRAPH_TEST_MAX_STEPS):
    return {
        "test_case": case_id,
        "scan_id": "zsNo4HB9uLZ",
        "agent_number": 3,
        "target_number": 4,
        "max_steps": max_steps,
        "agents": [
            {"id": "agent0", "start_viewpoint_id": "vp0"},
            {"id": "agent1", "start_viewpoint_id": "vp1"},
            {"id": "agent2", "start_viewpoint_id": "vp2"},
        ],
        "targets": [
            {"target_id": "2", "description": "target two"},
            {"target_id": "4", "description": "target four"},
            {"target_id": "5", "description": "target five"},
            {"target_id": "7", "description": "target seven"},
        ],
    }


def _source_summary():
    case = _case_record(max_steps=40)
    return {
        "batch_id": "batch_test",
        "batch_config_hash": "old-hash",
        "batch_case_generation_hash": "old-hash",
        "batch_visibility_hash": "old-visibility-hash",
        "generated_case_count": 1,
        "case_order": [DEFAULT_GRAPH_TEST_CASE_ID],
        "cases": {DEFAULT_GRAPH_TEST_CASE_ID: case},
    }


def _write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as file_handle:
        json.dump(payload, file_handle, indent=2)
        file_handle.write("\n")


def test_selected_case_validation_accepts_default_three_agent_case():
    batch_config = _read_json("scenarios/batch_test.json")

    case_spec = validate_selected_case(batch_config, DEFAULT_GRAPH_TEST_CASE_ID)

    assert case_spec["test_case"] == DEFAULT_GRAPH_TEST_CASE_ID
    assert case_spec["agent_number"] == 3


def test_selected_case_validation_rejects_non_three_agent_case():
    batch_config = _read_json("scenarios/batch_test.json")

    with pytest.raises(ValueError, match="exactly 3 agents"):
        validate_selected_case(batch_config, "r47D5H71a5s_case_0001")


def test_graph_benchmark_config_fixes_max_steps_and_detection_config():
    original = _minimal_batch_config()

    benchmark = build_graph_benchmark_batch_config(
        original,
        graph_model_name="gpt-5.4-2026-03-05",
        graph_api_type="openai_responses",
        graph_api_key_env="OPENAI_API_KEY",
        graph_reasoning_effort="medium",
    )

    assert original["max_steps"] == 40
    assert benchmark["max_steps"] == GRAPH_TEST_MAX_STEPS
    for key, value in FIXED_DETECTION_CONFIG.items():
        assert benchmark["mllm"][key] == value
    assert "detection_reasoning_effort" not in benchmark["mllm"]
    assert "detection_service_tier" not in benchmark["mllm"]
    assert benchmark["mllm"]["read_saved_raw_outputs"] is False
    assert benchmark["mllm"]["graph_model_name"] == "gpt-5.4-2026-03-05"
    assert benchmark["mllm"]["graph_api_type"] == "openai_responses"
    assert benchmark["mllm"]["graph_api_key_env"] == "OPENAI_API_KEY"
    assert benchmark["mllm"]["graph_reasoning_effort"] == "medium"
    assert benchmark["mllm"]["graph_service_tier"] == "auto"


def test_graph_benchmark_config_can_use_openai_detection_and_max_steps_override():
    benchmark = build_graph_benchmark_batch_config(
        _minimal_batch_config(),
        max_steps=25,
        detection_model_name="gpt-5.4-2026-03-05",
        detection_api_type="openai_responses",
        detection_api_key_env="OPENAI_API_KEY",
        detection_reasoning_effort="medium",
        detection_service_tier="flex",
        graph_model_name="gpt-5.4-2026-03-05",
        graph_api_type="openai_responses",
        graph_api_key_env="OPENAI_API_KEY",
        graph_reasoning_effort="medium",
        graph_service_tier="flex",
    )

    assert benchmark["max_steps"] == 25
    assert benchmark["mllm"]["detection_model_name"] == "gpt-5.4-2026-03-05"
    assert benchmark["mllm"]["detection_api_type"] == "openai_responses"
    assert benchmark["mllm"]["detection_api_key_env"] == "OPENAI_API_KEY"
    assert benchmark["mllm"]["detection_reasoning_effort"] == "medium"
    assert benchmark["mllm"]["detection_service_tier"] == "flex"
    assert benchmark["mllm"]["graph_model_name"] == "gpt-5.4-2026-03-05"
    assert benchmark["mllm"]["graph_api_type"] == "openai_responses"
    assert benchmark["mllm"]["graph_reasoning_effort"] == "medium"
    assert benchmark["mllm"]["graph_service_tier"] == "flex"


def test_default_run_id_uses_graph_model_name():
    assert (
        _run_id_for_graph_model("MiniMaxAI/MiniMax-M3:together")
        == "graph_eval_MiniMaxAI_MiniMax-M3_together"
    )


def test_default_run_id_includes_reasoning_effort_when_present():
    assert (
        _run_id_for_graph_model(
            "gpt-5.4-2026-03-05",
            graph_reasoning_effort="medium",
        )
        == "graph_eval_gpt-5.4-2026-03-05_reasoning-medium"
    )


def test_default_run_id_includes_non_default_max_steps():
    assert (
        _run_id_for_graph_model(
            "gpt-5.4-2026-03-05",
            graph_reasoning_effort="medium",
            max_steps=25,
        )
        == "graph_eval_gpt-5.4-2026-03-05_reasoning-medium_max-steps-25"
    )


def test_default_run_id_includes_non_default_thinking_format():
    assert (
        _run_id_for_graph_model(
            "qwen3.5-plus",
            graph_thinking_format="enable_thinking",
        )
        == "graph_eval_qwen3.5-plus_thinking-enable_thinking"
    )


def test_default_run_id_includes_reasoning_split():
    assert (
        _run_id_for_graph_model(
            "MiniMaxAI/MiniMax-M3:together",
            graph_reasoning_split=True,
        )
        == "graph_eval_MiniMaxAI_MiniMax-M3_together_reasoning-split"
    )


def test_graph_benchmark_config_sets_graph_thinking_format():
    benchmark = build_graph_benchmark_batch_config(
        _minimal_batch_config(),
        graph_model_name="qwen3.5-plus",
        graph_api_type="chat_completions",
        graph_base_url="https://dashscope-us.aliyuncs.com/compatible-mode/v1",
        graph_api_key_env="DASHSCOPE_API_KEY",
        graph_thinking_format="enable_thinking",
    )

    assert benchmark["mllm"]["graph_thinking_format"] == "enable_thinking"
    assert benchmark["mllm"]["graph_base_url"] == (
        "https://dashscope-us.aliyuncs.com/compatible-mode/v1"
    )
    assert benchmark["mllm"]["graph_api_key_env"] == "DASHSCOPE_API_KEY"
    assert "graph_service_tier" not in benchmark["mllm"]


def test_graph_benchmark_config_sets_graph_reasoning_split():
    benchmark = build_graph_benchmark_batch_config(
        _minimal_batch_config(),
        graph_model_name="MiniMaxAI/MiniMax-M3:together",
        graph_api_type="chat_completions",
        graph_reasoning_split=True,
    )

    assert benchmark["mllm"]["graph_reasoning_split"] is True


def test_graph_benchmark_summary_sets_run_roots_and_max_steps():
    batch_config = _read_json("scenarios/batch_test.json")

    summary = graph_benchmark_summary_from_source(
        source_summary=_source_summary(),
        batch_config=build_graph_benchmark_batch_config(
            batch_config,
            graph_model_name="MiniMaxAI/MiniMax-M3:together",
            graph_api_type="chat_completions",
        ),
        run_id="graph_eval_MiniMaxAI_MiniMax-M3_together",
    )

    case = summary["cases"][DEFAULT_GRAPH_TEST_CASE_ID]
    assert summary["run_id"] == "graph_eval_MiniMaxAI_MiniMax-M3_together"
    assert case["max_steps"] == GRAPH_TEST_MAX_STEPS
    assert (
        case["raw_output_dir"]
        == "graph_test/mllm_raw_outputs_graph_eval_MiniMaxAI_MiniMax-M3_together/"
        + DEFAULT_GRAPH_TEST_CASE_ID
    )
    assert (
        case["debug_output_dir"]
        == "graph_test/mllm_debug_outputs_graph_eval_MiniMaxAI_MiniMax-M3_together/"
        + DEFAULT_GRAPH_TEST_CASE_ID
    )
    assert summary["batch_case_generation_hash"] != "old-hash"


def test_graph_benchmark_summary_uses_requested_max_steps():
    batch_config = _read_json("scenarios/batch_test.json")

    summary = graph_benchmark_summary_from_source(
        source_summary=_source_summary(),
        batch_config=build_graph_benchmark_batch_config(
            batch_config,
            max_steps=25,
            graph_model_name="gpt-5.4-2026-03-05",
            graph_api_type="openai_responses",
        ),
        run_id="graph_eval_gpt-5.4-2026-03-05_reasoning-medium_max-steps-25",
        max_steps=25,
    )

    assert summary["cases"][DEFAULT_GRAPH_TEST_CASE_ID]["max_steps"] == 25


def test_graph_method_manifest_validates_selected_case_and_max_steps(tmp_path):
    debug_root = tmp_path / "mllm_debug_outputs_graph"
    method = GraphMethodSpec(
        name="GraphModel",
        debug_root=debug_root,
        raw_root=tmp_path / "mllm_raw_outputs_graph",
    )
    case = _case_record()
    _write_json(
        debug_root / "batch_test" / "sampled_generated_cases.json",
        {
            "case_order": [DEFAULT_GRAPH_TEST_CASE_ID],
            "cases": {DEFAULT_GRAPH_TEST_CASE_ID: case},
        },
    )
    _write_json(
        debug_root
        / DEFAULT_GRAPH_TEST_CASE_ID
        / ("%s_mllm_route_summary.txt" % DEFAULT_GRAPH_TEST_CASE_ID),
        {"max_steps": GRAPH_TEST_MAX_STEPS},
    )

    loaded = _load_method_case(
        method,
        "batch_test",
        DEFAULT_GRAPH_TEST_CASE_ID,
        GRAPH_TEST_MAX_STEPS,
    )

    assert loaded == case


def test_graph_method_manifest_rejects_wrong_max_steps(tmp_path):
    debug_root = tmp_path / "mllm_debug_outputs_graph"
    method = GraphMethodSpec(
        name="GraphModel",
        debug_root=debug_root,
        raw_root=tmp_path / "mllm_raw_outputs_graph",
    )
    _write_json(
        debug_root / "batch_test" / "sampled_generated_cases.json",
        {
            "case_order": [DEFAULT_GRAPH_TEST_CASE_ID],
            "cases": {DEFAULT_GRAPH_TEST_CASE_ID: _case_record(max_steps=40)},
        },
    )

    with pytest.raises(ValueError, match="expected 10"):
        _load_method_case(
            method,
            "batch_test",
            DEFAULT_GRAPH_TEST_CASE_ID,
            GRAPH_TEST_MAX_STEPS,
        )
