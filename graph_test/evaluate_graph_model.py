from __future__ import annotations

import argparse
import copy
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Dict, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GRAPH_TEST_ROOT = Path(__file__).resolve().parent
GRAPH_TEST_OUTPUT_PREFIX = GRAPH_TEST_ROOT.relative_to(PROJECT_ROOT)
sys.path.insert(0, str(PROJECT_ROOT))

from main import (  # noqa: E402
    _batch_case_generation_hash,
    _batch_case_summary_path,
    _batch_summary_with_output_roots,
    _batch_visibility_hash,
    _debug_output_root_name,
    _expected_batch_case_specs,
    _raw_output_root_name,
    _read_json,
    is_batch_config,
    run_batch_config,
    write_batch_case_summary,
)


DEFAULT_GRAPH_TEST_CASE_ID = "zsNo4HB9uLZ_case_0024"
GRAPH_TEST_MAX_STEPS = 10
API_TYPE_ALIASES = {
    "chat": "chat_completions",
    "chat_completion": "chat_completions",
    "chat_completions": "chat_completions",
    "responses": "openai_responses",
    "openai_response": "openai_responses",
    "openai_responses": "openai_responses",
    "gemini": "google_genai",
    "google": "google_genai",
    "google_genai": "google_genai",
}
REASONING_EFFORTS = {"none", "minimal", "low", "medium", "high", "xhigh"}
SERVICE_TIERS = {"auto", "flex", "priority"}
THINKING_FORMATS = {
    "thinking": "thinking_type",
    "thinking_type": "thinking_type",
    "dashscope": "enable_thinking",
    "dashscope_enable_thinking": "enable_thinking",
    "enable_thinking": "enable_thinking",
}

FIXED_DETECTION_CONFIG = {
    "detection_model_name": "Qwen/Qwen3-VL-30B-A3B-Thinking:novita",
    "detection_api_type": "chat_completions",
    "detection_base_url": "https://router.huggingface.co/v1",
    "detection_api_key_env": "HF_TOKEN",
}


def _run_id_for_graph_model(
    graph_model_name: str,
    graph_reasoning_effort: str | None = None,
    graph_thinking_format: str | None = None,
    graph_reasoning_split: bool = False,
    max_steps: int = GRAPH_TEST_MAX_STEPS,
) -> str:
    model_slug = re.sub(r"[^A-Za-z0-9._-]+", "_", str(graph_model_name).strip())
    model_slug = re.sub(r"_+", "_", model_slug).strip("._-")
    if not model_slug:
        model_slug = "unknown_model"
    run_id = "graph_eval_%s" % model_slug
    if graph_reasoning_effort is not None:
        effort_slug = re.sub(
            r"[^A-Za-z0-9._-]+",
            "_",
            str(graph_reasoning_effort).strip().lower(),
        )
        effort_slug = re.sub(r"_+", "_", effort_slug).strip("._-")
        if effort_slug:
            run_id = "%s_reasoning-%s" % (run_id, effort_slug)
    if graph_thinking_format is not None:
        normalized_format = _normalize_thinking_format(
            graph_thinking_format,
            "graph_thinking_format",
        )
        if normalized_format != "thinking_type":
            run_id = "%s_thinking-%s" % (run_id, normalized_format)
    if graph_reasoning_split:
        run_id = "%s_reasoning-split" % run_id
    if int(max_steps) != GRAPH_TEST_MAX_STEPS:
        run_id = "%s_max-steps-%d" % (run_id, int(max_steps))
    return run_id


def _read_batch_config(path: Path) -> Dict[str, object]:
    config = _read_json(path)
    if not isinstance(config, dict):
        raise TypeError("Batch config must be a JSON object.")
    if not is_batch_config(config):
        raise ValueError("%s is not a batch config." % str(path))
    return config


def _provider_defaults(api_type: str) -> tuple[str, str]:
    normalized = _normalize_api_type(api_type, "graph_api_type")
    if normalized == "google_genai":
        return "", "GEMINI_API_KEY"
    if normalized == "openai_responses":
        return "", "OPENAI_API_KEY"
    return "https://router.huggingface.co/v1", "HF_TOKEN"


def _normalize_api_type(value: object, field_name: str) -> str:
    normalized = str(value or "chat_completions").strip().lower()
    if normalized not in API_TYPE_ALIASES:
        raise ValueError(
            "%s must be exactly one of %s."
            % (field_name, ", ".join(sorted(set(API_TYPE_ALIASES.values()))))
        )
    return API_TYPE_ALIASES[normalized]


def _normalize_reasoning_effort(value: object, field_name: str) -> str:
    normalized = str(value).strip().lower()
    if normalized not in REASONING_EFFORTS:
        raise ValueError(
            "%s must be exactly one of %s."
            % (field_name, ", ".join(sorted(REASONING_EFFORTS)))
        )
    return normalized


def _normalize_service_tier(value: object, field_name: str) -> str:
    normalized = str(value).strip().lower()
    if normalized not in SERVICE_TIERS:
        raise ValueError(
            "%s must be exactly one of %s."
            % (field_name, ", ".join(sorted(SERVICE_TIERS)))
        )
    return normalized


def _normalize_thinking_format(value: object, field_name: str) -> str:
    normalized = str(value or "thinking_type").strip().lower()
    if normalized not in THINKING_FORMATS:
        raise ValueError(
            "%s must be exactly one of %s."
            % (field_name, ", ".join(sorted(set(THINKING_FORMATS.values()))))
        )
    return THINKING_FORMATS[normalized]


def build_graph_benchmark_batch_config(
    batch_config: Dict[str, object],
    *,
    max_steps: int = GRAPH_TEST_MAX_STEPS,
    detection_model_name: str | None = None,
    detection_api_type: str | None = None,
    detection_base_url: str | None = None,
    detection_api_key_env: str | None = None,
    detection_reasoning_effort: str | None = None,
    detection_service_tier: str | None = None,
    graph_model_name: str,
    graph_api_type: str,
    graph_base_url: str | None = None,
    graph_api_key_env: str | None = None,
    graph_reasoning_effort: str | None = None,
    graph_service_tier: str | None = None,
    graph_thinking_format: str | None = None,
    graph_reasoning_split: bool = False,
) -> Dict[str, object]:
    benchmark_config = copy.deepcopy(batch_config)
    normalized_max_steps = int(max_steps)
    if normalized_max_steps <= 0:
        raise ValueError("max_steps must be positive.")
    benchmark_config["max_steps"] = normalized_max_steps

    normalized_graph_api_type = _normalize_api_type(
        graph_api_type,
        "graph_api_type",
    )
    default_base_url, default_api_key_env = _provider_defaults(
        normalized_graph_api_type
    )
    mllm = dict(benchmark_config.get("mllm", {}))

    detection_config = dict(FIXED_DETECTION_CONFIG)
    if detection_model_name is not None:
        detection_config["detection_model_name"] = str(detection_model_name)
    normalized_detection_api_type = (
        _normalize_api_type(detection_api_type, "detection_api_type")
        if detection_api_type is not None
        else str(detection_config["detection_api_type"])
    )
    detection_default_base_url, detection_default_api_key_env = _provider_defaults(
        normalized_detection_api_type
    )
    detection_config["detection_api_type"] = normalized_detection_api_type
    if detection_base_url is not None:
        detection_config["detection_base_url"] = str(detection_base_url)
    elif detection_api_type is not None:
        detection_config["detection_base_url"] = detection_default_base_url
    if detection_api_key_env is not None:
        detection_config["detection_api_key_env"] = str(detection_api_key_env)
    elif detection_api_type is not None:
        detection_config["detection_api_key_env"] = detection_default_api_key_env
    mllm.update(detection_config)
    mllm["read_saved_raw_outputs"] = False
    mllm["graph_model_name"] = str(graph_model_name)
    mllm["graph_api_type"] = normalized_graph_api_type
    mllm["graph_base_url"] = (
        default_base_url if graph_base_url is None else str(graph_base_url)
    )
    mllm["graph_api_key_env"] = (
        default_api_key_env if graph_api_key_env is None else str(graph_api_key_env)
    )
    if graph_reasoning_effort is None:
        mllm.pop("graph_reasoning_effort", None)
    else:
        mllm["graph_reasoning_effort"] = _normalize_reasoning_effort(
            graph_reasoning_effort,
            "graph_reasoning_effort",
        )
    if graph_thinking_format is None:
        mllm.pop("graph_thinking_format", None)
    else:
        mllm["graph_thinking_format"] = _normalize_thinking_format(
            graph_thinking_format,
            "graph_thinking_format",
        )
    if graph_reasoning_split:
        mllm["graph_reasoning_split"] = True
    else:
        mllm.pop("graph_reasoning_split", None)

    if normalized_detection_api_type == "openai_responses":
        if detection_reasoning_effort is None:
            mllm.pop("detection_reasoning_effort", None)
        else:
            mllm["detection_reasoning_effort"] = _normalize_reasoning_effort(
                detection_reasoning_effort,
                "detection_reasoning_effort",
            )
        if detection_service_tier is None:
            mllm.pop("detection_service_tier", None)
        else:
            mllm["detection_service_tier"] = _normalize_service_tier(
                detection_service_tier,
                "detection_service_tier",
            )
    else:
        mllm.pop("detection_reasoning_effort", None)
        mllm.pop("detection_service_tier", None)

    if normalized_graph_api_type != "openai_responses":
        mllm.pop("graph_service_tier", None)
    elif graph_service_tier is not None:
        mllm["graph_service_tier"] = _normalize_service_tier(
            graph_service_tier,
            "graph_service_tier",
        )
    else:
        mllm["graph_service_tier"] = "auto"
    benchmark_config["mllm"] = mllm
    return benchmark_config


def validate_selected_case(
    batch_config: Dict[str, object],
    case_id: str,
) -> Dict[str, object]:
    _case_order, case_specs = _expected_batch_case_specs(batch_config)
    if str(case_id) not in case_specs:
        raise KeyError("Batch case %s is not present in generated cases." % case_id)
    case_spec = case_specs[str(case_id)]
    if int(case_spec["agent_number"]) != 3:
        raise ValueError(
            "Graph benchmark case %s must have exactly 3 agents; got %s."
            % (case_id, int(case_spec["agent_number"]))
        )
    return case_spec


def graph_benchmark_summary_from_source(
    source_summary: Dict[str, object],
    batch_config: Dict[str, object],
    run_id: str,
    max_steps: int = GRAPH_TEST_MAX_STEPS,
) -> Dict[str, object]:
    summary = copy.deepcopy(source_summary)
    for case in summary["cases"].values():
        case["max_steps"] = int(max_steps)

    case_generation_hash = _batch_case_generation_hash(batch_config)
    summary["batch_config_hash"] = case_generation_hash
    summary["batch_case_generation_hash"] = case_generation_hash
    summary["batch_visibility_hash"] = _batch_visibility_hash(batch_config)

    adjusted = _batch_summary_with_output_roots(summary, run_id=run_id)
    for case in adjusted["cases"].values():
        case["raw_output_dir"] = (
            GRAPH_TEST_OUTPUT_PREFIX / str(case["raw_output_dir"])
        ).as_posix()
        case["debug_output_dir"] = (
            GRAPH_TEST_OUTPUT_PREFIX / str(case["debug_output_dir"])
        ).as_posix()
    return adjusted


def write_graph_benchmark_case_summary(
    batch_config: Dict[str, object],
    batch_id: str,
    run_id: str,
    max_steps: int = GRAPH_TEST_MAX_STEPS,
) -> Path:
    source_summary_path = _batch_case_summary_path(
        batch_id=batch_id,
        project_root=PROJECT_ROOT,
        run_id=None,
    )
    source_summary = _read_json(source_summary_path)
    if not isinstance(source_summary, dict):
        raise TypeError("Generated batch case summary must be a JSON object.")
    summary = graph_benchmark_summary_from_source(
        source_summary=source_summary,
        batch_config=batch_config,
        run_id=run_id,
        max_steps=max_steps,
    )
    return write_batch_case_summary(
        batch_id=batch_id,
        summary=summary,
        project_root=GRAPH_TEST_ROOT,
        run_id=run_id,
    )


def _ensure_fresh_run_id(run_id: str) -> None:
    debug_root = GRAPH_TEST_ROOT / _debug_output_root_name(run_id)
    raw_root = GRAPH_TEST_ROOT / _raw_output_root_name(run_id)
    existing = [str(path) for path in (debug_root, raw_root) if path.exists()]
    if existing:
        raise FileExistsError(
            "Graph benchmark run id %s is not fresh; existing output path(s): %s"
            % (str(run_id), ", ".join(existing))
        )


def _write_temp_batch_config(batch_config: Dict[str, object], temp_dir: Path) -> Path:
    path = temp_dir / "batch_test.json"
    with open(path, "w", encoding="utf-8") as file_handle:
        json.dump(batch_config, file_handle, indent=2)
        file_handle.write("\n")
    return path


def run_graph_benchmark(args: argparse.Namespace) -> Dict[str, object]:
    max_steps = int(args.max_steps)
    run_id = (
        str(args.run_id)
        if args.run_id
        else _run_id_for_graph_model(
            graph_model_name=str(args.graph_model_name),
            graph_reasoning_effort=args.graph_reasoning_effort,
            graph_thinking_format=args.graph_thinking_format,
            graph_reasoning_split=bool(args.graph_reasoning_split),
            max_steps=max_steps,
        )
    )
    _ensure_fresh_run_id(run_id)

    batch_config_path = Path(args.batch_config)
    batch_config = _read_batch_config(batch_config_path)
    benchmark_config = build_graph_benchmark_batch_config(
        batch_config,
        max_steps=max_steps,
        detection_model_name=args.detection_model_name,
        detection_api_type=args.detection_api_type,
        detection_base_url=args.detection_base_url,
        detection_api_key_env=args.detection_api_key_env,
        detection_reasoning_effort=args.detection_reasoning_effort,
        detection_service_tier=args.detection_service_tier,
        graph_model_name=str(args.graph_model_name),
        graph_api_type=str(args.graph_api_type),
        graph_base_url=args.graph_base_url,
        graph_api_key_env=args.graph_api_key_env,
        graph_reasoning_effort=args.graph_reasoning_effort,
        graph_service_tier=args.graph_service_tier,
        graph_thinking_format=args.graph_thinking_format,
        graph_reasoning_split=bool(args.graph_reasoning_split),
    )
    validate_selected_case(benchmark_config, str(args.case_id))
    write_graph_benchmark_case_summary(
        batch_config=benchmark_config,
        batch_id="batch_test",
        run_id=run_id,
        max_steps=max_steps,
    )

    with tempfile.TemporaryDirectory(prefix="graph_benchmark_") as temp_dir_raw:
        temp_config_path = _write_temp_batch_config(
            benchmark_config,
            Path(temp_dir_raw),
        )
        return run_batch_config(
            temp_config_path,
            show_agent_views=not bool(args.hide_agent_views),
            run_id=run_id,
            batch_case_id=str(args.case_id),
            project_root=GRAPH_TEST_ROOT,
        )


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run one fixed-case graph-model benchmark."
    )
    parser.add_argument("--batch-config", required=True)
    parser.add_argument(
        "--run-id",
        help=(
            "Optional output suffix. Defaults to graph_eval_<graph model name> "
            "with path-unsafe characters replaced by underscores."
        ),
    )
    parser.add_argument(
        "--case-id",
        default=DEFAULT_GRAPH_TEST_CASE_ID,
        help="Generated batch case id. Must have exactly 3 agents.",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=GRAPH_TEST_MAX_STEPS,
        help="Route horizon for this graph benchmark run.",
    )
    parser.add_argument("--detection-model-name")
    parser.add_argument("--detection-api-type")
    parser.add_argument("--detection-base-url")
    parser.add_argument("--detection-api-key-env")
    parser.add_argument("--detection-reasoning-effort")
    parser.add_argument("--detection-service-tier")
    parser.add_argument("--graph-model-name", required=True)
    parser.add_argument("--graph-api-type", required=True)
    parser.add_argument("--graph-base-url")
    parser.add_argument("--graph-api-key-env")
    parser.add_argument("--graph-reasoning-effort")
    parser.add_argument("--graph-service-tier")
    parser.add_argument(
        "--graph-thinking-format",
        help=(
            "Chat-completions graph thinking encoding. Use enable_thinking for "
            "DashScope Qwen APIs that expect extra_body.enable_thinking."
        ),
    )
    parser.add_argument(
        "--graph-reasoning-split",
        action="store_true",
        help="Set chat-completions extra_body.reasoning_split to true.",
    )
    parser.add_argument(
        "--hide-agent-views",
        action="store_true",
        help="Hide interactive agent observation and rotation windows.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    result = run_graph_benchmark(args)
    if result.get("status") == "terminated":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
