import random

from route_plotter import EnvironmentGraph

import main


class FirstChoice:
    def choice(self, values):
        return list(values)[0]


def _line_graph():
    return EnvironmentGraph(
        scan_id="scan",
        viewpoint_id_by_index={
            0: "vp0",
            1: "vp1",
            2: "vp2",
            3: "vp3",
        },
        coords_by_node_id={
            0: (0.0, 0.0),
            1: (1.0, 0.0),
            2: (2.0, 0.0),
            3: (3.0, 0.0),
        },
        edge_distances={
            (0, 1): 1.0,
            (1, 2): 1.0,
            (2, 3): 1.0,
        },
    )


def test_select_spread_viewpoint_ids_is_unique():
    selected = main._select_spread_viewpoint_ids(
        environment_graph=_line_graph(),
        agent_number=4,
        random_source=random.Random(3),
    )

    assert len(selected) == 4
    assert len(set(selected)) == 4


def test_select_spread_viewpoint_ids_uses_maximin_shortest_path_distance():
    selected = main._select_spread_viewpoint_ids(
        environment_graph=_line_graph(),
        agent_number=3,
        random_source=FirstChoice(),
    )

    assert selected == ["vp0", "vp3", "vp1"]


def test_select_spread_viewpoint_ids_tie_breaking_is_seeded():
    first = main._select_spread_viewpoint_ids(
        environment_graph=_line_graph(),
        agent_number=3,
        random_source=random.Random(11),
    )
    second = main._select_spread_viewpoint_ids(
        environment_graph=_line_graph(),
        agent_number=3,
        random_source=random.Random(11),
    )

    assert first == second
