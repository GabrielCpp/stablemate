"""A book moved onto the format is worked in batches of a fixed number of notes, each played and committed on its own, and what the owner declines stays in the book's register."""
from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest
from okf_book.catch_up.flows import UPDATE, advance, book_exits, summarized, walk
from okf_book.catch_up.test_catch_up_format import PARTIAL, behind_book
from okf_book.catch_up.test_catch_up_notes import green, leading, listing, red
from okf_book.support import ScriptedRunner, git, install_book_skill, run_env
from workhorse import templates
from workhorse.pyflow import Await
from workhorse.pyflow.engine import Engine

from workhorse_workflows import okf_book
from workhorse_workflows.okf_book.catch_up.flow import CatchUpBooks
from workhorse_workflows.okf_book.catch_up.models import BookOutcome
from workhorse_workflows.okf_book.shared import book_gates
from workhorse_workflows.okf_book.shared.book_commits import caught_up_book_commit_subject, format_book_commit_subject
from workhorse_workflows.okf_book.shared.book_flow import ENVIRONMENT_GATE
from workhorse_workflows.okf_book.shared.blockers import Phase
from workhorse_workflows.okf_book.shared.metrics import record_turn, turn_metric
from workhorse.runner.usage import TurnUsage

FORTY = [*leading(*(f"S{n}" for n in range(30))), *listing(*(f"P{n}" for n in range(10)))]
ONE_BATCH = "batch 1: 16 asked, 16 done, 0 outside, 1 lap, 0 min, played 2 calls and 1 journey green, committed"
TWO_BATCH = "batch 2: 15 asked, 15 done, 0 outside, 1 lap, 0 min, played 2 calls and 1 journey green, committed"


def batched(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, checks: list[tuple[int, str]], declined: list[str] | None = None, **params: int) -> tuple[CatchUpBooks, ScriptedRunner, list[list[str]]]:
    """A book filed for the format whose check says each of `checks` in turn, and whose owner edits the book on every turn and declines `declined` on its first."""
    turns: list[int] = []
    flow, runner, _shas, _seen = behind_book(tmp_path, monkeypatch)

    def owner(_args: dict[str, object]) -> dict[str, object]:
        turns.append(1)
        with (flow.root / "services/ledger/service.py").open("a", encoding="utf-8") as book:
            _ = book.write(f"TURN_{len(turns)} = 1\n")
        return {"done": "moved", "declined": declined if len(turns) == 1 and declined else []}

    runner.replies[UPDATE] = owner
    seen = book_exits(monkeypatch, checks={"services.ledger": checks}, plans={"services.ledger": (0, PARTIAL)})
    install_book_skill(tmp_path / "home", monkeypatch)
    for name, value in params.items():
        setattr(flow, name, value)
    return flow, runner, seen


def listed(args: dict[str, object]) -> list[str]:
    groups = cast("list[dict[str, list[str]]]", args["notes"])
    return [element for group in groups for element in group["elements"]]


def test_the_defaults_are_fifteen_notes_a_batch_one_batch_a_run_and_fifteen_minutes_a_play() -> None:
    flow = CatchUpBooks(repo_dir=".")

    assert (flow.batch_notes, flow.batches, flow.play_minutes) == (15, 1, 15)


def test_forty_notes_in_batches_of_fifteen_two_batches_a_run_commit_twice_and_leave_ten(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    after_first = [*FORTY[15:]]
    after_second = [*FORTY[30:]]
    checks = [(1, red(*FORTY)), (0, green(*after_first)), (0, green(*after_first)), (0, green(*after_second))]
    flow, runner, _seen = batched(tmp_path, monkeypatch, checks, batches=2)
    before = git(flow.root, "rev-list", "--count", "HEAD").strip()

    step = walk(flow, flow.fill(), "write")
    walk(flow, step, "books")
    walk(flow, flow.books(), "summarize")

    first, second = runner.args_of(UPDATE)
    assert listed(first) == [f"screen S{n}" for n in range(15)]
    assert listed(second) == [f"screen S{n}" for n in range(15, 30)]
    assert int(git(flow.root, "rev-list", "--count", "HEAD").strip()) == int(before) + 2
    assert git(flow.root, "log", "-1", "--format=%s") == "docs(ledger): move the book onto the current book format (batch 2)\n"
    assert git(flow.root, "log", "-2", "--format=%s").splitlines()[1] == "docs(ledger): move the ledger book onto the current book format"
    done = summarized(flow)
    assert done.summary.splitlines() == [
        f"ledger: {ONE_BATCH}",
        f"ledger: {TWO_BATCH}",
        "ledger: nothing leads to it: 30 to 0",
        "ledger: nothing states what its list holds: 10 to 10",
        "ledger: 10 notes remain: run catch_up again, about 1 batch",
    ]
    assert done.books[0].remaining == 10 and [batch.number for batch in done.books[0].batches] == [1, 2]
    assert git(flow.root, "log", "-1", "--format=%b").strip().splitlines()[0].startswith("batch 2: 15 asked")


def test_a_run_stops_after_its_batches_and_says_how_many_more_it_takes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    checks = [(1, red(*FORTY)), (0, green(*FORTY[15:]))]
    flow, runner, _seen = batched(tmp_path, monkeypatch, checks)

    walk(flow, walk(flow, flow.fill(), "write"), "books")
    walk(flow, flow.books(), "summarize")

    assert runner.total == 1
    assert summarized(flow).summary.splitlines()[-1] == "ledger: 25 notes remain: run catch_up again, about 2 batches"
    assert summarized(flow).books[0].status == "moved, 25 notes remain"


def test_the_prompt_of_a_batch_lists_only_its_items_and_states_its_size(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    flow, runner, _seen = batched(tmp_path, monkeypatch, [(1, red(*FORTY)), (0, green(*FORTY[15:]))])

    advance(flow, walk(flow, flow.fill(), "write"))
    rendered = " ".join(templates.render("catch_up/prompts/update-book.md", runner.args_of(UPDATE)[0], Path(okf_book.__file__).parent).split())

    assert "This batch is 16 items." in rendered
    assert "- sources: Ping names no source" in rendered
    assert "nothing leads to it: 15 notes" in rendered and "- screen S14 " in rendered
    assert "- screen S15 " not in rendered and "nothing states what its list holds" not in rendered
    assert "Do not start on any note that is not listed here" in rendered
    assert "the run hands out the next ones" in rendered
    assert "The run records what you touched outside this list." in rendered


def test_a_note_outside_the_batch_that_goes_with_it_is_counted_as_outside(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    left = [note for note in FORTY[15:] if note != FORTY[20]]
    flow, _runner, _seen = batched(tmp_path, monkeypatch, [(1, red(*FORTY)), (0, green(*left))])

    walk(flow, walk(flow, flow.fill(), "write"), "books")
    walk(flow, flow.books(), "summarize")

    assert summarized(flow).summary.splitlines()[0] == "ledger: batch 1: 16 asked, 16 done, 1 outside, 1 lap, 0 min, played 2 calls and 1 journey green, committed"
    assert summarized(flow).summary.splitlines()[-1] == "ledger: 24 notes remain: run catch_up again, about 2 batches"


def test_declined_lines_land_in_the_register_and_a_second_run_neither_lists_nor_counts_them(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    notes = [*leading("A", "B"), *listing("P")]
    declined = ["screen A: the app never links to it", "nothing states what its list holds: another book states them"]
    flow, runner, _seen = batched(tmp_path, monkeypatch, [(1, red(*notes)), (0, green(*notes[:1], *notes[2:]))], declined)

    walk(flow, walk(flow, flow.fill(), "write"), "books")
    walk(flow, flow.books(), "summarize")

    register = (flow.root / "services/ledger/DECLINED.md").read_text(encoding="utf-8")
    assert register == (
        "# Notes the check prints that this book declines, one line each: `- <element>: <kind>: <reason>`, `*` for a whole kind\n\n"
        "- screen A: nothing leads to it: the app never links to it\n"
        "- *: nothing states what its list holds: another book states them\n"
    )
    assert "services/ledger/DECLINED.md" in git(flow.root, "show", "--name-only", "--format=", "HEAD")
    assert summarized(flow).summary.splitlines()[1:] == ["ledger: nothing leads to it: 2 to 0 (1 declined)", "ledger: nothing states what its list holds: 1 to 0 (1 declined)"]
    assert summarized(flow).books[0].remaining == 0

    second = CatchUpBooks(repo_dir=str(flow.root), stack_copy="evening")
    second._bind(Engine(run_env(tmp_path / "runs2", runner)))  # pyright: ignore[reportPrivateUsage]
    book_exits(monkeypatch, checks={"services.ledger": [(0, green(*notes[:1], *notes[2:]))]})
    second.fill()

    assert summarized(second).books == [BookOutcome(service="ledger", verdict="current")]
    assert runner.total == 1


def test_a_second_run_lists_a_note_the_register_does_not_cover_and_no_other(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    flow, runner, _seen = batched(tmp_path, monkeypatch, [(0, green(*leading("A", "B")))])
    (flow.root / "services/ledger/DECLINED.md").write_text("# register\n\n- screen A: nothing leads to it: never linked\n", encoding="utf-8")

    step = flow.fill()
    taken = walk(flow, step, "write")
    advance(flow, taken)

    assert [item.id for item in flow.work_list.items("book")] == ["ledger"]
    sent = runner.args_of(UPDATE)[0]
    assert listed(sent) == ["screen B"]
    assert sent["findings"] == []


def test_a_green_book_whose_notes_all_sit_in_the_register_is_current(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    flow, runner, _seen = batched(tmp_path, monkeypatch, [(0, green(*leading("A"), *listing("P")))])
    (flow.root / "services/ledger/DECLINED.md").write_text("# register\n\n- screen A: nothing leads to it: never linked\n- *: nothing states what its list holds: elsewhere\n", encoding="utf-8")
    (flow.root / "services/ledger/FORMAT").write_text(f"{git(flow.root, 'rev-parse', 'HEAD').strip()}\n", encoding="utf-8")
    monkeypatch.setattr("workhorse_workflows.okf_book.shared.book_format.history_repo", lambda: None)

    flow.fill()

    assert runner.total == 0
    assert summarized(flow).books == [BookOutcome(service="ledger", verdict="current")]


def test_a_play_past_the_limit_goes_to_the_environment_gate_with_the_limit_in_its_text(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    flow, _runner, _seen = batched(tmp_path, monkeypatch, [(1, red(*FORTY[:3])), (0, green())], play_minutes=7)
    inner = cast("Callable[..., subprocess.CompletedProcess[str]]", book_gates.run_tool)
    limits: list[object] = []

    def limited(argv: list[str], **kw: object) -> subprocess.CompletedProcess[str]:
        if argv[1] != "-c" and argv[3] == "run":
            limits.append(kw.get("timeout"))
            raise subprocess.TimeoutExpired(argv, 420.0, output="cell 3 begun\n")
        return inner(argv, **kw)

    monkeypatch.setattr(book_gates, "run_tool", limited)

    step = walk(flow, flow.fill(), "write")
    waiting = walk(flow, step, "play")
    waiting = advance(flow, waiting)

    assert isinstance(waiting, Await) and waiting.state == "play"
    assert waiting.path.name == ENVIRONMENT_GATE
    assert "the play did not end within 7 minutes (play_minutes)" in waiting.questions
    assert "exited 3" in waiting.questions
    assert limits == [420.0]


def test_the_minutes_of_a_batch_are_the_wall_clock_of_the_owner_turns_the_run_recorded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    flow, _runner, _seen = batched(tmp_path, monkeypatch, [(1, red(*FORTY[:3])), (0, green())])
    flow.fill()
    walk(flow, flow.books(), "write")
    record_turn(flow.run_dir, turn_metric(Phase.WRITE, "update-book", ("ledger",), 13.6, TurnUsage()))
    record_turn(flow.run_dir, turn_metric(Phase.WRITE, "update-book", ("web",), 40.0, TurnUsage()))

    assert flow._turn_minutes("ledger") == 13.6  # pyright: ignore[reportPrivateUsage]


def test_a_later_batch_adds_its_number_to_the_subject_where_it_fits_and_drops_it_where_it_cannot() -> None:
    assert format_book_commit_subject("ledger") == "docs(ledger): move the ledger book onto the current book format"
    assert format_book_commit_subject("ledger", 2) == "docs(ledger): move the book onto the current book format (batch 2)"
    assert format_book_commit_subject("a-service-with-a-very-long-name", 2) == "docs(a-service-with-a-very-long-name): adopt the current book format"
    assert caught_up_book_commit_subject("ledger", 3) == "docs(ledger): catch the ledger book up with the app (batch 3)"
    name = "a-service-name"
    assert len(caught_up_book_commit_subject(name)) <= 72 < len(caught_up_book_commit_subject(name) + " (batch 2)")
    assert caught_up_book_commit_subject(name, 2) == caught_up_book_commit_subject(name)
