from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from statistics import fmean
from typing import Dict, List, Mapping, Sequence, Tuple

from evaluate_batch_metrics import (
    MethodSpec as RouteMethodSpec,
    _method_case_metrics,
    _scan_target_detectable_viewpoints,
)
from evaluate_hypothesis_quality_metrics import (
    MethodSpec as HypothesisMethodSpec,
    _evaluate_case,
    _oracle_distance_profile,
)
from route_plotter import EnvironmentGraph, load_environment_graph


DEFAULT_CASE_ID = "RPmz2sHmrrY_case_0030"
DEFAULT_ORIGINAL_DEBUG_ROOT = Path(
    "mllm_debug_outputs_balanced100_Qwen36_35BA3BThinking"
)
DEFAULT_RELAXED_DEBUG_ROOT = Path(
    "mllm_debug_outputs_smoke_QwenThinkingRelaxedNewEdges"
)
DEFAULT_OUTPUT_DIR = Path(
    "relaxed_edge_prompt_qwen_thinking_case0030_comparison"
)

METRIC_FIELDS = [
    "variant",
    "case_id",
    "agent_number",
    "target_number",
    "status",
    "stop_reason",
    "steps_completed",
    "verified_success",
    "progress",
    "team_ppl_total",
    "team_ppl_makespan",
    "total_distance",
    "maximum_agent_distance",
    "f1",
    "pwgs_pair_count",
    "pwgs",
    "saved_new_edge_count",
    "last_ungrounded_edge_count",
    "edge_jnll",
    "edge_jnll_status",
]

EDGE_FIELDS = [
    "variant",
    "case_id",
    "last_ungrounded_step",
    "endpoint_i",
    "endpoint_j",
    "predicted_exist_prob",
    "predicted_distance_mean",
    "predicted_distance_variance",
    "oracle_edge_exists",
    "oracle_edge_distance",
    "edge_jnll",
]


def edge_joint_negative_log_likelihood(
    *,
    exist_prob: float,
    distance_mean: float,
    distance_var: float,
    oracle_edge_exists: bool,
    oracle_edge_distance: float | None,
) -> float:
    exist_prob = float(exist_prob)
    if not 0.0 <= exist_prob <= 1.0:
        raise ValueError("Edge existence probability must be in [0, 1].")
    if not oracle_edge_exists:
        return math.inf if exist_prob == 1.0 else -math.log1p(-exist_prob)
    if oracle_edge_distance is None:
        raise ValueError("An existing oracle edge requires its true distance.")
    if distance_var <= 0.0:
        raise ValueError("An ungrounded edge requires positive distance variance.")
    if exist_prob == 0.0:
        return math.inf
    return (
        -math.log(exist_prob)
        + 0.5 * math.log(2.0 * math.pi * float(distance_var))
        + (
            (float(oracle_edge_distance) - float(distance_mean)) ** 2
            / (2.0 * float(distance_var))
        )
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    case_id = str(args.case_id)
    batch_config = _read_json(_resolve_path(args.batch_config))
    frozen_manifest = _read_json(_resolve_path(args.frozen_manifest))
    if str(frozen_manifest["batch_case_generation_hash"]) != (
        "ec14c3efdcc190d8a3872e0f22cd89a9481485498a7fa1794610f043dd02a7e5"
    ):
        raise ValueError("The evaluator requires the frozen 100-case manifest.")
    generated_case = frozen_manifest["cases"][case_id]
    if int(generated_case["agent_number"]) != 3:
        raise ValueError("%s is not a three-agent case." % case_id)

    connectivity_dir = _resolve_path(args.connectivity_dir)
    environment = load_environment_graph(
        scan_id=str(generated_case["scan_id"]),
        connectivity_dir=connectivity_dir,
    )
    oracle_summaries = _read_json(_resolve_path(args.oracle_summaries))
    oracle_summary = oracle_summaries["cases"][case_id]
    scan_targets = _scan_target_detectable_viewpoints(batch_config)
    hypothesis_profiles = _hypothesis_profiles(
        generated_case=generated_case,
        scan_targets=scan_targets,
        environment=environment,
    )

    methods = [
        (
            "Original Qwen-Thinking",
            _resolve_path(args.original_debug_root),
        ),
        (
            "Relaxed new-edge prompt",
            _resolve_path(args.relaxed_debug_root),
        ),
    ]
    metric_rows: List[Dict[str, object]] = []
    edge_rows: List[Dict[str, object]] = []
    case_audits: Dict[str, object] = {}
    first_step_detections: Dict[str, object] = {}

    for variant, debug_root in methods:
        raw_root = _raw_root_for_debug_root(debug_root)
        first_step_detections[variant] = _read_json(
            raw_root / case_id / "detection_step_0001.json"
        )
        route_metrics = _method_case_metrics(
            method=RouteMethodSpec(
                name=variant,
                debug_root=debug_root,
                raw_root=raw_root,
            ),
            case_id=case_id,
            generated_case=generated_case,
            oracle_summary=oracle_summary,
            scan_targets=scan_targets,
            connectivity_dir=connectivity_dir,
        )
        hypothesis_row, hypothesis_audit, last_edges = _evaluate_case(
            method=HypothesisMethodSpec(
                name=variant,
                debug_root=debug_root,
                raw_root=raw_root,
            ),
            case_id=case_id,
            generated_case=generated_case,
            oracle_profile_by_scan_target=hypothesis_profiles,
        )
        variant_edge_rows = _edge_rows(
            variant=variant,
            case_id=case_id,
            predictions=last_edges,
            environment=environment,
        )
        edge_rows.extend(variant_edge_rows)
        edge_jnll = (
            fmean(float(row["edge_jnll"]) for row in variant_edge_rows)
            if variant_edge_rows
            else None
        )
        saved_new_edge_count = _saved_new_edge_count(raw_root / case_id)
        route_summary = _read_json(
            debug_root / case_id / ("%s_mllm_route_summary.txt" % case_id)
        )
        metric_rows.append(
            {
                "variant": variant,
                "case_id": case_id,
                "agent_number": int(generated_case["agent_number"]),
                "target_number": int(generated_case["target_number"]),
                "status": route_metrics["status"],
                "stop_reason": route_metrics["stop_reason"],
                "steps_completed": int(route_summary["steps_completed"]),
                "verified_success": route_metrics["verified_success"],
                "progress": route_metrics["progress"],
                "team_ppl_total": route_metrics["team_ppl_total"],
                "team_ppl_makespan": route_metrics["team_ppl_makespan"],
                "total_distance": route_metrics["total_distance"],
                "maximum_agent_distance": route_metrics[
                    "maximum_agent_distance"
                ],
                "f1": route_metrics["f1"],
                "pwgs_pair_count": hypothesis_row["pwgs_pair_count"],
                "pwgs": hypothesis_row["episode_pwgs"],
                "saved_new_edge_count": saved_new_edge_count,
                "last_ungrounded_edge_count": len(last_edges),
                "edge_jnll": "" if edge_jnll is None else edge_jnll,
                "edge_jnll_status": (
                    "not_estimable_no_ungrounded_predictions"
                    if edge_jnll is None
                    else "estimated_from_last_ungrounded_predictions"
                ),
            }
        )
        case_audits[variant] = {
            **hypothesis_audit,
            "saved_new_edge_count": saved_new_edge_count,
            "last_ungrounded_edge_count": len(last_edges),
        }

    output_dir = _resolve_path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(output_dir / "case_comparison_metrics.csv", metric_rows, METRIC_FIELDS)
    _write_csv(output_dir / "edge_predictions.csv", edge_rows, EDGE_FIELDS)
    comparison = _comparison_payload(metric_rows)
    first_step_detection_match = (
        first_step_detections["Original Qwen-Thinking"]
        == first_step_detections["Relaxed new-edge prompt"]
    )
    audit = {
        "case_id": case_id,
        "manifest_hash": frozen_manifest["batch_case_generation_hash"],
        "graph_model": "Qwen/Qwen3.6-35B-A3B",
        "prompt_variant_path": str(
            _resolve_path(args.prompt_variant)
        ),
        "prompt_variant_sha256": _sha256(
            _resolve_path(args.prompt_variant)
        ),
        "case_audits": case_audits,
        "first_step_detection_match": first_step_detection_match,
        "first_step_detections": first_step_detections,
        "comparison": comparison,
        "edge_candidate_set_caveat": (
            "The original run saved no ungrounded edge predictions. Its "
            "Edge-JNLL is therefore N/A, so Edge-JNLL cannot be compared "
            "numerically between variants in this one-case ablation."
        ),
    }
    _write_json(output_dir / "relaxed_edge_comparison_audit.json", audit)
    _write_report(
        output_dir / "relaxed_edge_comparison.md",
        rows=metric_rows,
        comparison=comparison,
        edge_rows=edge_rows,
        first_step_detection_match=first_step_detection_match,
    )
    print("Wrote relaxed-edge comparison to %s." % output_dir)
    return 0


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare one relaxed-edge Qwen-Thinking smoke run with its "
            "original frozen Qwen-Thinking case."
        )
    )
    parser.add_argument("--case-id", default=DEFAULT_CASE_ID)
    parser.add_argument("--batch-config", default="scenarios/batch_test.json")
    parser.add_argument(
        "--frozen-manifest",
        default=(
            "mllm_debug_outputs_balanced100_GPT54Medium/"
            "batch_test/sampled_generated_cases.json"
        ),
    )
    parser.add_argument(
        "--oracle-summaries",
        default=(
            "mllm_debug_outputs_balanced100_GPT54Medium/"
            "batch_test/oracle_summaries.json"
        ),
    )
    parser.add_argument(
        "--connectivity-dir",
        default="/root/mount/Matterport3DSimulator/connectivity",
    )
    parser.add_argument(
        "--original-debug-root",
        default=str(DEFAULT_ORIGINAL_DEBUG_ROOT),
    )
    parser.add_argument(
        "--relaxed-debug-root",
        default=str(DEFAULT_RELAXED_DEBUG_ROOT),
    )
    parser.add_argument(
        "--prompt-variant",
        default="prompts/graph_relaxed_newly_observed_edges.json",
    )
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    return parser.parse_args(argv)


def _resolve_path(path: str | Path) -> Path:
    path = Path(path)
    return path if path.is_absolute() else Path.cwd() / path


def _read_json(path: Path) -> object:
    with open(path, "r", encoding="utf-8") as file_handle:
        return json.load(file_handle)


def _write_json(path: Path, payload: object) -> None:
    with open(path, "w", encoding="utf-8") as file_handle:
        json.dump(payload, file_handle, indent=2, sort_keys=True)
        file_handle.write("\n")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_csv(
    path: Path,
    rows: Sequence[Mapping[str, object]],
    fields: Sequence[str],
) -> None:
    with open(path, "w", encoding="utf-8", newline="") as file_handle:
        writer = csv.DictWriter(file_handle, fieldnames=list(fields))
        writer.writeheader()
        writer.writerows(rows)


def _raw_root_for_debug_root(debug_root: Path) -> Path:
    if "debug_outputs" not in debug_root.name:
        raise ValueError("Cannot infer raw root from %s." % debug_root)
    return debug_root.with_name(
        debug_root.name.replace("debug_outputs", "raw_outputs")
    )


def _hypothesis_profiles(
    *,
    generated_case: Mapping[str, object],
    scan_targets: Mapping[str, Mapping[str, set[str]]],
    environment: EnvironmentGraph,
) -> Dict[Tuple[str, str], Tuple[Dict[str, float], float]]:
    scan_id = str(generated_case["scan_id"])
    profiles = {}
    for target in generated_case["targets"]:
        target_id = str(target["target_id"])
        distances, max_distance, _ = _oracle_distance_profile(
            environment=environment,
            oracle_detectable_viewpoint_ids=scan_targets[scan_id][target_id],
        )
        profiles[(scan_id, target_id)] = (distances, max_distance)
    return profiles


def _edge_rows(
    *,
    variant: str,
    case_id: str,
    predictions,
    environment: EnvironmentGraph,
) -> List[Dict[str, object]]:
    node_id_by_label = {
        str(label): int(node_id)
        for node_id, label in environment.viewpoint_id_by_index.items()
    }
    rows = []
    for endpoint_labels, prediction in sorted(predictions.items()):
        source_id = node_id_by_label[endpoint_labels[0]]
        target_id = node_id_by_label[endpoint_labels[1]]
        edge_id = tuple(sorted((source_id, target_id)))
        oracle_exists = edge_id in environment.edge_distances
        oracle_distance = (
            float(environment.edge_distances[edge_id])
            if oracle_exists
            else None
        )
        contribution = edge_joint_negative_log_likelihood(
            exist_prob=prediction.cond_exist_prob,
            distance_mean=prediction.distance_mean,
            distance_var=prediction.distance_var,
            oracle_edge_exists=oracle_exists,
            oracle_edge_distance=oracle_distance,
        )
        rows.append(
            {
                "variant": variant,
                "case_id": case_id,
                "last_ungrounded_step": prediction.step_index,
                "endpoint_i": endpoint_labels[0],
                "endpoint_j": endpoint_labels[1],
                "predicted_exist_prob": prediction.cond_exist_prob,
                "predicted_distance_mean": prediction.distance_mean,
                "predicted_distance_variance": prediction.distance_var,
                "oracle_edge_exists": int(oracle_exists),
                "oracle_edge_distance": (
                    "" if oracle_distance is None else oracle_distance
                ),
                "edge_jnll": contribution,
            }
        )
    return rows


def _saved_new_edge_count(raw_case_dir: Path) -> int:
    count = 0
    for path in raw_case_dir.glob("semantic_step_*.json"):
        payload = _read_json(path)
        count += len(payload["new_edges"])
    return count


def _comparison_payload(
    rows: Sequence[Mapping[str, object]],
) -> Dict[str, object]:
    by_variant = {str(row["variant"]): row for row in rows}
    original = by_variant["Original Qwen-Thinking"]
    relaxed = by_variant["Relaxed new-edge prompt"]
    higher_is_better = [
        "verified_success",
        "progress",
        "team_ppl_total",
        "team_ppl_makespan",
        "pwgs",
    ]
    lower_is_better = [
        "steps_completed",
        "total_distance",
        "maximum_agent_distance",
    ]
    deltas = {}
    for metric in higher_is_better + lower_is_better:
        deltas[metric] = float(relaxed[metric]) - float(original[metric])
    return {
        "relaxed_minus_original": deltas,
        "metric_directions": {
            **{metric: "higher_is_better" for metric in higher_is_better},
            **{metric: "lower_is_better" for metric in lower_is_better},
        },
        "scope": (
            "One preselected three-agent case; results are diagnostic and do "
            "not establish a population-level benefit."
        ),
    }


def _display(value: object, decimals: int = 3) -> str:
    if value == "" or value is None:
        return "--"
    return ("%%.%df" % decimals) % float(value)


def _write_report(
    path: Path,
    *,
    rows: Sequence[Mapping[str, object]],
    comparison: Mapping[str, object],
    edge_rows: Sequence[Mapping[str, object]],
    first_step_detection_match: bool,
) -> None:
    lines = [
        "# Qwen-Thinking relaxed new-edge prompt: one-case comparison",
        "",
        (
            "This is a controlled diagnostic on the frozen three-agent case "
            "`RPmz2sHmrrY_case_0030`. It is not sufficient for a paper-wide "
            "claim about effectiveness or efficiency."
        ),
        "",
        "| Variant | Internal outcome | Verified success | Verified progress | Team-PPL-total | Team-PPL-makespan | Total distance (m) | Max-agent distance (m) | Steps | F1 | PWGS | New edges | Edge-JNLL |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| {variant} | {outcome} | {success} | {progress} | {ppl_total} | "
            "{ppl_makespan} | {distance} | {max_distance} | {steps} | "
            "{f1} | {pwgs} | {new_edges} | {edge_jnll} |".format(
                variant=row["variant"],
                outcome="%s / %s" % (row["status"], row["stop_reason"]),
                success=_display(row["verified_success"]),
                progress=_display(row["progress"]),
                ppl_total=_display(row["team_ppl_total"]),
                ppl_makespan=_display(row["team_ppl_makespan"]),
                distance=_display(row["total_distance"]),
                max_distance=_display(row["maximum_agent_distance"]),
                steps=int(row["steps_completed"]),
                f1=_display(row["f1"]),
                pwgs=_display(row["pwgs"]),
                new_edges=int(row["saved_new_edge_count"]),
                edge_jnll=_display(row["edge_jnll"]),
            )
        )
    deltas = comparison["relaxed_minus_original"]
    lines.extend(
        [
            "",
            (
                "The internal outcome is based on the online detector's target "
                "state. Verified success and progress independently check the "
                "recorded found viewpoints against oracle-detectable viewpoints; "
                "an internally completed route can therefore have verified "
                "success equal to zero."
            ),
            "",
            "## Relaxed minus original",
            "",
            "| Metric | Difference | Better direction |",
            "|---|---:|---|",
        ]
    )
    for metric, difference in deltas.items():
        lines.append(
            "| {metric} | {difference:.3f} | {direction} |".format(
                metric=metric.replace("_", " "),
                difference=float(difference),
                direction=comparison["metric_directions"][metric].replace("_", " "),
            )
        )
    lines.extend(
        [
            "",
            "## Edge audit",
            "",
            (
                f"The relaxed run produced {len(edge_rows)} last-ungrounded "
                "edge prediction(s) available for Edge-JNLL."
            ),
            (
                "The original run has no ungrounded edge prediction, so its "
                "Edge-JNLL remains `--`; the two variants therefore do not "
                "have a directly comparable Edge-JNLL pair."
            ),
            "",
            "## Interpretation",
            "",
            (
                "The step-1 detection outputs "
                + ("match." if first_step_detection_match else "do not match. ")
                + (
                    ""
                    if first_step_detection_match
                    else (
                        "Because the initial panoramas are identical, this is "
                        "detector stochasticity before the routes diverge. The "
                        "observed route/effectiveness differences therefore "
                        "cannot be attributed solely to the graph-prompt change."
                    )
                )
            ),
            "",
            (
                "A benefit is supported for this case only if the relaxed row "
                "improves the task/route metrics in their stated directions. "
                "Even then, a single stochastic episode is an ablation example, "
                "not evidence of an average improvement over the 100-case set."
            ),
            "",
            "## Claim--evidence map",
            "",
            (
                "- Claim: the relaxed contract can create usable uncertain "
                "edges. | Evidence: saved `new_edges`, last-ungrounded snapshots, "
                f"and `edge_predictions.csv`. | Status: {'supported' if edge_rows else 'not supported'} "
                "in this run."
            ),
            "- Claim: relaxation improves this episode's effectiveness. | Evidence: success, progress, and PWGS relative to the original row. | Status: case-specific only.",
            "- Claim: relaxation improves this episode's efficiency. | Evidence: Team-PPL, total distance, maximum-agent distance, and steps. | Status: case-specific only.",
            "- Claim: relaxation generally improves the proposed method. | Evidence: one episode. | Status: needs a multi-seed or full-sample ablation.",
            "",
            "## Self-review",
            "",
            "- The comparison uses the same frozen case, Qwen-Thinking model configuration, detector family, optimization parameters, and 30-step budget.",
            "- Detection F1 is reported only as an on-policy diagnostic because the variants may execute different routes.",
            "- Edge-JNLL is not imputed for the original run.",
            "- No population-level claim is made from one case.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
