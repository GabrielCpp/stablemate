"""The repo's commit checks run over the book after its check passes and before it is played, so a refusal costs a fix turn and no replay."""
from __future__ import annotations

from pathlib import Path

import pytest
from okf_book.catch_up import flows as catch_up
from okf_book.main.flows import book_exits, fixing_flow
from okf_book.support import FIX_COMMIT_NODE, advance, git, refused_with
from workhorse.pyflow import Await, Continue

from workhorse_workflows.okf_book.main.python_book_flow import WritePythonBook
from workhorse_workflows.okf_book.shared import book_flow


def _staged(flow: WritePythonBook) -> str:
    return git(flow.root, "diff", "--cached", "--name-only")


def test_no_refusal_goes_to_play_and_leaves_the_index_as_it_was(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def _stages_then_passes(root: Path, _message: str, pathspecs: tuple[str, ...]) -> str:
        git(root, "add", "--", *pathspecs)
        return ""

    monkeypatch.setattr(book_flow, "declared_checks_failure", _stages_then_passes)
    flow, runner = fixing_flow(tmp_path)

    step = flow.checks(lap=1)

    assert isinstance(step, Continue) and step.state == "play"
    assert (_staged(flow), runner.turns[FIX_COMMIT_NODE]) == ("", 0)


def test_one_refusal_runs_one_fix_turn_and_returns_to_check(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _ = refused_with(monkeypatch, ["ruff said F401"])
    flow, runner = fixing_flow(tmp_path)

    step = flow.checks(lap=2)

    assert isinstance(step, Continue) and step.state == "check"
    assert (step.params["lap"], step.params["seen"], runner.turns[FIX_COMMIT_NODE]) == (2, ["ruff said F401"], 1)
    assert [str(sent["refusal"]) for sent in runner.args_of(FIX_COMMIT_NODE)] == ["ruff said F401"]


def test_a_repeated_refusal_waits_on_the_operator_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _ = refused_with(monkeypatch, ["ruff said F401"])
    flow, runner = fixing_flow(tmp_path)

    waiting = flow.checks(lap=1, seen=["ruff said F401"])

    assert isinstance(waiting, Await) and waiting.path == flow.run_dir / book_flow.COMMIT_GATE
    assert (waiting.state, waiting.params["seen"], runner.turns[FIX_COMMIT_NODE]) == ("checks", [], 0)
    assert "ruff said F401" in waiting.questions


def test_the_fifth_refusal_waits_on_the_operator_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _ = refused_with(monkeypatch, ["check 5 said no"])
    flow, runner = fixing_flow(tmp_path)

    waiting = flow.checks(lap=1, seen=[f"check {n} said no" for n in range(1, 5)])

    assert isinstance(waiting, Await) and waiting.path == flow.run_dir / book_flow.COMMIT_GATE
    assert runner.turns[FIX_COMMIT_NODE] == 0
    assert "check 5 said no" in waiting.questions


def test_a_resumed_state_keeps_its_count_through_the_check(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _ = refused_with(monkeypatch, ["third said no"])
    _ = book_exits(monkeypatch)
    flow, _runner = fixing_flow(tmp_path)

    back = flow.checks(lap=1, seen=["first said no", "second said no"])
    again = advance(flow, back)

    assert isinstance(back, Continue) and back.params["seen"] == ["first said no", "second said no", "third said no"]
    assert isinstance(again, Continue) and again.state == "checks" and again.params["seen"] == back.params["seen"]


def test_the_python_book_checks_between_check_and_play_and_a_refusal_plays_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ran = book_exits(monkeypatch)
    flow, _runner = fixing_flow(tmp_path)
    _ = refused_with(monkeypatch, ["", "ruff said F401"])

    checked = flow.check(lap=1)
    passed = advance(flow, checked)
    refused = advance(flow, flow.check(lap=1))

    assert (checked.state, passed.state, refused.state) == ("checks", "play", "check")
    assert not [argv for argv in ran if argv[3] == "run"]


def test_the_catch_up_checks_between_check_and_play_and_a_refusal_plays_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    flow, _runner, ran = catch_up.stale_book(tmp_path, monkeypatch)
    _ = refused_with(monkeypatch, ["", "ruff said F401"])
    catch_up.walk(flow, flow.books(), "write")

    checked = flow.check("ledger", 1, [], [])
    passed = catch_up.advance(flow, checked)
    refused = catch_up.advance(flow, flow.check("ledger", 1, [], []))

    assert (checked.state, passed.state, refused.state) == ("checks", "play", "check")
    assert not [argv for argv in ran if len(argv) > 3 and argv[3] == "run"]
