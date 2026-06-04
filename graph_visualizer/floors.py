from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path


MIN_FLOOR_GAP_METERS = 0.5
MIN_FLOOR_SUPPORT_FRACTION = 0.1


@dataclass(frozen=True)
class ConnectivityViewpoint:
    node_id: int
    viewpoint_id: str
    x: float
    y: float
    z: float


def load_connectivity_viewpoints(connectivity_path: Path) -> list[ConnectivityViewpoint]:
    connectivity = json.loads(connectivity_path.read_text(encoding="utf-8"))
    viewpoints: list[ConnectivityViewpoint] = []
    for item in connectivity:
        if not bool(item["included"]):
            continue
        pose = item["pose"]
        viewpoints.append(
            ConnectivityViewpoint(
                node_id=len(viewpoints),
                viewpoint_id=str(item["image_id"]),
                x=float(pose[3]),
                y=float(pose[7]),
                z=float(pose[11]),
            )
        )
    return viewpoints


def infer_floors(viewpoints: list[ConnectivityViewpoint]) -> list[dict[str, object]]:
    ordered = sorted(viewpoints, key=lambda item: (item.z, item.node_id))
    partitions = _select_z_partitions([item.z for item in ordered])
    floors = []
    for floor_index, (start, end) in enumerate(partitions):
        floor_viewpoints = ordered[start:end]
        zs = [item.z for item in floor_viewpoints]
        floors.append(
            {
                "floor_index": floor_index,
                "reference_z": float(sum(zs) / len(zs)),
                "z_min": float(min(zs)),
                "z_max": float(max(zs)),
                "node_ids": sorted(int(item.node_id) for item in floor_viewpoints),
            }
        )
    return floors


def floor_index_by_node_id(floors: list[dict[str, object]]) -> dict[int, int]:
    result = {}
    for floor in floors:
        floor_index = int(floor["floor_index"])
        for node_id in floor["node_ids"]:
            result[int(node_id)] = floor_index
    return result


def _select_z_partitions(z_values: list[float]) -> list[tuple[int, int]]:
    n = len(z_values)
    min_support = max(2, math.ceil(n * MIN_FLOOR_SUPPORT_FRACTION))
    candidate_gaps = {
        index + 1: z_values[index + 1] - z_values[index]
        for index in range(n - 1)
        if z_values[index + 1] - z_values[index] >= MIN_FLOOR_GAP_METERS
    }
    endpoints = [0, *sorted(candidate_gaps), n]
    best_score = {0: 0.0}
    best_previous: dict[int, int] = {}
    for end in endpoints[1:]:
        for start in endpoints:
            if start >= end:
                break
            if start not in best_score or end - start < min_support:
                continue
            score = best_score[start]
            if start > 0:
                score += candidate_gaps[start]
            if end not in best_score or score > best_score[end]:
                best_score[end] = score
                best_previous[end] = start

    cuts = []
    end = n
    while end in best_previous:
        start = best_previous[end]
        if start > 0:
            cuts.append(start)
        end = start
    cuts.reverse()

    partitions = []
    start = 0
    for end in [*cuts, len(z_values)]:
        partitions.append((start, end))
        start = end
    return partitions
