"""A book the workflow writes records the commit of the writer's instructions it was judged against, and a book that is behind on them is sent the changes."""
from __future__ import annotations

from pathlib import Path

import pytest
from okf_book.main.flows import book_exits, build_flow, written_book
from okf_book.support import commit_at, git, install_book_skill, skill_history
from workhorse import templates
from workhorse.pyflow import Await, Continue, Done

from workhorse_workflows import okf_book
from workhorse_workflows.okf_book.main.python_book_flow import PythonBookOutcome
from workhorse_workflows.okf_book.shared.book_flow import FORMAT_GATE

WRITE = "write-python-book"


def test_a_first_books_commit_carries_the_format_mark_at_the_head(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    shas = skill_history(tmp_path / "history", monkeypatch)
    book_exits(monkeypatch)
    flow, _runner = build_flow(tmp_path, history=str(tmp_path / "history"))
    repo = written_book(flow)

    stamped = flow.stamp(lap=1)
    flow.commit(lap=1)

    assert isinstance(stamped, Continue) and stamped.state == "render"
    assert (repo / "services/ledger/FORMAT").read_text(encoding="utf-8") == f"{shas[2]}\n"
    assert sorted(git(repo, "show", "--name-only", "--format=", "HEAD").split()) == ["services/ledger/FORMAT", "services/ledger/service.py"]


def test_an_existing_book_that_is_behind_gets_the_format_section_in_its_owner_prompt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    shas = skill_history(tmp_path / "history", monkeypatch)
    flow, runner = build_flow(tmp_path, {WRITE: lambda _args: {"done": "", "blocked": ""}}, history=str(tmp_path / "history"))
    repo = written_book(flow)
    git(repo, "add", "services")
    commit_at(repo, "docs(ledger): write the ledger book", "2026-11-02T12:00:00+00:00", monkeypatch)
    install_book_skill(tmp_path / "home", monkeypatch)

    started = flow.start()
    flow.write(gate="", lap=1)
    rendered = templates.render("main/prompts/write-python-book.md", runner.args_of(WRITE)[0], Path(okf_book.__file__).parent)

    assert isinstance(started, Continue)
    assert "The book format changed since this book was last judged against it." in rendered
    assert f"- `{shas[1][:7]}` docs(base-library): teach two" in rendered
    assert "+three" in rendered


def test_a_first_book_gets_no_format_section(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    skill_history(tmp_path / "history", monkeypatch)
    flow, runner = build_flow(tmp_path, {WRITE: lambda _args: {"done": "", "blocked": ""}}, history=str(tmp_path / "history"))
    install_book_skill(tmp_path / "home", monkeypatch)
    flow.root.mkdir(parents=True, exist_ok=True)

    flow.write(gate="", lap=1)
    rendered = templates.render("main/prompts/write-python-book.md", runner.args_of(WRITE)[0], Path(okf_book.__file__).parent)

    assert "The book format changed" not in rendered


def test_a_format_history_that_cannot_be_read_waits_on_the_operator_before_the_owner_writes(tmp_path: Path) -> None:
    (tmp_path / "nowhere").mkdir()
    flow, runner = build_flow(tmp_path, history=str(tmp_path / "nowhere"))
    written_book(flow)

    step = flow.start()

    assert isinstance(step, Await) and step.state == "start"
    assert step.path == flow.run_dir / FORMAT_GATE
    assert "rev-list" in step.questions
    assert runner.total == 0


def test_a_first_book_whose_format_history_cannot_be_read_ends_committed_with_no_format_mark(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "nowhere").mkdir()
    book_exits(monkeypatch)
    flow, _runner = build_flow(tmp_path, history=str(tmp_path / "nowhere"))
    started = flow.start()
    repo = written_book(flow)

    stamped = flow.stamp(lap=1)
    done = flow.commit(lap=1)

    assert isinstance(started, Continue) and started.state == "write"
    assert isinstance(stamped, Continue) and stamped.state == "render"
    assert isinstance(done, Done)
    assert not (repo / "services/ledger/FORMAT").exists()
    assert git(repo, "show", "--name-only", "--format=", "HEAD").split() == ["services/ledger/service.py"]
    assert isinstance(done.result, PythonBookOutcome)
    assert "format mark was not written" in done.result.unmarked
    assert "rev-list" in done.result.unmarked


def test_an_existing_book_whose_format_history_cannot_be_read_still_waits_at_the_stamp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "nowhere").mkdir()
    book_exits(monkeypatch)
    flow, _runner = build_flow(tmp_path, history=str(tmp_path / "nowhere"))
    written_book(flow)
    flow.start()

    step = flow.stamp(lap=1)

    assert isinstance(step, Await) and step.state == "stamp"
    assert step.path == flow.run_dir / FORMAT_GATE
