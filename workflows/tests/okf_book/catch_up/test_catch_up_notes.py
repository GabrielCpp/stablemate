"""The check's notes are work in a format move: the owner gets them by kind, declines what does not apply, and the run says how far each kind went."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import cast

import pytest
from okf_book.catch_up.flows import UPDATE, advance, book_exits, stale_printed, summarized, walk
from okf_book.catch_up.test_catch_up_format import PARTIAL, behind_book
from okf_book.support import ScriptedRunner, git, install_book_skill
from workhorse import templates
from workhorse.pyflow import Await, Continue

from workhorse_workflows import okf_book
from workhorse_workflows.okf_book.catch_up.flow import CatchUpBooks
from workhorse_workflows.okf_book.catch_up.report import is_declined, kind_moves, note_kinds, read_check, split_note
from workhorse_workflows.okf_book.shared.book_flow import MAX_LAPS, RED_GATE

LEADS = "nothing leads to it: state `leads_to` on the interaction that opens it, `inside` when another screen hosts it, or `first` when a person opens it directly"
LISTS = "nothing states what its list holds: give it options=(...) or lists=Lists(...)"
HOLD = "ledger and web both hold Entry: if it is one record, ask web's book for it"


def noted(*lines: str) -> str:
    return "".join(f"NOTE   {line}\n" for line in lines)


def leading(*names: str) -> list[str]:
    return [f"screen {name}: {LEADS}" for name in names]


def listing(*names: str) -> list[str]:
    return [f"screen {name}.kind: {LISTS}" for name in names]


def red(*notes: str) -> str:
    return f"CHECK  sources: Ping names no source\n{noted(*notes)}check: 1 finding, {len(notes)} notes\n"


def green(*notes: str) -> str:
    return f"{noted(*notes)}check: 0 findings, {len(notes)} notes\n"


def moving(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, checks: list[tuple[int, str]], replies: list[dict[str, object]]) -> tuple[CatchUpBooks, ScriptedRunner, list[list[str]]]:
    """A book filed for the format whose check says each of `checks` in turn, the first at filing, and whose owner replies each of `replies` in turn."""
    left = list(replies)
    flow, runner, _shas, _seen = behind_book(tmp_path, monkeypatch, {UPDATE: lambda _args: left.pop(0) if len(left) > 1 else left[0]})
    seen = book_exits(monkeypatch, checks={"services.ledger": checks}, plans={"services.ledger": (0, PARTIAL)})
    install_book_skill(tmp_path / "home", monkeypatch)
    return flow, runner, seen


def lap(flow: CatchUpBooks, step: Continue[...] | Await[...]) -> Continue[...] | Await[...]:
    """The owner's turn and the check after it."""
    return advance(flow, advance(flow, step))


def test_a_note_is_split_into_its_element_and_its_kind_cut_at_a_colon_or_sixty_characters() -> None:
    assert split_note(f"screen Home: {LEADS}") == ("screen Home", "nothing leads to it")
    assert split_note(f"screen Home.kind: {LISTS}") == ("screen Home.kind", "nothing states what its list holds")
    long = "an interaction leads to it and it states neither `route` nor `root`, so an arrival on it could not be recognised"
    assert split_note(f"screen Home: {long}") == ("screen Home", long[:60].strip())
    assert split_note("index: differs") == ("index", "differs")
    assert split_note("loose text") == ("", "loose text")


def test_a_declined_line_covers_a_kind_an_element_or_an_element_without_its_first_word() -> None:
    note = f"screen Home: {LEADS}"

    assert is_declined(note, {"nothing leads to it"})
    assert is_declined(note, {"screen Home"})
    assert is_declined(note, {"Home"})
    assert not is_declined(note, {"screen Other"})


def test_the_kinds_are_counted_largest_first_and_a_move_counts_what_is_declined() -> None:
    before = [*leading("A", "B", "C"), *listing("D")]
    after = [*leading("B", "C"), *listing("D")]

    assert [(group.kind, group.count) for group in note_kinds(before)] == [("nothing leads to it", 3), ("nothing states what its list holds", 1)]
    moves = kind_moves(before, after, ["screen B: the app never links to it"])
    assert [move.said for move in moves] == ["nothing leads to it: 3 to 2 (1 declined)", "nothing states what its list holds: 1 to 1"]


def test_the_notes_come_from_every_note_line_not_the_tail_of_the_output() -> None:
    read = read_check("services.ledger", 0, "check: 0 findings, 3 notes\n", noted=leading("A", "B", "C"))

    assert read.notes == 3 and len(read.noted) == 3


def test_a_book_filed_with_notes_gets_them_in_its_prompt_grouped_by_kind(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    many = leading(*(f"S{n}" for n in range(85)))
    flow, runner, _seen = moving(tmp_path, monkeypatch, [(1, red(*many, *listing("Pick"))), (0, green())], [{"done": "moved"}])

    step = walk(flow, flow.fill(), "write")
    advance(flow, step)
    rendered = templates.render("catch_up/prompts/update-book.md", runner.args_of(UPDATE)[0], Path(okf_book.__file__).parent)

    assert "nothing leads to it: 85 notes" in rendered
    assert "nothing states what its list holds: 1 notes" in rendered
    assert "- screen S0\n" in rendered and "- screen S79\n" in rendered and "- screen S80\n" not in rendered
    assert "- and 5 more are not listed here" in rendered
    assert "- screen Pick.kind" in rendered
    assert "A note left with neither is unfinished work" in rendered
    assert "`<Element>: <reason>`" in rendered and "`<kind>: <reason>`" in rendered
    assert "Never mark a screen `first` to silence a note when the app reaches it by a link." in rendered
    assert "--partial --journey" in rendered
    assert '"declined"' in rendered


def test_a_lap_that_leaves_undeclined_notes_gets_another_lap_with_the_remaining_ones(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    first = [*leading("A", "B", "C"), *listing("D")]
    flow, runner, _seen = moving(tmp_path, monkeypatch, [(1, red(*first)), (0, green(*leading("B", "C"), *listing("D"))), (0, green())], [{"done": "some"}, {"done": "rest"}])

    step = walk(flow, flow.fill(), "write")
    again = lap(flow, step)

    assert isinstance(again, Continue) and again.state == "write" and again.params["lap"] == 2
    said = cast("str", again.params["gate"])
    assert "nothing leads to it: 2" in said and "- screen B" in said and "- screen C" in said and "- screen A" not in said
    assert "nothing states what its list holds: 1" in said
    after = advance(flow, again)
    assert runner.total == 2
    done = advance(flow, after)
    assert isinstance(done, Continue) and done.state == "checks"


def test_declined_elements_and_declined_kinds_end_the_loop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    filed = [*leading("A", "B", "C"), *listing("D", "E"), f"record Entry: {HOLD}"]
    left = [*leading("A"), *listing("D", "E"), f"record Entry: {HOLD}"]
    declined = ["screen A: the app never links to it", "nothing states what its list holds: another book states them", "record Entry: ledger and web hold it, and web owns it"]
    flow, _runner, _seen = moving(tmp_path, monkeypatch, [(1, red(*filed)), (0, green(*left))], [{"done": "moved", "declined": declined}])

    step = walk(flow, flow.fill(), "write")
    after = lap(flow, step)

    assert isinstance(after, Continue) and after.state == "checks"


def test_the_cap_sends_the_remaining_notes_to_the_operator(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stuck = [*leading("A", "B"), *listing("D")]
    flow, _runner, _seen = moving(tmp_path, monkeypatch, [(1, red(*stuck)), (0, green(*stuck))], [{"done": "nothing more"}])

    step: Continue[...] | Await[...] = walk(flow, flow.fill(), "write")
    for _ in range(MAX_LAPS - 1):
        step = lap(flow, step)
        assert isinstance(step, Continue) and step.state == "write"
    waiting = lap(flow, step)

    assert isinstance(waiting, Await)
    assert waiting.path.name == RED_GATE
    assert "after 3 laps" in waiting.questions
    assert "nothing leads to it: 2" in waiting.questions and "- screen A" in waiting.questions and "nothing states what its list holds: 1" in waiting.questions


def test_the_last_lines_of_a_moved_book_say_each_kind_and_its_declined_count_and_the_commit_body_repeats_them(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    filed = [*leading(*(f"S{n}" for n in range(8))), *listing("P", "Q")]
    left = [*leading("S5"), *listing("P", "Q")]
    declined = ["screen S5: the app never links to it", "nothing states what its list holds: another book states them"]
    flow, _runner, _seen = moving(tmp_path, monkeypatch, [(1, red(*filed)), (0, green(*left))], [{"done": "moved", "declined": declined}])
    caplog.set_level(logging.INFO)

    step = walk(flow, flow.fill(), "write")
    walk(flow, lap(flow, step), "books")
    walk(flow, flow.books(), "summarize")
    caplog.clear()
    done = summarized(flow)

    assert done.summary.splitlines() == [
        "ledger: moved onto the format in 1 laps, check 1 findings to 0, played 2 calls and 1 journeys green",
        "ledger: nothing leads to it: 8 to 1 (1 declined)",
        "ledger: nothing states what its list holds: 2 to 2 (2 declined)",
    ]
    assert [record.getMessage() for record in caplog.records][-3:] == done.summary.splitlines()
    assert git(flow.root, "log", "-1", "--format=%s") == "docs(ledger): move the ledger book onto the current book format\n"
    assert git(flow.root, "log", "-1", "--format=%b").strip().splitlines() == ["nothing leads to it: 8 to 1 (1 declined)", "nothing states what its list holds: 2 to 2 (2 declined)"]
    assert done.books[0].declined == declined


def test_a_book_stale_in_the_app_and_red_on_the_check_gets_the_before_numbers_and_the_notes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    flow, runner, _shas, _seen = behind_book(tmp_path, monkeypatch, {UPDATE: lambda _args: {"done": "moved"}})
    first = git(flow.root, "rev-list", "--max-parents=0", "HEAD").strip()
    said = stale_printed(first, {"Ping": "ledger/ping.py"}, [])
    seen = book_exits(monkeypatch, stale={"services.ledger": (1, said)}, calls={"services.ledger": ["Ping"]}, checks={"services.ledger": [(1, red(*leading("A", "B"))), (0, green())]})
    install_book_skill(tmp_path / "home", monkeypatch)

    flow.fill()
    step = walk(flow, flow.books(), "write")
    advance(flow, step)
    rendered = templates.render("catch_up/prompts/update-book.md", runner.args_of(UPDATE)[0], Path(okf_book.__file__).parent)
    walk(flow, advance(flow, step), "books")
    walk(flow, flow.books(), "summarize")

    assert [argv[3] for argv in seen][:2] == ["stale", "check"]
    assert "- sources: Ping names no source" in rendered and "nothing leads to it: 2 notes" in rendered
    done = summarized(flow)
    assert done.summary.splitlines() == ["ledger: caught up in 1 laps, 1 elements changed, 0 endpoints added, check 1 findings to 0", "ledger: nothing leads to it: 2 to 0"]
    assert git(flow.root, "log", "-1", "--format=%s") == "docs(ledger): catch the ledger book up with the app\n"
    assert git(flow.root, "log", "-1", "--format=%b").strip() == "nothing leads to it: 2 to 0"
