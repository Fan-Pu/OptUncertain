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
from run_benchmark_sweep import (
    DEFAULT_CONFIG_PATH,
    _configured_batch,
)


def build_smoke_scenario(
    *,
    method: str,
    case_id: str,
    max_steps: int,
    beta: float,
    default_config: Dict[str, object],
    batch_config: Dict[str, object],
) -> Dict[str, object]:
    sample_path = PROJECT_ROOT / str(
        default_config["benchmark"]["sample_manifest"]
    )
    sample = _read_json(sample_path)
    if case_id not in sample["cases"]:
        raise KeyError("Smoke case %s is absent from the exact test sample." % case_id)
    case = sample["cases"][case_id]
    configured = _configured_batch(
        method=method,
        batch_config=batch_config,
        default_config=default_config,
        beta=float(beta) if method == "vlfm_g" else None,
    )
    if method == "vlfm_g":
        label = "VLFMG"
    elif method == "dec_graph":
        label = "DecGraph"
    else:
        label = "MLLMDirect_GPT54Medium"
    scenario = {
        "test_case": str(case_id),
        "scan_id": str(case["scan_id"]),
        "agents": copy.deepcopy(case["agents"]),
        "targets": copy.deepcopy(case["targets"]),
        "max_steps": int(max_steps),
        "batch_id": str(sample["batch_id"]),
        "mllm": copy.deepcopy(configured["mllm"]),
        "bayes": copy.deepcopy(default_config["bayes"]),
        "optimizer": copy.deepcopy(default_config["optimizer"]),
        "benchmark": copy.deepcopy(configured["benchmark"]),
    }
    scenario["mllm"]["raw_output_dir"] = (
        Path("mllm_raw_outputs_smoke_%s" % label) / case_id
    ).as_posix()
    scenario["mllm"]["debug_output_dir"] = (
        Path("mllm_debug_outputs_smoke_%s" % label) / case_id
    ).as_posix()
    return scenario


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run one isolated one-case Dec-Graph, VLFM-G, or MLLM-Direct "
            "smoke test."
        )
    )
    parser.add_argument(
        "--method",
        required=True,
        choices=["dec_graph", "vlfm_g", "mllm_direct"],
    )
    parser.add_argument("--case-id", default="JF19kD82Mey_case_0006")
    parser.add_argument("--max-steps", type=int, default=1)
    parser.add_argument("--beta", type=float, default=0.25)
    parser.add_argument("--batch-config", default="scenarios/batch_test.json")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.max_steps <= 0:
        raise ValueError("--max-steps must be positive.")
    default_config = _read_json(args.config)
    batch_config = _read_json(args.batch_config)
    scenario = build_smoke_scenario(
        method=args.method,
        case_id=args.case_id,
        max_steps=args.max_steps,
        beta=args.beta,
        default_config=default_config,
        batch_config=batch_config,
    )
    result = run_scenario(scenario, show_agent_views=False)
    result_path = (
        PROJECT_ROOT
        / str(scenario["mllm"]["debug_output_dir"])
        / "smoke_result.json"
    )
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print("Saved smoke result to %s." % result_path)
    return 1 if result.get("status") == "terminated" else 0


if __name__ == "__main__":
    raise SystemExit(main())
