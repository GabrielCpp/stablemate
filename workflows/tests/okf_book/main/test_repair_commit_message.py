"""A repair commit is named by a small model that reads its diff, and keeps the fixed subject when that model cannot."""
from __future__ import annotations

from functools import partial
from pathlib import Path

import pytest
from okf_book.main.tally import NOTE, PAGE, TALLY, App, DriveBook, stub_a_book_sent_to_repair
from okf_book.support import Reply, ScriptedRunner, always, commits, git
from workhorse.runner.failure import BackendInvocationError, OutputParseError

from workhorse_workflows.okf_book.main import settle_repair_turn_flow
from workhorse_workflows.okf_book.main.nodes.report import BookReport
from workhorse_workflows.okf_book.workflow import OkfBook


@pytest.fixture
def over_the_ceiling(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_a_book_sent_to_repair(monkeypatch)


def _noting(repo: Path, _args: dict[str, object]) -> dict[str, object]:
    page = repo / PAGE
    _ = page.write_text(page.read_text(encoding="utf-8") + NOTE, encoding="utf-8")
    return {"value": "repaired tally.md"}


def _repairer_described_by(repo: Path, describe: Reply) -> ScriptedRunner:
    runner = ScriptedRunner({"repair-pages": partial(_noting, repo)})
    runner.replies[settle_repair_turn_flow.DESCRIBE_LABEL] = describe
    return runner


def _head_message(repo: Path) -> str:
    return git(repo, "log", "-1", "--format=%B").strip()


@pytest.mark.usefixtures("over_the_ceiling")
def test_a_repair_commit_is_named_by_what_its_diff_changed_and_marked_as_a_repair(app: App, drive_book: DriveBook) -> None:
    repo = app("tally-cli")
    runner = _repairer_described_by(repo, always({"description": "note what tally prints", "body": "The page missed its note."}))

    result = drive_book(OkfBook(repo_dir=str(repo), surfaces=(TALLY,)), runner)

    assert isinstance(result, BookReport)
    assert _head_message(repo) == "docs(tally): note what tally prints\n\nThe page missed its note.\n\nOkf-Book: repaired"
    described = runner.args_of(settle_repair_turn_flow.DESCRIBE_LABEL)
    assert len(described) == 1
    assert described[0]["pages"] == [PAGE]
    assert NOTE.strip() in str(described[0]["diff"])
    assert git(repo, "status", "--porcelain").strip() == ""


@pytest.mark.usefixtures("over_the_ceiling")
@pytest.mark.parametrize("broken", ["Note what tally prints.", "docs(tally): note what tally prints"])
def test_a_description_that_breaks_the_subject_rules_is_asked_for_again(app: App, drive_book: DriveBook, broken: str) -> None:
    repo = app("tally-cli")

    def _describe(args: dict[str, object]) -> dict[str, object]:
        if args.get("refused"):
            return {"description": "note what tally prints", "body": ""}
        return {"description": broken, "body": ""}

    runner = _repairer_described_by(repo, _describe)

    _ = drive_book(OkfBook(repo_dir=str(repo), surfaces=(TALLY,)), runner)

    assert [node for node, _ in runner.refused] == [settle_repair_turn_flow.DESCRIBE_LABEL]
    assert commits(repo)[0] == "docs(tally): note what tally prints"


@pytest.mark.usefixtures("over_the_ceiling")
def test_a_describe_turn_that_fails_keeps_the_fixed_subject(app: App, drive_book: DriveBook) -> None:
    repo = app("tally-cli")

    def _dies(_args: dict[str, object]) -> dict[str, object]:
        raise BackendInvocationError("no result event")

    result = drive_book(OkfBook(repo_dir=str(repo), surfaces=(TALLY,)), _repairer_described_by(repo, _dies))

    assert isinstance(result, BookReport)
    assert _head_message(repo) == "docs(tally): repair pages of the tally book\n\nOkf-Book: repaired"


@pytest.mark.usefixtures("over_the_ceiling")
def test_a_describe_turn_whose_every_reply_is_refused_keeps_the_fixed_subject(app: App, drive_book: DriveBook) -> None:
    repo = app("tally-cli")

    def _refused(_args: dict[str, object]) -> dict[str, object]:
        raise OutputParseError("the subject is 75 characters, over 72")

    result = drive_book(OkfBook(repo_dir=str(repo), surfaces=(TALLY,)), _repairer_described_by(repo, _refused))

    assert isinstance(result, BookReport)
    assert _head_message(repo) == "docs(tally): repair pages of the tally book\n\nOkf-Book: repaired"
