from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import tempfile
from pathlib import Path
from typing import Dict, List, Sequence

from evaluate_batch_metrics import main as evaluate_metrics_main
from main import (
    _read_json,
    merge_batch_config_overrides,
    run_batch_config,
    sample_batch_case_ids,
)
from oracle_runner import run_oracle
from run_batch_sweep import build_sweep_batch_config, selected_graph_model


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "default_config.json"
METHODS = {"vlfm_g", "mllm_direct"}


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _manifest_hash(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _read_object(path: str | Path, label: str) -> Dict[str, object]:
    payload = _read_json(path)
    if not isinstance(payload, dict):
        raise TypeError("%s must be a JSON object." % label)
    return payload


def _case_order(manifest: Dict[str, object]) -> List[str]:
    return [str(case_id) for case_id in manifest["case_order"]]


def _validate_sample_manifest(
    sample_manifest: Dict[str, object],
    source_manifest: Dict[str, object],
) -> None:
    source_cases = source_manifest["cases"]
    sample_cases = sample_manifest["cases"]
    for case_id in _case_order(sample_manifest):
        if case_id not in source_cases:
            raise KeyError("Sample case %s is absent from the source manifest." % case_id)
        for field in ("scan_id", "agents", "targets", "max_steps"):
            if sample_cases[case_id].get(field) != source_cases[case_id].get(field):
                raise ValueError(
                    "Sample case %s field %s differs from the source manifest."
                    % (case_id, field)
                )


def _source_manifest_path(batch_config_path: Path) -> Path:
    return PROJECT_ROOT / "mllm_debug_outputs" / batch_config_path.stem / "generated_cases.json"


def _method_run_id(method: str, action_model_label: str) -> str:
    if method == "vlfm_g":
        return "balanced100_VLFMG"
    return "balanced100_MLLMDirect_%s" % str(action_model_label)


def _beta_slug(beta: float) -> str:
    return ("%g" % float(beta)).replace(".", "p").replace("-", "m")


def _configured_batch(
    *,
    method: str,
    batch_config: Dict[str, object],
    default_config: Dict[str, object],
    beta: float | None = None,
) -> Dict[str, object]:
    merged_defaults = merge_batch_config_overrides(
        default_config=default_config,
        batch_config=batch_config,
    )
    configured = copy.deepcopy(batch_config)
    benchmark = copy.deepcopy(default_config["benchmark"])
    benchmark["method"] = method

    if method == "mllm_direct":
        label = str(benchmark["mllm_direct"]["action_model_label"])
        graph_model = selected_graph_model(default_config, selected_label=label)
        configured = build_sweep_batch_config(
            batch_config=configured,
            default_config=merged_defaults,
            graph_model=graph_model,
        )
        configured["mllm"]["graph_service_tier"] = benchmark[
            "mllm_direct"
        ]["action_service_tier"]
    else:
        if beta is None:
            raise ValueError("VLFM-G requires a frozen beta value.")
        benchmark["vlfm_g"]["beta"] = float(beta)
        configured["mllm"] = copy.deepcopy(merged_defaults["mllm"])

    configured["benchmark"] = benchmark
    return configured


def _run_cases(
    *,
    batch_config_path: Path,
    configured_batch: Dict[str, object],
    case_ids: List[str],
    run_id: str,
) -> Dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="benchmark_sweep_") as temp_dir_raw:
        temp_path = Path(temp_dir_raw) / batch_config_path.name
        _write_json(temp_path, configured_batch)
        return run_batch_config(
            temp_path,
            show_agent_views=False,
            sample_seed=0,
            sample_balance="param_config",
            run_id=run_id,
            sampled_case_ids=case_ids,
            project_root=PROJECT_ROOT,
        )


def _calibration_manifest(
    *,
    source_manifest: Dict[str, object],
    test_manifest: Dict[str, object],
    count: int,
    seed: int,
) -> Dict[str, object]:
    test_ids = set(_case_order(test_manifest))
    eligible_order = [
        case_id
        for case_id in _case_order(source_manifest)
        if case_id not in test_ids
    ]
    eligible = copy.deepcopy(source_manifest)
    eligible["case_order"] = eligible_order
    eligible["cases"] = {
        case_id: copy.deepcopy(source_manifest["cases"][case_id])
        for case_id in eligible_order
    }
    eligible["generated_case_count"] = len(eligible_order)
    selected_ids = sample_batch_case_ids(
        summary=eligible,
        sample_count=int(count),
        sample_seed=int(seed),
        sample_balance="param_config",
    )
    return {
        "batch_id": str(source_manifest["batch_id"]),
        "purpose": "vlfm_g_beta_calibration",
        "calibration_seed": int(seed),
        "generated_case_count": len(selected_ids),
        "case_order": selected_ids,
        "cases": {
            case_id: copy.deepcopy(source_manifest["cases"][case_id])
            for case_id in selected_ids
        },
        "excluded_test_manifest_hash": _manifest_hash(test_manifest),
    }


def _run_calibration_oracles(
    calibration_manifest: Dict[str, object],
    output_root: Path,
) -> Path:
    cases = calibration_manifest["cases"]
    summaries = {}
    for case_id in _case_order(calibration_manifest):
        case_output = output_root / "oracles" / case_id
        summary_path = case_output / ("%s_oracle_route_summary.txt" % case_id)
        route_path = case_output / "optimizer_routes_oracle.json"
        if summary_path.exists() and route_path.exists():
            summaries[case_id] = _read_object(summary_path, "oracle summary")
            continue
        summaries[case_id] = run_oracle(
            test_case=cases[case_id],
            project_root=PROJECT_ROOT,
            connectivity_dir=PROJECT_ROOT / "connectivity",
            output_dir=case_output,
            print_summary=False,
            write_model_lp=False,
            use_shortest_walk_solver=True,
        )
    aggregate_path = output_root / "oracle_summaries.json"
    _write_json(
        aggregate_path,
        {
            "batch_id": str(calibration_manifest["batch_id"]),
            "oracle_case_count": len(summaries),
            "case_order": _case_order(calibration_manifest),
            "cases": summaries,
        },
    )
    return aggregate_path


def _select_beta(
    metrics_path: Path,
    beta_by_method: Dict[str, float],
) -> tuple[float, List[Dict[str, object]]]:
    rows = []
    with open(metrics_path, "r", encoding="utf-8", newline="") as file_handle:
        for row in csv.DictReader(file_handle):
            method = str(row["method"])
            if method not in beta_by_method:
                continue
            rows.append(
                {
                    "method": method,
                    "beta": beta_by_method[method],
                    "team_ppl_total": float(row["team_ppl_total"]),
                    "progress": float(row["progress"]),
                    "verified_success_rate": float(row["verified_success_rate"]),
                    "mean_total_distance": float(row["mean_total_distance"]),
                }
            )
    if len(rows) != len(beta_by_method):
        raise ValueError("Calibration metrics do not contain every beta candidate.")
    ranked = sorted(
        rows,
        key=lambda row: (
            -float(row["team_ppl_total"]),
            -float(row["progress"]),
            -float(row["verified_success_rate"]),
            float(row["mean_total_distance"]),
            float(row["beta"]),
        ),
    )
    return float(ranked[0]["beta"]), ranked


def calibrate_vlfm_g(
    batch_config_path: Path,
    default_config: Dict[str, object],
    batch_config: Dict[str, object],
    test_manifest: Dict[str, object],
    source_manifest: Dict[str, object],
) -> Dict[str, object]:
    config = default_config["benchmark"]["vlfm_g"]
    output_root = PROJECT_ROOT / "mllm_debug_outputs_vlfmg_calibration" / batch_config_path.stem
    calibration_manifest = _calibration_manifest(
        source_manifest=source_manifest,
        test_manifest=test_manifest,
        count=int(config["calibration_case_count"]),
        seed=int(config["calibration_seed"]),
    )
    manifest_path = output_root / "calibration_generated_cases.json"
    _write_json(manifest_path, calibration_manifest)
    manifest_digest = _manifest_hash(calibration_manifest)
    oracle_path = _run_calibration_oracles(calibration_manifest, output_root)

    method_specs = []
    beta_by_method = {}
    for beta_raw in config["beta_grid"]:
        beta = float(beta_raw)
        method_name = "VLFMG_beta_%s" % _beta_slug(beta)
        run_id = "calibration20_VLFMG_beta_%s" % _beta_slug(beta)
        configured = _configured_batch(
            method="vlfm_g",
            batch_config=batch_config,
            default_config=default_config,
            beta=beta,
        )
        result = _run_cases(
            batch_config_path=batch_config_path,
            configured_batch=configured,
            case_ids=_case_order(calibration_manifest),
            run_id=run_id,
        )
        if result["status"] == "terminated":
            return result
        debug_root = PROJECT_ROOT / ("mllm_debug_outputs_%s" % run_id)
        method_specs.extend(["--method", "%s=%s" % (method_name, debug_root)])
        beta_by_method[method_name] = beta

    metrics_dir = output_root / "metrics"
    evaluate_metrics_main(
        [
            "--batch-config",
            str(batch_config_path),
            "--generated-cases",
            str(manifest_path),
            "--oracle-summaries",
            str(oracle_path),
            *method_specs,
            "--out",
            str(metrics_dir),
        ]
    )
    selected_beta, ranked = _select_beta(
        metrics_dir / "method_metrics.csv",
        beta_by_method,
    )
    selection_path = PROJECT_ROOT / str(config["beta_selection_path"])
    selection = {
        "selected_beta": selected_beta,
        "selection_order": [
            "team_ppl_total_desc",
            "progress_desc",
            "verified_success_rate_desc",
            "mean_total_distance_asc",
            "beta_asc",
        ],
        "calibration_manifest_path": str(manifest_path.relative_to(PROJECT_ROOT)),
        "calibration_manifest_sha256": manifest_digest,
        "candidate_metrics": ranked,
    }
    _write_json(selection_path, selection)
    return {
        "status": "completed",
        "selected_beta": selected_beta,
        "selection_path": str(selection_path),
    }


def _frozen_beta(default_config: Dict[str, object]) -> float:
    config = default_config["benchmark"]["vlfm_g"]
    selection_path = PROJECT_ROOT / str(config["beta_selection_path"])
    if not selection_path.exists():
        raise FileNotFoundError(
            "VLFM-G beta selection is missing: %s. Run --calibrate first."
            % selection_path
        )
    selection = _read_object(selection_path, "VLFM-G beta selection")
    manifest_path = PROJECT_ROOT / str(selection["calibration_manifest_path"])
    manifest = _read_object(manifest_path, "VLFM-G calibration manifest")
    actual_hash = _manifest_hash(manifest)
    expected_hash = str(selection["calibration_manifest_sha256"])
    if actual_hash != expected_hash:
        raise ValueError(
            "VLFM-G calibration manifest hash differs from the frozen selection."
        )
    return float(selection["selected_beta"])


def run_benchmark_sweep(
    *,
    batch_config_path: str | Path,
    method: str,
    calibrate: bool = False,
    default_config_path: str | Path = DEFAULT_CONFIG_PATH,
) -> Dict[str, object]:
    method = str(method).strip().lower()
    if method not in METHODS:
        raise ValueError("method must be vlfm_g or mllm_direct.")
    if calibrate and method != "vlfm_g":
        raise ValueError("--calibrate is available only for vlfm_g.")

    batch_path = Path(batch_config_path).resolve()
    default_config = _read_object(default_config_path, "default config")
    batch_config = _read_object(batch_path, "batch config")
    sample_path = PROJECT_ROOT / str(default_config["benchmark"]["sample_manifest"])
    test_manifest = _read_object(sample_path, "test sample manifest")
    source_manifest = _read_object(
        _source_manifest_path(batch_path),
        "source generated-case manifest",
    )
    _validate_sample_manifest(test_manifest, source_manifest)

    if calibrate:
        return calibrate_vlfm_g(
            batch_config_path=batch_path,
            default_config=default_config,
            batch_config=batch_config,
            test_manifest=test_manifest,
            source_manifest=source_manifest,
        )

    benchmark = default_config["benchmark"]
    action_label = str(benchmark["mllm_direct"]["action_model_label"])
    beta = _frozen_beta(default_config) if method == "vlfm_g" else None
    configured = _configured_batch(
        method=method,
        batch_config=batch_config,
        default_config=default_config,
        beta=beta,
    )
    return _run_cases(
        batch_config_path=batch_path,
        configured_batch=configured,
        case_ids=_case_order(test_manifest),
        run_id=_method_run_id(method, action_label),
    )


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run VLFM-G or MLLM-Direct on an exact saved batch sample."
    )
    parser.add_argument("--batch-config", required=True)
    parser.add_argument("--method", required=True, choices=sorted(METHODS))
    parser.add_argument("--calibrate", action="store_true")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    result = run_benchmark_sweep(
        batch_config_path=args.batch_config,
        method=args.method,
        calibrate=bool(args.calibrate),
        default_config_path=args.config,
    )
    return 1 if result.get("status") == "terminated" else 0


if __name__ == "__main__":
    raise SystemExit(main())
