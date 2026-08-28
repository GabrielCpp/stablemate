"""The frozen-app trial's setup ordering: what the before-commit has to already contain.

One property, and it is the one that cost every trial of the first scoring round a
`repair-qa-context` lap: the QA lane mints its obligations from `HEAD..WORKTREE`, so
anything created in the trial tree *after* the before-commit is indistinguishable from the
story's implementation. `farrier install` creates half a dozen such files. It therefore has
to run inside `materialize`, before the commit — and a test is the only thing that keeps it
there, because moving it back out breaks nothing that fails loudly.
"""

from __future__ import annotations

import contextlib
import importlib.util
import json
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
import yaml

from paddock import loader
from paddock.pointer import Pointer
from paddock.runner import Run

DATA = Path(__file__).parents[1]
APP = DATA / "apps" / "policy-desk"


@contextlib.contextmanager
def _tasks_dir_on_path() -> Iterator[None]:
    """Stand in for the interpreter, exactly as `paddock.loader` does.

    Task modules are loose files that import their siblings by bare name, so a loader —
    here, the test — has to put their directory on the path the way `python tasks/x.py`
    would, and take it off again.
    """
    saved = sys.path[:]
    sys.path.insert(0, str(DATA / "tasks"))
    try:
        yield
    finally:
        sys.path[:] = saved


def _load_frozenapp() -> ModuleType:
    path = DATA / "tasks" / "_frozenapp.py"
    spec = importlib.util.spec_from_file_location("_frozenapp", path)
    assert spec is not None and spec.loader is not None  # noqa: S101 - a real file on disk
    module = importlib.util.module_from_spec(spec)
    with _tasks_dir_on_path():
        sys.modules["_frozenapp"] = module
        spec.loader.exec_module(module)
    return module


frozenapp = _load_frozenapp()


def manifest(story: str) -> set[str]:
    data = yaml.safe_load((APP / "stories" / story / "diff.yml").read_text(encoding="utf-8"))
    return {*(data.get("changed") or []), *(data.get("added") or [])}


def dirty(repo: Path) -> set[str]:
    lines = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=str(repo), capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    return {line[3:] for line in lines}


@pytest.mark.skipif(not APP.is_dir(), reason="the policy-desk fixture is not in this tree")
def test_the_install_layer_is_committed_with_the_before_tree(tmp_path: Path) -> None:
    generated = ".claude/skills/pretend/scripts/run.sh"

    def install(repo: Path) -> None:
        target = repo / generated
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("#!/bin/sh\n", encoding="utf-8")

    dest = frozenapp.materialize(APP, "create-policy", tmp_path / "policy-desk", install)

    # The generated file exists and is *not* part of the diff the QA lane will be asked to
    # own — which is the whole property. Were `install` run after the commit, it would be.
    assert (dest / generated).is_file()
    assert dirty(dest) == manifest("create-policy")


@pytest.mark.skipif(not APP.is_dir(), reason="the policy-desk fixture is not in this tree")
def test_materialize_without_an_installer_is_unchanged(tmp_path: Path) -> None:
    dest = frozenapp.materialize(APP, "create-policy", tmp_path / "policy-desk")
    assert dirty(dest) == manifest("create-policy")


# ── fixture-scoped and audit-on rounds ────────────────────────────────────────────────


def make_run(tmp_path: Path, **params: str) -> Run:
    """A `Run` carrying nothing but params and paths — what the round functions read."""
    return Run(
        task=loader.load_path(DATA / "tasks" / "expense_split.py"),
        label="t1",
        stage=tmp_path / "stage",
        repo=tmp_path / "stage" / "policy-desk",
        scratch=tmp_path / "scratch",
        config=tmp_path / "config.toml",
        data_dir=DATA,
        store=tmp_path / "store",
        seed=Pointer(name="policy-desk", repo_dir="policy-desk", sha256="0" * 64, bytes=1),
        params=params,
    )


def fixture(**overrides: object):  # noqa: ANN201 - frozenapp.Fixture, loaded above
    return frozenapp.Fixture(app="apps/policy-desk", repo_dir="policy-desk", **overrides)


@pytest.mark.skipif(not APP.is_dir(), reason="the policy-desk fixture is not in this tree")
def test_fixture_defects_scope_the_round_and_a_param_still_narrows(tmp_path: Path) -> None:
    """A task may pin the rows it exists to measure — an audit task re-buying the whole
    answer key would spend five QA-route trials to score the one audit-route row — and
    `--param defects=…` keeps overriding, because narrowing a run is the operator's call."""
    scoped = frozenapp.plan_round(make_run(tmp_path), APP, fixture(defects=("P2",)))
    assert scoped == [("create-policy", None)] + [
        (story, row) for story, row in scoped if row and row["id"] == "P2"
    ]
    assert len(scoped) == 2
    overridden = frozenapp.plan_round(
        make_run(tmp_path, defects="P1"), APP, fixture(defects=("P2",))
    )
    assert [row["id"] for _story, row in overridden if row] == ["P1"]


@pytest.mark.skipif(not APP.is_dir(), reason="the policy-desk fixture is not in this tree")
def test_audit_on_reaches_the_trial_params_and_the_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`first_verdict=False` is only real if both readers see it: the lane must be told to
    run past the verdict (`stop_at_first_verdict: false` in `--params`), and the ledger
    must say the auditor had a turn (`audit_turn: true`), or `classify` scores an `audit`
    row as inconclusive on a round that paid for the audit."""
    run = make_run(tmp_path, no_control="yes")
    fx_row = fixture(first_verdict=False, defects=("P2",))
    commands: list[tuple[str, ...]] = []

    def fake_cli(*argv: str, **_kwargs: object) -> SimpleNamespace:
        commands.append(argv)
        return SimpleNamespace(returncode=0)

    def fake_materialize(_source: Path, _story: str, dest: Path, *_a: object) -> Path:
        dest.mkdir(parents=True, exist_ok=True)
        return dest

    def fake_witness(_repo: Path, dest: Path, extra: tuple[str, ...] = ()) -> Path:
        dest.mkdir(parents=True, exist_ok=True)
        return dest

    monkeypatch.setattr(frozenapp, "stablemate_checkout", lambda _run: tmp_path / "sm")
    monkeypatch.setattr(frozenapp, "effective", lambda _run: tmp_path / "config.toml")
    monkeypatch.setattr(frozenapp, "pin_held", lambda _pinned: None)
    monkeypatch.setattr(frozenapp, "no_leaks", lambda *_a, **_k: contextlib.nullcontext())
    monkeypatch.setattr(frozenapp, "materialize", fake_materialize)
    monkeypatch.setattr(frozenapp, "seed_defect", lambda *_a: None)
    monkeypatch.setattr(frozenapp, "reset_stack_state", lambda _repo: None)
    monkeypatch.setattr(frozenapp, "capture_witness", fake_witness)
    monkeypatch.setattr(frozenapp.fx, "timing_of", lambda *_a: {})
    monkeypatch.setattr(frozenapp.fx, "laps_of", lambda *_a: {})
    monkeypatch.setattr(run, "cli", fake_cli)

    frozenapp.run_round(run, fx_row)

    qa = next(argv for argv in commands if "qa" in argv)
    params = json.loads(qa[qa.index("--params") + 1])
    assert params["stop_at_first_verdict"] is False
    ledger = json.loads(
        (run.stage / "artifacts" / "trials" / "trials.json").read_text(encoding="utf-8")
    )
    assert [entry["defect"] for entry in ledger] == ["P2"]
    assert all(entry["audit_turn"] is True for entry in ledger)
