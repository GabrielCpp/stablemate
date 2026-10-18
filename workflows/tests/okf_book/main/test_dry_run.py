"""A dry run walks the whole book flow without the app's stack, its scenarios or an agent."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from okf_book.conftest import run_env
from okf_book.main.tally import App
from okf_book.support import ScriptedRunner, driver
from workhorse.pyflow.engine import stub_nodes

from workhorse_workflows.okf_book.main import exercise_book_flow
from workhorse_workflows.okf_book.main.nodes.report import BookReport
from workhorse_workflows.okf_book.main.nodes.surface import Surface, SurfaceKind
from workhorse_workflows.okf_book.workflow import OkfBook, workflow


def _never(*_args: object, **_kwargs: object) -> object:
    raise AssertionError("a dry run must not touch the app's stack")


def test_a_dry_run_ends_in_a_clean_report_without_the_stack(
    app: App, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = app("tally-cli")
    for name in ("compile_scenarios", "bring_up", "run_plan"):
        monkeypatch.setattr(exercise_book_flow, name, _never)
    runner = ScriptedRunner({})
    env = replace(
        run_env(tmp_path, runner, "dry"),
        dry_run=True,
        nodes=stub_nodes(workflow.nodes),
        agent_stubs=workflow.agent_stubs,
    )
    surface = Surface(service="tally", kind=SurfaceKind.CLI, entry="tally")

    result = driver(OkfBook(repo_dir=str(repo), surfaces=(surface,)), env)

    assert runner.total == 0
    assert isinstance(result, BookReport)
    assert result.blockers == ()
