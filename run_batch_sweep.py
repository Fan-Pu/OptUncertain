from __future__ import annotations

import argparse
import copy
import json
import re
import tempfile
from pathlib import Path
from typing import Dict, List, Sequence

from main import SAMPLE_BALANCE_MODES, _read_json, run_batch_config


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "default_config.json"
DEFAULT_SWEEP_SAMPLE_COUNT = 100
DEFAULT_SWEEP_SAMPLE_SEED = 0
DEFAULT_SWEEP_SAMPLE_BALANCE = "param_config"
DEFAULT_SWEEP_RUN_ID_PREFIX = "balanced100"

GRAPH_MODEL_FIELDS = {
    "graph_model_name",
    "graph_api_type",
    "graph_base_url",
    "graph_api_key_env",
    "graph_reasoning_effort",
    "graph_service_tier",
    "graph_thinking",
    "graph_thinking_format",
    "graph_reasoning_split",
    "graph_extra_body_enabled",
    "graph_presence_penalty_enabled",
}
GRAPH_MODEL_OPTIONAL_CONTROL_FIELDS = {
    "graph_reasoning_effort",
    "graph_service_tier",
    "graph_thinking",
    "graph_thinking_format",
    "graph_reasoning_split",
}
REQUIRED_GRAPH_MODEL_FIELDS = {
    "label",
    "graph_model_name",
    "graph_api_type",
}


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as file_handle:
        json.dump(payload, file_handle, indent=2)
        file_handle.write("\n")


def _slug(value: object, field_name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value).strip())
    slug = re.sub(r"_+", "_", slug).strip("._-")
    if not slug:
        raise ValueError("%s must contain at least one path-safe character." % field_name)
    return slug


def _read_default_config(path: str | Path) -> Dict[str, object]:
    config = _read_json(path)
    if not isinstance(config, dict):
        raise TypeError("Default config must be a JSON object.")
    if "mllm" not in config or not isinstance(config["mllm"], dict):
        raise KeyError("Default config must contain an object mllm block.")
    return copy.deepcopy(config)


def _sweep_block(default_config: Dict[str, object]) -> Dict[str, object]:
    block = default_config.get("batch_sweep")
    if not isinstance(block, dict):
        raise KeyError("Default config is missing object batch_sweep block.")
    return block


def _graph_models(default_config: Dict[str, object]) -> List[Dict[str, object]]:
    models = _sweep_block(default_config).get("graph_models")
    if not isinstance(models, list) or not models:
        raise ValueError("batch_sweep.graph_models must be a non-empty list.")

    seen_labels = set()
    seen_run_id_slugs = set()
    normalized_models = []
    for index, model in enumerate(models):
        if not isinstance(model, dict):
            raise TypeError("batch_sweep.graph_models[%d] must be an object." % index)

        missing = sorted(REQUIRED_GRAPH_MODEL_FIELDS - set(model))
        if missing:
            raise KeyError(
                "batch_sweep.graph_models[%d] is missing required field(s): %s."
                % (index, ", ".join(missing))
            )

        unknown = sorted(set(model) - GRAPH_MODEL_FIELDS - {"label"})
        if unknown:
            raise KeyError(
                "batch_sweep.graph_models[%d] has unknown field(s): %s."
                % (index, ", ".join(unknown))
            )

        label = str(model["label"]).strip()
        if not label:
            raise ValueError("batch_sweep.graph_models[%d].label must be non-empty." % index)
        if label in seen_labels:
            raise ValueError("Duplicate graph model label %r." % label)
        seen_labels.add(label)

        run_slug = _slug(label, "batch_sweep.graph_models[%d].label" % index)
        if run_slug in seen_run_id_slugs:
            raise ValueError("Duplicate graph model run-id slug %r." % run_slug)
        seen_run_id_slugs.add(run_slug)

        normalized_models.append(copy.deepcopy(model))

    return normalized_models


def selected_graph_model(
    default_config: Dict[str, object],
    selected_label: str | None = None,
) -> Dict[str, object]:
    sweep_config = _sweep_block(default_config)
    label = (
        str(selected_label).strip()
        if selected_label is not None
        else str(sweep_config.get("selected_graph_model_label", "")).strip()
    )
    if not label:
        raise KeyError("batch_sweep.selected_graph_model_label must be non-empty.")

    matches = [model for model in _graph_models(default_config) if model["label"] == label]
    if not matches:
        raise KeyError("Selected graph model label %r was not found." % label)
    return copy.deepcopy(matches[0])


def sweep_run_id(prefix: object, graph_model: Dict[str, object]) -> str:
    return "%s_%s" % (
        _slug(prefix, "batch_sweep.run_id_prefix"),
        _slug(graph_model["label"], "graph model label"),
    )


def build_sweep_batch_config(
    batch_config: Dict[str, object],
    default_config: Dict[str, object],
    graph_model: Dict[str, object],
) -> Dict[str, object]:
    if not isinstance(batch_config, dict):
        raise TypeError("Batch config must be a JSON object.")
    if not isinstance(default_config.get("mllm"), dict):
        raise KeyError("Default config must contain an object mllm block.")

    sweep_config = copy.deepcopy(batch_config)
    mllm = copy.deepcopy(default_config["mllm"])
    for key in GRAPH_MODEL_OPTIONAL_CONTROL_FIELDS:
        if key not in graph_model:
            mllm[key] = None
    for key in GRAPH_MODEL_FIELDS:
        if key in graph_model:
            mllm[key] = copy.deepcopy(graph_model[key])
    sweep_config["mllm"] = mllm
    return sweep_config


def _write_temp_batch_config(
    batch_config: Dict[str, object],
    temp_dir: Path,
    source_batch_config_path: Path,
) -> Path:
    path = temp_dir / source_batch_config_path.name
    _write_json(path, batch_config)
    return path


def _setting(
    cli_value,
    sweep_config: Dict[str, object],
    key: str,
    default_value,
):
    return cli_value if cli_value is not None else sweep_config.get(key, default_value)


def run_batch_sweep(
    *,
    batch_config_path: str | Path,
    default_config_path: str | Path = DEFAULT_CONFIG_PATH,
    sample_count: int | None = None,
    sample_seed: int | None = None,
    sample_balance: str | None = None,
    hide_agent_views: bool | None = None,
    run_id_prefix: str | None = None,
    graph_model_label: str | None = None,
) -> Dict[str, object]:
    default_config = _read_default_config(default_config_path)
    batch_config = _read_json(batch_config_path)
    if not isinstance(batch_config, dict):
        raise TypeError("Batch config must be a JSON object.")

    sweep_config = _sweep_block(default_config)
    model = selected_graph_model(default_config, selected_label=graph_model_label)
    resolved_sample_count = int(
        _setting(sample_count, sweep_config, "sample_count", DEFAULT_SWEEP_SAMPLE_COUNT)
    )
    resolved_sample_seed = int(
        _setting(sample_seed, sweep_config, "sample_seed", DEFAULT_SWEEP_SAMPLE_SEED)
    )
    resolved_sample_balance = str(
        _setting(
            sample_balance,
            sweep_config,
            "sample_balance",
            DEFAULT_SWEEP_SAMPLE_BALANCE,
        )
    )
    if resolved_sample_balance not in SAMPLE_BALANCE_MODES:
        raise ValueError(
            "sample_balance must be one of %s."
            % ", ".join(SAMPLE_BALANCE_MODES)
        )
    resolved_hide_agent_views = bool(
        _setting(hide_agent_views, sweep_config, "hide_agent_views", True)
    )
    resolved_run_id_prefix = str(
        _setting(
            run_id_prefix,
            sweep_config,
            "run_id_prefix",
            DEFAULT_SWEEP_RUN_ID_PREFIX,
        )
    )

    results = {}
    source_batch_config_path = Path(batch_config_path)
    with tempfile.TemporaryDirectory(prefix="batch_sweep_") as temp_dir_raw:
        temp_dir = Path(temp_dir_raw)
        run_id = sweep_run_id(resolved_run_id_prefix, model)
        print(
            "Running batch sweep graph model %s with run id %s."
            % (str(model["label"]), run_id),
            flush=True,
        )
        temp_batch_config = build_sweep_batch_config(
            batch_config=batch_config,
            default_config=default_config,
            graph_model=model,
        )
        temp_batch_config_path = _write_temp_batch_config(
            temp_batch_config,
            temp_dir / run_id,
            source_batch_config_path,
        )
        result = run_batch_config(
            temp_batch_config_path,
            show_agent_views=not resolved_hide_agent_views,
            sample_count=resolved_sample_count,
            sample_seed=resolved_sample_seed,
            sample_balance=resolved_sample_balance,
            run_id=run_id,
        )
        results[str(model["label"])] = result
        if result.get("status") == "terminated":
            return {
                "status": "terminated",
                "terminated_label": str(model["label"]),
                "results": results,
            }

    return {"status": "completed", "results": results}


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a full-pipeline batch sweep over configured graph models."
    )
    parser.add_argument("--batch-config", required=True)
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Default config containing the batch_sweep block.",
    )
    parser.add_argument("--sample-count", type=int)
    parser.add_argument("--sample-seed", type=int)
    parser.add_argument(
        "--sample-balance",
        choices=SAMPLE_BALANCE_MODES,
    )
    parser.add_argument(
        "--hide-agent-views",
        action="store_true",
        default=None,
    )
    parser.add_argument("--run-id-prefix")
    parser.add_argument(
        "--graph-model-label",
        help=(
            "Override batch_sweep.selected_graph_model_label for this run."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    result = run_batch_sweep(
        batch_config_path=args.batch_config,
        default_config_path=args.config,
        sample_count=args.sample_count,
        sample_seed=args.sample_seed,
        sample_balance=args.sample_balance,
        hide_agent_views=args.hide_agent_views,
        run_id_prefix=args.run_id_prefix,
        graph_model_label=args.graph_model_label,
    )
    if result.get("status") == "terminated":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
