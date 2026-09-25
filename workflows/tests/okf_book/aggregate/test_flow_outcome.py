"""A job out of turns keeps its pages when its last turn left fewer defects than it found, and puts the book back otherwise."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from okf_book.support import Reply, ScriptedRunner, WorkListView, WriteOnly, always, commits, drafted, git, judged, listing_runner, promised_contracts

from workhorse_workflows.okf_book.main.nodes.surface import Surface, SurfaceKind
from workhorse_workflows.okf_book.shared.attempts import MAX_ATTEMPTS
from workhorse_workflows.okf_book.shared.blockers import Phase, read_blockers
from workhorse_workflows.okf_book.shared.entries import FEATURES_DIR
from workhorse_workflows.okf_book.shared.work import BLOCKED, JOB, ids

App = Callable[[str], Path]
RunBook = Callable[[WriteOnly, ScriptedRunner], WorkListView]

COMMANDS = ("init", "add", "import", "report", "export")
TALLY = Surface(service="tally", kind=SurfaceKind.CLI, entry="tally/__main__.py")
ROOT_PAGE = f"{FEATURES_DIR}/tally/tally.md"


def _drafted(repo: Path, page: str) -> dict[str, object]:
    text = (repo / page).read_text(encoding="utf-8") + "\nTally keeps a ledger.\n"
    return drafted("wrote", (page, text))


def _writer(repo: Path) -> Reply:
    def _reply(args: dict[str, object]) -> dict[str, object]:
        return _drafted(repo, str(args["page"]))

    return _reply


def _run(repo: Path, run_book: RunBook, write: Reply | None = None) -> tuple[WriteOnly, ScriptedRunner]:
    runner = listing_runner(
        *COMMANDS,
        document_files=promised_contracts,
        write_page=write or _writer(repo),
        write_operations=always({"summary": "none"}),
        write_flows=always({"summary": "none"}),
        verify_page=judged(),
    )
    flow = WriteOnly(repo_dir=str(repo), surfaces=(TALLY,))
    _ = run_book(flow, runner)
    return flow, runner


def _pages_written(runner: ScriptedRunner, page: str) -> list[dict[str, object]]:
    return [args for args in runner.args_of("write-page") if args["page"] == page]


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


def test_a_repair_that_leaves_fewer_defects_than_it_found_is_kept_and_blocked(app: App, run_book: RunBook) -> None:
    repo = app("tally-cli")
    trigger = "- trigger: the caller runs `tally import` in a directory with no ledger.\n"
    run = '- run: invoke(argv=["import", "expenses.csv"])\n'

    def repair(args: dict[str, object]) -> dict[str, object]:
        page = str(args["page"])
        if page != ROOT_PAGE:
            return _drafted(repo, page)
        text = (repo / page).read_text(encoding="utf-8")
        return drafted("wrote", (page, text if run in text else text.replace(trigger, trigger + run)))

    flow, runner = _run(repo, run_book, write=repair)

    assert len(_pages_written(runner, ROOT_PAGE)) == MAX_ATTEMPTS
    assert run in (repo / ROOT_PAGE).read_text(encoding="utf-8")
    assert "docs(tally): write tally" in commits(repo)
    [blocker] = [b for b in read_blockers(flow.run_dir) if b.subject == ROOT_PAGE]
    assert "does not compile" in blocker.reason
    assert ROOT_PAGE in ids(flow.work, JOB, BLOCKED)
    assert git(repo, "status", "--porcelain") == ""


def test_a_page_the_job_owns_is_charged_when_the_turn_leaves_it_alone(app: App, run_book: RunBook) -> None:
    repo = app("tally-cli")
    _flow, runner = _run(repo, run_book, write=always(drafted("wrote nothing")))

    tries = _pages_written(runner, ROOT_PAGE)
    assert len(tries) == MAX_ATTEMPTS
    assert "does not compile" in str(tries[-1]["problems"])
