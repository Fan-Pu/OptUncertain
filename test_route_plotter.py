from __future__ import annotations

import json
import math

import pytest

from route_plotter import load_environment_graph


def _pose(x: float, y: float, z: float) -> list[float]:
    pose = [0.0] * 16
    pose[3] = x
    pose[7] = y
    pose[11] = z
    return pose


def test_environment_graph_uses_xy_for_display_coordinates(tmp_path):
    connectivity_dir = tmp_path / "connectivity"
    connectivity_dir.mkdir()
    (connectivity_dir / "scan_connectivity.json").write_text(
        json.dumps(
            [
                {
                    "image_id": "vp0",
                    "included": True,
                    "pose": _pose(1.0, 2.0, 100.0),
                    "unobstructed": [False, True],
                },
                {
                    "image_id": "vp1",
                    "included": True,
                    "pose": _pose(5.0, 7.0, 106.0),
                    "unobstructed": [True, False],
                },
            ]
        ),
        encoding="utf-8",
    )

    graph = load_environment_graph("scan", connectivity_dir=connectivity_dir)

    assert graph.coords_by_node_id[0] == (1.0, 2.0)
    assert graph.coords_by_node_id[1] == (5.0, 7.0)
    assert graph.edge_distances[(0, 1)] == pytest.approx(
        math.sqrt(4.0**2 + 5.0**2 + 6.0**2)
    )
