"""A repair batch whose fix goes on a journey owns the journey pages, adds only link lines to an entry page, and may not change a page another batch closed, whose later problems are left for the book check."""
from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import TypeAdapter
from okf_book.main.tally import (
    FLOW_PAGE,
    NEW_FLOW,
    NOTE,
    OTHER_PAGE,
    OUTSIDE_EDIT,
    PAGE,
    TALLY,
    App,
    DriveBook,
    off_journey_until_noted,
    repair_over_the_ceiling,
    repairer_also_editing,
)
from okf_book.support import ScriptedRunner, git

from workhorse_workflows.okf_book.main import repair_book_flow
from workhorse_workflows.okf_book.main.nodes.journey import JourneyPages
from workhorse_workflows.okf_book.main.nodes.repair_batches import PackedRepairs, PageRepair, RepairBatch, pack_repairs
from workhorse_workflows.okf_book.main.nodes.report import BookReport
from workhorse_workflows.okf_book.shared.page_check import PageProblem
from workhorse_workflows.okf_book.workflow import OkfBook


@pytest.fixture
def over_the_ceiling(monkeypatch: pytest.MonkeyPatch) -> None:
    repair_over_the_ceiling(monkeypatch)


@pytest.mark.usefixtures("over_the_ceiling")
def test_a_batch_with_a_page_off_the_journey_owns_the_entry_and_flow_pages_and_a_new_flow(
    app: App, drive_book: DriveBook, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = app("tally-cli")
    monkeypatch.setattr(repair_book_flow, "page_problems", off_journey_until_noted)
    runner = repairer_also_editing(repo, OTHER_PAGE, FLOW_PAGE, NEW_FLOW)

    result = drive_book(OkfBook(repo_dir=str(repo), surfaces=(TALLY,)), runner)

    assert isinstance(result, BookReport)
    assert runner.args_of("repair-pages")[0]["journey_pages"] == [PAGE, FLOW_PAGE]
    assert sorted(git(repo, "show", "--name-only", "--format=", "HEAD").split()) == sorted([PAGE, FLOW_PAGE, NEW_FLOW])
    assert OUTSIDE_EDIT.strip() not in (repo / OTHER_PAGE).read_text(encoding="utf-8")
    assert git(repo, "status", "--porcelain").strip() == ""


def _writes_a_flow_then_notes(repo: Path) -> ScriptedRunner:
    def _reply(_args: dict[str, object]) -> dict[str, object]:
        if (repo / NEW_FLOW).is_file():
            _ = (repo / PAGE).write_text((repo / PAGE).read_text(encoding="utf-8") + NOTE, encoding="utf-8")
        else:
            _ = (repo / NEW_FLOW).write_text(OUTSIDE_EDIT, encoding="utf-8")
        return {"value": f"repaired {PAGE}"}

    return ScriptedRunner({"repair-pages": _reply})


@pytest.mark.usefixtures("over_the_ceiling")
def test_a_later_round_keeps_the_journey_pages_the_first_round_planned(
    app: App, drive_book: DriveBook, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = app("tally-cli")
    monkeypatch.setattr(repair_book_flow, "page_problems", off_journey_until_noted)
    runner = _writes_a_flow_then_notes(repo)

    result = drive_book(OkfBook(repo_dir=str(repo), surfaces=(TALLY,)), runner)

    assert isinstance(result, BookReport)
    assert runner.total == 2
    assert [args["journey_pages"] for args in runner.args_of("repair-pages")] == [[PAGE, FLOW_PAGE], [PAGE, FLOW_PAGE]]
    assert (repo / NEW_FLOW).is_file()


LINK_LINE = "- [Track a trip](flows/track-a-trip.md)\n"


def _flow_until_noted(root: Path, _service: str) -> tuple[PageProblem, ...]:
    noted = NOTE.strip() in (root / FLOW_PAGE).read_text(encoding="utf-8")
    return () if noted else (PageProblem(FLOW_PAGE, "track-a-trip.md needs a note", needs_journey=True),)


def _notes_the_flow_and_adds_to_the_entry_page(repo: Path, addition: str) -> ScriptedRunner:
    def _reply(_args: dict[str, object]) -> dict[str, object]:
        for page, text in ((FLOW_PAGE, NOTE), (PAGE, addition)):
            _ = (repo / page).write_text((repo / page).read_text(encoding="utf-8") + text, encoding="utf-8")
        return {"value": f"repaired {FLOW_PAGE}"}

    return ScriptedRunner({"repair-pages": _reply})


@pytest.mark.usefixtures("over_the_ceiling")
@pytest.mark.parametrize(("addition", "kept"), [(LINK_LINE, True), (LINK_LINE + OUTSIDE_EDIT, False)])
def test_a_turn_keeps_an_entry_page_it_only_added_link_lines_to(
    app: App, drive_book: DriveBook, monkeypatch: pytest.MonkeyPatch, addition: str, kept: bool
) -> None:
    repo = app("tally-cli")
    monkeypatch.setattr(repair_book_flow, "page_problems", _flow_until_noted)
    committed = (repo / PAGE).read_text(encoding="utf-8")

    result = drive_book(OkfBook(repo_dir=str(repo), surfaces=(TALLY,)), _notes_the_flow_and_adds_to_the_entry_page(repo, addition))

    assert isinstance(result, BookReport)
    assert (LINK_LINE.strip() in (repo / PAGE).read_text(encoding="utf-8")) is kept
    assert kept or (repo / PAGE).read_text(encoding="utf-8") == committed
    assert git(repo, "status", "--porcelain").strip() == ""


BREAK = "\na flow step that walks no endpoint\n"


def _flow_and_page_until_noted(root: Path, service: str) -> tuple[PageProblem, ...]:
    flow_text = (root / FLOW_PAGE).read_text(encoding="utf-8")
    broken = BREAK.strip() in flow_text or BREAK.strip() in (root / PAGE).read_text(encoding="utf-8")
    flow_open = NOTE.strip() not in flow_text or broken
    flow_problems = (PageProblem(FLOW_PAGE, "track-a-trip.md needs a note", needs_journey=True),) if flow_open else ()
    return (*flow_problems, *off_journey_until_noted(root, service))


def _one_page_per_batch(
    root: Path, by_page: dict[str, tuple[PageProblem, ...]], journey: JourneyPages | None = None, pages_needing_journey: frozenset[str] = frozenset()
) -> PackedRepairs:
    packed = pack_repairs(root, by_page, journey, pages_needing_journey)
    batches = tuple(batch.model_copy(update={"pages": (page,)}) for batch in packed.batches for page in batch.pages)
    return packed.model_copy(update={"batches": batches})


def _notes_its_page_and_breaks_the_flow(repo: Path, broken_page: str) -> ScriptedRunner:
    def _reply(args: dict[str, object]) -> dict[str, object]:
        [repair] = TypeAdapter(tuple[PageRepair, ...]).validate_python(args["pages"])
        edits = ((FLOW_PAGE, NOTE),) if repair.page == FLOW_PAGE else ((PAGE, NOTE), (broken_page, BREAK))
        for page, text in edits:
            _ = (repo / page).write_text((repo / page).read_text(encoding="utf-8") + text, encoding="utf-8")
        return {"value": f"repaired {repair.page}"}

    return ScriptedRunner({"repair-pages": _reply})


def _sent_pages(runner: ScriptedRunner) -> list[str]:
    return [TypeAdapter(tuple[PageRepair, ...]).validate_python(args["pages"])[0].page for args in runner.args_of("repair-pages")]


@pytest.fixture
def one_page_per_batch(monkeypatch: pytest.MonkeyPatch) -> None:
    repair_over_the_ceiling(monkeypatch)
    monkeypatch.setattr(repair_book_flow, "page_problems", _flow_and_page_until_noted)
    monkeypatch.setattr(repair_book_flow, "pack_repairs", _one_page_per_batch)


@pytest.mark.usefixtures("one_page_per_batch")
def test_a_later_batch_cannot_change_a_flow_page_an_earlier_batch_closed(app: App, drive_book: DriveBook) -> None:
    repo = app("tally-cli")
    runner = _notes_its_page_and_breaks_the_flow(repo, FLOW_PAGE)

    result = drive_book(OkfBook(repo_dir=str(repo), surfaces=(TALLY,)), runner)

    assert isinstance(result, BookReport)
    assert _sent_pages(runner) == [FLOW_PAGE, PAGE]
    assert BREAK.strip() not in (repo / FLOW_PAGE).read_text(encoding="utf-8")
    assert git(repo, "status", "--porcelain").strip() == ""


@pytest.mark.usefixtures("one_page_per_batch")
def test_a_page_a_batch_closed_that_another_page_breaks_is_left_for_the_book_check(app: App, drive_book: DriveBook) -> None:
    repo = app("tally-cli")
    runner = _notes_its_page_and_breaks_the_flow(repo, PAGE)

    result = drive_book(OkfBook(repo_dir=str(repo), surfaces=(TALLY,)), runner)

    assert isinstance(result, BookReport)
    assert _sent_pages(runner) == [FLOW_PAGE, PAGE]
    assert BREAK.strip() in (repo / PAGE).read_text(encoding="utf-8")


def _batch_of(page: str, journey: JourneyPages | None) -> RepairBatch:
    return RepairBatch(pages=(PageRepair(page=page, problems=("p",)),), tokens=1, journey=journey)


def test_an_entry_page_closes_only_after_the_last_batch_of_the_round_that_may_add_links_to_it() -> None:
    journey = JourneyPages(pages=(PAGE, FLOW_PAGE), flow_folder=Path(FLOW_PAGE).parent.as_posix())
    batches = (_batch_of(PAGE, journey), _batch_of(FLOW_PAGE, journey), _batch_of(OTHER_PAGE, None))
    this_round = repair_book_flow.RepairRound(uncommitted_at_start=(), planned_pages=(), journey=journey, number=1, batches=batches)

    after_first = this_round.with_clean_pages_closed(0, ())
    after_last_journey_batch = after_first.with_clean_pages_closed(1, ())

    assert after_first.closed_pages == ()
    assert after_last_journey_batch.closed_pages == (PAGE, FLOW_PAGE)
