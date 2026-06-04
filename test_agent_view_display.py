import importlib
from pathlib import Path
from types import SimpleNamespace


class FakeSim:
    def __init__(self):
        self.state = SimpleNamespace(
            heading=0.0,
            navigableLocations=[
                SimpleNamespace(viewpointId="current"),
                SimpleNamespace(viewpointId="next"),
            ],
        )
        self.actions = []

    def getState(self):
        return [self.state]

    def makeAction(self, location_indices, headings, elevations):
        self.actions.append((list(location_indices), list(headings), list(elevations)))
        self.state.heading += float(headings[0])


def test_execute_individual_rotations_can_skip_render(monkeypatch):
    Helper = importlib.import_module("Helper")
    render_calls = []
    sim = FakeSim()

    monkeypatch.setattr(
        Helper,
        "render_sim_state",
        lambda *args, **kwargs: render_calls.append((args, kwargs)),
    )

    Helper.execute_individual_rotations(
        sims=[sim],
        target_headings=[Helper.DELTA_HEADING_RAD],
        notifications=["Target target0 is found."],
        render=False,
    )

    assert len(sim.actions) == 1
    assert render_calls == []


def test_execute_individual_first_hops_can_skip_render(monkeypatch):
    Helper = importlib.import_module("Helper")
    render_calls = []
    sim = FakeSim()

    monkeypatch.setattr(
        Helper,
        "render_sim_state",
        lambda *args, **kwargs: render_calls.append((args, kwargs)),
    )

    Helper.execute_individual_first_hops(
        sims=[sim],
        move_specs=[
            {
                "target_heading": Helper.DELTA_HEADING_RAD,
                "target_viewpoint_id": "next",
            }
        ],
        render=False,
    )

    assert len(sim.actions) == 2
    assert sim.actions[-1] == ([1], [0.0], [0.0])
    assert render_calls == []


def test_main_hide_agent_views_passes_false_to_run_scenario(monkeypatch):
    main = importlib.import_module("main")
    calls = []

    monkeypatch.setattr(
        main,
        "run_scenario",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    monkeypatch.setattr(main.debugpy, "breakpoint", lambda: None)

    result = main.main(["test1", "--hide-agent-views"])

    assert result == 0
    assert calls == [
        ((str(Path("scenarios") / "test1.json"),), {"show_agent_views": False})
    ]


def test_main_shows_agent_views_by_default(monkeypatch):
    main = importlib.import_module("main")
    calls = []

    monkeypatch.setattr(
        main,
        "run_scenario",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    monkeypatch.setattr(main.debugpy, "breakpoint", lambda: None)

    result = main.main(["test1"])

    assert result == 0
    assert calls == [
        ((str(Path("scenarios") / "test1.json"),), {"show_agent_views": True})
    ]
