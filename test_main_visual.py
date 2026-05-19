from types import SimpleNamespace

import pytest

import main_visual


class _StoppedThread:
    def is_alive(self):
        return False


def test_main_visual_requires_test_case():
    with pytest.raises(SystemExit) as exc_info:
        main_visual.main([])

    assert exc_info.value.code == 2


def test_main_visual_starts_visualizer_for_named_case(monkeypatch):
    calls = []

    def fake_visualize_instance(test_case):
        calls.append(test_case)
        return SimpleNamespace(
            url="http://127.0.0.1:1/",
            thread=_StoppedThread(),
            shutdown=lambda: None,
        )

    monkeypatch.setattr(main_visual, "visualize_instance", fake_visualize_instance)

    assert main_visual.main(["test1"]) == 0
    assert calls == ["test1"]


def test_main_visual_oracle_mode_calls_oracle_runner(monkeypatch):
    calls = []

    def fake_run_oracle(test_case):
        calls.append(test_case)

    monkeypatch.setattr(main_visual, "run_oracle", fake_run_oracle)

    assert main_visual.main(["test1", "--oracle"]) == 0
    assert calls == ["test1"]
