"""The frozen-app answer key: defects, their selection, the round's plan and the fixture's guard."""

from __future__ import annotations

from pathlib import Path

import pytest
from fakes import fake_run

from paddock.tasks import frozenapp as fz
from paddock.tasks import leverage as lev
from paddock.tasks.stablemate import TrialError


def write_key(app: Path, body: str) -> Path:
    app.mkdir(parents=True, exist_ok=True)
    (app / "defects.yml").write_text(body, encoding="utf-8")
    return app


KEY = """defects:
  - id: D1
    story: S-1
    path: a.py
    expect: contradicted
  - id: D2
    story: S-1
    path: b.py
    expect: contradicted
    caught_by: audit
"""


def test_a_fixture_refuses_a_leverage_key_it_does_not_have() -> None:
    with pytest.raises(ValueError, match="leverage must name one or more of"):
        fz.Fixture(app="apps/x", repo_dir="x", leverage=("obligations", "clicks"))
    assert fz.Fixture(app="apps/x", repo_dir="x").leverage == lev.LEVERAGE_KEYS


def test_load_defects_defaults_the_catch_route_and_refuses_an_unknown_one(tmp_path: Path) -> None:
    rows = fz.load_defects(write_key(tmp_path / "app", KEY))
    assert [row["caught_by"] for row in rows] == ["run", "audit"]
    with pytest.raises(TrialError, match="caught_by: 'nope'"):
        fz.load_defects(write_key(tmp_path / "bad", KEY.replace("audit", "nope")))


def test_a_missing_answer_key_is_named(tmp_path: Path) -> None:
    with pytest.raises(TrialError, match="no answer key"):
        fz.load_defects(tmp_path)


def test_select_defects_keeps_the_asked_order_and_names_a_stranger(tmp_path: Path) -> None:
    app = write_key(tmp_path / "app", KEY)
    assert [row["id"] for row in fz.select_defects(app, ("D2", "D1"))] == ["D2", "D1"]
    assert len(fz.select_defects(app, ())) == 2
    with pytest.raises(TrialError, match="no such defect"):
        fz.select_defects(app, ("D9",))


def test_key_dir_reads_the_app_beside_the_benchmarks_tasks(tmp_path: Path) -> None:
    run = fake_run(tmp_path)
    fixture = fz.Fixture(app="apps/x", repo_dir="x")
    with pytest.raises(TrialError, match="no answer key under"):
        fz.key_dir(run, fixture)
    write_key(run.benchmark.root / "apps" / "x", KEY)
    assert fz.key_dir(run, fixture) == run.benchmark.root / "apps" / "x"


def test_headline_counts_caught_missed_and_false() -> None:
    trials = [
        {"defect": "D1", "verdict": "caught"},
        {"defect": "D2", "verdict": "missed"},
        {"defect": fz.CLEAN, "verdict": "false"},
    ]
    assert fz.headline(trials).startswith("caught 1/2  missed 1  false 1")


def test_the_trials_dir_lives_in_the_stage(tmp_path: Path) -> None:
    run = fake_run(tmp_path)
    assert fz.trials_dir(run) == run.stage / "artifacts" / "trials"
    assert fz.trials_dir(run).is_dir()
