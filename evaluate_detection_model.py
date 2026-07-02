from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Dict, Iterable, List, Sequence


def _read_json(path: str | Path) -> object:
    with open(path, "r", encoding="utf-8") as file_handle:
        return json.load(file_handle)


def _ratio(numerator: int, denominator: int) -> float:
    return float(numerator) / float(denominator) if int(denominator) else 0.0


def _f1(tp: int, fp: int, fn: int) -> float:
    denominator = 2 * int(tp) + int(fp) + int(fn)
    return float(2 * int(tp)) / float(denominator) if denominator else 0.0


def _debug_root_for_run(run_id: str) -> Path:
    return Path("mllm_debug_outputs_%s" % str(run_id))


def _run_id_for_model(model_name: str) -> str:
    model_slug = re.sub(r"[^A-Za-z0-9._-]+", "_", str(model_name).strip())
    model_slug = re.sub(r"_+", "_", model_slug).strip("._-")
    if not model_slug:
        model_slug = "unknown_model"
    return "detection_eval_%s" % model_slug


def _selected_case_ids(
    summary: Dict[str, object],
    sample_count: int | None,
    sample_seed: int,
    sample_balance: str,
    case_ids: Sequence[str],
) -> List[str]:
    from main import _case_order_from_batch_summary, sample_batch_case_ids

    if case_ids:
        missing = [case_id for case_id in case_ids if case_id not in summary["cases"]]
        if missing:
            raise KeyError("Unknown generated batch case ids: %s" % ", ".join(missing))
        return [str(case_id) for case_id in case_ids]

    if sample_count is None:
        return _case_order_from_batch_summary(summary)

    return sample_batch_case_ids(
        summary=summary,
        sample_count=int(sample_count),
        sample_seed=int(sample_seed),
        sample_balance=str(sample_balance),
    )


def _read_case_id_file(path: str | Path) -> List[str]:
    case_ids = []
    with open(path, "r", encoding="utf-8") as file_handle:
        for line in file_handle:
            text = line.strip()
            if not text or text.startswith("#"):
                continue
            case_ids.append(text)
    return case_ids


def _target_visibility_by_scan(
    batch_config: Dict[str, object],
) -> Dict[str, Dict[str, set[str]]]:
    visibility_by_scan = {}
    for scan in batch_config["scans"]:
        scan_id = str(scan["scan_id"])
        visibility_by_scan[scan_id] = {
            str(target["target_id"]): {
                str(viewpoint_id)
                for viewpoint_id in target.get("detectable_viewpoint_ids", [])
            }
            for target in scan["targets"]
        }
    return visibility_by_scan


def _normalize_targets(targets: Iterable[Dict[str, object]]) -> List[Dict[str, object]]:
    return [
        {
            "target_id": str(target["target_id"]),
            "description": str(target["description"]),
        }
        for target in targets
    ]


def _prediction_map(detections: Sequence[Dict[str, object]]) -> Dict[str, set[str]]:
    predicted_by_agent: Dict[str, set[str]] = {}
    for detection in detections:
        agent_id = str(detection["agent_id"])
        predicted_by_agent.setdefault(agent_id, set()).update(
            str(target_id) for target_id in detection["found_target_indices"]
        )
    return predicted_by_agent


def _center_x_map(
    detections: Sequence[Dict[str, object]],
) -> Dict[tuple[str, str], float]:
    centers = {}
    for detection in detections:
        agent_id = str(detection["agent_id"])
        for target_id, center_x in zip(
            detection["found_target_indices"],
            detection["target_center_xs"],
        ):
            centers[(agent_id, str(target_id))] = float(center_x)
    return centers


def _api_config_defaults(
    mllm: Dict[str, object],
    prefix: str,
) -> tuple[str, str, str]:
    from semantic_persistence import MLLMClient

    api_type = str(mllm.get("%s_api_type" % prefix, "chat_completions"))
    normalized_api_type = MLLMClient._normalize_api_type(
        api_type,
        "%s_api_type" % prefix,
    )
    if normalized_api_type == "google_genai":
        default_base_url = ""
        default_api_key_env = "GEMINI_API_KEY"
    elif normalized_api_type == "openai_responses":
        default_base_url = ""
        default_api_key_env = "OPENAI_API_KEY"
    else:
        default_base_url = "https://router.huggingface.co/v1"
        default_api_key_env = "HF_TOKEN"

    base_url = str(mllm.get("%s_base_url" % prefix, default_base_url))
    api_key_env = str(mllm.get("%s_api_key_env" % prefix, default_api_key_env))
    if normalized_api_type == "google_genai":
        if base_url == "https://router.huggingface.co/v1":
            base_url = ""
        if api_key_env == "HF_TOKEN":
            api_key_env = "GEMINI_API_KEY"
    elif normalized_api_type == "openai_responses":
        if base_url == "https://router.huggingface.co/v1":
            base_url = ""
        if api_key_env == "HF_TOKEN":
            api_key_env = "OPENAI_API_KEY"

    return (normalized_api_type, base_url, api_key_env)


def _init_detection_client(scenario: Dict[str, object]):
    from semantic_persistence import MLLMClient

    mllm = scenario["mllm"]
    detection_api_type, detection_base_url, detection_api_key_env = (
        _api_config_defaults(mllm, "detection")
    )
    graph_api_type, graph_base_url, graph_api_key_env = _api_config_defaults(
        mllm,
        "graph",
    )
    return MLLMClient(
        graph_model_name=str(mllm["graph_model_name"]),
        detection_model_name=str(mllm["detection_model_name"]),
        detection_base_url=detection_base_url,
        detection_api_key_env=detection_api_key_env,
        detection_api_type=detection_api_type,
        graph_base_url=graph_base_url,
        graph_api_key_env=graph_api_key_env,
        graph_api_type=graph_api_type,
        read_saved_raw_outputs=bool(mllm.get("read_saved_raw_outputs", False)),
        raw_output_dir=str(mllm["raw_output_dir"]),
        raw_debug_dir=str(mllm["debug_output_dir"]),
        request_timeout=float(mllm.get("request_timeout", 120.0)),
        max_validation_retries=int(mllm.get("max_validation_retries", 2)),
        max_request_timeout_retries=int(mllm.get("max_request_timeout_retries", 1)),
        graph_thinking=mllm.get("graph_thinking"),
        graph_thinking_format=mllm.get("graph_thinking_format"),
        graph_reasoning_split=mllm.get("graph_reasoning_split", False),
        detection_reasoning_effort=mllm.get("detection_reasoning_effort"),
        graph_reasoning_effort=mllm.get("graph_reasoning_effort"),
        detection_service_tier=mllm.get("detection_service_tier"),
        graph_service_tier=mllm.get("graph_service_tier"),
    )


def _render_case_observations(scenario: Dict[str, object]):
    import Helper
    from main import _init_agent_sims

    scan_id = str(scenario["scan_id"])
    Helper.build_viewpoint_index(scan_id)
    sims = _init_agent_sims(scenario=scenario, scan_id=scan_id)
    agent_ids = [str(agent["id"]) for agent in scenario["agents"]]
    return Helper.horizon_scan_individual_sims_return(
        sims=sims,
        agent_ids=agent_ids,
        viewpoint_index_by_vp=Helper.viewpoint_index_by_vp_label,
    )


def _score_case(
    scenario: Dict[str, object],
    detections: Sequence[Dict[str, object]],
    observations: Sequence[Dict[str, object]],
    visibility_by_scan: Dict[str, Dict[str, set[str]]],
) -> tuple[Dict[str, object], List[Dict[str, object]]]:
    case_id = str(scenario["test_case"])
    scan_id = str(scenario["scan_id"])
    targets = _normalize_targets(scenario["targets"])
    predicted_by_agent = _prediction_map(detections)
    center_by_agent_target = _center_x_map(detections)
    detectable_by_target = visibility_by_scan[scan_id]
    target_by_id = {str(target["target_id"]): target for target in targets}

    rows = []
    tp = fp = fn = tn = 0
    for observation in observations:
        agent_id = str(observation["agent_id"])
        viewpoint_id = str(observation["current_viewpoint_id"])
        viewpoint_index = int(observation["current_viewpoint_index"])
        predicted_target_ids = predicted_by_agent.get(agent_id, set())
        for target_id in sorted(target_by_id):
            oracle_visible = viewpoint_id in detectable_by_target[target_id]
            predicted = target_id in predicted_target_ids
            if predicted and oracle_visible:
                outcome = "tp"
                tp += 1
            elif predicted and not oracle_visible:
                outcome = "fp"
                fp += 1
            elif (not predicted) and oracle_visible:
                outcome = "fn"
                fn += 1
            else:
                outcome = "tn"
                tn += 1

            rows.append(
                {
                    "case_id": case_id,
                    "scan_id": scan_id,
                    "agent_id": agent_id,
                    "viewpoint_id": viewpoint_id,
                    "viewpoint_index": viewpoint_index,
                    "target_id": target_id,
                    "target_description": str(target_by_id[target_id]["description"]),
                    "oracle_visible": int(oracle_visible),
                    "predicted": int(predicted),
                    "target_center_x": center_by_agent_target.get(
                        (agent_id, target_id), ""
                    ),
                    "outcome": outcome,
                }
            )

    case_metrics = {
        "case_id": case_id,
        "scan_id": scan_id,
        "agent_count": len(observations),
        "target_count": len(targets),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": _ratio(tp, tp + fp),
        "recall": _ratio(tp, tp + fn),
        "f1": _f1(tp, fp, fn),
    }
    return case_metrics, rows


def _write_csv(
    path: Path, rows: Sequence[Dict[str, object]], fieldnames: Sequence[str]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as file_handle:
        writer = csv.DictWriter(file_handle, fieldnames=list(fieldnames))
        writer.writeheader()
        writer.writerows(rows)


def _run_detection_case(
    scenario: Dict[str, object],
    visibility_by_scan: Dict[str, Dict[str, set[str]]],
) -> tuple[Dict[str, object], List[Dict[str, object]], Dict[str, object]]:
    client = _init_detection_client(scenario)
    observations = _render_case_observations(scenario)
    targets = _normalize_targets(scenario["targets"])
    image_content, image_records = client._build_detection_image_content(
        agent_observations=list(observations),
        step_index=1,
    )
    detections = client._detect_targets(
        agent_observations=list(observations),
        targets=targets,
        image_content=image_content,
        detection_image_records=image_records,
        step_index=1,
    )
    case_metrics, target_rows = _score_case(
        scenario=scenario,
        detections=detections,
        observations=observations,
        visibility_by_scan=visibility_by_scan,
    )
    prediction_record = {
        "case_id": str(scenario["test_case"]),
        "scan_id": str(scenario["scan_id"]),
        "raw_output_dir": str(scenario["mllm"]["raw_output_dir"]),
        "debug_output_dir": str(scenario["mllm"]["debug_output_dir"]),
        "detections": list(detections),
    }
    return case_metrics, target_rows, prediction_record


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate the detection MLLM alone on generated batch-test panoramas."
        )
    )
    parser.add_argument(
        "--batch-config",
        default="scenarios/batch_test.json",
        help="Batch config to generate/select cases from.",
    )
    parser.add_argument(
        "--run-id",
        help=(
            "Isolated output suffix. Defaults to detection_eval_<detection model name> "
            "with path-unsafe characters replaced by underscores."
        ),
    )
    parser.add_argument(
        "--sample-count",
        type=int,
        default=30,
        help="Balanced number of generated cases to evaluate. Ignored with --case-id.",
    )
    parser.add_argument(
        "--sample-seed",
        type=int,
        default=0,
        help="Tie-break seed for balanced case sampling.",
    )
    parser.add_argument(
        "--sample-balance",
        choices=("marginal", "param_config"),
        default="marginal",
        help=(
            "Sampling balance mode. 'marginal' preserves the existing sampler; "
            "'param_config' balances full generated parameter configurations."
        ),
    )
    parser.add_argument(
        "--case-id",
        action="append",
        default=[],
        help="Specific generated case id to evaluate. Can be repeated.",
    )
    parser.add_argument(
        "--case-id-file",
        help="Text file with one generated case id per line. Disables sampling.",
    )
    parser.add_argument(
        "--out",
        help=(
            "Output metrics directory. Defaults to "
            "mllm_debug_outputs_<run_id>/<batch_id>/detection_metrics."
        ),
    )
    args = parser.parse_args(argv)

    from main import (
        load_default_config,
        load_or_generate_batch_scenarios,
        merge_batch_config_overrides,
        write_sampled_batch_manifests,
    )

    batch_config_path = Path(args.batch_config)
    batch_config = _read_json(batch_config_path)
    if not isinstance(batch_config, dict):
        raise TypeError("Batch config must be a JSON object.")

    batch_id = batch_config_path.stem
    default_config = merge_batch_config_overrides(
        load_default_config(),
        batch_config=batch_config,
    )
    detection_model_name = str(default_config["mllm"]["detection_model_name"])
    run_id = (
        str(args.run_id) if args.run_id else _run_id_for_model(detection_model_name)
    )

    scenarios, summary, _summary_path = load_or_generate_batch_scenarios(
        batch_config=batch_config,
        batch_id=batch_id,
        default_config=default_config,
        run_id=run_id,
    )
    explicit_case_ids = list(args.case_id)
    if args.case_id_file:
        explicit_case_ids.extend(_read_case_id_file(args.case_id_file))
    case_ids = _selected_case_ids(
        summary=summary,
        sample_count=None if explicit_case_ids else int(args.sample_count),
        sample_seed=int(args.sample_seed),
        sample_balance=str(args.sample_balance),
        case_ids=explicit_case_ids,
    )
    scenario_by_case_id = {
        str(scenario["test_case"]): scenario for scenario in scenarios
    }
    selected_scenarios = [scenario_by_case_id[case_id] for case_id in case_ids]

    write_sampled_batch_manifests(
        batch_id=batch_id,
        summary=summary,
        sampled_case_ids=case_ids,
        sample_count=len(case_ids),
        sample_seed=int(args.sample_seed),
        run_id=run_id,
        sample_balance=str(args.sample_balance),
    )

    output_dir = (
        Path(args.out)
        if args.out
        else _debug_root_for_run(run_id) / batch_id / "detection_metrics"
    )
    visibility_by_scan = _target_visibility_by_scan(batch_config)

    case_rows = []
    target_rows = []
    prediction_records = []
    for scenario in selected_scenarios:
        print("Running detection benchmark case %s." % str(scenario["test_case"]))
        case_metrics, rows, predictions = _run_detection_case(
            scenario=scenario,
            visibility_by_scan=visibility_by_scan,
        )
        case_rows.append(case_metrics)
        target_rows.extend(rows)
        prediction_records.append(predictions)

    total_tp = sum(int(row["tp"]) for row in case_rows)
    total_fp = sum(int(row["fp"]) for row in case_rows)
    total_fn = sum(int(row["fn"]) for row in case_rows)
    total_tn = sum(int(row["tn"]) for row in case_rows)
    method_rows = [
        {
            "case_count": len(case_rows),
            "agent_target_pairs": total_tp + total_fp + total_fn + total_tn,
            "tp": total_tp,
            "fp": total_fp,
            "fn": total_fn,
            "tn": total_tn,
            "precision": _ratio(total_tp, total_tp + total_fp),
            "recall": _ratio(total_tp, total_tp + total_fn),
            "f1": _f1(total_tp, total_fp, total_fn),
        }
    ]

    output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(
        output_dir / "detection_case_metrics.csv",
        case_rows,
        [
            "case_id",
            "scan_id",
            "agent_count",
            "target_count",
            "tp",
            "fp",
            "fn",
            "tn",
            "precision",
            "recall",
            "f1",
        ],
    )
    _write_csv(
        output_dir / "detection_target_metrics.csv",
        target_rows,
        [
            "case_id",
            "scan_id",
            "agent_id",
            "viewpoint_id",
            "viewpoint_index",
            "target_id",
            "target_description",
            "oracle_visible",
            "predicted",
            "target_center_x",
            "outcome",
        ],
    )
    _write_csv(
        output_dir / "detection_method_metrics.csv",
        method_rows,
        [
            "case_count",
            "agent_target_pairs",
            "tp",
            "fp",
            "fn",
            "tn",
            "precision",
            "recall",
            "f1",
        ],
    )
    with open(
        output_dir / "detection_predictions.json", "w", encoding="utf-8"
    ) as file_handle:
        json.dump(
            {
                "batch_config": str(batch_config_path),
                "run_id": run_id,
                "detection_model_name": detection_model_name,
                "detection_reasoning_effort": default_config["mllm"].get(
                    "detection_reasoning_effort"
                ),
                "detection_service_tier": default_config["mllm"].get(
                    "detection_service_tier"
                ),
                "case_order": case_ids,
                "predictions": prediction_records,
            },
            file_handle,
            indent=2,
        )
        file_handle.write("\n")

    print("Detection model: %s" % detection_model_name)
    print("Run id: %s" % run_id)
    print(
        "Wrote detection case metrics to %s"
        % str(output_dir / "detection_case_metrics.csv")
    )
    print(
        "Wrote detection target metrics to %s"
        % str(output_dir / "detection_target_metrics.csv")
    )
    print(
        "Wrote detection method metrics to %s"
        % str(output_dir / "detection_method_metrics.csv")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
