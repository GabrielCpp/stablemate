"""A book commit the repo refuses gets a fix turn for each new refusal, and the operator once a refusal repeats or the turns run out."""
from __future__ import annotations

from pathlib import Path

import pytest
from okf_book.main.flows import build_flow, written_book
from okf_book.support import FIX_COMMIT_NODE, ScriptedRunner
from workhorse.pyflow import Await

from workhorse_workflows.okf_book.main.python_book_flow import WritePythonBook
from workhorse_workflows.okf_book.shared import book_flow


def _refusals(monkeypatch: pytest.MonkeyPatch, said: list[str]) -> list[str]:
    left = list(said)

    def _declared(_root: Path, _message: str, _pathspecs: tuple[str, ...]) -> str:
        return left.pop(0)

    monkeypatch.setattr(book_flow, "declared_checks_failure", _declared)
    return left


def _flow(tmp_path: Path) -> tuple[WritePythonBook, ScriptedRunner]:
    flow, runner = build_flow(tmp_path, {FIX_COMMIT_NODE: lambda _args: {"fixed": "repaired it", "blocked": ""}})
    _ = written_book(flow)
    return flow, runner


def _commit(flow: WritePythonBook) -> object:
    return flow._commit_or_await("docs(ledger): write the book", ("services/ledger",), flow.commit, lap=1)  # pyright: ignore[reportPrivateUsage]


def test_a_different_refusal_after_a_fix_turn_gets_its_own_turn(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    left = _refusals(monkeypatch, ["ruff said F401", "ty said bad type", ""])
    flow, runner = _flow(tmp_path)

    waiting = _commit(flow)

    assert (waiting, left, runner.turns[FIX_COMMIT_NODE]) == (None, [], 2)
    assert [str(sent["refusal"]) for sent in runner.args_of(FIX_COMMIT_NODE)] == ["ruff said F401", "ty said bad type"]


def test_the_same_refusal_twice_gets_one_turn_then_the_operator(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _ = _refusals(monkeypatch, ["ruff said F401", "ruff said F401"])
    flow, runner = _flow(tmp_path)

    waiting = _commit(flow)

    assert isinstance(waiting, Await) and waiting.path == flow.run_dir / book_flow.COMMIT_GATE
    assert runner.turns[FIX_COMMIT_NODE] == 1


def test_four_different_refusals_then_a_fifth_go_to_the_operator(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _ = _refusals(monkeypatch, [f"check {n} said no" for n in range(1, 6)])
    flow, runner = _flow(tmp_path)

    waiting = _commit(flow)

    assert isinstance(waiting, Await) and waiting.path == flow.run_dir / book_flow.COMMIT_GATE
    assert runner.turns[FIX_COMMIT_NODE] == book_flow.FIX_COMMIT_TURNS == 4
    assert "check 5 said no" in waiting.questions
