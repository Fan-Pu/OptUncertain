from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List


def write_optimizer_route_log(
    output_dir: str | Path,
    test_case: str,
    optimization_result: Dict[str, object],
    agent_ids: List[str],
    step_index: int | None,
    filename: str | None = None,
) -> Path:
    payload = build_optimizer_route_log_payload(
        test_case=test_case,
        optimization_result=optimization_result,
        agent_ids=agent_ids,
        step_index=step_index,
    )
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    output_path = output_root / (
        filename
        if filename is not None
        else "optimizer_routes_step_%04d.json" % int(step_index)
    )
    with open(output_path, "w", encoding="utf-8") as route_file_handle:
        json.dump(payload, route_file_handle, indent=2)
    return output_path


def build_optimizer_route_log_payload(
    test_case: str,
    optimization_result: Dict[str, object],
    agent_ids: List[str],
    step_index: int | None,
) -> Dict[str, object]:
    agent_paths = optimization_result["agent_paths"]
    return {
        "solver": optimization_result["solver"],
        "target_assignments": optimization_result["target_assignments"],
        "agents": [
            {
                "agent_id": str(agent_id),
                "route_node_ids": [
                    int(node_id)
                    for node_id in agent_paths[agent_id]["route_node_ids"]
                ],
                "objective_terms": agent_paths[agent_id]["objective_terms"],
            }
            for agent_id in agent_ids
        ],
    }
