from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys
from typing import Dict, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from main import _read_json, run_scenario
from run_batch_sweep import build_sweep_batch_config, selected_graph_model


DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "default_config.json"
DEFAULT_BATCH_CONFIG_PATH = PROJECT_ROOT / "scenarios" / "batch_test.json"
DEFAULT_CASE_ID = "RPmz2sHmrrY_case_0030"
DEFAULT_GRAPH_MODEL_LABEL = "Qwen36_35BA3BThinking"
DEFAULT_PROMPT_VARIANT_PATH = (
    PROJECT_ROOT / "prompts" / "graph_relaxed_newly_observed_edges.json"
)
RUN_LABEL = "QwenThinkingRelaxedNewEdges"


def build_relaxed_edge_scenario(
    *,
    case_id: str,
    default_config: Dict[str, object],
    batch_config: Dict[str, object],
    prompt_variant_path: str | Path,
    run_label: str = RUN_LABEL,
) -> Dict[str, object]:
    sample_path = PROJECT_ROOT / str(
        default_config["benchmark"]["sample_manifest"]
    )
    sample = _read_json(sample_path)
    if str(sample["batch_case_generation_hash"]) != (
        "ec14c3efdcc190d8a3872e0f22cd89a9481485498a7fa1794610f043dd02a7e5"
    ):
        raise ValueError("The configured sample manifest is not the frozen 100-case sample.")
    if case_id not in sample["cases"]:
        raise KeyError("%s is absent from the frozen sample." % case_id)
    case = sample["cases"][case_id]
    if int(case["agent_number"]) != 3:
        raise ValueError("%s is not a three-agent case." % case_id)

    graph_model = selected_graph_model(
        default_config,
        selected_label=DEFAULT_GRAPH_MODEL_LABEL,
    )
    configured_batch = build_sweep_batch_config(
        batch_config=batch_config,
        default_config=default_config,
        graph_model=graph_model,
    )
    prompt_variant_path = Path(prompt_variant_path).resolve()
    raw_output_dir = (
        Path("mllm_raw_outputs_smoke_%s" % str(run_label)) / case_id
    ).as_posix()
    debug_output_dir = (
        Path("mllm_debug_outputs_smoke_%s" % str(run_label)) / case_id
    ).as_posix()

    scenario = {
        "test_case": str(case_id),
        "scan_id": str(case["scan_id"]),
        "agents": copy.deepcopy(case["agents"]),
        "targets": copy.deepcopy(case["targets"]),
        "max_steps": int(case["max_steps"]),
        "batch_id": str(sample["batch_id"]),
        "mllm": copy.deepcopy(configured_batch["mllm"]),
        "bayes": copy.deepcopy(default_config["bayes"]),
        "optimizer": copy.deepcopy(default_config["optimizer"]),
        "benchmark": {"method": "proposed"},
    }
    scenario["mllm"].update(
        {
            "raw_output_dir": raw_output_dir,
            "debug_output_dir": debug_output_dir,
            "graph_prompt_variant_path": str(prompt_variant_path),
            "read_saved_raw_outputs": False,
            "detection_cache_read": True,
            "detection_cache_write": False,
        }
    )
    return scenario


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run one isolated proposed-method Qwen-Thinking case with the "
            "newly-observed-edge prompt variant."
        )
    )
    parser.add_argument("--case-id", default=DEFAULT_CASE_ID)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument(
        "--batch-config",
        default=str(DEFAULT_BATCH_CONFIG_PATH),
    )
    parser.add_argument(
        "--prompt-variant",
        default=str(DEFAULT_PROMPT_VARIANT_PATH),
    )
    parser.add_argument("--run-label", default=RUN_LABEL)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    default_config = _read_json(args.config)
    batch_config = _read_json(args.batch_config)
    scenario = build_relaxed_edge_scenario(
        case_id=str(args.case_id),
        default_config=default_config,
        batch_config=batch_config,
        prompt_variant_path=args.prompt_variant,
        run_label=str(args.run_label),
    )
    raw_output_dir = PROJECT_ROOT / str(scenario["mllm"]["raw_output_dir"])
    debug_output_dir = PROJECT_ROOT / str(scenario["mllm"]["debug_output_dir"])
    if raw_output_dir.exists() or debug_output_dir.exists():
        raise FileExistsError(
            "Relaxed-edge smoke outputs already exist; refusing to overwrite "
            "or repeat paid calls."
        )
    debug_output_dir.mkdir(parents=True)
    run_config_path = debug_output_dir / "relaxed_edge_run_config.json"
    run_config_path.write_text(
        json.dumps(scenario, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    prompt_variant = _read_json(
        scenario["mllm"]["graph_prompt_variant_path"]
    )
    (debug_output_dir / "graph_prompt_variant.json").write_text(
        json.dumps(prompt_variant, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    result = run_scenario(scenario, show_agent_views=False)
    result_path = debug_output_dir / "smoke_result.json"
    result_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print("Saved relaxed-edge smoke result to %s." % result_path)
    return 1 if result.get("status") == "terminated" else 0


if __name__ == "__main__":
    raise SystemExit(main())
