"""A fix turn sent to a refused commit that changed the book's Python sends the book through its gates again before the commit is retried."""
from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

import pytest
from okf_book.catch_up import flows as catch_up
from okf_book.main.flows import book_exits, build_flow, written_book
from okf_book.support import FIX_COMMIT_NODE
from workhorse.pyflow import Continue

from workhorse_workflows.okf_book.main.python_book_flow import WritePythonBook
from workhorse_workflows.okf_book.shared import book_flow
from workhorse_workflows.okf_book.shared.book_flow import book_digest

LOG = logging.getLogger("test")


def _refused_once(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    left = ["ruff said F401", ""]

    def _declared(_root: Path, _message: str, _pathspecs: tuple[str, ...]) -> str:
        return left.pop(0)

    monkeypatch.setattr(book_flow, "declared_checks_failure", _declared)
    return left


def _editing_flow(tmp_path: Path, edits: bool) -> WritePythonBook:
    held: list[WritePythonBook] = []

    def _fix(_args: dict[str, object]) -> dict[str, object]:
        if edits:
            (held[0].root / "services/ledger/extra.py").write_text("EXTRA = 1\n", encoding="utf-8")
        return {"fixed": "repaired it", "blocked": ""}

    flow, _runner = build_flow(tmp_path, {FIX_COMMIT_NODE: _fix})
    held.append(flow)
    _ = written_book(flow)
    return flow


def _commit(flow: WritePythonBook, replay: Callable[[], Continue[...] | None]) -> object:
    return flow._commit_or_await("docs(ledger): write the book", ("services/ledger",), replay, flow.commit, lap=1)  # pyright: ignore[reportPrivateUsage]


def test_a_fix_turn_that_leaves_the_book_alone_retries_the_commit_without_a_replay(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    left = _refused_once(monkeypatch)
    replays: list[int] = []

    done = _commit(_editing_flow(tmp_path, edits=False), lambda: replays.append(1))

    assert (done, left, replays) == (None, [], [])


def test_a_fix_turn_that_changed_the_book_and_a_green_replay_retries_the_commit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    left = _refused_once(monkeypatch)
    replays: list[int] = []

    def _green() -> None:
        replays.append(1)

    done = _commit(_editing_flow(tmp_path, edits=True), _green)

    assert (done, left, replays) == (None, [], [1])


def test_a_fix_turn_that_changed_the_book_and_a_red_replay_returns_the_replay_without_a_commit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    left = _refused_once(monkeypatch)
    flow = _editing_flow(tmp_path, edits=True)
    red = Continue("red", flow.write, gate="run said no", lap=2).because("the book is red")

    done = _commit(flow, lambda: red)

    assert (done, left) == (red, [""])


def test_the_digest_follows_the_python_files_and_ignores_results_and_bytecode(tmp_path: Path) -> None:
    book = tmp_path / "services/ledger"
    (book / "results").mkdir(parents=True)
    (book / "__pycache__").mkdir()
    (book / "service.py").write_text("NAME = 'ledger'\n", encoding="utf-8")
    first = book_digest(LOG, tmp_path, ("services/ledger",))

    (book / "results/run.py").write_text("x = 1\n", encoding="utf-8")
    (book / "__pycache__/service.py").write_text("x = 1\n", encoding="utf-8")
    (book / "notes.md").write_text("text\n", encoding="utf-8")
    unchanged = book_digest(LOG, tmp_path, ("services/ledger",))
    (book / "service.py").write_text("NAME = 'other'\n", encoding="utf-8")
    changed = book_digest(LOG, tmp_path, ("services/ledger",))

    assert first == unchanged != changed


def test_a_red_replay_in_the_python_book_flow_sends_the_owner_another_lap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _ = _refused_once(monkeypatch)
    _ = book_exits(monkeypatch, run=1)
    flow = _editing_flow(tmp_path, edits=True)

    step = flow.commit(lap=1)

    assert isinstance(step, Continue) and step.state == "write"
    assert step.params["lap"] == 2


def test_a_red_replay_in_the_catch_up_flow_sends_the_owner_another_lap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _ = _refused_once(monkeypatch)
    held: list[catch_up.CatchUpBooks] = []

    def _fix(_args: dict[str, object]) -> dict[str, object]:
        (held[0].root / "services/ledger/extra.py").write_text("EXTRA = 1\n", encoding="utf-8")
        return {"fixed": "repaired it", "blocked": ""}

    flow, _runner, _seen = catch_up.stale_book(tmp_path, monkeypatch, {catch_up.UPDATE: lambda _args: {"done": "the ledger book", "blocked": "", "added": []}, FIX_COMMIT_NODE: _fix}, run=1)
    held.append(flow)
    catch_up.walk(flow, flow.books(), "write")

    step = flow.commit(service="ledger", lap=1, added=[], ignored=[])

    assert isinstance(step, Continue) and step.state == "write"
    assert step.params["lap"] == 2
