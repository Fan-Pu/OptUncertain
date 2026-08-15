from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from statistics import fmean
from typing import Iterable, Mapping, Sequence


GROUP_ORDER = ("single", "multi")
SUMMARY_FIELDS = (
    "method",
    "agent_group",
    "case_count",
    "progress",
    "team_ppl_total",
    "team_ppl_makespan",
    "f1",
    "target_balanced_pwgs",
    "mean_total_distance",
    "mean_maximum_agent_distance",
    "tp",
    "fp",
    "fn",
)
CASE_FIELDS = (
    "method",
    "task_metric_method",
    "agent_group",
    "case_id",
    "agent_number",
    "target_number",
    "progress",
    "team_ppl_total",
    "team_ppl_makespan",
    "total_distance",
    "maximum_agent_distance",
    "tp",
    "fp",
    "fn",
    "episode_target_balanced_pwgs",
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Recompute task and target-balanced PWGS metrics on identical "
            "single- and multi-agent common-support case sets."
        )
    )
    parser.add_argument(
        "--method",
        action="append",
        required=True,
        metavar="REPORT_NAME=TASK_METRIC_NAME",
    )
    parser.add_argument(
        "--benchmark-method",
        action="append",
        default=[],
        metavar="REPORT_NAME=TASK_METRIC_NAME@GROUP[,GROUP]",
        help=(
            "Add a task-only benchmark to selected agent groups. Its "
            "TB-PWGS is reported as unavailable."
        ),
    )
    parser.add_argument("--task-case-metrics", type=Path, required=True)
    parser.add_argument("--hypothesis-case-metrics", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def _parse_method_specs(specs: Sequence[str]) -> list[tuple[str, str]]:
    parsed: list[tuple[str, str]] = []
    for spec in specs:
        report_name, separator, task_name = spec.partition("=")
        if not separator or not report_name or not task_name:
            raise ValueError(
                "Each --method must be REPORT_NAME=TASK_METRIC_NAME; received "
                f"{spec!r}."
            )
        parsed.append((report_name, task_name))
    report_names = [report_name for report_name, _ in parsed]
    task_names = [task_name for _, task_name in parsed]
    if len(report_names) != len(set(report_names)):
        raise ValueError("Report method names must be unique.")
    if len(task_names) != len(set(task_names)):
        raise ValueError("Task metric method names must be unique.")
    return parsed


def _parse_benchmark_specs(
    specs: Sequence[str],
) -> list[tuple[str, str, frozenset[str]]]:
    parsed: list[tuple[str, str, frozenset[str]]] = []
    for spec in specs:
        method_spec, group_separator, group_text = spec.rpartition("@")
        report_name, method_separator, task_name = method_spec.partition("=")
        if (
            not group_separator
            or not method_separator
            or not report_name
            or not task_name
            or not group_text
        ):
            raise ValueError(
                "Each --benchmark-method must be "
                "REPORT_NAME=TASK_METRIC_NAME@GROUP[,GROUP]; received "
                f"{spec!r}."
            )
        groups = frozenset(group_text.split(","))
        invalid_groups = groups - set(GROUP_ORDER)
        if invalid_groups:
            raise ValueError(
                f"Invalid benchmark groups for {report_name}: "
                f"{sorted(invalid_groups)}."
            )
        parsed.append((report_name, task_name, groups))
    report_names = [report_name for report_name, _, _ in parsed]
    task_names = [task_name for _, task_name, _ in parsed]
    if len(report_names) != len(set(report_names)):
        raise ValueError("Benchmark report method names must be unique.")
    if len(task_names) != len(set(task_names)):
        raise ValueError("Benchmark task metric method names must be unique.")
    return parsed


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as file_handle:
        return list(csv.DictReader(file_handle))


def _write_csv(
    path: Path,
    rows: Iterable[Mapping[str, object]],
    fieldnames: Sequence[str],
) -> None:
    with path.open("w", encoding="utf-8", newline="") as file_handle:
        writer = csv.DictWriter(file_handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _index_unique(
    rows: Sequence[Mapping[str, str]],
    key_fields: Sequence[str],
) -> dict[tuple[str, ...], Mapping[str, str]]:
    indexed: dict[tuple[str, ...], Mapping[str, str]] = {}
    for row in rows:
        key = tuple(row[field] for field in key_fields)
        if key in indexed:
            raise ValueError(f"Duplicate row for key {key}.")
        indexed[key] = row
    return indexed


def _common_case_ids(
    hypothesis_rows: Sequence[Mapping[str, str]],
    report_methods: Sequence[str],
) -> dict[str, list[str]]:
    case_ids_by_method_group: dict[tuple[str, str], set[str]] = {}
    for report_method in report_methods:
        for group in GROUP_ORDER:
            case_ids_by_method_group[(report_method, group)] = {
                row["case_id"]
                for row in hypothesis_rows
                if row["method"] == report_method
                and row["agent_group"] == group
                and row["in_common_support"] == "1"
            }

    common_by_group: dict[str, list[str]] = {}
    for group in GROUP_ORDER:
        reference_method = report_methods[0]
        reference = case_ids_by_method_group[(reference_method, group)]
        for report_method in report_methods[1:]:
            candidate = case_ids_by_method_group[(report_method, group)]
            if candidate != reference:
                raise ValueError(
                    f"Common-support case IDs differ for {group}: "
                    f"{reference_method} versus {report_method}."
                )
        if not reference:
            raise ValueError(f"No common-support cases found for {group}.")
        common_by_group[group] = sorted(reference)
    return common_by_group


def _micro_f1(tp: int, fp: int, fn: int) -> float:
    denominator = 2 * tp + fp + fn
    if denominator == 0:
        raise ValueError("Micro-F1 is undefined because TP=FP=FN=0.")
    return 2 * tp / denominator


def _aggregate_summary(
    method: str,
    group: str,
    rows: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    if not rows:
        raise ValueError(f"No matched rows for {method} {group}.")
    tp = sum(int(row["tp"]) for row in rows)
    fp = sum(int(row["fp"]) for row in rows)
    fn = sum(int(row["fn"]) for row in rows)

    def mean(field: str) -> float:
        return fmean(float(row[field]) for row in rows)

    return {
        "method": method,
        "agent_group": group,
        "case_count": len(rows),
        "progress": mean("progress"),
        "team_ppl_total": mean("team_ppl_total"),
        "team_ppl_makespan": mean("team_ppl_makespan"),
        "f1": _micro_f1(tp, fp, fn),
        "target_balanced_pwgs": (
            ""
            if all(
                row["episode_target_balanced_pwgs"] == ""
                for row in rows
            )
            else mean("episode_target_balanced_pwgs")
        ),
        "mean_total_distance": mean("total_distance"),
        "mean_maximum_agent_distance": mean("maximum_agent_distance"),
        "tp": tp,
        "fp": fp,
        "fn": fn,
    }


def calculate_matched_metrics(
    method_specs: Sequence[tuple[str, str]],
    task_rows: Sequence[Mapping[str, str]],
    hypothesis_rows: Sequence[Mapping[str, str]],
    benchmark_specs: Sequence[
        tuple[str, str, frozenset[str]]
    ] = (),
) -> tuple[
    list[dict[str, object]],
    list[dict[str, object]],
    dict[str, list[str]],
]:
    report_methods = [report_name for report_name, _ in method_specs]
    common_by_group = _common_case_ids(hypothesis_rows, report_methods)
    task_index = _index_unique(task_rows, ("method", "case_id"))
    hypothesis_index = _index_unique(
        hypothesis_rows,
        ("method", "case_id"),
    )

    case_rows: list[dict[str, object]] = []
    summary_rows: list[dict[str, object]] = []
    for group in GROUP_ORDER:
        for report_method, task_method in method_specs:
            method_case_rows: list[dict[str, object]] = []
            for case_id in common_by_group[group]:
                task_key = (task_method, case_id)
                hypothesis_key = (report_method, case_id)
                if task_key not in task_index:
                    raise ValueError(f"Missing task metric row for {task_key}.")
                if hypothesis_key not in hypothesis_index:
                    raise ValueError(
                        f"Missing hypothesis metric row for {hypothesis_key}."
                    )
                task_row = task_index[task_key]
                hypothesis_row = hypothesis_index[hypothesis_key]
                if hypothesis_row["agent_group"] != group:
                    raise ValueError(
                        f"Agent-group mismatch for {hypothesis_key}: "
                        f"{hypothesis_row['agent_group']} versus {group}."
                    )
                if hypothesis_row["in_common_support"] != "1":
                    raise ValueError(
                        f"Case {hypothesis_key} is not marked common support."
                    )
                row = {
                    "method": report_method,
                    "task_metric_method": task_method,
                    "agent_group": group,
                    "case_id": case_id,
                    "agent_number": int(task_row["agent_number"]),
                    "target_number": int(task_row["target_number"]),
                    "progress": float(task_row["progress"]),
                    "team_ppl_total": float(task_row["team_ppl_total"]),
                    "team_ppl_makespan": float(
                        task_row["team_ppl_makespan"]
                    ),
                    "total_distance": float(task_row["total_distance"]),
                    "maximum_agent_distance": float(
                        task_row["maximum_agent_distance"]
                    ),
                    "tp": int(task_row["tp"]),
                    "fp": int(task_row["fp"]),
                    "fn": int(task_row["fn"]),
                    "episode_target_balanced_pwgs": float(
                        hypothesis_row["episode_target_balanced_pwgs"]
                    ),
                }
                method_case_rows.append(row)
                case_rows.append(row)
            summary_rows.append(
                _aggregate_summary(
                    method=report_method,
                    group=group,
                    rows=method_case_rows,
                )
            )
        for report_method, task_method, included_groups in benchmark_specs:
            if group not in included_groups:
                continue
            method_case_rows = []
            for case_id in common_by_group[group]:
                task_key = (task_method, case_id)
                if task_key not in task_index:
                    raise ValueError(f"Missing task metric row for {task_key}.")
                task_row = task_index[task_key]
                row = {
                    "method": report_method,
                    "task_metric_method": task_method,
                    "agent_group": group,
                    "case_id": case_id,
                    "agent_number": int(task_row["agent_number"]),
                    "target_number": int(task_row["target_number"]),
                    "progress": float(task_row["progress"]),
                    "team_ppl_total": float(task_row["team_ppl_total"]),
                    "team_ppl_makespan": float(
                        task_row["team_ppl_makespan"]
                    ),
                    "total_distance": float(task_row["total_distance"]),
                    "maximum_agent_distance": float(
                        task_row["maximum_agent_distance"]
                    ),
                    "tp": int(task_row["tp"]),
                    "fp": int(task_row["fp"]),
                    "fn": int(task_row["fn"]),
                    "episode_target_balanced_pwgs": "",
                }
                method_case_rows.append(row)
                case_rows.append(row)
            summary_rows.append(
                _aggregate_summary(
                    method=report_method,
                    group=group,
                    rows=method_case_rows,
                )
            )
    return case_rows, summary_rows, common_by_group


def _display_metric(value: object) -> str:
    if value == "":
        return "--"
    return f"{float(value):.3f}"


def _markdown_table(
    rows: Sequence[Mapping[str, object]],
    group: str,
) -> list[str]:
    group_rows = [row for row in rows if row["agent_group"] == group]
    lines = [
        "| Method | Cases | Progress ↑ | Team-PPL Total ↑ | "
        "Team-PPL Makespan ↑ | F1 ↑ | TB-PWGS ↑ |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in group_rows:
        lines.append(
            f"| {row['method']} | {row['case_count']} | "
            f"{_display_metric(row['progress'])} | "
            f"{_display_metric(row['team_ppl_total'])} | "
            f"{_display_metric(row['team_ppl_makespan'])} | "
            f"{_display_metric(row['f1'])} | "
            f"{_display_metric(row['target_balanced_pwgs'])} |"
        )
    return lines


def _markdown_distance_table(
    rows: Sequence[Mapping[str, object]],
    group: str,
) -> list[str]:
    group_rows = [row for row in rows if row["agent_group"] == group]
    lines = [
        "| Method | Mean total distance (m) ↓ | "
        "Mean maximum-agent distance (m) ↓ |",
        "|---|---:|---:|",
    ]
    for row in group_rows:
        lines.append(
            "| {method} | {mean_total_distance:.3f} | "
            "{mean_maximum_agent_distance:.3f} |".format(**row)
        )
    return lines


def _latex_table(
    rows: Sequence[Mapping[str, object]],
    group: str,
) -> list[str]:
    group_rows = [row for row in rows if row["agent_group"] == group]
    title = "single-agent" if group == "single" else "multi-agent"
    case_count = int(group_rows[0]["case_count"])
    lines = [
        r"\begin{table}[t]",
        r"\centering",
        (
            r"\caption{Performance on the common "
            f"{case_count} {title} test cases. All metrics are computed on "
            r"identical cases.}"
        ),
        rf"\label{{tab:common_{group}_metrics}}",
        r"\begin{tabular}{lccccc}",
        r"\toprule",
        r"Method & Progress & \multicolumn{2}{c}{Team-PPL} & F1 & TB-PWGS \\",
        r"\cmidrule(lr){3-4}",
        r" & & Total & Makespan & & \\",
        r"\midrule",
    ]
    for row in group_rows:
        lines.append(
            f"{row['method']} & {_display_metric(row['progress'])} & "
            f"{_display_metric(row['team_ppl_total'])} & "
            f"{_display_metric(row['team_ppl_makespan'])} & "
            f"{_display_metric(row['f1'])} & "
            f"{_display_metric(row['target_balanced_pwgs'])} \\\\"
        )
    lines.extend(
        [
            r"\bottomrule",
            r"\end{tabular}",
            r"\end{table}",
        ]
    )
    return lines


def _write_report(
    path: Path,
    summary_rows: Sequence[Mapping[str, object]],
    common_by_group: Mapping[str, Sequence[str]],
) -> None:
    lines = [
        "# Common-Support Performance Metrics",
        "",
        (
            "All task metrics and Target-Balanced PWGS (TB-PWGS) below use "
            "the identical PWGS-evaluable case set for every method."
        ),
        "",
        (
            f"- Single-agent common support: "
            f"{len(common_by_group['single'])}/34 cases."
        ),
        (
            f"- Multi-agent common support: "
            f"{len(common_by_group['multi'])}/66 cases."
        ),
        (
            "- Progress and both Team-PPL variants are equal-weight episode "
            "means."
        ),
        (
            "- F1 is micro-aggregated after summing TP, FP, and FN over the "
            "matched cases."
        ),
        (
            "- TB-PWGS averages over time within each target, then equally "
            "over targets within each episode, and finally equally over "
            "episodes."
        ),
        (
            "- VLFM-G has no evaluated hypothesis distribution. Dec-Graph "
            "has separate private hypotheses for each agent rather than one "
            "shared team distribution. Their TB-PWGS entries are therefore "
            "reported as unavailable instead of imposing a new fusion rule."
        ),
        "",
        "## Single-agent results",
        "",
        *_markdown_table(summary_rows, "single"),
        "",
        "### Single-agent travel distances",
        "",
        *_markdown_distance_table(summary_rows, "single"),
        "",
        "## Multi-agent results",
        "",
        *_markdown_table(summary_rows, "multi"),
        "",
        "### Multi-agent travel distances",
        "",
        *_markdown_distance_table(summary_rows, "multi"),
        "",
        "## Copy-ready LaTeX",
        "",
        "```latex",
        *_latex_table(summary_rows, "single"),
        "",
        *_latex_table(summary_rows, "multi"),
        "```",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = _parse_args()
    method_specs = _parse_method_specs(args.method)
    benchmark_specs = _parse_benchmark_specs(args.benchmark_method)
    all_report_names = [name for name, _ in method_specs] + [
        name for name, _, _ in benchmark_specs
    ]
    all_task_names = [name for _, name in method_specs] + [
        name for _, name, _ in benchmark_specs
    ]
    if len(all_report_names) != len(set(all_report_names)):
        raise ValueError("All report method names must be unique.")
    if len(all_task_names) != len(set(all_task_names)):
        raise ValueError("All task metric method names must be unique.")
    task_rows = _read_csv(args.task_case_metrics)
    hypothesis_rows = _read_csv(args.hypothesis_case_metrics)
    case_rows, summary_rows, common_by_group = calculate_matched_metrics(
        method_specs=method_specs,
        task_rows=task_rows,
        hypothesis_rows=hypothesis_rows,
        benchmark_specs=benchmark_specs,
    )

    args.output_dir.mkdir(parents=True, exist_ok=False)
    _write_csv(
        args.output_dir / "matched_common_support_case_metrics.csv",
        case_rows,
        CASE_FIELDS,
    )
    _write_csv(
        args.output_dir / "matched_common_support_summary_metrics.csv",
        summary_rows,
        SUMMARY_FIELDS,
    )
    audit = {
        "method_mapping": {
            report_name: task_name
            for report_name, task_name in method_specs
        },
        "benchmark_method_mapping": {
            report_name: {
                "task_metric_method": task_name,
                "included_groups": sorted(groups),
                "target_balanced_pwgs": "not_applicable",
            }
            for report_name, task_name, groups in benchmark_specs
        },
        "source_task_case_metrics": str(args.task_case_metrics),
        "source_hypothesis_case_metrics": str(
            args.hypothesis_case_metrics
        ),
        "common_case_count": {
            group: len(case_ids)
            for group, case_ids in common_by_group.items()
        },
        "common_case_ids": common_by_group,
        "aggregation": {
            "progress": "equal-weight mean across matched episodes",
            "team_ppl_total": "equal-weight mean across matched episodes",
            "team_ppl_makespan": "equal-weight mean across matched episodes",
            "f1": "micro-F1 from summed TP, FP, and FN",
            "target_balanced_pwgs": (
                "time mean within target, equal target mean within episode, "
                "equal episode mean within group"
            ),
        },
    }
    (args.output_dir / "matched_common_support_audit.json").write_text(
        json.dumps(audit, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_report(
        args.output_dir / "matched_common_support_results.md",
        summary_rows=summary_rows,
        common_by_group=common_by_group,
    )
    print(
        f"Wrote {args.output_dir} "
        f"(single={len(common_by_group['single'])}, "
        f"multi={len(common_by_group['multi'])})."
    )


if __name__ == "__main__":
    main()
