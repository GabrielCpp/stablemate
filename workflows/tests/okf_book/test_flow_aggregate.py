"""Each page is written from its contracts, checked, judged by another turn, and committed on its own."""
from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from okf_book.support import Reply, ScriptedRunner, WriteOnly, always, commits, git, listing_runner

from ostler.stamp import digest_file
from pydantic import TypeAdapter

from workhorse_workflows.okf_book.blockers import Phase, read_blockers
from workhorse_workflows.okf_book.budget import ALONE_CEILING_TOKENS, CHARS_PER_TOKEN, TURN_BUDGET_TOKENS
from workhorse_workflows.okf_book.attempts import MAX_ATTEMPTS
from workhorse_workflows.okf_book.entries import FEATURES_DIR
from workhorse_workflows.okf_book.flow_aggregate import UNJUDGED_PROBLEM
from workhorse_workflows.okf_book.garbage import delete_book_pages
from workhorse_workflows.okf_book.settled import committed_jobs, settled_jobs
from workhorse_workflows.okf_book.metrics import read_metrics
from workhorse_workflows.okf_book.report import orphan_pages, unqueued_pages
from workhorse_workflows.okf_book.surface import Surface, SurfaceKind
from workhorse_workflows.okf_book.work_set import WorkSet

App = Callable[[str], Path]
RunBook = Callable[[WriteOnly, ScriptedRunner], WorkSet]
COMMANDS = ("init", "add", "import", "report", "export")
TALLY = Surface(service="tally", kind=SurfaceKind.CLI, entry="tally/__main__.py")
BOOK = f"{FEATURES_DIR}/tally"
CONCEPT = f"{BOOK}/concepts/ledger-file.md"
ROOT_PAGE = f"{BOOK}/tally.md"
FIXTURE = f"{BOOK}/fixtures/expenses-csv.md"
ORPHAN = f"{BOOK}/concepts/budget.md"
UNREACHED = ("tally-checkout", "run-tally", "track-a-trip")
STALE = "@000000000000"
PASS = always({"passed": True, "problems": []})
BRIEFS = TypeAdapter(list[dict[str, object]])
NAMES = TypeAdapter(list[str])


def _contracts(args: dict[str, object]) -> dict[str, object]:
    return {"contracts": [
        {"file": brief["file"], "purpose": "It runs part of tally.", "promises": [{"text": "It works."}]}
        for brief in BRIEFS.validate_python(args["files"])
    ]}


def _append(repo: Path, rel: str, text: str) -> None:
    path = repo / rel
    _ = path.write_text(path.read_text(encoding="utf-8") + text, encoding="utf-8")


def _writer(repo: Path, *elsewhere: str) -> Reply:
    def _reply(args: dict[str, object]) -> dict[str, object]:
        _append(repo, str(args["page"]), "\nTally keeps a ledger.\n")
        for rel in elsewhere:
            _append(repo, rel, "\nstray = 1\n")
        return {"summary": "wrote"}

    return _reply


def _on_concept(repo: Path, edit: Callable[[Path], None]) -> Reply:
    def _reply(args: dict[str, object]) -> dict[str, object]:
        _append(repo, str(args["page"]), "\nTally keeps a ledger.\n")
        if args["page"] == CONCEPT:
            edit(repo)
        return {"summary": "wrote"}

    return _reply


def _commit_orphan(repo: Path) -> None:
    _ = (repo / ORPHAN).write_text("---\ntype: concept\ntitle: Budget\n---\n# Budget\n\nA budget caps a trip.\n", encoding="utf-8")
    _ = git(repo, "add", ORPHAN)
    _ = git(repo, "commit", "-q", "-m", "orphan concept")


def _run(
    repo: Path,
    run_book: RunBook,
    *elsewhere: str,
    verify: Reply = PASS,
    write: Reply | None = None,
    operations: Reply | None = None,
) -> tuple[WriteOnly, ScriptedRunner]:
    runner = listing_runner(
        *COMMANDS,
        document_files=_contracts,
        write_page=write or _writer(repo, *elsewhere),
        write_operations=operations or always({"summary": "none"}),
        write_flows=always({"summary": "none"}),
        verify_page=verify,
    )
    flow = WriteOnly(repo_dir=str(repo), surfaces=(TALLY,))
    _ = run_book(flow, runner)
    return flow, runner


def _ledger_digest(repo: Path) -> str:
    return digest_file((repo / "tally" / "ledger.py").read_bytes())


def _pages_written(runner: ScriptedRunner, page: str) -> list[dict[str, object]]:
    return [args for args in runner.args_of("write-page") if args["page"] == page]


def test_a_page_that_passes_is_stamped_and_committed_on_its_own(app: App, run_book: RunBook) -> None:
    repo = app("tally-cli")
    page = repo / CONCEPT
    _ = page.write_text(re.sub(r"@[0-9a-f]{12}", STALE, page.read_text(encoding="utf-8")), encoding="utf-8")
    _ = git(repo, "commit", "-q", "-am", "stale stamps")

    _ = _run(repo, run_book)

    assert "docs(tally): write ledger-file" in commits(repo)
    shown = git(repo, "log", "-1", "--name-only", "--format=", "--grep=write ledger-file").split()
    assert shown == [CONCEPT]
    text = page.read_text(encoding="utf-8")
    assert "Tally keeps a ledger." in text
    assert STALE not in text
    assert f"tally/ledger.py::save@{_ledger_digest(repo)}" in text
    assert git(repo, "status", "--porcelain") == ""


def test_every_write_and_verify_turn_is_packed_under_the_budget(app: App, run_book: RunBook) -> None:
    flow, runner = _run(app("tally-cli"), run_book)

    turns = [m for m in read_metrics(flow.run_dir) if m.phase is Phase.AGGREGATE]
    assert {m.node for m in turns} >= {"write-page", "verify-page"}
    assert all(0 < m.tokens <= TURN_BUDGET_TOKENS for m in turns)
    judged = BRIEFS.validate_python(runner.args_of("verify-page")[0]["pages"])
    assert all(page["body"] for page in judged)


def test_pages_nothing_reaches_are_deleted_each_in_its_own_commit(app: App, run_book: RunBook) -> None:
    repo = app("tally-cli")
    _ = _run(repo, run_book)

    subjects = commits(repo)
    assert sorted(s for s in subjects if s.endswith("nothing reaches it")) == sorted(
        f"docs(tally): delete {stem}, nothing reaches it" for stem in UNREACHED
    )
    assert not [p for p in (repo / BOOK).rglob("*.md") if p.stem in UNREACHED]


def test_a_page_whose_obligations_do_not_compile_is_put_back_and_blocked(app: App, run_book: RunBook) -> None:
    repo = app("tally-cli")
    flow, runner = _run(repo, run_book)

    tries = _pages_written(runner, ROOT_PAGE)
    assert len(tries) == MAX_ATTEMPTS
    assert "does not compile" in str(tries[-1]["problems"])
    assert "Tally keeps a ledger." not in (repo / ROOT_PAGE).read_text(encoding="utf-8")
    [blocker] = [b for b in read_blockers(flow.run_dir) if b.subject == ROOT_PAGE]
    assert blocker.phase is Phase.AGGREGATE
    assert "does not compile" in blocker.reason
    assert git(repo, "status", "--porcelain") == ""


def test_a_verifier_rejection_is_retried_with_its_problems_then_blocked(app: App, run_book: RunBook) -> None:
    def reject(args: dict[str, object]) -> dict[str, object]:
        if CONCEPT in [page["page"] for page in BRIEFS.validate_python(args["pages"])]:
            return {"passed": False, "problems": ["The page says nothing about the ledger's columns."]}
        return {"passed": True, "problems": []}

    repo = app("tally-cli")
    flow, runner = _run(repo, run_book, verify=reject)

    tries = _pages_written(runner, CONCEPT)
    assert len(tries) == MAX_ATTEMPTS
    assert tries[-1]["problems"] == ["The page says nothing about the ledger's columns."]
    assert "docs(tally): write ledger-file" not in commits(repo)
    assert "Tally keeps a ledger." not in (repo / CONCEPT).read_text(encoding="utf-8")
    assert [b.subject for b in read_blockers(flow.run_dir) if b.subject == CONCEPT] == [CONCEPT]
    assert {s.job.subject: s.committed for s in settled_jobs(flow.run_dir)}[CONCEPT] is False
    assert CONCEPT not in [job.subject for job in committed_jobs(flow.run_dir)]
    assert git(repo, "status", "--porcelain") == ""


def test_the_verifier_is_told_the_book_s_other_pages(app: App, run_book: RunBook) -> None:
    _flow, runner = _run(app("tally-cli"), run_book)

    [args] = [a for a in runner.args_of("verify-page") if CONCEPT in [p["page"] for p in BRIEFS.validate_python(a["pages"])]]
    others = NAMES.validate_python(args["other_pages"])
    assert {FIXTURE, ROOT_PAGE} <= set(others)
    assert CONCEPT not in others


def test_a_page_a_job_only_adds_a_link_to_is_not_judged_as_its_work(app: App, run_book: RunBook) -> None:
    repo = app("tally-cli")
    line = "\nThe checkout is [tally-checkout](ops/tally-checkout.md).\n"

    def write_operations(args: dict[str, object]) -> dict[str, object]:
        _append(repo, FIXTURE, "\nThe scenario directory holds it.\n")
        _append(repo, ROOT_PAGE, line)
        return {"summary": "linked"}

    _flow, runner = _run(repo, run_book, operations=write_operations)

    operations = [args for args in runner.args_of("verify-page") if args["kind"] == "operations"]
    assert [page["page"] for args in operations for page in BRIEFS.validate_python(args["pages"])] == [FIXTURE]
    assert line in (repo / ROOT_PAGE).read_text(encoding="utf-8")


def test_a_page_too_large_to_judge_charges_the_job_without_a_verify_turn(app: App, run_book: RunBook) -> None:
    def bloat(repo: Path) -> None:
        _append(repo, CONCEPT, "Tally keeps a ledger.\n" * (ALONE_CEILING_TOKENS * CHARS_PER_TOKEN // 20))

    repo = app("tally-cli")
    flow, runner = _run(repo, run_book, write=_on_concept(repo, bloat))

    tries = _pages_written(runner, CONCEPT)
    assert len(tries) == MAX_ATTEMPTS
    assert tries[-1]["problems"] == [UNJUDGED_PROBLEM]
    judged = [page["page"] for args in runner.args_of("verify-page") for page in BRIEFS.validate_python(args["pages"])]
    assert CONCEPT not in judged
    assert CONCEPT not in [job.subject for job in committed_jobs(flow.run_dir)]
    assert git(repo, "status", "--porcelain") == ""


def test_deleting_the_same_picked_pages_twice_skips_the_ones_already_gone(app: App) -> None:
    repo = app("tally-cli")
    delete_book_pages(repo, (ORPHAN,))
    delete_book_pages(repo, (ORPHAN,))
    assert not (repo / ORPHAN).exists()


def test_edits_outside_the_book_and_to_the_entries_page_are_put_back(app: App, run_book: RunBook) -> None:
    source = "tally/cli.py"
    entries = f"{BOOK}/entries.md"
    repo = app("tally-cli")
    _ = _run(repo, run_book, source, entries)

    assert "stray = 1" not in (repo / source).read_text(encoding="utf-8")
    assert "stray = 1" not in (repo / entries).read_text(encoding="utf-8")
    assert "docs(tally): write ledger-file" in commits(repo)
    assert git(repo, "status", "--porcelain") == ""


def test_a_page_not_its_own_keeps_only_the_lines_a_turn_adds(app: App, run_book: RunBook) -> None:
    repo = app("tally-cli")
    heading = "# tally\n"
    root_before = (repo / ROOT_PAGE).read_text(encoding="utf-8")

    def edit(repo: Path) -> None:
        _append(repo, FIXTURE, "\nThe ledger file reads these rows.\n")
        page = repo / ROOT_PAGE
        _ = page.write_text(page.read_text(encoding="utf-8").replace(heading, "# tally, rewritten\n"), encoding="utf-8")

    _ = _run(repo, run_book, write=_on_concept(repo, edit))

    assert "The ledger file reads these rows." in (repo / FIXTURE).read_text(encoding="utf-8")
    assert "docs(tally): write expenses-csv" in commits(repo)
    assert (repo / ROOT_PAGE).read_text(encoding="utf-8") == root_before
    assert git(repo, "status", "--porcelain") == ""


def test_a_page_linked_after_the_queue_froze_is_reported_and_not_written(app: App, run_book: RunBook) -> None:
    repo = app("tally-cli")
    _commit_orphan(repo)

    flow, runner = _run(repo, run_book, write=_on_concept(repo, lambda r: _append(r, CONCEPT, "\nSee [budget](budget.md).\n")))

    assert _pages_written(runner, ORPHAN) == []
    assert unqueued_pages(repo, flow.run_dir, ("tally",)) == (ORPHAN,)
    assert orphan_pages(repo, ("tally",)) == ()


def test_a_page_nothing_reached_before_the_run_and_no_job_owns_is_kept_and_reported(app: App, run_book: RunBook) -> None:
    repo = app("tally-cli")
    _commit_orphan(repo)

    flow, _runner = _run(repo, run_book)

    assert (repo / ORPHAN).is_file()
    assert "docs(tally): delete budget, nothing reaches it" not in commits(repo)
    assert orphan_pages(repo, ("tally",)) == (ORPHAN,)
    assert unqueued_pages(repo, flow.run_dir, ("tally",)) == ()



def test_a_page_an_earlier_job_wrote_is_kept_when_a_later_job_unlinks_it(app: App, run_book: RunBook) -> None:
    repo = app("tally-cli")
    _commit_orphan(repo)
    _append(repo, CONCEPT, "\nSee [budget](budget.md).\n")
    _ = git(repo, "commit", "-q", "-am", "link budget")
    trip = f"{BOOK}/concepts/trip.md"
    link = "\nSee [trip](trip.md).\n"

    def write(args: dict[str, object]) -> dict[str, object]:
        page = str(args["page"])
        _append(repo, page, "\nTally keeps a ledger.\n")
        if page == CONCEPT:
            _ = (repo / trip).write_text("---\ntype: concept\ntitle: Trip\n---\n# Trip\n\nA trip groups expenses.\n", encoding="utf-8")
            _append(repo, ORPHAN, link)
        if page == ORPHAN:
            path = repo / ORPHAN
            _ = path.write_text(path.read_text(encoding="utf-8").replace(link, ""), encoding="utf-8")
            _append(repo, trip, "\nA trip has one budget.\n")
        return {"summary": "wrote"}

    _ = _run(repo, run_book, write=write)

    assert "docs(tally): write trip" in commits(repo)
    assert link not in (repo / ORPHAN).read_text(encoding="utf-8")
    assert "A trip has one budget." in (repo / trip).read_text(encoding="utf-8")
    assert "docs(tally): delete trip, nothing reaches it" not in commits(repo)
    assert orphan_pages(repo, ("tally",)) == (trip,)


def test_a_queued_page_an_earlier_job_unlinks_is_written_by_its_own_job_then_collected(app: App, run_book: RunBook) -> None:
    repo = app("tally-cli")
    _commit_orphan(repo)
    link = "\nSee [budget](budget.md).\n"
    _append(repo, CONCEPT, link)
    _ = git(repo, "commit", "-q", "-am", "link budget")

    def unlink(repo: Path) -> None:
        page = repo / CONCEPT
        _ = page.write_text(page.read_text(encoding="utf-8").replace(link, ""), encoding="utf-8")

    _flow, runner = _run(repo, run_book, write=_on_concept(repo, unlink))

    subjects = commits(repo)
    assert len(_pages_written(runner, ORPHAN)) == 1
    assert subjects.index("docs(tally): delete budget, nothing reaches it") < subjects.index("docs(tally): write budget")
    assert not (repo / ORPHAN).exists()


def test_a_committed_orphan_a_turn_adds_to_is_kept_and_the_turn_not_charged(app: App, run_book: RunBook) -> None:
    repo = app("tally-cli")
    _commit_orphan(repo)

    _flow, runner = _run(repo, run_book, write=_on_concept(repo, lambda r: _append(r, ORPHAN, "\nA trip has one budget.\n")))

    assert len(_pages_written(runner, CONCEPT)) == 1
    assert "A trip has one budget." in (repo / ORPHAN).read_text(encoding="utf-8")
    assert orphan_pages(repo, ("tally",)) == (ORPHAN,)


def test_a_turn_adding_to_a_page_that_already_does_not_compile_is_not_charged_for_it(
    app: App, run_book: RunBook
) -> None:
    repo = app("tally-cli")
    line = "\nThe ledger lives in [ledger-file](concepts/ledger-file.md).\n"

    _flow, runner = _run(repo, run_book, write=_on_concept(repo, lambda r: _append(r, ROOT_PAGE, line)))

    assert len(_pages_written(runner, CONCEPT)) == 1
    assert "docs(tally): write ledger-file" in commits(repo)
    assert line in (repo / ROOT_PAGE).read_text(encoding="utf-8")


def test_an_operations_page_written_after_the_queue_froze_is_not_the_operations_job_s(
    app: App, run_book: RunBook
) -> None:
    repo = app("tally-cli")
    late = f"{BOOK}/fixtures/trips-csv.md"
    late_text = (repo / f"{BOOK}/fixtures/second-ledger.md").read_text(encoding="utf-8").replace("Second ledger", "Trips CSV")

    def write_page(args: dict[str, object]) -> dict[str, object]:
        _append(repo, str(args["page"]), "\nTally keeps a ledger.\n")
        if args["page"] == ROOT_PAGE and not (repo / late).is_file():
            _ = (repo / late).write_text(late_text, encoding="utf-8")
            _append(repo, CONCEPT, "\nTrips come from [trips](../fixtures/trips-csv.md).\n")
            _ = git(repo, "add", late, CONCEPT)
            _ = git(repo, "commit", "-q", "-m", "late fixture")
        return {"summary": "wrote"}

    def write_operations(args: dict[str, object]) -> dict[str, object]:
        for rel in (FIXTURE, late):
            page = repo / rel
            _ = page.write_text(page.read_text(encoding="utf-8").replace("The working directory", "The scenario directory"), encoding="utf-8")
        return {"summary": "rewrote"}

    _flow, runner = _run(repo, run_book, write=write_page, operations=write_operations)

    assert late not in NAMES.validate_python(runner.args_of("write-operations")[0]["pages"])
    assert "The scenario directory" in (repo / FIXTURE).read_text(encoding="utf-8")
    assert (repo / late).read_text(encoding="utf-8") == late_text
