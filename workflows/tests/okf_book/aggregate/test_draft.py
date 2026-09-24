"""A drafted page lands in the book only where its job may write it, whole, and twice the same as once."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from workhorse_workflows.okf_book.aggregate.nodes.draft import Drafted, DraftedPage, apply_draft, read_draft
from workhorse_workflows.okf_book.aggregate.nodes.format_rules import format_rules
from workhorse_workflows.okf_book.shared.confine import draftable
from workhorse_workflows.okf_book.shared.entries import FEATURES_DIR
from workhorse_workflows.okf_book.shared.jobs import Job, JobKind

App = Callable[[str], Path]
BOOK = f"{FEATURES_DIR}/tally"
CONCEPT = f"{BOOK}/concepts/ledger-file.md"
FIXTURE = f"{BOOK}/fixtures/expenses-csv.md"
TRIP = f"{BOOK}/concepts/trip.md"
JOB = Job(service="tally", kind=JobKind.PAGE, page=CONCEPT)
TRIP_TEXT = "---\ntype: concept\nslug: trip\ntitle: Trip\n---\n# Trip\n\nA trip groups expenses.\n"


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (CONCEPT, True),
        (TRIP, True),
        (FIXTURE, False),
        (f"{BOOK}/entries.md", False),
        (f"{BOOK}/../tally.md", False),
        (f"/{CONCEPT}", False),
        (f"{BOOK}/concepts/notes.txt", False),
        ("README.md", False),
        (f"{FEATURES_DIR}/other/concepts/trip.md", False),
    ],
)
def test_a_job_may_draft_its_own_page_and_new_pages_of_its_book(app: App, path: str, expected: bool) -> None:
    assert draftable(app("tally-cli"), JOB, path) is expected


def test_a_draft_writes_the_pages_the_job_may_write_and_drops_the_rest(app: App) -> None:
    repo = app("tally-cli")
    fixture = (repo / FIXTURE).read_text(encoding="utf-8")
    concept = (repo / CONCEPT).read_text(encoding="utf-8") + "\nTally keeps a ledger."
    pages = (
        DraftedPage(path=CONCEPT, text=concept),
        DraftedPage(path=TRIP, text=TRIP_TEXT),
        DraftedPage(path=FIXTURE, text="---\ntype: fixture\n---\n# Overwritten\n"),
    )

    applied = apply_draft(repo, JOB, pages)

    assert applied.written == (CONCEPT, TRIP)
    assert applied.dropped == (FIXTURE,)
    assert (repo / CONCEPT).read_text(encoding="utf-8").endswith("Tally keeps a ledger.\n")
    assert "A trip groups expenses." in (repo / TRIP).read_text(encoding="utf-8")
    assert (repo / FIXTURE).read_text(encoding="utf-8") == fixture


def test_applying_the_same_draft_twice_leaves_the_book_as_once(app: App) -> None:
    repo = app("tally-cli")
    pages = (DraftedPage(path=TRIP, text=TRIP_TEXT),)

    _ = apply_draft(repo, JOB, pages)
    once = (repo / TRIP).read_text(encoding="utf-8")
    _ = apply_draft(repo, JOB, pages)

    assert (repo / TRIP).read_text(encoding="utf-8") == once


def test_the_format_places_each_writable_type_and_orders_its_bullets() -> None:
    rules = format_rules(BOOK)

    assert f"a file page `{BOOK}/concepts/<slug>.md`, with frontmatter `type: concept`" in rules
    assert "### entries" not in rules
    assert "### untyped" not in rules
    assert "- `code:` a code citation `path::symbol`" in rules
    assert "under `## Commands`" in rules


def test_the_format_puts_a_run_and_a_verify_under_each_claim_not_after_them_all() -> None:
    rules = format_rules(BOOK)
    field = rules[rules.index("### field") : rules.index("### step")]
    listed, bound = field.split("Each claim is followed by its own bullets, in this order:")

    assert "- `default:` a claim" in listed
    assert "`verify:`" not in listed
    assert "- `run:` one literal call\n- `verify:` a check call" in bound


def test_a_reply_is_cut_into_its_pages_with_their_text_as_written() -> None:
    check = '- verify: stdout(matches="\\"entries\\": \\d+")'
    reply = f"Wrote the trip.\n=== page: {TRIP} ===\n{TRIP_TEXT}{check}\n=== end ===\n=== page: {CONCEPT} ===\n# Ledger\n=== end ===\n"
    drafted = read_draft(reply)
    assert drafted.summary == "Wrote the trip."
    assert drafted.pages == (DraftedPage(path=TRIP, text=f"{TRIP_TEXT}{check}\n"), DraftedPage(path=CONCEPT, text="# Ledger\n"))


def test_a_page_the_writer_json_escaped_whole_is_read_as_the_text_it_encodes() -> None:
    page = f'{TRIP_TEXT}- verify: created(subject="trip.json")\n- verify: stdout(matches="\\d+ trips")\n'
    escaped = page.replace("\\", "\\\\").replace('"', '\\"')
    drafted = read_draft(f"=== page: {TRIP} ===\n{escaped}=== end ===\n")
    assert drafted.pages == (DraftedPage(path=TRIP, text=page),)


def test_a_page_the_reply_never_closes_runs_to_its_end() -> None:
    drafted = read_draft(f"=== page: {TRIP} ===\n{TRIP_TEXT}")
    assert drafted.pages == (DraftedPage(path=TRIP, text=TRIP_TEXT),)


def test_a_reply_with_no_page_is_all_summary() -> None:
    assert read_draft("Nothing to change.\n") == Drafted(summary="Nothing to change.", pages=())
