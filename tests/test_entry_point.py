import runpy
from importlib.metadata import entry_points

import big_o
import big_o.app as metro_app


def test_console_script_points_at_main():
    (script,) = [ep for ep in entry_points(group="console_scripts") if ep.name == "big-o"]

    assert script.load() is big_o.main


def test_main_runs_the_app(monkeypatch):
    calls = []
    monkeypatch.setattr(metro_app.app, "run", lambda **kwargs: calls.append(kwargs))

    big_o.main()

    assert calls == [{"host": "127.0.0.1", "port": 5000, "debug": True}]


def test_python_dash_m_runs_main(monkeypatch):
    calls = []
    monkeypatch.setattr(metro_app.app, "run", lambda **kwargs: calls.append(kwargs))

    runpy.run_module("big_o", run_name="__main__")

    assert len(calls) == 1
