from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

DEFAULT_CONNECTIVITY_DIR = Path("/root/mount/Matterport3DSimulator/connectivity")


@dataclass
class EnvironmentGraph:
    scan_id: str
    viewpoint_id_by_index: Dict[int, str]
    coords_by_node_id: Dict[int, Tuple[float, float]]
    edge_distances: Dict[Tuple[int, int], float]


def load_environment_graph(
    scan_id: str,
    connectivity_dir: str | Path | None = None,
) -> EnvironmentGraph:
    connectivity_root = (
        Path(connectivity_dir)
        if connectivity_dir is not None
        else Path(
            os.environ.get("MATTERPORT_CONNECTIVITY_DIR", DEFAULT_CONNECTIVITY_DIR)
        )
    )
    connectivity = _read_json(connectivity_root / ("%s_connectivity.json" % scan_id))

    index_by_original_index = {}
    viewpoint_id_by_index = {}
    position_by_index = {}

    for original_index, item in enumerate(connectivity):
        if not bool(item["included"]):
            continue
        node_id = len(index_by_original_index)
        index_by_original_index[original_index] = node_id
        viewpoint_id_by_index[node_id] = str(item["image_id"])
        position_by_index[node_id] = _pose_xyz(item["pose"])

    edge_distances = {}
    for original_index, item in enumerate(connectivity):
        if original_index not in index_by_original_index:
            continue
        source_id = index_by_original_index[original_index]
        for neighbor_original_index, unobstructed in enumerate(item["unobstructed"]):
            if not bool(unobstructed):
                continue
            if neighbor_original_index not in index_by_original_index:
                continue
            target_id = index_by_original_index[neighbor_original_index]
            if source_id == target_id:
                continue
            edge_id = tuple(sorted((source_id, target_id)))
            if edge_id in edge_distances:
                continue
            edge_distances[edge_id] = math.dist(
                position_by_index[source_id],
                position_by_index[target_id],
            )

    return EnvironmentGraph(
        scan_id=str(scan_id),
        viewpoint_id_by_index=viewpoint_id_by_index,
        coords_by_node_id={
            node_id: (position[0], position[2])
            for node_id, position in position_by_index.items()
        },
        edge_distances=edge_distances,
    )


def summarize_agent_routes(
    environment_graph: EnvironmentGraph,
    routes_by_agent: Dict[str, List[int]],
) -> List[Dict[str, object]]:
    summaries = []
    for agent_id, route_node_ids_raw in routes_by_agent.items():
        route_node_ids = [int(node_id) for node_id in route_node_ids_raw]
        edge_distances = [
            environment_graph.edge_distances[tuple(sorted((source_id, target_id)))]
            for source_id, target_id in zip(route_node_ids, route_node_ids[1:])
        ]
        summaries.append(
            {
                "agent_id": str(agent_id),
                "route_node_ids": route_node_ids,
                "route_viewpoint_ids": [
                    environment_graph.viewpoint_id_by_index[node_id]
                    for node_id in route_node_ids
                ],
                "edge_distances": edge_distances,
                "path_distance": sum(edge_distances),
            }
        )
    return summaries


def summarize_routes(
    test_case: str,
    environment_graph: EnvironmentGraph,
    routes_by_agent: Dict[str, List[int]],
    target_node_ids_by_target_id: Dict[str, int],
) -> Dict[str, object]:
    agent_summaries = summarize_agent_routes(
        environment_graph=environment_graph,
        routes_by_agent=routes_by_agent,
    )
    return {
        "test_case": str(test_case),
        "agents": agent_summaries,
        "total_distance": sum(
            float(agent_summary["path_distance"]) for agent_summary in agent_summaries
        ),
        "target_node_ids_by_target_id": {
            str(target_id): int(node_id)
            for target_id, node_id in target_node_ids_by_target_id.items()
        },
    }


def plot_environment_routes(
    environment_graph: EnvironmentGraph,
    agent_summaries: List[Dict[str, object]],
    output_path: str | Path,
    title: str,
    target_node_ids_by_target_id: Dict[str, int],
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    colors = [
        "#d62728",
        "#1f77b4",
        "#2ca02c",
        "#ff7f0e",
        "#9467bd",
        "#17becf",
    ]

    fig, ax = plt.subplots(figsize=(10, 8))
    for source_id, target_id in sorted(environment_graph.edge_distances):
        x0, y0 = environment_graph.coords_by_node_id[source_id]
        x1, y1 = environment_graph.coords_by_node_id[target_id]
        ax.plot([x0, x1], [y0, y1], color="#c7c7c7", linewidth=0.8, zorder=1)

    xs = [coord[0] for coord in environment_graph.coords_by_node_id.values()]
    ys = [coord[1] for coord in environment_graph.coords_by_node_id.values()]
    ax.scatter(xs, ys, s=14, color="#4d4d4d", zorder=2, label="Viewpoints")

    for agent_index, agent_summary in enumerate(agent_summaries):
        color = colors[agent_index % len(colors)]
        route_node_ids = [int(node_id) for node_id in agent_summary["route_node_ids"]]
        route_xs = [
            environment_graph.coords_by_node_id[node_id][0]
            for node_id in route_node_ids
        ]
        route_ys = [
            environment_graph.coords_by_node_id[node_id][1]
            for node_id in route_node_ids
        ]
        ax.plot(
            route_xs,
            route_ys,
            color=color,
            linewidth=2.8,
            marker="o",
            markersize=5,
            zorder=4,
            label=str(agent_summary["agent_id"]),
        )
        start_node_id = route_node_ids[0]
        ax.scatter(
            [environment_graph.coords_by_node_id[start_node_id][0]],
            [environment_graph.coords_by_node_id[start_node_id][1]],
            color=color,
            marker="s",
            s=90,
            edgecolors="black",
            zorder=5,
            label="%s start" % str(agent_summary["agent_id"]),
        )

    for target_id, node_id in target_node_ids_by_target_id.items():
        x, y = environment_graph.coords_by_node_id[int(node_id)]
        ax.scatter(
            [x],
            [y],
            marker="*",
            s=180,
            color="#f2c300",
            edgecolors="black",
            zorder=6,
            label="target %s" % str(target_id),
        )
        ax.annotate(
            str(target_id),
            (x, y),
            xytext=(6, 6),
            textcoords="offset points",
            fontsize=9,
            color="black",
        )

    ax.set_title(title)
    ax.set_xlabel("Matterport pose x")
    ax.set_ylabel("Matterport pose z")
    ax.set_aspect("equal", adjustable="datalim")
    ax.legend(loc="best", fontsize=8)
    ax.grid(True, color="#eeeeee", linewidth=0.6)
    fig.tight_layout()
    fig.savefig(output_path, dpi=200)
    plt.close(fig)


def print_route_summary(summary: Dict[str, object], title: str) -> None:
    print(title)
    print("Target viewpoint indices:")
    for target_id, node_id in sorted(summary["target_node_ids_by_target_id"].items()):
        print("  target %s: %s" % (target_id, node_id))
    print()

    for agent_summary in summary["agents"]:
        print("Agent %s" % agent_summary["agent_id"])
        print("  route node indices: %s" % agent_summary["route_node_ids"])
        print("  route viewpoint ids: %s" % agent_summary["route_viewpoint_ids"])
        print(
            "  edge distances: %s"
            % [
                round(float(distance), 6)
                for distance in agent_summary["edge_distances"]
            ]
        )
        print("  path distance: %.6f" % float(agent_summary["path_distance"]))
        print()

    print("Sum of all path distances: %.6f" % float(summary["total_distance"]))
    print("Route plot: %s" % summary["plot_path"])


def _read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _pose_xyz(pose: List[float]) -> Tuple[float, float, float]:
    return (float(pose[3]), float(pose[7]), float(pose[11]))
