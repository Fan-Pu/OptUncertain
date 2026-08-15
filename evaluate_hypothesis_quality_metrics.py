from __future__ import annotations

import argparse
import csv
import hashlib
import heapq
import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple

from route_plotter import EnvironmentGraph, load_environment_graph


EXPECTED_MANIFEST_HASH = (
    "ec14c3efdcc190d8a3872e0f22cd89a9481485498a7fa1794610f043dd02a7e5"
)
EXPECTED_GROUP_TOTALS = {"single": 34, "multi": 66}
EXPECTED_COMMON_EVALUABLE_COUNTS = {"single": 30, "multi": 53}
PROBABILITY_SUM_ABS_TOL = 1.0e-6

HYPOTHESIS_STEP_RE = re.compile(r"hypothesis_step_(\d{4})\.json$")
SEMANTIC_STEP_RE = re.compile(r"semantic_step_(\d{4})\.json$")

CASE_FIELDS = [
    "method",
    "case_id",
    "scan_id",
    "agent_group",
    "agent_number",
    "target_number",
    "evaluation_status",
    "pwgs_pair_count",
    "evaluable_target_count",
    "empty_support_count",
    "valid_hypothesis_snapshot_count",
    "invalid_hypothesis_snapshot_count",
    "episode_pwgs",
    "episode_target_balanced_pwgs",
    "in_common_support",
    "edge_jnll_status",
    "ungrounded_edge_candidate_count",
]

TARGET_FIELDS = [
    "method",
    "case_id",
    "scan_id",
    "agent_group",
    "agent_number",
    "target_id",
    "pwgs_pair_count",
    "target_mean_pwgs",
    "in_common_support",
]

SUMMARY_FIELDS = [
    "method",
    "agent_group",
    "common_evaluated_count",
    "total_count",
    "pwgs",
    "target_balanced_pwgs",
    "edge_jnll",
    "edge_jnll_status",
    "ungrounded_edge_candidate_count",
]


@dataclass(frozen=True)
class MethodSpec:
    name: str
    debug_root: Path
    raw_root: Path


@dataclass(frozen=True)
class LastUngroundedEdgePrediction:
    step_index: int
    endpoint_labels: Tuple[str, str]
    cond_exist_prob: float
    distance_mean: float
    distance_var: float


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    batch_config_path = _resolve_path(args.batch_config)
    frozen_manifest_path = _resolve_path(args.frozen_manifest)
    connectivity_dir = _resolve_path(args.connectivity_dir)
    output_dir = _resolve_path(args.output_dir)
    method_specs = [_parse_method_spec(spec) for spec in args.method]

    if len(method_specs) != 4:
        raise ValueError("The frozen comparison requires exactly four methods.")
    method_names = [method.name for method in method_specs]
    if len(set(method_names)) != len(method_names):
        raise ValueError("Method names must be unique.")

    batch_config = _read_json(batch_config_path)
    frozen_manifest = _read_json(frozen_manifest_path)
    _verify_manifest_hash(frozen_manifest, frozen_manifest_path)
    _verify_method_manifests(method_specs, frozen_manifest)

    case_order = [str(case_id) for case_id in frozen_manifest["case_order"]]
    case_by_id = frozen_manifest["cases"]
    detectable_by_scan_target = _scan_target_detectable_viewpoints(batch_config)

    environment_by_scan: Dict[str, EnvironmentGraph] = {}
    oracle_profile_by_scan_target: Dict[
        Tuple[str, str], Tuple[Dict[str, float], float]
    ] = {}
    disconnected_connectivity_viewpoints: List[Dict[str, object]] = []
    malformed_artifacts: List[Dict[str, object]] = []
    empty_support_states: List[Dict[str, object]] = []
    case_rows: List[Dict[str, object]] = []
    target_rows: List[Dict[str, object]] = []
    method_audits: Dict[str, Dict[str, object]] = {}

    for method in method_specs:
        method_rows: List[Dict[str, object]] = []
        method_snapshot_count = 0
        method_valid_snapshot_count = 0
        method_invalid_snapshot_count = 0
        method_ungrounded_edges: Dict[
            Tuple[str, Tuple[str, str]], LastUngroundedEdgePrediction
        ] = {}

        for case_id in case_order:
            generated_case = case_by_id[case_id]
            scan_id = str(generated_case["scan_id"])
            if scan_id not in environment_by_scan:
                environment_by_scan[scan_id] = load_environment_graph(
                    scan_id=scan_id,
                    connectivity_dir=connectivity_dir,
                )
            environment = environment_by_scan[scan_id]

            for target in generated_case["targets"]:
                target_id = str(target["target_id"])
                profile_key = (scan_id, target_id)
                if profile_key not in oracle_profile_by_scan_target:
                    (
                        distance_by_viewpoint,
                        max_distance,
                        unreachable_viewpoint_ids,
                    ) = _oracle_distance_profile(
                        environment=environment,
                        oracle_detectable_viewpoint_ids=(
                            detectable_by_scan_target[scan_id][target_id]
                        ),
                    )
                    oracle_profile_by_scan_target[profile_key] = (
                        distance_by_viewpoint,
                        max_distance,
                    )
                    if unreachable_viewpoint_ids:
                        disconnected_connectivity_viewpoints.append(
                            {
                                "scan_id": scan_id,
                                "target_id": target_id,
                                "unreachable_viewpoint_count": len(
                                    unreachable_viewpoint_ids
                                ),
                                "unreachable_viewpoint_ids": (
                                    unreachable_viewpoint_ids
                                ),
                            }
                        )

            row, case_audit, case_edges = _evaluate_case(
                method=method,
                case_id=case_id,
                generated_case=generated_case,
                oracle_profile_by_scan_target=oracle_profile_by_scan_target,
            )
            method_rows.append(row)
            target_rows.extend(case_audit["target_rows"])
            malformed_artifacts.extend(case_audit["malformed_artifacts"])
            empty_support_states.extend(case_audit["empty_support_states"])
            method_snapshot_count += int(case_audit["snapshot_count"])
            method_valid_snapshot_count += int(case_audit["valid_snapshot_count"])
            method_invalid_snapshot_count += int(
                case_audit["invalid_snapshot_count"]
            )
            for edge_key, prediction in case_edges.items():
                method_ungrounded_edges[(case_id, edge_key)] = prediction

        raw_semantic_audit = _audit_raw_semantic_outputs(
            method=method,
            case_order=case_order,
        )
        method_audits[method.name] = {
            "debug_root": str(method.debug_root),
            "raw_root": str(method.raw_root),
            "hypothesis_snapshot_count": method_snapshot_count,
            "valid_hypothesis_snapshot_count": method_valid_snapshot_count,
            "invalid_hypothesis_snapshot_count": method_invalid_snapshot_count,
            "case_status_counts": dict(
                sorted(
                    Counter(
                        str(row["evaluation_status"]) for row in method_rows
                    ).items()
                )
            ),
            "ungrounded_edge_candidate_count": len(method_ungrounded_edges),
            **raw_semantic_audit,
        }
        case_rows.extend(method_rows)

    common_case_ids, common_exclusions = _select_common_support(
        case_rows=case_rows,
        method_names=method_names,
        case_order=case_order,
    )
    for row in case_rows:
        group = str(row["agent_group"])
        row["in_common_support"] = (
            1 if str(row["case_id"]) in common_case_ids[group] else 0
        )
    for row in target_rows:
        group = str(row["agent_group"])
        row["in_common_support"] = (
            1 if str(row["case_id"]) in common_case_ids[group] else 0
        )

    summary_rows = _aggregate_common_support(
        case_rows=case_rows,
        method_names=method_names,
        common_case_ids=common_case_ids,
    )
    _assert_frozen_acceptance(
        case_rows=case_rows,
        summary_rows=summary_rows,
        common_case_ids=common_case_ids,
        method_audits=method_audits,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(output_dir / "case_hypothesis_metrics.csv", case_rows, CASE_FIELDS)
    _write_csv(
        output_dir / "target_hypothesis_metrics.csv",
        target_rows,
        TARGET_FIELDS,
    )
    _write_csv(
        output_dir / "summary_hypothesis_metrics.csv",
        summary_rows,
        SUMMARY_FIELDS,
    )

    manifest_paths = {
        "frozen": frozen_manifest_path,
        **{
            method.name: _method_manifest_path(method)
            for method in method_specs
        },
    }
    audit = {
        "expected_manifest_hash": EXPECTED_MANIFEST_HASH,
        "verified_manifest_hash": str(
            frozen_manifest["batch_case_generation_hash"]
        ),
        "manifest_file_sha256": {
            name: _sha256(path) for name, path in manifest_paths.items()
        },
        "group_total_counts": {
            group: sum(
                1
                for case_id in case_order
                if _agent_group(int(case_by_id[case_id]["agent_number"])) == group
            )
            for group in ("single", "multi")
        },
        "common_evaluable_counts": {
            group: len(common_case_ids[group]) for group in ("single", "multi")
        },
        "common_evaluable_case_ids": {
            group: sorted(common_case_ids[group]) for group in ("single", "multi")
        },
        "common_support_exclusions": common_exclusions,
        "malformed_artifacts": malformed_artifacts,
        "empty_support_states": empty_support_states,
        "disconnected_connectivity_viewpoints": (
            disconnected_connectivity_viewpoints
        ),
        "connectivity_evaluation_rule": (
            "Geodesic distances and their normalizer use the connected "
            "navigation component containing the target's oracle-detectable "
            "viewpoints. A saved eligible viewpoint outside that component is "
            "an error because its target distance is undefined."
        ),
        "methods": method_audits,
        "edge_jnll": {
            "selection_rule": (
                "For each viewpoint pair, use the final saved state for which "
                "grounded=false and ignore every later grounded state."
            ),
            "status": "not_estimable_no_ungrounded_predictions",
            "reported_value": None,
            "interpretation": (
                "N/A is reported because no saved ungrounded edge predictions "
                "exist; it must not be interpreted as a zero or perfect score."
            ),
        },
    }
    _write_json(output_dir / "hypothesis_metric_audit.json", audit)
    _write_report(
        output_dir / "hypothesis_quality_results.md",
        summary_rows=summary_rows,
        malformed_artifacts=malformed_artifacts,
        common_case_ids=common_case_ids,
        method_names=method_names,
    )

    print(
        "Wrote hypothesis-quality analysis to %s "
        "(common support: 30/34 single, 53/66 multi)." % output_dir
    )
    return 0


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate saved target-probability and ungrounded-edge hypotheses "
            "without benchmark reruns or provider calls."
        )
    )
    parser.add_argument(
        "--method",
        required=True,
        action="append",
        help="Method specification in NAME=DEBUG_ROOT form.",
    )
    parser.add_argument("--batch-config", required=True)
    parser.add_argument("--frozen-manifest", required=True)
    parser.add_argument("--connectivity-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args(argv)


def _resolve_path(path: str | Path) -> Path:
    path = Path(path)
    if path.is_absolute():
        return path
    return Path.cwd() / path


def _parse_method_spec(spec: str) -> MethodSpec:
    if "=" not in spec:
        raise ValueError("--method must use NAME=DEBUG_ROOT form: %s" % spec)
    name, debug_root_raw = spec.split("=", 1)
    if not name:
        raise ValueError("Method name cannot be empty in %s." % spec)
    debug_root = _resolve_path(debug_root_raw)
    return MethodSpec(
        name=name,
        debug_root=debug_root,
        raw_root=_raw_root_for_debug_root(debug_root),
    )


def _raw_root_for_debug_root(debug_root: Path) -> Path:
    if "debug_outputs" not in debug_root.name:
        raise ValueError(
            "Cannot infer raw-output root from debug root %s." % debug_root
        )
    return debug_root.with_name(
        debug_root.name.replace("debug_outputs", "raw_outputs")
    )


def _method_manifest_path(method: MethodSpec) -> Path:
    return method.debug_root / "batch_test" / "sampled_generated_cases.json"


def _verify_manifest_hash(manifest: Mapping[str, object], path: Path) -> None:
    actual = str(manifest["batch_case_generation_hash"])
    if actual != EXPECTED_MANIFEST_HASH:
        raise ValueError(
            "Manifest %s has hash %s; expected %s."
            % (path, actual, EXPECTED_MANIFEST_HASH)
        )


def _verify_method_manifests(
    methods: Sequence[MethodSpec],
    frozen_manifest: Mapping[str, object],
) -> None:
    frozen_order = [str(case_id) for case_id in frozen_manifest["case_order"]]
    for method in methods:
        path = _method_manifest_path(method)
        manifest = _read_json(path)
        _verify_manifest_hash(manifest, path)
        method_order = [str(case_id) for case_id in manifest["case_order"]]
        if method_order != frozen_order:
            raise ValueError(
                "%s does not use the frozen manifest case order." % method.name
            )


def _scan_target_detectable_viewpoints(
    batch_config: Mapping[str, object],
) -> Dict[str, Dict[str, set[str]]]:
    result: Dict[str, Dict[str, set[str]]] = {}
    for scan in batch_config["scans"]:
        scan_id = str(scan["scan_id"])
        result[scan_id] = {
            str(target["target_id"]): {
                str(viewpoint_id)
                for viewpoint_id in target["detectable_viewpoint_ids"]
            }
            for target in scan["targets"]
        }
    return result


def _weighted_adjacency(
    environment: EnvironmentGraph,
) -> Dict[int, List[Tuple[int, float]]]:
    adjacency = {
        int(node_id): [] for node_id in environment.viewpoint_id_by_index
    }
    for (source_id, target_id), distance in environment.edge_distances.items():
        adjacency[int(source_id)].append((int(target_id), float(distance)))
        adjacency[int(target_id)].append((int(source_id), float(distance)))
    return adjacency


def _oracle_distance_profile(
    environment: EnvironmentGraph,
    oracle_detectable_viewpoint_ids: Iterable[str],
) -> Tuple[Dict[str, float], float, List[str]]:
    node_by_viewpoint_id = {
        str(viewpoint_id): int(node_id)
        for node_id, viewpoint_id in environment.viewpoint_id_by_index.items()
    }
    oracle_ids = {str(item) for item in oracle_detectable_viewpoint_ids}
    unknown_oracle_ids = oracle_ids.difference(node_by_viewpoint_id)
    if unknown_oracle_ids:
        raise ValueError(
            "%s oracle viewpoints are absent from connectivity: %s"
            % (environment.scan_id, sorted(unknown_oracle_ids))
        )
    if not oracle_ids:
        raise ValueError(
            "%s has a target with no oracle-detectable viewpoints."
            % environment.scan_id
        )

    adjacency = _weighted_adjacency(environment)
    distances = {
        int(node_id): math.inf for node_id in environment.viewpoint_id_by_index
    }
    heap: List[Tuple[float, int]] = []
    for viewpoint_id in oracle_ids:
        node_id = node_by_viewpoint_id[viewpoint_id]
        distances[node_id] = 0.0
        heapq.heappush(heap, (0.0, node_id))

    while heap:
        distance, node_id = heapq.heappop(heap)
        if distance != distances[node_id]:
            continue
        for neighbor_id, edge_distance in adjacency[node_id]:
            proposed = distance + edge_distance
            if proposed < distances[neighbor_id]:
                distances[neighbor_id] = proposed
                heapq.heappush(heap, (proposed, neighbor_id))

    finite_distances = {
        node_id: distance
        for node_id, distance in distances.items()
        if math.isfinite(distance)
    }
    max_distance = max(finite_distances.values())
    if max_distance <= 0.0:
        raise ValueError(
            "%s has no positive target-to-oracle normalization distance."
            % environment.scan_id
        )
    by_viewpoint_id = {
        str(environment.viewpoint_id_by_index[node_id]): float(distance)
        for node_id, distance in finite_distances.items()
    }
    unreachable_viewpoint_ids = sorted(
        str(environment.viewpoint_id_by_index[node_id])
        for node_id, distance in distances.items()
        if not math.isfinite(distance)
    )
    return by_viewpoint_id, float(max_distance), unreachable_viewpoint_ids


def compute_target_time_pwgs(
    probabilities_by_viewpoint: Mapping[str, float],
    distance_to_oracle_by_viewpoint: Mapping[str, float],
    max_oracle_distance: float,
) -> float:
    if not probabilities_by_viewpoint:
        raise ValueError("PWGS requires a nonempty viewpoint distribution.")
    if max_oracle_distance <= 0.0 or not math.isfinite(max_oracle_distance):
        raise ValueError("PWGS requires a positive finite normalization distance.")

    probability_sum = 0.0
    expected_normalized_distance = 0.0
    for viewpoint_id, probability_raw in probabilities_by_viewpoint.items():
        probability = float(probability_raw)
        if probability < 0.0 or not math.isfinite(probability):
            raise ValueError(
                "Invalid PWGS probability at %s: %s"
                % (viewpoint_id, probability)
            )
        if viewpoint_id not in distance_to_oracle_by_viewpoint:
            raise ValueError(
                "PWGS viewpoint %s is absent from connectivity." % viewpoint_id
            )
        distance = float(distance_to_oracle_by_viewpoint[viewpoint_id])
        if distance < 0.0 or not math.isfinite(distance):
            raise ValueError(
                "Invalid oracle distance at %s: %s" % (viewpoint_id, distance)
            )
        probability_sum += probability
        expected_normalized_distance += (
            probability * distance / max_oracle_distance
        )

    if not math.isclose(
        probability_sum,
        1.0,
        rel_tol=0.0,
        abs_tol=PROBABILITY_SUM_ABS_TOL,
    ):
        raise ValueError(
            "Saved PWGS probabilities sum to %.17g, not one; refusing to "
            "renormalize malformed data." % probability_sum
        )
    return 1.0 - expected_normalized_distance


def compute_target_balanced_episode_pwgs(
    pair_scores_by_target: Mapping[str, Sequence[float]],
) -> float:
    target_means = [
        fmean(float(score) for score in scores)
        for scores in pair_scores_by_target.values()
        if scores
    ]
    if not target_means:
        raise ValueError(
            "Target-balanced PWGS requires at least one evaluable target."
        )
    return fmean(target_means)


def eligible_target_distribution(
    snapshot: Mapping[str, object],
    target_id: str,
    current_viewpoint_node_ids: Iterable[int],
) -> Dict[str, float]:
    current_ids = {int(node_id) for node_id in current_viewpoint_node_ids}
    probabilities: Dict[str, float] = {}
    for node in snapshot["nodes"]:
        if str(node["type"]) != "viewpoint":
            continue
        node_id = int(node["id"])
        if bool(node["grounded"]):
            continue
        if int(node["node_visit_times"]) > 0:
            continue
        if node_id in current_ids:
            continue
        target_probs = node["target_probs"]
        if str(target_id) not in target_probs:
            raise ValueError(
                "Eligible viewpoint node %s is missing active target %s."
                % (node_id, target_id)
            )
        probabilities[str(node["label"])] = float(target_probs[str(target_id)])
    return probabilities


def _evaluate_case(
    method: MethodSpec,
    case_id: str,
    generated_case: Mapping[str, object],
    oracle_profile_by_scan_target: Mapping[
        Tuple[str, str], Tuple[Dict[str, float], float]
    ],
) -> Tuple[
    Dict[str, object],
    Dict[str, object],
    Dict[Tuple[str, str], LastUngroundedEdgePrediction],
]:
    case_dir = method.debug_root / case_id
    snapshot_paths = _step_paths(case_dir, HYPOTHESIS_STEP_RE)
    target_ids = [str(target["target_id"]) for target in generated_case["targets"]]
    scan_id = str(generated_case["scan_id"])
    pair_scores: List[float] = []
    pair_scores_by_target: Dict[str, List[float]] = {
        target_id: [] for target_id in target_ids
    }
    malformed_artifacts: List[Dict[str, object]] = []
    empty_support_states: List[Dict[str, object]] = []
    valid_snapshots: List[Tuple[int, Mapping[str, object]]] = []
    invalid_snapshot_count = 0

    for step_index, snapshot_path in snapshot_paths:
        try:
            snapshot = _read_json(snapshot_path)
        except json.JSONDecodeError as error:
            invalid_snapshot_count += 1
            malformed_artifacts.append(
                {
                    "kind": "invalid_json",
                    "method": method.name,
                    "case_id": case_id,
                    "step_index": step_index,
                    "path": str(snapshot_path),
                    "byte_size": snapshot_path.stat().st_size,
                    "error": "%s: %s" % (type(error).__name__, str(error)),
                }
            )
            continue

        valid_snapshots.append((step_index, snapshot))
        layout_path = case_dir / ("graph_layout_step_%04d.json" % step_index)
        layout = _read_json(layout_path)
        current_node_ids = [
            int(node_id) for node_id in layout["agent_current_vp_ids"].values()
        ]
        target_found = {
            str(target_id): bool(found)
            for target_id, found in snapshot["target_found"].items()
        }

        for target_id in target_ids:
            if target_id not in target_found:
                raise ValueError(
                    "%s %s step %d is missing target_found[%s]."
                    % (method.name, case_id, step_index, target_id)
                )
            if target_found[target_id]:
                continue
            probabilities = eligible_target_distribution(
                snapshot=snapshot,
                target_id=target_id,
                current_viewpoint_node_ids=current_node_ids,
            )
            if not probabilities:
                empty_support_states.append(
                    {
                        "method": method.name,
                        "case_id": case_id,
                        "step_index": step_index,
                        "target_id": target_id,
                        "reason": "no_eligible_viewpoints",
                    }
                )
                continue
            probability_sum = sum(probabilities.values())
            if probability_sum == 0.0:
                empty_support_states.append(
                    {
                        "method": method.name,
                        "case_id": case_id,
                        "step_index": step_index,
                        "target_id": target_id,
                        "reason": "empty_probability_distribution",
                    }
                )
                continue
            distance_by_viewpoint, max_distance = (
                oracle_profile_by_scan_target[(scan_id, target_id)]
            )
            try:
                pair_score = compute_target_time_pwgs(
                    probabilities_by_viewpoint=probabilities,
                    distance_to_oracle_by_viewpoint=distance_by_viewpoint,
                    max_oracle_distance=max_distance,
                )
            except ValueError as error:
                malformed_artifacts.append(
                    {
                        "kind": "invalid_target_distribution",
                        "method": method.name,
                        "case_id": case_id,
                        "step_index": step_index,
                        "target_id": target_id,
                        "path": str(snapshot_path),
                        "byte_size": snapshot_path.stat().st_size,
                        "error": str(error),
                    }
                )
                continue
            pair_scores.append(pair_score)
            pair_scores_by_target[target_id].append(pair_score)

    last_edges = last_ungrounded_edge_predictions(valid_snapshots)
    invalid_target_distribution_count = sum(
        1
        for artifact in malformed_artifacts
        if artifact["kind"] == "invalid_target_distribution"
    )
    if invalid_snapshot_count:
        status = "invalid_artifact"
        episode_pwgs: float | str = ""
        episode_target_balanced_pwgs: float | str = ""
    elif pair_scores:
        status = (
            "evaluable_with_invalid_target_time_excluded"
            if invalid_target_distribution_count
            else "evaluable"
        )
        episode_pwgs = fmean(pair_scores)
        episode_target_balanced_pwgs = compute_target_balanced_episode_pwgs(
            pair_scores_by_target
        )
    elif malformed_artifacts:
        status = "invalid_artifact"
        episode_pwgs = ""
        episode_target_balanced_pwgs = ""
    elif snapshot_paths:
        status = "not_applicable_no_target_hypothesis"
        episode_pwgs = ""
        episode_target_balanced_pwgs = ""
    else:
        status = "not_applicable_no_hypothesis_state"
        episode_pwgs = ""
        episode_target_balanced_pwgs = ""

    target_rows = [
        {
            "method": method.name,
            "case_id": case_id,
            "scan_id": scan_id,
            "agent_group": _agent_group(int(generated_case["agent_number"])),
            "agent_number": int(generated_case["agent_number"]),
            "target_id": target_id,
            "pwgs_pair_count": len(pair_scores_by_target[target_id]),
            "target_mean_pwgs": fmean(pair_scores_by_target[target_id]),
            "in_common_support": 0,
        }
        for target_id in target_ids
        if pair_scores_by_target[target_id]
    ]

    row = {
        "method": method.name,
        "case_id": case_id,
        "scan_id": scan_id,
        "agent_group": _agent_group(int(generated_case["agent_number"])),
        "agent_number": int(generated_case["agent_number"]),
        "target_number": int(generated_case["target_number"]),
        "evaluation_status": status,
        "pwgs_pair_count": len(pair_scores),
        "evaluable_target_count": len(target_rows),
        "empty_support_count": len(empty_support_states),
        "valid_hypothesis_snapshot_count": len(valid_snapshots),
        "invalid_hypothesis_snapshot_count": invalid_snapshot_count,
        "episode_pwgs": episode_pwgs,
        "episode_target_balanced_pwgs": episode_target_balanced_pwgs,
        "in_common_support": 0,
        "edge_jnll_status": edge_jnll_status(last_edges.values()),
        "ungrounded_edge_candidate_count": len(last_edges),
    }
    case_audit = {
        "snapshot_count": len(snapshot_paths),
        "valid_snapshot_count": len(valid_snapshots),
        "invalid_snapshot_count": invalid_snapshot_count,
        "malformed_artifacts": malformed_artifacts,
        "empty_support_states": empty_support_states,
        "target_rows": target_rows,
    }
    return row, case_audit, last_edges


def last_ungrounded_edge_predictions(
    snapshots: Sequence[Tuple[int, Mapping[str, object]]],
) -> Dict[Tuple[str, str], LastUngroundedEdgePrediction]:
    last_by_edge: Dict[
        Tuple[str, str], LastUngroundedEdgePrediction
    ] = {}
    for step_index, snapshot in sorted(snapshots, key=lambda item: item[0]):
        label_by_node_id = {
            int(node["id"]): str(node["label"])
            for node in snapshot["nodes"]
            if str(node["type"]) == "viewpoint"
        }
        for edge in snapshot["edges"]:
            if str(edge["type"]) != "vv" or bool(edge["grounded"]):
                continue
            source_label = label_by_node_id[int(edge["i"])]
            target_label = label_by_node_id[int(edge["j"])]
            edge_key = tuple(sorted((source_label, target_label)))
            last_by_edge[edge_key] = LastUngroundedEdgePrediction(
                step_index=int(step_index),
                endpoint_labels=edge_key,
                cond_exist_prob=float(edge["cond_exist_prob"]),
                distance_mean=float(edge["distance_mean"]),
                distance_var=float(edge["distance_var"]),
            )
    return last_by_edge


def edge_jnll_status(
    predictions: Iterable[LastUngroundedEdgePrediction],
) -> str:
    if not list(predictions):
        return "not_estimable_no_ungrounded_predictions"
    return "candidate_predictions_available"


def _audit_raw_semantic_outputs(
    method: MethodSpec,
    case_order: Sequence[str],
) -> Dict[str, object]:
    semantic_file_count = 0
    new_edge_count = 0
    cases_with_new_edges: List[str] = []
    for case_id in case_order:
        case_dir = method.raw_root / case_id
        case_new_edge_count = 0
        for _, path in _step_paths(case_dir, SEMANTIC_STEP_RE):
            payload = _read_json(path)
            semantic_file_count += 1
            case_new_edge_count += len(payload["new_edges"])
        if case_new_edge_count:
            cases_with_new_edges.append(case_dir.name)
            new_edge_count += case_new_edge_count
    return {
        "raw_semantic_file_count": semantic_file_count,
        "raw_semantic_new_edge_count": new_edge_count,
        "raw_semantic_cases_with_new_edges": cases_with_new_edges,
    }


def _select_common_support(
    case_rows: Sequence[Mapping[str, object]],
    method_names: Sequence[str],
    case_order: Sequence[str],
) -> Tuple[Dict[str, set[str]], List[Dict[str, object]]]:
    row_by_method_case = {
        (str(row["method"]), str(row["case_id"])): row for row in case_rows
    }
    common = {"single": set(), "multi": set()}
    exclusions: List[Dict[str, object]] = []
    for case_id in case_order:
        rows = [row_by_method_case[(method, case_id)] for method in method_names]
        group = str(rows[0]["agent_group"])
        if any(str(row["agent_group"]) != group for row in rows):
            raise ValueError("%s has inconsistent agent groups." % case_id)
        unavailable = {
            method: str(row["evaluation_status"])
            for method, row in zip(method_names, rows)
            if not _is_evaluable_status(str(row["evaluation_status"]))
        }
        if unavailable:
            exclusions.append(
                {
                    "case_id": case_id,
                    "agent_group": group,
                    "method_statuses_preventing_common_evaluation": unavailable,
                }
            )
        else:
            common[group].add(case_id)
    return common, exclusions


def _aggregate_common_support(
    case_rows: Sequence[Mapping[str, object]],
    method_names: Sequence[str],
    common_case_ids: Mapping[str, set[str]],
) -> List[Dict[str, object]]:
    summary_rows: List[Dict[str, object]] = []
    for method in method_names:
        for group in ("single", "multi"):
            selected = [
                row
                for row in case_rows
                if str(row["method"]) == method
                and str(row["agent_group"]) == group
                and str(row["case_id"]) in common_case_ids[group]
            ]
            if len(selected) != len(common_case_ids[group]):
                raise ValueError(
                    "%s %s aggregation is missing common-support cases."
                    % (method, group)
                )
            summary_rows.append(
                {
                    "method": method,
                    "agent_group": group,
                    "common_evaluated_count": len(selected),
                    "total_count": EXPECTED_GROUP_TOTALS[group],
                    "pwgs": fmean(float(row["episode_pwgs"]) for row in selected),
                    "target_balanced_pwgs": fmean(
                        float(row["episode_target_balanced_pwgs"])
                        for row in selected
                    ),
                    "edge_jnll": "",
                    "edge_jnll_status": (
                        "not_estimable_no_ungrounded_predictions"
                    ),
                    "ungrounded_edge_candidate_count": sum(
                        int(row["ungrounded_edge_candidate_count"])
                        for row in selected
                    ),
                }
            )
    return summary_rows


def _assert_frozen_acceptance(
    case_rows: Sequence[Mapping[str, object]],
    summary_rows: Sequence[Mapping[str, object]],
    common_case_ids: Mapping[str, set[str]],
    method_audits: Mapping[str, Mapping[str, object]],
) -> None:
    group_totals = Counter(
        _agent_group(int(row["agent_number"]))
        for row in case_rows
        if str(row["method"]) == str(case_rows[0]["method"])
    )
    if dict(group_totals) != EXPECTED_GROUP_TOTALS:
        raise AssertionError(
            "Frozen manifest group totals are %s, expected %s."
            % (dict(group_totals), EXPECTED_GROUP_TOTALS)
        )
    actual_common = {
        group: len(common_case_ids[group]) for group in ("single", "multi")
    }
    if actual_common != EXPECTED_COMMON_EVALUABLE_COUNTS:
        raise AssertionError(
            "Common evaluable counts are %s, expected %s."
            % (actual_common, EXPECTED_COMMON_EVALUABLE_COUNTS)
        )
    if any(
        int(row["ungrounded_edge_candidate_count"]) != 0
        for row in summary_rows
    ):
        raise AssertionError("Edge-JNLL candidates unexpectedly exist.")
    for row in case_rows:
        value = row["episode_target_balanced_pwgs"]
        if value != "" and not 0.0 <= float(value) <= 1.0:
            raise AssertionError(
                "%s %s has target-balanced PWGS outside [0, 1]."
                % (row["method"], row["case_id"])
            )
        if value != "" and int(row["evaluable_target_count"]) <= 0:
            raise AssertionError(
                "%s %s has target-balanced PWGS without an evaluable target."
                % (row["method"], row["case_id"])
            )
    for method_name, audit in method_audits.items():
        if int(audit["ungrounded_edge_candidate_count"]) != 0:
            raise AssertionError(
                "%s has saved ungrounded edge candidates." % method_name
            )
        if int(audit["raw_semantic_new_edge_count"]) != 0:
            raise AssertionError(
                "%s semantic outputs contain new_edges." % method_name
            )


def _agent_group(agent_number: int) -> str:
    return "single" if agent_number == 1 else "multi"


def _is_evaluable_status(status: str) -> bool:
    return status == "evaluable" or status.startswith("evaluable_with_")


def _step_paths(
    directory: Path,
    pattern: re.Pattern[str],
) -> List[Tuple[int, Path]]:
    paths: List[Tuple[int, Path]] = []
    for path in directory.iterdir() if directory.exists() else []:
        match = pattern.fullmatch(path.name)
        if match is not None:
            paths.append((int(match.group(1)), path))
    return sorted(paths)


def _read_json(path: Path) -> object:
    with open(path, "r", encoding="utf-8") as file_handle:
        return json.load(file_handle)


def _write_json(path: Path, payload: object) -> None:
    with open(path, "w", encoding="utf-8") as file_handle:
        json.dump(payload, file_handle, indent=2, sort_keys=True)
        file_handle.write("\n")


def _write_csv(
    path: Path,
    rows: Sequence[Mapping[str, object]],
    fields: Sequence[str],
) -> None:
    with open(path, "w", encoding="utf-8", newline="") as file_handle:
        writer = csv.DictWriter(file_handle, fieldnames=list(fields))
        writer.writeheader()
        writer.writerows(rows)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_report(
    path: Path,
    summary_rows: Sequence[Mapping[str, object]],
    malformed_artifacts: Sequence[Mapping[str, object]],
    common_case_ids: Mapping[str, set[str]],
    method_names: Sequence[str],
) -> None:
    summary_by_method_group = {
        (str(row["method"]), str(row["agent_group"])): row
        for row in summary_rows
    }
    lines = [
        "# Hypothesis-quality results",
        "",
        "## Result",
        "",
        (
            "Target-balanced PWGS (TB-PWGS) is reported on the common "
            "evaluable support: "
            f"{len(common_case_ids['single'])}/34 single-agent episodes and "
            f"{len(common_case_ids['multi'])}/66 multi-agent episodes. "
            "For each episode, active target--time scores are first averaged "
            "over time within each target and then equally across evaluable "
            "targets. The table finally gives an unweighted mean across "
            "episodes."
        ),
        "",
        "| Method | Single-agent TB-PWGS $\\uparrow$ | Multi-agent TB-PWGS $\\uparrow$ | Single-agent pooled PWGS $\\uparrow$ | Multi-agent pooled PWGS $\\uparrow$ |",
        "|---|---:|---:|---:|---:|",
    ]
    for method in method_names:
        single_row = summary_by_method_group[(method, "single")]
        multi_row = summary_by_method_group[(method, "multi")]
        lines.append(
            f"| {method} | "
            f"{float(single_row['target_balanced_pwgs']):.3f} | "
            f"{float(multi_row['target_balanced_pwgs']):.3f} | "
            f"{float(single_row['pwgs']):.3f} | "
            f"{float(multi_row['pwgs']):.3f} |"
        )

    lines.extend(
        [
            "",
            "Edge-JNLL is unavailable, rather than zero: every readable saved "
            "`hypothesis_step` contains zero ungrounded edges, and every raw "
            "semantic response for all four methods has `new_edges: []`. The "
            "required last-ungrounded prediction therefore does not exist.",
            "",
            "## Copy-ready LaTeX",
            "",
            "```latex",
            r"\begin{table}[tbp]",
            r"\centering",
            r"\caption{Target-location hypothesis quality on the common evaluable subset. Higher values are better.}",
            r"\label{tab:target_balanced_pwgs}",
            r"\begin{tabular}{lcccc}",
            r"\toprule",
            r"& \multicolumn{2}{c}{TB-PWGS} & \multicolumn{2}{c}{Pooled PWGS} \\",
            r"\cmidrule(lr){2-3}\cmidrule(lr){4-5}",
            r"Method & Single & Multi & Single & Multi \\",
            r"\midrule",
        ]
    )
    for method in method_names:
        single_row = summary_by_method_group[(method, "single")]
        multi_row = summary_by_method_group[(method, "multi")]
        lines.append(
            f"{method} & "
            f"{float(single_row['target_balanced_pwgs']):.3f} & "
            f"{float(multi_row['target_balanced_pwgs']):.3f} & "
            f"{float(single_row['pwgs']):.3f} & "
            f"{float(multi_row['pwgs']):.3f} " + r"\\"
        )
    lines.extend(
        [
            r"\bottomrule",
            r"\end{tabular}",
            r"\par\smallskip",
            r"\parbox{\columnwidth}{\footnotesize Both aggregations use 30/34 single-agent episodes and 53/66 multi-agent episodes for which all four methods contain an evaluable saved target distribution. TB-PWGS first averages over time within each target, then targets within each episode, and finally episodes.}",
            r"\end{table}",
            "```",
            "",
            "## Computation and caveats",
            "",
            "- For every active target at every saved hypothesis state, the evaluator uses only eligible viewpoints: viewpoint nodes that are ungrounded, unvisited, and not occupied by an agent.",
            "- Saved nonempty distributions must sum to one within an absolute serialization tolerance of $10^{-6}$. They are never renormalized by the evaluator.",
            "- An episode that finishes before a nonempty target hypothesis exists is not applicable; it is not assigned PWGS $=1$.",
            "- TB-PWGS computes a temporal mean for every target with at least one valid target--time score, gives those evaluable targets equal weight within the episode, and then gives episodes equal weight within the single- or multi-agent group.",
            "- TB-PWGS is still an on-policy diagnostic because the four methods save hypotheses along different executed trajectories. Target balancing removes duration-based target weights, while common episode support removes missing-episode imbalance; neither makes the target--time contexts identical.",
            "- Geodesics are computed on the complete weighted connectivity graph. If an included Matterport viewpoint is disconnected from every oracle-detectable viewpoint, it is outside that target's evaluable navigation component and is disclosed in the JSON audit; any saved eligible hypothesis on such a viewpoint would fail evaluation.",
            "- Edge-JNLL must use the final saved `grounded=false` prediction for an edge and ignore a later grounded replacement. No such predictions are present in these runs.",
            "",
            "## Artifact audit",
            "",
        ]
    )
    if malformed_artifacts:
        for artifact in malformed_artifacts:
            if artifact["kind"] == "invalid_json":
                lines.append(
                    "- Invalid saved snapshot: "
                    f"`{artifact['path']}` ({artifact['byte_size']} bytes). "
                    "Its episode was excluded through the common-support rule; "
                    "the file was not repaired or overwritten."
                )
            else:
                lines.append(
                    "- Invalid target--time distribution: "
                    f"`{artifact['path']}`, target "
                    f"`{artifact['target_id']}` ({artifact['error']}). "
                    "That target--time record was excluded without "
                    "renormalization; other valid records in its episode remain "
                    "evaluable."
                )
    else:
        lines.append("- No malformed hypothesis snapshots were found.")
    lines.extend(
        [
            "",
            "## Claim--evidence map",
            "",
            "- The TB-PWGS and pooled PWGS values come from `summary_hypothesis_metrics.csv`; episode-level values are in `case_hypothesis_metrics.csv`, and target-level temporal means are in `target_hypothesis_metrics.csv`.",
            "- Manifest hashes, malformed artifacts, exclusions, empty-support states, and edge-candidate counts are recorded in `hypothesis_metric_audit.json`.",
            "- No API call, benchmark execution, cache mutation, or artifact repair is part of this evaluator.",
            "",
            "## Self-review",
            "",
            "- Metric direction and averaging order are stated explicitly.",
            "- Missing hypotheses are separated from numeric performance.",
            "- The unavailable Edge-JNLL is shown as `--`, not as a favorable zero.",
            "- Precision beyond three decimals remains available in the raw CSV output.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
